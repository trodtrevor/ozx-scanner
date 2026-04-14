import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import time
import os
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="OZx Day Trader Scanner", layout="wide")
st.title("🚀 OZx Day Trader Scanner — $30–$350 NYSE")
st.caption("Your custom low-volume big-move scanner • Auto-refresh enabled • Built exactly to your specs")

# ====================== CONFIG ======================
API_KEY = os.getenv("POLYGON_API_KEY") or st.secrets.get("POLYGON_API_KEY")
if not API_KEY:
    st.error("🚨 Add your POLYGON_API_KEY in Streamlit Secrets (Settings → Secrets)")
    st.stop()

client = RESTClient(API_KEY)

PRICE_RANGES = {
    "Low": (30, 136),
    "Mid": (137, 243),
    "High": (244, 350)
}

MIN_AVG_DOLLAR_MOVE = 5.0
DAYS_FOR_ATR = 20
CATALYST_KEYWORDS = ["earnings", "FDA", "merger", "acquisition", "contract", "short squeeze", "Hormuz", "oil", "Iran", "ceasefire"]

FED_STANCE = "holding 3.5-3.75% with hawkish tilt due to oil inflation"
GEOPOL = "high - Iran/Hormuz oil shock; energy names favored"

# ====================== CORE FUNCTIONS ======================
def get_historical_data(ticker, days=DAYS_FOR_ATR):
    try:
        end = datetime.now()
        start = end - timedelta(days=days + 10)
        aggs = client.get_aggs(ticker, 1, "day", from_=start.strftime("%Y-%m-%d"), to=end.strftime("%Y-%m-%d"), limit=50000)
        df = pd.DataFrame([a.__dict__ for a in aggs])
        if df.empty:
            return None
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp')
        df['prev_close'] = df['close'].shift(1)
        df['tr'] = pd.DataFrame({
            'hl': df['high'] - df['low'],
            'hc': abs(df['high'] - df['prev_close']),
            'lc': abs(df['low'] - df['prev_close'])
        }).max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()
        df['daily_dollar_move'] = df['high'] - df['low']
        avg_dollar = df['daily_dollar_move'].mean()
        avg_vol = df['volume'].mean()
        latest_price = df['close'].iloc[-1]
        latest_dollar_move = df['daily_dollar_move'].iloc[-1]
        latest_vol = df['volume'].iloc[-1]
        rvol = latest_vol / avg_vol if avg_vol > 0 else 0
        move_efficiency = (latest_dollar_move / avg_dollar) / (rvol if rvol > 0 else 1)
        move_per_million = avg_dollar / (avg_vol / 1_000_000) if avg_vol > 0 else 0
        return {
            'price': latest_price,
            'avg_$move': avg_dollar,
            'move_per_million_shares': move_per_million,
            'rvol': rvol,
            'move_efficiency': move_efficiency,
            'atr': df['atr'].iloc[-1]
        }
    except:
        return None

def get_recent_news_score(ticker):
    try:
        news = client.list_ticker_news(ticker, limit=10)
        score = 0
        for item in news:
            title = (item.title or "").lower()
            if any(kw in title for kw in CATALYST_KEYWORDS):
                score += 2
            if "earnings" in title:
                score += 3
        return min(score, 10)
    except:
        return 0

def analyze_stock(ticker):
    try:
        details = client.get_ticker_details(ticker)
        if not details:
            return None
        price = details.weighted or 0
        if not any(low <= price <= high for low, high in PRICE_RANGES.values()):
            return None
    except:
        return None
    
    hist = get_historical_data(ticker)
    if not hist or hist['avg_$move'] < MIN_AVG_DOLLAR_MOVE:
        return None
    
    news_score = get_recent_news_score(ticker)
    vol_score = (hist['avg_$move'] / hist['price']) * 100
    composite = (
        hist['avg_$move'] * 0.4 +
        hist['move_per_million_shares'] * 0.25 +      # Your key "big move on low volume" metric
        hist['move_efficiency'] * 0.15 +
        vol_score * 0.1 +
        news_score * 2 +
        (10 if "energy" in (details.sector or "").lower() else 0)
    )
    
    return {
        'ticker': ticker,
        'price': round(hist['price'], 2),
        'avg_$move': round(hist['avg_$move'], 2),
        'move_per_million_shares': round(hist['move_per_million_shares'], 2),
        '%_move': round(vol_score, 2),
        'RVOL': round(hist['rvol'], 2),
        'efficiency': round(hist['move_efficiency'], 2),
        'news_score': news_score,
        'composite_score': round(composite, 1),
        'notes': f"Low-vol big-move: {hist['move_per_million_shares']:.1f} | Fed: {FED_STANCE} | Geo: {GEOPOL}"
    }

# ====================== CSV UPLOAD & ANALYSIS ======================
uploaded_file = st.file_uploader("Upload your Finviz export CSV (Price $30–$350, high volatility, volume >500k)", type="csv")

if "full_results" not in st.session_state:
    st.session_state.full_results = pd.DataFrame()

refresh_button = st.button("🔄 Refresh Now", type="primary", use_container_width=True)

if refresh_button or uploaded_file is not None:
    with st.spinner("Scanning stocks across all three ranges... (this takes 1–4 minutes)"):
        if uploaded_file is not None:
            df_candidates = pd.read_csv(uploaded_file)
            if 'Ticker' not in df_candidates.columns:
                st.error("CSV must have a 'Ticker' column from Finviz.")
                st.stop()
            tickers = df_candidates['Ticker'].tolist()
        else:
            st.warning("Please upload a Finviz CSV to run a full scan.")
            st.stop()
        
        results = []
        def process(t):
            return analyze_stock(t)
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            for res in executor.map(process, tickers):
                if res:
                    results.append(res)
        
        st.session_state.full_results = pd.DataFrame(results)
        st.success(f"✅ Scanned {len(results)} qualifying stocks at {datetime.now().strftime('%H:%M:%S')}")

# ====================== THREE TABS ======================
tab1, tab2, tab3 = st.tabs(["Low: $30–$136", "Mid: $137–$243", "High: $244–$350"])

for tab, (name, (low, high)) in zip([tab1, tab2, tab3], PRICE_RANGES.items()):
    with tab:
        st.subheader(f"{name} Range — ${low}–${high}")
        if st.session_state.full_results.empty:
            st.info("Upload Finviz CSV and click Refresh Now to see results.")
        else:
            subset = st.session_state.full_results[
                (st.session_state.full_results['price'] >= low) &
                (st.session_state.full_results['price'] <= high)
            ].copy()
            if subset.empty:
                st.info("No stocks in this range yet.")
            else:
                subset = subset.sort_values("composite_score", ascending=False)
                st.dataframe(subset[['ticker', 'price', 'avg_$move', 'move_per_million_shares', '%_move', 'RVOL', 'efficiency', 'news_score', 'composite_score', 'notes']], use_container_width=True, hide_index=True)
                st.download_button(f"Download {name} CSV", subset.to_csv(index=False), f"ozx_{name.lower()}_scan.csv", "text/csv")

st.caption("Pro tip: Export a fresh Finviz CSV anytime (Price 30-350 + high volatility + volume >500k) and upload it here. The app auto-sorts by your low-volume big-move criteria.")
