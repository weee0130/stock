import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from concurrent.futures import ThreadPoolExecutor

# --- 1. 技術指標計算 ---
def calculate_indicators(df, window=20, std_dev=2):
    try:
        # 處理 yfinance 可能產生的 MultiIndex 欄位問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['Close'])

        # 布林通道 (20MA)
        df['MB'] = df['Close'].rolling(window=window).mean()
        df['STD'] = df['Close'].rolling(window=window).std()
        df['UP'] = df['MB'] + (std_dev * df['STD'])
        df['DN'] = df['MB'] - (std_dev * df['STD'])
        df['bandwidth'] = (df['UP'] - df['DN']) / df['MB']

        # 成交量均線 (5日)
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()

        # MACD (12, 26, 9)
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD'] - df['Signal']

        return df
    except:
        return None

# --- 2. 抓取「上市股票」清單 (限定 4 碼個股) ---
@st.cache_data(ttl=3600)
def get_tw_listed_stocks():
    try:
        # 只抓上市 (Mode=2)
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res = requests.get(url)
        df = pd.read_html(res.text)[0]
        df.columns = df.iloc[0]
        df = df.iloc[2:]
        
        codes = []
        full_space = '\u3000' # 避開 f-string 內的反斜線
        
        for item in df['有價證券代號及名稱']:
            item_str = str(item)
            code = item_str.split(full_space)[0].strip()
            # 只要是 4 位數純數字，就是上市個股
            if len(code) == 4 and code.isdigit():
                codes.append(f"{code}.TW")
        return codes
    except Exception as e:
        st.error(f"上市清單抓取失敗: {e}")
        return ["2330.TW", "2317.TW", "2454.TW", "2382.TW", "3231.TW"]

# --- 3. 核心選股邏輯 (橫盤 + 糾結 + 突破 + 量增 + 張口 + MACD) ---
def scan_logic(symbol, params):
    try:
        # 下載 100 天日線 (加長天數以利指標計算)
        df = yf.download(symbol, period="100d", interval="1d", progress=False, threads=False, timeout=10)
        if df is None or len(df) < 40: return None
        
        df = calculate_indicators(df)
        if df is None: return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. 壓縮天數判斷：過去 N 天平均帶寬
        history_bw = df['bandwidth'].iloc[-(params['settle_days']+1):-1]
        avg_bw = float(history_bw.mean())
        
        # 2. 突破判斷：今日收盤 > 上軌
        price_break = float(last['Close']) > float(last['UP'])

        # 3. 選項：帶量突破 (今日量 > 5日均量 * 倍數)
        vol_ok = True
        if params['use_vol']:
            vol_ok = float(last['Volume']) > (float(last['Vol_MA5']) * params['vol_ratio'])

        # 4. 選項：布林張口 (上軌往上 且 下軌往下)
        open_ok = True
        if params['use_open']:
            open_ok = float(last['UP']) > float(prev['UP']) and float(last['DN']) < float(prev['DN'])

        # 5. 選項：MACD 強勢 (紅柱 > 0)
        macd_ok = True
        if params['use_macd']:
            macd_ok = float(last['Hist']) > 0

        # 最終組合篩選
        if avg_bw < (params['bw_limit']/100) and price_break and vol_ok and open_ok and macd_ok:
            return {
                "symbol": symbol,
                "price": round(float(last['Close']), 2),
                "vol_ratio": round(float(last['Volume']/last['Vol_MA5']), 2),
                "avg_bw": f"{round(avg_bw*100, 2)}%",
                "df": df
            }
    except:
        pass
    return None

# --- 4. Streamlit UI 介面 ---
st.set_page_config(page_title="台股上市標的精選器", layout="wide")
st.title("🏹 台股上市股票「全能突破」深度篩選")
st.markdown("專注於**上市市場**中悶了很久、均線合一、今日帶量且指標強勢的標的。")

with st.sidebar:
    st.header("⚙️ 篩選策略參數")
    bw_limit = st.slider("盤整期帶寬 (%)", 3.0, 15.0, 10.0, help="數值越小盤整越窄")
    settle_days = st.slider("維持窄幅天數", 5, 20, 10, help="布林通道需要維持窄幅的天數")
    
    st.divider()
    st.header("🛡️ 進階過濾開關")
    use_vol = st.toggle("帶量突破 (成交量放大)", value=True)
    vol_ratio = st.slider("放量倍數", 1.0, 3.0, 1.5) if use_vol else 1.0
    
    use_open = st.toggle("布林張口 (喇叭口開花)", value=True)
    use_macd = st.toggle("MACD 強勢 (紅柱轉正)", value=True)
    
    st.divider()
    stock_limit = st.number_input("掃描上市股票數量 (最高 1500)", 10, 1500, 1500)

params = {
    "bw_limit": bw_limit, "settle_days": settle_days, "use_vol": use_vol,
    "vol_ratio": vol_ratio, "use_open": use_open, "use_macd": use_macd
}

if st.button("🚀 開始全上市市場大掃描"):
    all_listed = get_tw_listed_stocks()
    target_list = all_listed[:stock_limit]
    
    hits = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 使用 ThreadPoolExecutor 同步下載提升效率
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(scan_logic, s, params) for s in target_list]
        for i, future in enumerate(futures):
            res = future.result()
            if res: hits.append(res)
            progress_bar.progress((i + 1) / len(target_list))
            status_text.text(f"掃描上市進度： {i+1}/{len(target_list)}")

    st.divider()
    if hits:
        st.success(f"🎉 掃描完成！在上市市場中找到 {len(hits)} 檔精選標的。")
        for hit in hits:
            with st.expander(f"💎 {hit['symbol']} | 價: {hit['price']} | 量增: {hit['vol_ratio']}倍 | 盤整度: {hit['avg_bw']}"):
                df_p = hit['df'].tail(60)
                # K線 + MACD 子圖
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                # K線、布林與均線
                fig.add_trace(go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'], name="K線"), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_p.index, y=df_p['UP'], name="上軌", line=dict(color='red', width=1.5)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_p.index, y=df_p['DN'], name="下軌", line=dict(color='blue', width=1.5)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df_p.index, y=df_p['MB'], name="20MA", line=dict(color='orange', dash='dash')), row=1, col=1)
                
                # MACD 柱狀體
                colors = ['red' if val > 0 else 'green' for val in df_p['Hist']]
                fig.add_trace(go.Bar(x=df_p.index, y=df_p['Hist'], name="MACD柱狀體", marker_color=colors), row=2, col=1)
                
                fig.update_layout(xaxis_rangeslider_visible=False, height=600, margin=dict(l=10, r=10, b=10, t=30), hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("☹️ 目前上市市場沒有符合所有嚴格條件的股票。建議將「帶寬%」調大（如 12-15%）或關閉部分過濾開關後重新掃描。")