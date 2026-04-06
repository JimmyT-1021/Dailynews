# 微調內文以適應多重關鍵字
    html_content = f"""
    <html>
    <body style="font-family: sans-serif; font-size: 16px; color: #333; line-height: 1.6;">
        <h2 style="color: #007BFF;">早安！這是為您準備的今日資訊彙報。</h2>
        <p>系統已自動為您整理了<b>共 {len(TOPICS)} 項專屬關注領域</b>的最新動態。</p>
        <p>為保持版面簡潔，詳細摘要請至您的專屬網頁閱讀：</p>
        <p><a href="https://dailynews-g3ghcx7krscevm4hudr5fb.streamlit.app/" style="background-color: #007BFF; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-size: 18px;">👉 點擊前往專屬資訊網頁</a></p>
        <hr>
        <p style="font-size: 14px; color: #888;">祝您有美好的一天！自動化機器人 敬上</p>
    </body>
    </html>
    """
