import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from concurrent.futures import ThreadPoolExecutor
import urllib3
from datetime import datetime

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 技術指標計算 ---
def calculate_indicators(df, window=20, std_dev=2):
    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['Close'])

        df['MB'] = df['Close'].rolling(window=window).mean()
        df['STD'] = df['Close'].rolling(window=window).std()
        df['UP'] = df['MB'] + (std_dev * df['STD'])
        df['DN'] = df['MB'] - (std_dev * df['STD'])
        df['bandwidth'] = (df['UP'] - df['DN']) / df['MB']
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD'] - df['Signal']

        return df
    except:
        return None

# --- 2. 抓取「上市股票」清單 (含代碼名稱對照) ---
@st.cache_data(ttl=3600)
def get_tw_listed_stocks_with_names():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, verify=False, timeout=20)
        res.encoding = 'big5'
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[2:]
        
        name_map = {}
        full_space = '\u3000'
        
        for item in df['有價證券代號及名稱']:
            item_str = str(item)
            if full_space in item_str:
                parts = item_str.split(full_space)
                code = parts[0].strip()
                name = parts[1].strip()
                if len(code) == 4 and code.isdigit():
                    name_map[f"{code}.TW"] = name
                    
        return name_map
    except Exception as e:
        return {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科"}

# --- 3. 核心選股邏輯 ---
def scan_logic(symbol, name, params):
    try:
        df = yf.download(symbol, period="180d", interval="1d", progress=False, threads=False, timeout=10)
        if df is None or len(df) < (params['settle_days'] + 20): return None
        
        df = calculate_indicators(df)
        if df is None: return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]

        history_bw = df['bandwidth'].iloc[-(params['settle_days']+1):-1]
        avg_bw = float(history_bw.mean())
        price_break = float(last['Close']) > float(last['UP'])

        vol_ok = (float(last['Volume']) > (float(last['Vol_MA5']) * params['vol_ratio'])) if params['use_vol'] else True
        open_ok = (float(last['UP']) > float(prev['UP']) and float(last['DN']) < float(prev['DN'])) if params['use_open'] else True
        macd_ok = float(last['Hist']) > 0 if params['use_macd'] else True

        if avg_bw < (params['bw_limit']/100) and price_break and vol_ok and open_ok and macd_ok:
            return {
                "代號": symbol,
                "名稱": name,
                "純代碼": symbol.split('.')[0],
                "現價": round(float(last['Close']), 2),
                "量增倍數": round(float(last['Volume']/last['Vol_MA5']), 2),
                "壓縮帶寬": f"{round(avg_bw*100, 2)}%",
                "df": df
            }
    except:
        pass
    return None

# --- 4. Streamlit UI ---
st.set_page_config(page_title="台股長週期壓縮篩選器 (專業版)", layout="wide")
st.title("🏹 台股「長週期橫盤突破」量化篩選系統")
st.caption("自動過濾盤整 90 交易日、帶量張口且 MACD 強勢之上市個股")

with st.sidebar:
    st.header("⚙️ 盤整參數 (交易日)")
    bw_limit = st.slider("盤整期帶寬 (%)", 3.0, 15.0, 10.0)
    settle_days = st.slider("維持窄幅交易日", 5, 90, 20)
    
    st.divider()
    st.header("🛡️ 強度過濾開關")
    use_vol = st.toggle("帶量突破", value=True)
    vol_ratio = st.slider("放量倍數", 1.0, 5.0, 1.5)
    use_open = st.toggle("布林張口", value=True)
    use_macd = st.toggle("MACD 紅柱", value=True)
    
    st.divider()
    stock_limit = st.number_input("掃描上市股票數量", 10, 1500, 1500)

if st.button("🚀 開始深度精選掃描"):
    name_map = get_tw_listed_stocks_with_names()
    target_list = list(name_map.keys())[:stock_limit]
    
    hits = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    params = {
        "bw_limit": bw_limit, "settle_days": settle_days, 
        "use_vol": use_vol, "vol_ratio": vol_ratio, 
        "use_open": use_open, "use_macd": use_macd
    }
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 將名稱也傳入 scan_logic
        futures = [executor.submit(scan_logic, s, name_map[s], params) for s in target_list]
        for i, future in enumerate(futures):
            res = future.result()
            if res: hits.append(res)
            progress_bar.progress((i + 1) / len(target_list))
            status_text.text(f"掃描進度： {i+1}/{len(target_list)}")

    if hits:
        st.success(f"🎉 找到 {len(hits)} 檔符合條件標的！")
        
        # 製作下載清單
        download_df = pd.DataFrame(hits).drop(columns=['df'])
        csv = download_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載篩選清單 (含名稱與大戶連結)",
            data=csv,
            file_name=f"stock_scan_{datetime.now().strftime('%Y%m%d')}.csv",
            mime='text/csv'
        )

        for hit in hits:
            # 修改 Expand 標題，增加中文名稱
            with st.expander(f"💎 {hit['代號']} {hit['名稱']} | 價: {hit['現價']} | 盤整帶寬: {hit['壓縮帶寬']}"):
                col1, col2, col3 = st.columns(3)
                with col1: st.link_button(f"📊 {hit['名稱']} 大戶持股", f"https://www.wantgoo.com/stock/{hit['純代碼']}/major-holders")
                with col2: st.link_button(f"🕵️ {hit['名稱']}-籌碼分佈", f"https://statementdog.com/analysis/{hit['純代碼']}/equity-distribution")
                with col3: st.link_button(f"📰 {hit['名稱']}-Yahoo新聞", f"https://tw.stock.yahoo.com/quote/{hit['代號']}")
                
                df_p = hit['df'].tail(120)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'], name="K線"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_p.index, y=df_p['UP'], name="上軌", line=dict(color='red', width=1.5)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_p.index, y=df_p['DN'], name="下軌", line=dict(color='blue', width=1.5)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_p.index, y=df_p['MB'], name="20MA", line=dict(color='orange', dash='dash')), row=1, col=1)
                
                colors = ['red' if val > 0 else 'green' for val in df_p['Hist']]
                fig.add_trace(go.Bar(x=df_p.index, y=df_p['Hist'], name="MACD", marker_color=colors), row=2, col=1)
                
                fig.update_layout(xaxis_rangeslider_visible=False, height=600, margin=dict(l=10, r=10, b=10, t=30), hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("查無標的，請放寬參數或增加掃描量。")
