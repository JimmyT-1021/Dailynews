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
        if response.status_code != 200: return ""
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(["script", "style", "header", "footer", "nav", "aside"]): tag.decompose()
        paragraphs = soup.find_all('p')
        text = ' '.join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 35])
        if len(text) < 100:
            meta_desc = soup.find("meta", property="og:description")
            if meta_desc: text = meta_desc.get("content", "")
        return text[:3000]
    except: return ""

def summarize_content(text, topic, title):
    if len(text) < 80: return f"已鎖定關於【{topic}】的報導，但原始網頁具備存取限制。建議您點擊標題直接前往閱讀。"
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
    try:
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts: return "AI 判斷此新聞內容涉及敏感或安全限制字眼，無法生成摘要，請點擊標題查看全文。"
        return response.text.strip().replace('\n', '')
    except Exception as e:
        print(f"  [AI 摘要失敗] {title} - 錯誤原因: {e}")
        return "AI 摘要模組暫時無回應，請點擊標題查看全文。"

# === 新增：第二階段商業深度分析功能 ===
def generate_business_analysis(news_list):
    if not news_list: return ""
    
    # 將今日所有新聞摘要組合給 AI 閱讀
    catalog = ""
    for i, n in enumerate(news_list):
        catalog += f"[{i+1}] 標題：{n['title']}\n摘要：{n['summary']}\n\n"
        
    prompt = f"""你是一位頂尖的商業戰略分析師。以下是今日收集到的科技產業新聞清單：

{catalog}

請從中挑選出「最多 3 篇」最具有商業效應與產業變現潛力的新聞，並針對這幾篇進行深度商業分析。
請嚴格依照下方格式輸出，並直接使用 HTML 標籤排版以便嵌入信件中。請勿輸出 ```html 等 Markdown 標記，直接輸出乾淨的 HTML 碼即可。

針對每一篇的輸出格式必須如下：

<div style="background-color: #f8f9fa; padding: 15px; margin-bottom: 20px; border-radius: 8px; border-left: 5px solid #0056b3;">
    <h3 style="color: #0056b3; margin-top: 0;">新聞：[填入原新聞標題]</h3>
    
    <h4 style="color: #333; margin-bottom: 5px;">一、 商業變現路徑 (Revenue & Cost Drivers)</h4>
    <ul style="margin-top: 0; padding-left: 20px; line-height: 1.6;">
        <li><b>1.營收增長 (Top-line Growth)：</b>[具體分析]</li>
        <li><b>2.成本優化 (Bottom-line Savings)：</b>[具體分析]</li>
    </ul>

    <h4 style="color: #333; margin-bottom: 5px;">二、 產業衝擊與機會 (Impact & Opportunities)</h4>
    <ul style="margin-top: 0; padding-left: 20px; line-height: 1.6;">
        <li><b>1.機會 (Value Creation)：</b>[具體分析]</li>
        <li><b>2.衝擊 (Value Destruction)：</b>[具體分析]</li>
    </ul>

    <h4 style="color: #333; margin-bottom: 5px;">三、 影響對象精準定位 (Stakeholder Mapping)</h4>
    <ul style="margin-top: 0; padding-left: 20px; line-height: 1.6;">
        <li><b>1.直接受益者：</b>[具體分析]</li>
        <li><b>2.直接受災者：</b>[具體分析]</li>
    </ul>
</div>
"""
    try:
        response = model.generate_content(prompt)
        # 清除可能殘留的 markdown 標記
        html_output = response.text.strip().replace('```html', '').replace('```', '')
        return html_output
    except Exception as e:
        print(f"產生商業分析失敗: {e}")
        return ""

# ==========================================

now_utc = datetime.now(timezone.utc)
time_threshold = now_utc - timedelta(hours=24)

print(f"--- 啟動 RSS 訂閱解析任務: {datetime.now()} ---")

for feed_url in RSS_FEEDS:
    try:
        response = requests.get(feed_url, timeout=15)
        if response.status_code != 200: continue
        root = ET.fromstring(response.content)
        feed_title = root.find('atom:title', namespaces).text
        topic_match = re.search(r'Google 快訊 - (.*?)\s*\(site:', feed_title)
        topic = topic_match.group(1).strip() if topic_match else "產業焦點"
        verification_keyword = topic.replace('"', '').replace('“', '').replace('”', '').strip().lower()
        entries = root.findall('atom:entry', namespaces)
        
        for entry in entries:
            published_element = entry.find('atom:published', namespaces)
            if published_element is not None and published_element.text:
                published_str = published_element.text
                published_time = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if published_time < time_threshold: continue 
                
            raw_title = entry.find('atom:title', namespaces).text
            clean_title = re.sub('<[^<]+>', '', raw_title)
            raw_link = entry.find('atom:link', namespaces).attrib['href']
            parsed_link = urllib.parse.urlparse(raw_link)
            query_params = urllib.parse.parse_qs(parsed_link.query)
            actual_url = query_params.get('url', [raw_link])[0]
            
            if actual_url not in seen_urls:
                seen_urls.add(actual_url)
                content = get_page_content(actual_url)
                if verification_keyword not in clean_title.lower() and verification_keyword not in content.lower(): continue
                if any(keyword in clean_title for keyword in EXCLUDE_KEYWORDS) or any(keyword in content for keyword in EXCLUDE_KEYWORDS): continue
                
                print(f"  └ 新增並送交分析: {clean_title}")
                summary = summarize_content(content, topic, clean_title)
                if "REJECT_FINANCE" in summary: continue
                
                collected_news.append({"category": topic, "title": clean_title, "url": actual_url, "summary": summary})
                time.sleep(5) 
    except Exception as e:
        print(f"解析異常: {e}")

# 5. 構建與發送郵件
today_str = datetime.now().strftime("%Y-%m-%d")
msg = MIMEMultipart()
msg['From'] = GMAIL_ADDRESS
msg['To'] = GMAIL_ADDRESS

if collected_news:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 產業要聞與商業洞察"
    
    # 觸發商業深度分析
    print("正在匯總今日新聞，進行 Top 3 商業深度分析...")
    business_analysis_html = generate_business_analysis(collected_news)
    
    collected_news.sort(key=lambda x: x['category'])
    news_html = ""
    current_cat = ""
    for n in collected_news:
        if n['category'] != current_cat:
            current_cat = n['category']
            news_html += f"""<tr style="background:#f4f8ff;"><td style="padding:12px; border-left:5px solid #0056b3;"><b>■ {current_cat}</b></td></tr>"""
        news_html += f"""<tr><td style="padding:15px 10px; border-bottom:1px solid #eee;"><div style="font-size:16px; font-weight:bold; margin-bottom:5px;"><a href="{n['url']}" style="color:#0056b3; text-decoration:none;">▷ {n['title']}</a></div><div style="font-size:14px; color:#333; line-height:1.6;">{n['summary']}</div></td></tr>"""
        
    # 組合最終信件內容 (上方為深度分析，下方為完整清單)
    final_email_content = ""
    if business_analysis_html:
        final_email_content += f"<h2 style='color:#333; border-bottom: 2px solid #ccc; padding-bottom: 8px;'>🏆 今日 Top 3 商業深度洞察</h2>"
        final_email_content += business_analysis_html
        final_email_content += f"<h2 style='color:#333; border-bottom: 2px solid #ccc; padding-bottom: 8px; margin-top: 40px;'>📰 完整產業動態快報</h2>"
        
    final_email_content += f"<table style='width:100%; border-collapse:collapse; font-family: sans-serif;'>{news_html}</table>"
    body_html = f"<html><body style='font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;'>{final_email_content}</body></html>"
else:
    msg['Subject'] = f"【Jimmy的每日新聞】{today_str} 今日無相關產業動態"
    body_html = "<html><body><p>經過股市雜訊過濾與關鍵字比對後，過去 24 小時內並無高度相關的技術發展動態。</p></body></html>"

msg.attach(MIMEText(body_html, 'html'))

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("發信程序完成。")
except Exception as e:
    print(f"發信失敗: {e}")
