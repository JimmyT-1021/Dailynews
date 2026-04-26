import os, smtplib, requests, time, re
import urllib.parse
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai

# 1. 讀取環境變數
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# 2. 設定 Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro-latest')

# 3. 專屬 RSS 資料流清單 (共 13 組)
RSS_FEEDS = [
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/18404326158233745867",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/7518766543809525173",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2384905966260938889",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/18404326158233747233",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/7518766543809524008",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2384905966260937948",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/18404326158233746651",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/7518766543809526938",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2507623650954553224",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/18404326158233745156",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/7518766543809525223",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2507623650954551914",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2507623650954551348"
]

collected_news = []
seen_urls = set()
namespaces = {'atom': 'http://www.w3.org/2005/Atom'}

def get_page_content(url):
    """針對指定媒體之內文擷取邏輯"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Referer': 'https://www.google.com/',
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return ""
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
            tag.decompose()
            
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 35])
        
        return text[:3000]
    except Exception as e:
        return ""

def summarize_content(text, topic, title):
    if len(text) < 80:
        return f"已鎖定關於【{topic}】的報導，但原始網頁具備存取限制。建議您點擊標題直接前往閱讀。"
    
    prompt = f"你是一位專業科技分析師。請為讀者『Jimmy』摘要以下文章，字數 150 字內，語氣專業精確，並點出產業影響。標題：{title}\n內容：{text}"
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace('\n', ' ')
    except:
        return "AI 摘要模組暫時無回應，請點擊標題查看全文。"

# 設定時間邊界：僅處理過去 24 小時內的快訊
now_utc = datetime.now(timezone.utc)
time_threshold = now_utc - timedelta(hours=24)

print(f"--- 啟動 RSS 訂閱解析任務: {datetime.now()} ---")

for feed_url in RSS_FEEDS:
    try:
        response = requests.get(feed_url, timeout=15)
        if response.status_code != 200:
            print(f"無法讀取 RSS: {feed_url}")
            continue
            
        root = ET.fromstring(response.content)
        
        # 從 feed title 中動態萃取關鍵字 (例如 "Google 快訊 - 數位簽章 (site:...)")
        feed_title = root.find('atom:title', namespaces).text
        topic_match = re.search(r'Google 快訊 - (.*?)\s*\(site:', feed_title)
        topic = topic_match.group(1).strip() if topic_match else "產業焦點"
        
        entries = root.findall('atom:entry', namespaces)
