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

# 指定 7 大權威媒體來源
SITES = "(site:ithome.com.tw OR site:moda.gov.tw OR site:techorange.com OR site:money.udn.com OR site:ctee.com.tw OR site:technews.tw OR site:bnext.com.tw)"

# 監控關鍵字清單
TOPICS = [
    "數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", 
    "電子簽章", "生物辨識", "保險科技", "電子簽名", 
    "數位發展部", "數位簽章", "FIDO", "GEO", "開源模型", "LLM"
]

collected_news = []
seen_urls = set()

def get_page_content(url):
    """強化版網頁抓取，應對 iThome 等媒體"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            return ""
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # 移除不必要的標籤
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
            
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 20])
        return text[:2500] # 增加抓取長度確保 AI 有足夠資訊摘要
    except Exception as e:
        print(f"抓取內文失敗 ({url}): {e}")
        return ""

def summarize_content(text, topic, title):
    """使用 1.5 Pro 生成高品質專業摘要"""
    if len(text) < 100:
        return f"偵測到該篇關於【{topic}】的報導，但自動摘要受阻，建議您直接點擊標題查看完整內容。"
    
    prompt = f"""你是一位專業的資安與數位科技分析師。
    請閱讀以下內容，並為讀者『Jimmy』提供一份約 150 字的繁體中文重點摘要。
    摘要要求：語氣精準、避開口語贅字、保留關鍵技術術語（如 PQC, FIDO 等）。
    
    標題：{title}
    內文：{text}"""
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace('\n', ' ')
    except:
        return "AI 摘要引擎忙碌中，請點擊連結閱讀全文。"

# 3. 執行 Google Search API (極致檢索模式)
print(f"--- 啟動深度檢索任務: {datetime.now()} ---")

for topic in TOPICS:
    search_query = f"{topic} {SITES}"
    
    url = "https://customsearch.googleapis.com/customsearch/v1"
    params = {
        'key': SEARCH_API_KEY,
        'cx': SEARCH_ENGINE_ID,
        'q': search_query,
        'dateRestrict': 'd7',  # 擴張至 7 天，對抗 API 索引延遲
        'sort': 'date',       # 確保最新發布優先回傳
        'num': 10             # 每次關鍵字抓取前 10 筆，不放過任何 PR 稿
    }
    
    try:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            items = response.json().get('items', [])
            print(f"關鍵字【{topic}】: 找到 {len(items)} 筆結果")
            
            for item in items:
                title = item.get('title')
                link = item.get('link')
                
                # 排除重複網址與非目標媒體
                if title and link and link not in seen_urls:
                    seen_urls.add(link)
                    print(f"  └ 處理中: {title}")
                    
                    content = get_page_content(link)
                    summary = summarize_content(content, topic, title)
                    
                    collected_news.append({
                        "category": topic,
                        "title": title,
                        "url": link,
                        "summary": summary
                    })
                    # 避免呼叫過快觸發頻率限制
                    time.sleep(1)
        else:
            print(f"API 請求失敗 ({topic}): {response.status_code}")
    except Exception as e:
        print(f"搜尋過程出錯 ({topic}): {e}")

# 4. 構建與發送專屬郵件
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
            news_html += f'<tr style="background:#f0f7ff;"><td style="padding:10px; border-left:4px solid #0056b3;"><b>■ {current_cat}</b></td></tr>'
        
        news_html += f'''
            <tr>
                <td style="padding:15px 10px; border-bottom:1px solid #eee;">
                    <div style="font-size:16px; font-weight:bold; margin-bottom:8px;">
                        <a href="{n['url']}" style="color:#0056b3; text-decoration:none;">▷ {n['title']}</a>
                    </div>
                    <div style="font-size:14px; color:#444; line-height:1.7;">{n['summary']}</div>
                </td>
            </tr>
        '''
    body_html = f"<html><body style='font-family:sans-serif; max-width:800px; margin:auto;'><table style='width:100%; border-collapse:collapse;'>{news_html}</table></body></html>"
else:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 今日無相關產業動態"
    body_html = "<html><body><p style='color:#666;'>監控的 15 項關鍵字在過去 7 日內於指定媒體無最新動態。</p></body></html>"

msg.attach(MIMEText(body_html, 'html'))

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("--- 任務完成：郵件已送出 ---")
except Exception as e:
    print(f"郵件發送失敗: {e}")
