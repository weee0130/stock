import streamlit as st
import pandas as pd

# --- 1. 介面設定 (側邊欄) ---
st.set_page_config(layout="wide", page_title="盤中高震盪飆股監控")
st.sidebar.header("📊 篩選條件設定")

# 使用者自選振幅
amp_input = st.sidebar.slider("自選振幅門檻 (%)", 2.0, 8.0, 3.5, 0.5)
vol_threshold = st.sidebar.number_input("最低張數門檻", value=3000, step=500)
ratio_threshold = st.sidebar.slider("開盤量佔昨量比 (%)", 10, 50, 20)

# --- 2. 模擬資料獲取 (請替換為你的 API) ---
@st.cache_data(ttl=60) # 每 60 秒更新一次
def get_processed_data():
    # 這裡放你原有的 Python 篩選邏輯
    # df = fetch_api_data() 
    # return processed_df
    pass

# --- 3. 核心標籤分類邏輯 ---
def apply_tags(row):
    # A 區：力道指標
    if row['gap_percent'] > 2.5:
        return "🔥 強攻型 (A-1)"
    elif row['vol_spike'] > 2.0:
        return "⚡ 動能型 (A-2)"
    elif row['buy_ratio'] > 0.55:
        return "🔵 收貨型 (A-3)"
    
    # B 區：籌碼指標
    if row['inst_buy'] > 0:
        return "🧱 大人型 (B-1)"
    elif row['short_ratio'] > 0.15:
        return "🚀 軋空型 (B-2)"
    
    return "⚪ 一般震盪"

# --- 4. 主畫面顯示 ---
st.title("🏹 開盤 20 分鐘震盪追蹤器")
st.info(f"當前設定：振幅 > {amp_input}% | 成交量 > {vol_threshold}張 或 > 昨量 {ratio_threshold}%")

# 假設 df_final 是篩選後的結果
# df_final['分類標籤'] = df_final.apply(apply_tags, axis=1)

# 使用 Streamlit 的 dataframe 顯示，並加入顏色標註
st.subheader("🎯 篩選結果 (09:20 自動掃描)")

# 範例表格呈現
example_data = {
    "股票代碼": ["2330 台積電", "2603 長榮", "3231 緯創"],
    "現價": [605, 155, 110],
    "今日振幅%": [4.2, 3.8, 5.1],
    "量能佔比%": [25.4, 18.2, 31.0],
    "分類標籤": ["🔥 強攻型 (A-1)", "🧱 大人型 (B-1)", "⚡ 動能型 (A-2)"]
}
df_display = pd.DataFrame(example_data)

# 讓表格更漂亮
st.dataframe(
    df_display.style.highlight_max(axis=0, subset=['今日振幅%', '量能佔比%']),
    use_container_width=True
)
