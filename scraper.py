import os, smtplib, requests, time
from datetime import datetime
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai

# 1. 讀取環境變數
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")

# 2. 設定 Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro-latest')

# 精準指定來源
SITES = "(site:ithome.com.tw OR site:moda.gov.tw OR site:techorange.com OR site:money.udn.com OR site:ctee.com.tw OR site:technews.tw OR site:bnext.com.tw)"

# 更新後的 10 項核心議題
TOPICS = [
    "數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", 
    "電子簽章", "生物辨識", "電子簽名", "數位簽章", "FIDO"
]

collected_news = []
seen_urls = set()

def get_page_content(url):
    """針對 UDN 強化之深度爬蟲"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Referer': 'https://www.google.com/',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return ""
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 移除干擾元素
        for tag in soup(["script", "style", "header", "footer", "nav", "aside", "iframe"]):
            tag.decompose()
            
        # 優先抓取主要報導內容區塊
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 35])
        
        # 若 <p> 抓不到，嘗試 meta description (對抗 UDN 阻擋)
        if len(text) < 100:
            meta_desc = soup.find("meta", property="og:description")
            if meta_desc:
                text = meta_desc.get("content", "")
                
        return text[:3000]
    except:
        return ""

def summarize_content(text, topic, title):
    if len(text) < 80:
        return f"已鎖定關於【{topic}】的新聞，但內文受保護。建議點擊標題直接閱讀原始內容。"
    
    prompt = f"你是一位專業科技分析師。請為讀者『Jimmy』摘要以下文章，字數 150 字內，語氣專業精確。標題：{title}\n內容：{text}"
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace('\n', ' ')
    except:
        return "摘要引擎稍後再試，請點擊標題查看全文。"

# 3. 執行 Google Search API (日期優先模式)
print(f"--- 啟動深度任務: {datetime.now()} ---")

for topic in TOPICS:
    search_query = f"{topic} {SITES}"
    
    url = "https://customsearch.googleapis.com/customsearch/v1"
    params = {
        'key': SEARCH_API_KEY,
        'cx': SEARCH_ENGINE_ID,
        'q': search_query,
        'dateRestrict': 'd3',      # 固定 3 天範圍
        'sort': 'date:D:s',       # 強制精確日期排序
        'num': 10                 # 增加檢索深度
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            items = response.json().get('items', [])
            print(f"【{topic}】找到 {len(items)} 則結果")
            
            for item in items:
                title = item.get('title')
                link = item.get('link')
                
                if title and link and link not in seen_urls:
                    seen_urls.add(link)
                    print(f"  └ 正在解析: {title}")
                    content = get_page_content(link)
                    summary = summarize_content(content, topic, title)
                    
                    collected_news.append({
                        "category": topic,
                        "title": title,
                        "url": link,
                        "summary": summary
                    })
                    time.sleep(1)
        else:
            print(f"  API報錯 {topic}: {response.status_code}")
    except Exception as e:
        print(f"  發生錯誤 {topic}: {e}")

# 4. 寄送郵件
today_str = datetime.now().strftime("%Y-%m-%d")
msg = MIMEMultipart()
msg['From'] = GMAIL_ADDRESS
msg['To'] = GMAIL_ADDRESS

if collected_news:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 產業要聞與技術趨勢"
    news_html = ""
    current_cat = ""
    for n in collected_news:
        if n['category'] != current_cat:
            current_cat = n['category']
            news_html += f'<tr style="background:#f4f8ff;"><td style="padding:12px; border-left:5px solid #0056b3;"><b>■ {current_cat}</b></td></tr>'
        news_html += f'<tr><td style="padding:15px 10px; border-bottom:1px solid #eee;"><div style="font-size:16px; font-weight:bold; margin-bottom:5px;"><a href="{n['url']}" style="color:#0056b3; text-decoration:none;">▷ {n['title']}</a></div><div style="font-size:14px; color:#333; line-height:1.6;">{n['summary']}</div></td></tr>'
    body_html = f"<html><body><table style='width:100%; border-collapse:collapse;'>{news_html}</table></body></html>"
else:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 今日無相關產業動態"
    body_html = "<html><body><p>監控範圍內過去 72 小時無相關更新。</p></body></html>"

msg.attach(MIMEText(body_html, 'html'))

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("發信成功")
except Exception as e:
    print(f"發信失敗: {e}")
