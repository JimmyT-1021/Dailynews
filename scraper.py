import os, smtplib, requests
from datetime import datetime
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai
from duckduckgo_search import DDGS

# 1. 讀取環境變數
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# 2. 設定 Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro-latest')

# 精準搜尋設定：關鍵字 + 指定來源 (site:)
# 您可以自由增減底下的 site: 網域
SITES = " (site:ithome.com.tw OR site:moda.gov.tw OR site:technews.tw)"
TOPICS = [
    "數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", 
    "電子簽章", "生物辨識", "保險科技", "電子簽名", 
    "數位發展部", "數位簽章"
]

collected_news = []

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text for p in paragraphs])
        return text[:1500] 
    except:
        return ""

def summarize_content(text, topic, title):
    if not text:
        return f"無法抓取完整內文，請點擊連結閱讀關於【{topic}】的原文。"
    prompt = f"請針對以下網頁內容進行繁體中文摘要，長度約 100 字，必須展現專業語調。標題：{title}\n內容：{text}"
    try:
        response = model.generate_content(prompt)
        return response.text.replace('\n', '')
    except:
        return "摘要生成失敗，請點擊連結查看原文。"

# 3. 執行精準搜尋與抓取
for topic in TOPICS:
    search_query = f"{topic}{SITES}"
    print(f"執行精準搜尋: {search_query}")
    try:
        with DDGS() as ddgs:
            # 抓取過去 24 小時內最相關的 2 則新聞
            results = list(ddgs.text(search_query, region='tw-tz', timelimit='d', max_results=2))
            
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
        print(f"處理 {topic} 時發生錯誤: {e}")

# 4. 構建純文字信件內容 (主標、副標、內文)
if collected_news:
    today_str = datetime.now().strftime("%Y-%m-%d")
    msg = MIMEMultipart()
    msg['From'] = GMAIL_ADDRESS
    msg['To'] = GMAIL_ADDRESS
    msg['Subject'] = f"【每日情報彙編】{today_str} 產業要聞與技術趨勢"

    # 生成 HTML 內容
    news_html_sections = ""
    current_category = ""
    
    for news in collected_news:
        # 如果是新類別，加入主標
        if news['category'] != current_category:
            current_category = news['category']
            news_html_sections += f"""
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border-left: 5px solid #007BFF;">
                        <h2 style="margin: 0; color: #333; font-size: 20px;">■ {current_category}</h2>
                    </td>
                </tr>
            """
        
        # 加入副標(標題)與內文(摘要)
        news_html_sections += f"""
            <tr>
                <td style="padding: 15px 10px;">
                    <h3 style="margin: 0 0 10px 0; color: #0056b3; font-size: 18px;">▷ {news['title']}</h3>
                    <p style="margin: 0 0 10px 0; color: #444; font-size: 15px; line-height: 1.6;">{news['summary']}</p>
                    <a href="{news['url']}" style="color: #007BFF; text-decoration: none; font-size: 14px;">[閱讀原文]</a>
                </td>
            </tr>
            <tr><td><hr style="border: 0; border-top: 1px solid #eee; margin: 0;"></td></tr>
        """

    full_html = f"""
    <html>
    <body style="font-family: 'Microsoft JhengHei', sans-serif; max-width: 800px; margin: 20px auto;">
        <h1 style="text-align: center; color: #333;">每日專屬產業情報</h1>
        <p style="text-align: center; color: #666;">報告日期：{today_str}</p>
        <table style="width: 100%; border-collapse: collapse;">
            {news_html_sections}
        </table>
        <p style="font-size: 12px; color: #aaa; text-align: center; margin-top: 30px;">本郵件由 AI 自動生成並發送，旨在提供技術趨勢參考。</p>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(full_html, 'html'))

    # 5. 發送郵件
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("資訊彙報郵件已成功發送。")
    except Exception as e:
        print(f"發信失敗: {e}")
else:
    print("本日指定來源中未發現相關更新，跳過發信步驟。")
