import streamlit as st
import json

st.set_page_config(page_title="專屬產業資訊彙報", layout="centered")
st.title("📊 每日專屬產業資訊彙報")
st.write("這是由自動化系統每日抓取並生成的最新動態。")
st.divider()

try:
    with open('news_data.json', 'r', encoding='utf-8') as f:
        news_data = json.load(f)
        
    if not news_data:
        st.info("今日尚無符合條件的最新新聞資料。")
    else:
        # 同步更新的 11 項關鍵字
        topics = [
            "數位轉型", "PQC", "金融科技", "OCR", "自然人憑證", 
            "電子簽章", "生物辨識", "保險科技", "電子簽名", 
            "數位發展部", "數位簽章"
        ]
        
        for topic in topics:
            st.header(f"📌 {topic}")
            
            topic_news = [item for item in news_data if item.get("category") == topic]
            
            if not topic_news:
                st.write("今日無此主題之相關更新。")
            else:
                for item in topic_news:
                    st.subheader(item.get("title"))
                    st.write(item.get("summary"))
                    st.markdown(f"[🔗 點此閱讀原始網頁]({item.get('url')})")
            st.divider()

except FileNotFoundError:
    st.error("目前尚未建立新聞資料盒 (news_data.json)，系統將於下次排程自動生成。")
