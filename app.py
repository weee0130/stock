import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- 1. 技術指標計算 ---
def calculate_indicators(df, window=20, std_dev=2):
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['Close'])
        # 布林帶
        df['MB'] = df['Close'].rolling(window=window).mean()
        df['STD'] = df['Close'].rolling(window=window).std()
        df['UP'] = df['MB'] + (std_dev * df['STD'])
        df['DN'] = df['MB'] - (std_dev * df['STD'])
        df['bandwidth'] = (df['UP'] - df['DN']) / df['MB']
        # 其他指標
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD'] - df['Signal']
        return df
    except:
        return None

# --- 2. 靜態上市股票清單 (代碼 + 中文名稱) ---
def get_static_tw_stocks_with_names():
    # 此處維持之前的 900+ 檔資料庫...
    # (為了節省篇幅，這部分代碼建議保留上一版的 stock_db 內容)
    stock_db = {
        "1101.TW": "台泥", "1102.TW": "亞泥", "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科",
        "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海", "2881.TW": "富邦金", "2882.TW": "國泰金"
        # ...其餘 900 檔... (請將上一版的完整字典貼於此)
    }
    # 這裡我先用精簡版演示，請務必把上一版的完整清單貼回來
    return stock_db

# --- 3. 核心選股邏輯 (進化版) ---
def scan_logic(symbol, name, params):
    try:
        df = yf.download(symbol, period="180d", interval="1d", progress=False, threads=False, timeout=10)
        if df is None or len(df) < (params['settle_days'] + 20):
            return None
        
        df = calculate_indicators(df)
        if df is None: return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # 盤整期數據
        history_bw = df['bandwidth'].iloc[-(params['settle_days']+1):-1]
        
        # --- 邏輯分支 ---
        if params['strict_mode']:
            # 嚴格模式：找出區間內的「最大值」，必須小於門檻
            check_val = float(history_bw.max())
            val_label = "區間最大帶寬"
        else:
            # 一般模式：看平均值
            check_val = float(history_bw.mean())
            val_label = "區間平均帶寬"
        
        # 條件判斷
        price_break = float(last['Close']) > float(last['UP'])
        vol_ok = (float(last['Volume']) > (float(last['Vol_MA5']) * params['vol_ratio'])) if params['use_vol'] else True
        open_ok = (float(last['UP']) > float(prev['UP']) and float(last['DN']) < float(prev['DN'])) if params['use_open'] else True
        macd_ok = float(last['Hist']) > 0 if params['use_macd'] else True

        if check_val < (params['bw_limit']/100) and price_break and vol_ok and open_ok and macd_ok:
            return {
                "代號": symbol, "名稱": name, "純代碼": symbol.split('.')[0],
                "現價": round(float(last['Close']), 2),
                "量增倍數": round(float(last['Volume']/last['Vol_MA5']), 2),
                "數值": f"{round(check_val*100, 2)}%",
                "標籤": val_label,
                "df": df
            }
    except:
        pass
    return None

# --- 4. Streamlit UI ---
st.set_page_config(page_title="台股長週期選股系統", layout="wide")
st.title("🏹 台股「長週期橫盤突破」量化篩選系統")

name_map = get_static_tw_stocks_with_names()
total_listed = len(name_map)

with st.sidebar:
    st.header("⚙️ 盤整參數")
    bw_limit = st.slider("帶寬門檻 (%)", 3.0, 15.0, 10.0)
    settle_days = st.slider("盤整交易日", 5, 90, 20)
    
    # 核心新功能：嚴格模式開關
    strict_mode = st.toggle("開啟嚴格模式", value=True, help="開啟後，盤整期間『每一天』的帶寬都必須小於門檻。")
    
    st.divider()
    st.header("🛡️ 強度過濾")
    use_vol = st.toggle("帶量突破", value=True)
    vol_ratio = st.slider("放量倍數", 1.0, 5.0, 1.5)
    use_open = st.toggle("布林張口", value=True)
    use_macd = st.toggle("MACD 紅柱", value=True)
    st.divider()
    stock_limit = st.number_input(f"掃描數量", 1, total_listed, 500)

if st.button("🚀 開始深度精選掃描"):
    target_list = list(name_map.keys())[:stock_limit]
    hits = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    params = {
        "bw_limit": bw_limit, "settle_days": settle_days, 
        "use_vol": use_vol, "vol_ratio": vol_ratio, 
        "use_open": use_open, "use_macd": use_macd,
        "strict_mode": strict_mode
    }
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(scan_logic, s, name_map[s], params) for s in target_list]
        for i, future in enumerate(futures):
            res = future.result()
            if res: hits.append(res)
            progress_bar.progress((i + 1) / len(target_list))
            status_text.text(f"掃描進度： {i+1} / {len(target_list)}")

    if hits:
        st.success(f"🎉 找到 {len(hits)} 檔符合條件標的！")
        for hit in hits:
            with st.expander(f"💎 {hit['代號']} {hit['名稱']} | {hit['標籤']}: {hit['數值']}"):
                # (其餘連結與繪圖代碼維持原樣...)
                st.write(f"當前價格: {hit['現價']} | 量增倍數: {hit['量增倍數']}")
                # 此處略過 Plotly 繪圖代碼，請直接沿用上一版
    else:
        st.warning("查無標的，請放寬參數（例如增加帶寬門檻至 12%）。")
