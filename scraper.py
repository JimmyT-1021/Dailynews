import os, json, smtplib, requests
from datetime import datetime
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import build
import google.generativeai as genai

# 1. 讀取保險箱中的金鑰
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# 2. 設定 Gemini 與搜尋引擎
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro-latest') # 使用最新的模型
search_service = build("customsearch", "v1", developerKey=SEARCH_API_KEY)

TOPICS = ["數位轉型", "PQC", "金融科技"]
collected_news = []

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text for p in paragraphs])
        return text[:1500] # 取前 1500 字交給 Gemini 摘要即可
    except:
        return ""

def summarize_content(text, topic, title):
    if not text:
        return f"無法抓取完整內文，請點擊原始網頁閱讀這篇關於【{topic}】的報導。"
    prompt = f"請針對以下網頁內容進行繁體中文摘要，長度約 80-100 字，讓人能快速掌握重點。標題：{title}\n內容：{text}"
    try:
        response = model.generate_content(prompt)
        return response.text.replace('\n', '')
    except:
        return "摘要生成失敗，請點擊連結查看原文。"

# 3. 執行搜尋與抓取 (設定抓取過去 24 小時的資訊)
for topic in TOPICS:
    try:
        # dateRestrict='d1' 代表限制搜尋過去 1 天內的網頁
        result = search_service.cse().list(q=topic, cx=SEARCH_ENGINE_ID, dateRestrict='d1', num=3).execute()
        items = result.get('items', [])
        for item in items:
            title = item.get('title')
            link = item.get('link')
            content = get_page_content(link)
            summary = summarize_content(content, topic, title)
            
            collected_news.append({
                "category": topic,
                "title": title,
                "url": link,
                "summary": summary
            })
    except Exception as e:
        print(f"抓取 {topic} 時發生錯誤: {e}")

# 4. 更新資料盒 (news_data.json)
with open('news_data.json', 'w', encoding='utf-8') as f:
    json.dump(collected_news, f, ensure_ascii=False, indent=4)

# 5. 發送專屬早安 Gmail
if collected_news:
    today_str = datetime.now().strftime("%Y-%m-%d")
    msg = MIMEMultipart()
    msg['From'] = GMAIL_ADDRESS
    msg['To'] = GMAIL_ADDRESS
    msg['Subject'] = f"【前日資訊彙報】{today_str} 您的專屬產業動態已更新"

    html_content = f"""
    <html>
    <body style="font-family: sans-serif; font-size: 16px; color: #333; line-height: 1.6;">
        <h2 style="color: #007BFF;">早安！這是為您準備的今日資訊彙報。</h2>
        <p>系統已自動為您整理了<b>數位轉型、PQC、金融科技</b>的最新動態。</p>
        <p>為保持版面簡潔，詳細摘要請至您的專屬網頁閱讀：</p>
        <p><a href="這裡之後會換成您的Streamlit網址" style="background-color: #007BFF; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-size: 18px;">👉 點擊前往專屬資訊網頁</a></p>
        <hr>
        <p style="font-size: 14px; color: #888;">祝您有美好的一天！自動化機器人 敬上</p>
    </body>
    </html>
    """
    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("郵件發送成功！")
    except Exception as e:
        print(f"郵件發送失敗: {e}")
