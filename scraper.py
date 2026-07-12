import os
import google.generativeai as genai

# 1. 讀取環境變數中的 API 金鑰
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

print("=== 您的 API 金鑰支援的模型清單 ===")
try:
    # 2. 向 Google 伺服器請求真實模型清單
    models = genai.list_models()
    for m in models:
        # 3. 篩選出支援文字生成的模型並印出
        if 'generateContent' in m.supported_generation_methods:
            print(f"可用模型名稱: {m.name}")
except Exception as e:
    print(f"獲取模型清單失敗: {e}")
print("====================================")
