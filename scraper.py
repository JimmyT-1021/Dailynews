import os, smtplib, requests, time, re
import urllib.parse
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# 1. 讀取環境變數
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# 2. 設定 Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-3.5-flash')

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

# 4. 股市與財報雜訊排除參數庫
EXCLUDE_KEYWORDS = [
    "股價", "營收", "大盤", "外資", "EPS", "台股", "升息", 
    "殖利率", "投機", "多頭", "空頭", "個股", "法人", 
    "買超", "賣超", "目標價", "股市", "除息", "配息"
]

# 5. 付費牆與訂閱特徵字庫
PAYWALL_KEYWORDS = [
    "訂閱解鎖", "VIP專屬", "付費會員", "付費解鎖", "訂閱觀看全文",
    "加入會員觀看全文", "解鎖全文", "VIP會員", "限訂閱者閱讀"
]

collected_news = []
seen_urls = set()
namespaces = {'atom': 'http://www.w3.org/2005/Atom'}

def get_page_content(url):
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
        
        full_text_no_spaces = soup.text.replace(' ', '').replace('\n', '')
        if any(keyword in full_text_no_spaces for keyword in PAYWALL_KEYWORDS):
            return "PAYWALL_DETECTED"
        
        for tag in soup(["script", "style", "header", "footer", "nav", "aside"]):
            tag.decompose()
            
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 35])
        
        if len(text) < 100:
            meta_desc = soup.find("meta", property="og:description")
            if meta_desc:
                text = meta_desc.get("content", "")
                
        return text[:3000]
    except Exception as e:
        return ""

def summarize_content(text, topic, title):
    if len(text) < 80:
        return f"已鎖定關於【{topic}】的報導，但原始網頁具備存取限制。建議您點擊標題直接前往閱讀。"
    
    prompt = f"""你是一位專業科技分析師。請嚴格遵守以下所有規則來為讀者『Jimmy』處理以下文章：
1. 開頭必須一字不差地使用：「Jimmy您好，摘要如下，」
2. 嚴禁使用任何 Markdown 符號（包含但不限於 ** 或 ：）。
3. 字數嚴格限制在 65 字以內（若技術內容極度複雜，最多僅能放寬至 75 字）。
4. 內容必須絕對聚焦於：科技發展、運用場景、實際痛點或使用者反饋。
5. 審查機制：若判斷該文章核心為股市分析、股價預測、企業營收或金融市場動態，請直接回傳「REJECT_FINANCE」，不要輸出任何其他文字。

標題：{title}
內容：{text}"""
    
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }
    
    # 導入防 429 重試機制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt, safety_settings=safety_settings)
            if not response.parts:
                return "AI 判斷此新聞內容涉及敏感或安全限制字眼，無法生成摘要，請點擊標題查看全文。"
            return response.text.strip().replace('\n', '')
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg and attempt < max_retries - 1:
                wait_time = 20 * (attempt + 1)
                print(f"  [API 流量控管] 觸發 429 限制，暫停 {wait_time} 秒後進行第 {attempt+2} 次重試...")
                time.sleep(wait_time)
            else:
                print(f"  [AI 摘要失敗] {title} - 錯誤原因: {e}")
                return "AI 摘要模組暫時無回應，請點擊標題查看全文。"

def generate_business_analysis(news_list):
    if len(news_list) < 3:
        return ""
    
    news_text = ""
    for i, n in enumerate(news_list):
        news_text += f"[{i+1}] 標題：{n['title']}\n摘要：{n['summary']}\n\n"
        
    prompt = f"""你是一位頂尖的商業戰略分析師。請從以下今日新聞清單中，挑選出「最具商業變現潛力與產業影響力」的 3 篇新聞，並嚴格依照以下格式輸出 HTML 程式碼（不需輸出 ```html 標籤，直接輸出 HTML 內容即可，方便我嵌入信件中）。

格式要求：
對於每一篇選出的新聞，請產出以下 HTML 結構：
<div style="background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
    <h3 style="color: #0056b3; margin-top: 0; margin-bottom: 15px;">新聞標題（填寫原文標題）</h3>
    
    <h4 style="color: #333; border-bottom: 2px solid #f0f0f0; padding-bottom: 5px; margin-bottom: 10px;">一、 商業變現路徑 (Revenue & Cost Drivers)</h4>
    <ul style="font-size: 14px; color: #444; margin-top: 0;">
        <li><strong>營收增長 (Top-line Growth)：</strong>（具體分析說明）</li>
        <li><strong>成本優化 (Bottom-line Savings)：</strong>（具體分析說明
