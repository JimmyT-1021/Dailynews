import streamlit as st
import json

# 設定網頁標題與排版
st.set_page_config(page_title="專屬資訊彙報", page_icon="📰", layout="centered")

# 注入扁平化、淺藍色系 CSS，並設定舒適的大字體與寬行距
st.markdown("""
<style>
    .stApp { background-color: #F4F9FF; }
    h1, h2, h3 { color: #0056b3; font-family: 'sans-serif'; }
    p, div, li, span { font-size: 20px !important; line-height: 1.8 !important; color: #2C3E50; }
    .news-box { background-color: #FFFFFF; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 5px solid #007BFF; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

st.title("📰 每日資訊彙報")
st.markdown("追蹤主題：**數位轉型**、**PQC**、**金融科技**")
st.divider()

try:
    with open('news_data.json', 'r', encoding='utf-8') as f:
        news_list = json.load(f)
        
    if not news_list:
        st.info("目前尚無資料，系統即將進行首次抓取。")
    else:
        for item in news_list:
            st.markdown(f"""
            <div class="news-box">
                <h3 style="margin-top:0;">【{item['category']}】{item['title']}</h3>
                <p>{item['summary']}</p>
                <a href="{item['url']}" target="_blank" style="font-size: 18px; color: #007BFF; text-decoration: none;">🔗 閱讀原始網頁</a>
            </div>
            """, unsafe_allow_html=True)
except FileNotFoundError:
    st.info("資料庫建置中，請等待系統首次自動執行。")
