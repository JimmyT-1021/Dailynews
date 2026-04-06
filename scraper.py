import os, json, smtplib, requests
from datetime import datetime
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai
from duckduckgo_search import DDGS

# 1. 讀取保險箱中的金鑰 (已移除失效的 Google 搜尋金鑰)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# 2. 設定 Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro-latest')

TOPICS = ["數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", "電子簽章", "生物辨識", "保險科技", "電子簽名"]
collected_news = []

def get_page_content(url):
    try:
        # 加入更完整的瀏覽器偽裝，避免被新聞網站阻擋
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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

# 3. 執行免費開源搜尋 (使用 DuckDuckGo，設定台灣繁體與過去24小時)
for topic in TOPICS:
    print(f"開始搜尋: {topic}")
    try:
        with DDGS() as ddgs:
            # timelimit='d' 代表過去一天，region='tw-tz' 代表台灣
            results = list(ddgs.text(f"{topic} 新聞", region='tw-tz', timelimit='d', max_results=3))
            
            for item in results:
                title = item.get('title')
                link = item.get('href')
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
else:
    print("今日無抓取到符合條件的新聞，不發送郵件。")
