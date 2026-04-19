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

# 精準搜尋設定：指定來源 (site:)
# 來源已更新：移除 Yahoo 新聞，保留 iThome、數位部、科技報橘、經濟日報、工商時報、科技新報、數位時代
SITES = " (site:ithome.com.tw OR site:moda.gov.tw OR site:techorange.com OR site:money.udn.com OR site:ctee.com.tw OR site:technews.tw OR site:bnext.com.tw)"
TOPICS = [
    "數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", 
    "電子簽章", "生物辨識", "保險科技", "電子簽名", 
    "數位發展部", "數位簽章", "GEO"
]

collected_news = []

def get_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if p.text.strip()])
        return text[:1500] 
    except:
        return ""

def summarize_content(text, topic, title):
    if len(text) < 50: # 若內文過短，視為無效抓取
        return f"網頁可能設有阻擋機制或內容過短，請點擊標題直接前往原始網頁閱讀這篇關於【{topic}】的報導。"
    prompt = f"請針對以下網頁內容進行繁體中文摘要，長度約 100 字，必須展現專業語調。標題：{title}\n內容：{text}"
    try:
        response = model.generate_content(prompt)
        return response.text.replace('\n', '')
    except:
        return "AI 摘要生成暫時遇到問題，請點擊原文連結閱讀完整內容。"

# 3. 執行精準搜尋與抓取 (維持 24 小時限制)
for topic in TOPICS:
    search_query = f"{topic}{SITES}"
    print(f"執行搜尋: {search_query}")
    try:
        with DDGS() as ddgs:
            # timelimit='d' 堅持每日新鮮度
            results = list(ddgs.text(search_query, region='tw-tz', timelimit='d', max_results=2))
            
            for item in results:
                title = item.get('title')
                link = item.get('href')
                
                # 防呆機制：確保標題與連結皆存在才處理
                if title and link:
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

# 4. 構建純文字信件內容
today_str = datetime.now().strftime("%Y-%m-%d")
msg = MIMEMultipart()
msg['From'] = GMAIL_ADDRESS
msg['To'] = GMAIL_ADDRESS

if collected_news:
    msg['Subject'] = f"【每日情報彙編】{today_str} 產業要聞與技術趨勢"
    news_html_sections = ""
    current_category = ""
    
    for news in collected_news:
        if news['category'] != current_category:
            current_category = news['category']
            news_html_sections += f"""
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 10px; border-left: 5px solid #007BFF;">
                        <h2 style="margin: 0; color: #333; font-size: 20px;">■ {current_category}</h2>
                    </td>
                </tr>
            """
        
        news_html_sections += f"""
            <tr>
                <td style="padding: 15px 10px;">
                    <h3 style="margin: 0 0 10px 0; font-size: 18px;">
                        <a href="{news['url']}" style="color: #0056b3; text-decoration: none;">▷ {news['title']}</a>
                    </h3>
                    <p style="margin: 0; color: #444; font-size: 15px; line-height: 1.6;">{news['summary']}</p>
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
        <p style="font-size: 12px; color: #aaa; text-align: center; margin-top: 30px;">本郵件由 AI 自動生成，彙整過去 24 小時內之重要動態。</p>
    </body>
    </html>
    """
else:
    # 零更新防護機制：發送「無新聞」通知信
    msg['Subject'] = f"【系統狀態更新】{today_str} 今日無相關產業動態"
    full_html = f"""
    <html>
    <body style="font-family: 'Microsoft JhengHei', sans-serif; max-width: 800px; margin: 20px auto; text-align: center;">
        <h2 style="color: #555;">今日無相關產業更新</h2>
        <p style="color: #666; font-size: 16px; line-height: 1.6;">
            為您監控的 11 項關鍵字與 6 大科技媒體，在過去 24 小時內皆無符合條件的新聞發布。<br>
            系統運作一切正常，我們明日將繼續為您追蹤最新動態。
        </p>
        <p style="font-size: 12px; color: #aaa; margin-top: 30px;">本郵件由自動化情報系統發送。</p>
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
    print("郵件已成功發送。")
except Exception as e:
    print(f"發信失敗: {e}")
