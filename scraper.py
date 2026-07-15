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

# ==================== 安全鎖與配額設定 ====================
# 【強制安全鎖】每次執行最多只呼叫 API 處理 30 篇新聞，徹底杜絕 429 額度耗盡
MAX_API_CALLS = 30 
api_call_count = 0 
# ==========================================================

# 3. 專屬 RSS 資料流清單 (共 13 組)
RSS_FEEDS = [
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/7518766543809525173",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2384905966260938889",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/18404326158233747233",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/7518766543809524008",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2384905966260937948",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/18404326158233746651",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/7518766543809526938",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2507623650954553224",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/18404326158233745156",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2507623650954551914",
    "https://www.google.com.tw/alerts/feeds/13554238838654288953/2507623650954551348"
]

# 4. 字典庫設定
# 【新增】AI 專屬白名單 (沒提到這些字，直接丟棄)
TARGET_AI_KEYWORDS = ["AI", "人工智慧", "人工智能", "生成式", "Generative AI", "LLM", "大模型"]

PAYWALL_KEYWORDS = ["訂閱解鎖", "VIP專屬", "付費會員", "付費解鎖", "訂閱觀看全文", "加入會員觀看全文", "解鎖全文", "VIP會員", "限訂閱者閱讀"]
EXCLUDE_KEYWORDS = ["股價", "營收", "大盤", "外資", "EPS", "台股", "升息", "殖利率", "投機", "多頭", "空頭", "個股", "法人", "買超", "賣超", "目標價", "股市", "除息", "配息"]
COURSE_KEYWORDS = ["開課", "招生", "研習營", "培訓班", "學分班", "報名連結", "補習班", "冬令營", "夏令營", "工作坊", "講座報名"]
CONSUMER_KEYWORDS = ["開箱", "評測", "懶人包", "限時下殺", "哪裡買", "優惠碼", "性價比", "促銷", "早鳥價", "折扣"]
GOSSIP_KEYWORDS = ["網友熱議", "網爆", "炎上", "吵翻", "鄉民", "PTT熱議", "Dcard", "傻眼", "網怒", "酸民"]
PR_KEYWORDS = ["榮獲", "頒獎典禮", "殊榮", "廣編特輯", "品牌大使", "共襄盛舉", "獲頒", "盛大開幕", "圓滿落幕"]

# 組合所有黑名單字典以便快速掃描
ALL_BLACKLIST = EXCLUDE_KEYWORDS + COURSE_KEYWORDS + CONSUMER_KEYWORDS + GOSSIP_KEYWORDS + PR_KEYWORDS

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
3. 字數嚴格限制在 65 字以內。
4. 內容必須絕對聚焦於：AI 科技發展、實際企業運用場景、產業衝擊。
5. 審查機制（嚴格把關）：
   - 若為股市/股價/金融預測，回傳「REJECT_FINANCE」
   - 若為大學課程、政府招生、補習班推廣，回傳「REJECT_COURSE」
   - 若為手機/筆電開箱、促銷優惠，回傳「REJECT_CONSUMER」
   - 若為 PTT/Dcard 網友八卦爭吵，回傳「REJECT_GOSSIP」
   - 若純屬企業得獎自嗨公關稿，回傳「REJECT_PR」
   - 若文章實質上與 AI/人工智慧的商業或技術發展無關，回傳「REJECT_NOT_AI」

標題：{title}
內容：{text}"""
    
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt, safety_settings=safety_settings)
            if not response.parts:
                return "AI 判斷此新聞內容涉及敏感限制字眼，無法生成摘要。"
            return response.text.strip().replace('\n', '')
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg and attempt < max_retries - 1:
                wait_time = 20 * (attempt + 1)
                time.sleep(wait_time)
            else:
                print(f"  [AI 摘要失敗] {title} - 錯誤原因: {e}")
                return "AI 摘要模組暫時無回應，請點擊標題查看全文。"

def generate_business_analysis(news_list):
    if len(news_list) < 1:
        return ""
    
    news_text = ""
    for i, n in enumerate(news_list[:3]): # 最多取前3篇進行商業分析
        news_text += f"[{i+1}] 標題：{n['title']}\n摘要：{n['summary']}\n\n"
        
    prompt = f"""你是一位頂尖的商業戰略分析師。請從以下今日新聞清單中，挑選出「最具商業變現潛力與產業影響力」的 AI 新聞，並嚴格依照以下格式輸出 HTML 程式碼（直接輸出 HTML 內容即可）。

格式要求：
對於每一篇選出的新聞，請產出以下 HTML 結構：
<div style="background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
    <h3 style="color: #0056b3; margin-top: 0; margin-bottom: 15px;">新聞標題（填寫原文標題）</h3>
    
    <h4 style="color: #333; border-bottom: 2px solid #f0f0f0; padding-bottom: 5px; margin-bottom: 10px;">一、 商業變現路徑 (Revenue & Cost Drivers)</h4>
    <ul style="font-size: 14px; color: #444; margin-top: 0;">
        <li><strong>營收增長 (Top-line Growth)：</strong>（具體分析說明）</li>
        <li><strong>成本優化 (Bottom-line Savings)：</strong>（具體分析說明）</li>
    </ul>

    <h4 style="color: #333; border-bottom: 2px solid #f0f0f0; padding-bottom: 5px; margin-bottom: 10px;">二、 產業衝擊與機會 (Impact & Opportunities)</h4>
    <ul style="font-size: 14px; color: #444; margin-top: 0;">
        <li><strong>機會 (Value Creation)：</strong>（具體分析說明）</li>
        <li><strong>衝擊 (Value Destruction)：</strong>（具體分析說明）</li>
    </ul>

    <h4 style="color: #333; border-bottom: 2px solid #f0f0f0; padding-bottom: 5px; margin-bottom: 10px;">三、 影響對象精準定位 (Stakeholder Mapping)</h4>
    <ul style="font-size: 14px; color: #444; margin-top: 0;">
        <li><strong>直接受益者：</strong>（具體點出獲益對象）</li>
        <li><strong>直接受災者：</strong>（具體點出受衝擊對象）</li>
    </ul>
</div>

今日新聞清單如下：
{news_text}
"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            if response.text:
                return f"""
                <div style="background-color: #eaf1f8; padding: 20px; border-radius: 10px; margin-bottom: 30px;">
                    <h2 style="color: #d32f2f; margin-top: 0; text-align: center;">🏆 今日 Top AI 商業戰略洞察</h2>
                    <p style="text-align: center; font-size: 14px; color: #666; margin-bottom: 20px;">基於今日產業動態，為您淬鍊出最具變現潛力之 AI 情報分析</p>
                    {response.text.strip().replace('```html', '').replace('```', '')}
                </div>
                """
            return ""
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg and attempt < max_retries - 1:
                wait_time = 30 * (attempt + 1)
                time.sleep(wait_time)
            else:
                print(f"  [AI 商業分析生成失敗] 錯誤原因: {e}")
                return f"""
                <div style="background-color: #fff3cd; padding: 15px; border-left: 5px solid #ffc107; margin-bottom: 20px;">
                    <strong style="color: #856404;">系統提示：</strong><span style="color: #856404; font-size: 14px;"> 今日 Google API 免費運算額度已達上限，暫停生成商業深度分析。下方仍為您提供一般快報整理。</span>
                </div>
                """

now_utc = datetime.now(timezone.utc)
time_threshold = now_utc - timedelta(hours=24)

print(f"--- 啟動 AI 專屬情報解析任務: {datetime.now()} ---")

for feed_url in RSS_FEEDS:
    if api_call_count >= MAX_API_CALLS:
        print("【安全鎖觸發】已達本次排程最大分析額度 (30篇)，停止抓取新資訊以保護 API。")
        break

    try:
        response = requests.get(feed_url, timeout=15)
        if response.status_code != 200:
            continue
            
        root = ET.fromstring(response.content)
        feed_title = root.find('atom:title', namespaces).text
        topic_match = re.search(r'Google 快訊 - (.*?)\s*\(site:', feed_title)
        topic = topic_match.group(1).strip() if topic_match else "產業焦點"
        
        entries = root.findall('atom:entry', namespaces)
        print(f"解析【{topic}】RSS 流...")
        
        for entry in entries:
            if api_call_count >= MAX_API_CALLS:
                break # 再次確認安全鎖

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
                
                content = get_page_content(actual_url)
                
                if content == "PAYWALL_DETECTED":
                    continue
                
                # 【第一道防線】本地端白名單確認：沒提到 AI 相關字詞直接捨棄 (零成本)
                text_to_check = (clean_title + content).lower()
                is_ai_related = any(kw.lower() in text_to_check for kw in TARGET_AI_KEYWORDS)
                if not is_ai_related:
                    print(f"  └ [非AI新聞直接捨棄]: {clean_title}")
                    continue
                
                # 【第二道防線】本地端黑名單過濾：股市、公關、農場文、課程
                if any(keyword in clean_title for keyword in ALL_BLACKLIST) or any(keyword in content for keyword in ALL_BLACKLIST):
                    print(f"  └ [命中黑名單字詞過濾]: {clean_title}")
                    continue

                print(f"  └ [符合 AI 商業要件] 呼叫 API 進行分析: {clean_title}")
                api_call_count += 1 # 準備呼叫 API，計數器 +1
                summary = summarize_content(content, topic, clean_title)
                
                # 【第三道防線】AI 語意判官最終裁量
                if "REJECT_" in summary:
                    print(f"  └ [遭 AI 語意審查剔除]: {summary} - {clean_title}")
                    continue
                
                collected_news.append({
                    "category": topic,
                    "title": clean_title,
                    "url": actual_url,
                    "summary": summary
                })
                
                time.sleep(15) 
                
    except Exception as e:
        print(f"解析過程中發生異常: {e}")

# 5. 構建與發送郵件
today_str = datetime.now().strftime("%Y-%m-%d")
msg = MIMEMultipart()
msg['From'] = GMAIL_ADDRESS
msg['To'] = GMAIL_ADDRESS

if collected_news:
    msg['Subject'] = f"【Jimmy的AI戰略情報】{today_str} 商業變現與產業衝擊分析"
    collected_news.sort(key=lambda x: x['category'])
    
    api_call_count += 1 # 總結分析也算 1 次 API 呼叫
    business_analysis_html = generate_business_analysis(collected_news)
    
    news_html = ""
    current_cat = ""
    for n in collected_news:
        if n['category'] != current_cat:
            current_cat = n['category']
            news_html += f"""
            <tr style="background:#f4f8ff;">
                <td style="padding:12px; border-left:5px solid #0056b3; margin-top:10px;">
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
        
    body_html = f"<html><body style='font-family: sans-serif; max-width: 800px; margin: 0 auto;'>"
    body_html += business_analysis_html
    body_html += f"<h3>📰 AI 戰略情報總覽</h3>"
    body_html += f"<table style='width:100%; border-collapse:collapse;'>{news_html}</table></body></html>"
else:
    msg['Subject'] = f"【Jimmy的AI戰略情報】{today_str} 今日無高價值 AI 動態"
    body_html = "<html><body><p>經過層層黑名單與非AI雜訊過濾後，過去 24 小時內並無高度相關的商業/技術發展動態。</p></body></html>"

msg.attach(MIMEText(body_html, 'html'))

try:
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("發信程序完成。")
except Exception as e:
    print(f"發信失敗: {e}")
