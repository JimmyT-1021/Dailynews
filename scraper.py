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

# 精準指定 7 大來源
SITES = "(site:ithome.com.tw OR site:moda.gov.tw OR site:techorange.com OR site:money.udn.com OR site:ctee.com.tw OR site:technews.tw OR site:bnext.com.tw)"

# 監控議題 (15項)
TOPICS = [
    "數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", 
    "電子簽章", "生物辨識", "電子簽名", 
    "數位簽章", "FIDO", 
]

collected_news = []
seen_urls = set()

def get_page_content(url):
    """專門對抗 UDN 與 iThome 阻擋的強化爬蟲"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Referer': 'https://www.google.com/',
        }
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"  [跳過] 網站阻擋: {url} (Status: {response.status_code})")
            return ""
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 針對經濟日報與 iThome 的內文區塊精準定位
        for tag in soup(["script", "style", "header", "footer", "nav", "iframe", "aside"]):
            tag.decompose()
            
        # 抓取所有段落並過濾廣告雜訊
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 30])
        return text[:3000]
    except Exception as e:
        print(f"  [錯誤] 無法讀取內容: {e}")
        return ""

def summarize_content(text, topic, title):
    if len(text) < 100:
        return f"已偵測到關於【{topic}】的最新報導，但網頁內容受到保護。建議點擊標題直接閱讀原始內容。"
    
    prompt = f"你是一位高階產業顧問。請為讀者『Jimmy』閱讀以下文章，並提供一份 150 字內的繁體中文專業摘要。摘要必須包含技術關鍵字與產業影響力。標題：{title}\n內容：{text}"
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace('\n', ' ')
    except:
        return "AI 摘要生成忙碌，請點擊標題查看全文。"

# 3. 執行 Google Search API (深度搜尋模式)
print(f"--- 開始深度抓取任務: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

for topic in TOPICS:
    search_query = f"{topic} {SITES}"
    
    url = "https://customsearch.googleapis.com/customsearch/v1"
    params = {
        'key': SEARCH_API_KEY,
        'cx': SEARCH_ENGINE_ID,
        'q': search_query,
        'dateRestrict': 'd3',      # 擴張至 3 天以跨越 API 索引時差
        'sort': 'date:D:s',       # 強制依日期精確排序
        'num': 10                 # 增加單次檢索深度，確保能翻到第 2 頁
    }
    
    try:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            items = response.json().get('items', [])
            print(f"關鍵字【{topic}】: 搜尋到 {len(items)} 則潛在新聞")
            
            for item in items:
                title = item.get('title')
                link = item.get('link')
                
                # 去重與過濾
                if title and link and link not in seen_urls:
                    seen_urls.add(link)
                    print(f"  └ 正在分析: {title}")
                    
                    content = get_page_content(link)
                    summary = summarize_content(content, topic, title)
                    
                    collected_news.append({
                        "category": topic,
                        "title": title,
                        "url": link,
                        "summary": summary
                    })
                    time.sleep(1) # 保護機制避免 API 頻率過快
        else:
            print(f"  [API報錯] {topic}: {response.status_code}")
    except Exception as e:
        print(f"  [搜尋出錯] {topic}: {e}")

# 4. 發送 Jimmy 專屬郵件
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
            news_html += f'<tr style="background:#eef4ff;"><td style="padding:12px; border-left:5px solid #0056b3;"><b>■ {current_cat}</b></td></tr>'
        news_html += f'''
            <tr>
                <td style="padding:15px 10px; border-bottom:1px solid #ddd;">
                    <div style="font-size:16px; font-weight:bold; margin-bottom:5px;">
                        <a href="{n['url']}" style="color:#0056b3; text-decoration:none;">▷ {n['title']}</a>
                    </div>
                    <div style="font-size:14px; color:#333; line-height:1.7;">{n['summary']}</div>
                </td>
            </tr>'''
    body_html = f"<html><body><table style='width:100%; border-collapse:collapse; font-family:sans-serif;'>{news_html}</table></body></html>"
else:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 今日無相關產業動態"
    body_html = "<html><body><p>過去 72 小時內，監控之媒體無相關更新。</p></body></html>"

msg.attach(MIMEText(body_html, 'html'))

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("--- 任務圓滿完成：郵件已成功寄出 ---")
except Exception as e:
    print(f"發信失敗: {e}")
