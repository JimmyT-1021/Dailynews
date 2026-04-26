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
model = genai.GenerativeModel('gemini-2.5-flash')

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
    
    prompt = f"你是一位專業科技分析師。請為讀者『Jimmy』摘要以下文章，字數 150 字內，語氣專業精確，並點出產業影響。標題：{title}\n內容：{text}"
    
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }
    
    try:
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts:
            return "AI 判斷此新聞內容涉及敏感或安全限制字眼，無法生成摘要，請點擊標題查看全文。"
        return response.text.strip().replace('\n', ' ')
    except Exception as e:
        print(f"  [AI 摘要失敗] {title} - 錯誤原因: {e}")
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
        
        feed_title = root.find('atom:title', namespaces).text
        topic_match = re.search(r'Google 快訊 - (.*?)\s*\(site:', feed_title)
        topic = topic_match.group(1).strip() if topic_match else "產業焦點"
        
        # 產生純淨的驗證關鍵字（去除可能存在的雙引號並轉小寫，確保比對精準）
        verification_keyword = topic.replace('"', '').replace('“', '').replace('”', '').strip().lower()
        
        entries = root.findall('atom:entry', namespaces)
        print(f"解析【{topic}】RSS 流... 發現 {len(entries)} 筆紀錄")
        
        for entry in entries:
            published_element = entry.find('atom:published', namespaces)
            if published_element is not None and published_element.text:
                published_str = published_element.text
                published_time = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if published_time < time_threshold:
                    continue 
                
            raw_title = entry.find('atom:title', namespaces).text
            clean_title = re.sub('<[^<]+>', '', raw_title)
            
            raw_link = entry.find('atom:link', namespaces).attrib['href']
            parsed_link = urllib.parse.urlparse(raw_link)
            query_params = urllib.parse.parse_qs(parsed_link.query)
            actual_url = query_params.get('url', [raw_link])[0]
            
            if actual_url not in seen_urls:
                seen_urls.add(actual_url)
                
                # 抓取網頁純淨內文
                content = get_page_content(actual_url)
                
                # 【二次攔截防線】：如果標題與純淨內文中，完全找不到關鍵字，則視為雜訊並丟棄
                if verification_keyword not in clean_title.lower() and verification_keyword not in content.lower():
                    print(f"  └ [已過濾雜訊] 內文無實質關鍵字：{clean_title}")
                    continue
                
                print(f"  └ 新增並摘要: {clean_title}")
                summary = summarize_content(content, topic, clean_title)
                
                collected_news.append({
                    "category": topic,
                    "title": clean_title,
                    "url": actual_url,
                    "summary": summary
                })
                
                time.sleep(5) 
                
    except Exception as e:
        print(f"解析過程中發生異常: {e}")

# 4. 構建與發送郵件
today_str = datetime.now().strftime("%Y-%m-%d")
msg = MIMEMultipart()
msg['From'] = GMAIL_ADDRESS
msg['To'] = GMAIL_ADDRESS

if collected_news:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 產業要聞與技術趨勢"
    collected_news.sort(key=lambda x: x['category'])
    
    news_html = ""
    current_cat = ""
    for n in collected_news:
        if n['category'] != current_cat:
            current_cat = n['category']
            news_html += f"""
            <tr style="background:#f4f8ff;">
                <td style="padding:12px; border-left:5px solid #0056b3;">
                    <b>■ {current_cat}</b>
                </td>
            </tr>
            """
        news_html += f"""
        <tr>
            <td style="padding:15px 10px; border-bottom:1px solid #eee;">
                <div style="font-size:16px; font-weight:bold; margin-bottom:5px;">
                    <a href="{n['url']}" style="color:#0056b3; text-decoration:none;">▷ {n['title']}</a>
                </div>
                <div style="font-size:14px; color:#333; line-height:1.6;">{n['summary']}</div>
            </td>
        </tr>
        """
        
    body_html = f"<html><body><table style='width:100%; border-collapse:collapse; font-family: sans-serif;'>{news_html}</table></body></html>"
else:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 今日無相關產業動態"
    body_html = "<html><body><p>經過防雜訊過濾後，過去 24 小時內並無高度相關的產業動態。</p></body></html>"

msg.attach(MIMEText(body_html, 'html'))

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("發信程序完成。")
except Exception as e:
    print(f"發信失敗: {e}")
