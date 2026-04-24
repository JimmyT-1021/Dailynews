import os, smtplib, requests
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

# 精準搜尋設定：指定 7 大媒體來源
SITES = "(site:ithome.com.tw OR site:moda.gov.tw OR site:techorange.com OR site:money.udn.com OR site:ctee.com.tw OR site:technews.tw OR site:bnext.com.tw)"

# 核心議題清單 (15項)
TOPICS = [
    "數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", 
    "電子簽章", "生物辨識", "保險科技", "電子簽名", 
    "數位發展部", "數位簽章", "FIDO", "GEO", "開源模型", "LLM"
]

collected_news = []
seen_urls = set() # 避免 d2 導致的重複抓取

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=12)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if p.text.strip()])
        return text[:2000] # 增加文本長度至 2000 字以提升摘要品質
    except:
        return ""

def summarize_content(text, topic, title):
    if len(text) < 50:
        return f"網頁內容擷取受阻，請點擊標題直接前往原始網頁閱讀這篇關於【{topic}】的報導。"
    prompt = f"請針對以下網頁內容進行繁體中文摘要，長度約 120 字，語氣專業精準。標題：{title}\n內容：{text}"
    try:
        response = model.generate_content(prompt)
        return response.text.replace('\n', '')
    except:
        return "AI 摘要生成暫時遇到問題，請點擊原文連結閱讀完整內容。"

# 3. 執行 Google Search API (修正為 d2 範圍與日期排序)
for topic in TOPICS:
    search_query = f"{topic} {SITES}"
    print(f"執行搜尋: {search_query}")
    
    url = "https://customsearch.googleapis.com/customsearch/v1"
    params = {
        'key': SEARCH_API_KEY,
        'cx': SEARCH_ENGINE_ID,
        'q': search_query,
        'dateRestrict': 'd2',  # 擴大至 48 小時以消除盲區
        'sort': 'date',       # 強制依日期排序，確保最新消息排在最前
        'num': 3              # 稍微擴大檢索數量
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            items = data.get('items', [])
            
            for item in items:
                title = item.get('title')
                link = item.get('link')
                
                # 排除重複與無效連結
                if title and link and link not in seen_urls:
                    seen_urls.add(link)
                    content = get_page_content(link)
                    summary = summarize_content(content, topic, title)
                    
                    collected_news.append({
                        "category": topic,
                        "title": title,
                        "url": link,
                        "summary": summary
                    })
        else:
            print(f"API Error {response.status_code} on {topic}")
    except Exception as e:
        print(f"Error on {topic}: {e}")

# 4. 構建信件 (更新標題為您指定的格式)
today_str = datetime.now().strftime("%Y-%m-%d")
msg = MIMEMultipart()
msg['From'] = GMAIL_ADDRESS
msg['To'] = GMAIL_ADDRESS

if collected_news:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 產業要聞與技術趨勢"
    news_html_sections = ""
    current_category = ""
    
    for news in collected_news:
        if news['category'] != current_category:
            current_category = news['category']
            news_html_sections += f"""
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border-left: 5px solid #007BFF;">
                        <h2 style="margin: 0; color: #333; font-size: 18px;">■ {current_category}</h2>
                    </td>
                </tr>
            """
        news_html_sections += f"""
            <tr>
                <td style="padding: 15px 10px;">
                    <h3 style="margin: 0 0 8px 0; font-size: 16px;">
                        <a href="{news['url']}" style="color: #0056b3; text-decoration: none;">▷ {news['title']}</a>
                    </h3>
                    <p style="margin: 0; color: #444; font-size: 14px; line-height: 1.6;">{news['summary']}</p>
                </td>
            </tr>
            <tr><td><hr style="border: 0; border-top: 1px solid #eee; margin: 0;"></td></tr>
        """
    content_html = f"<html><body style='max-width:800px; margin:auto;'>{news_html_sections}</body></html>"
else:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 今日無相關產業動態"
    content_html = f"<html><body><p>監控關鍵字在過去 48 小時內於指定媒體無更新。</p></body></html>"

msg.attach(MIMEText(content_html, 'html'))

# 5. 發送
try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("發送成功")
except Exception as e:
    print(f"發信失敗: {e}")
