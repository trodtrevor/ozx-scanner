import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient
import time
import os
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="OZx Day Trader Scanner", layout="wide")
st.title("🚀 OZx Day Trader Scanner — $30–$520 NYSE")
st.caption("Your exact volume-price imbalance metric • Broad NYSE scan • 3 tabs")

API_KEY = os.getenv("POLYGON_API_KEY") or st.secrets.get("POLYGON_API_KEY")
if not API_KEY:
    st.error("Add your POLYGON_API_KEY in Streamlit Secrets")
    st.stop()

client = RESTClient(API_KEY)

PRICE_RANGES = {
    "Low": (30, 136),
    "Mid": (137, 243),
    "High": (244, 520)
}

DEFAULT_TICKERS = ["AMD","NVDA","TSLA","AAPL","GOOGL","MSFT","AMZN","META","NFLX","AVGO","ADBE","CRM","INTC","QCOM","TXN","MU","AMAT","KLAC","LRCX","ASML","PLTR","CRWD","PANW","ZS","NET","DDOG","MDB","HUBS","NOW","TEAM","WDAY","SHOP","SQ","PYPL","COIN","HOOD","RBLX","U","PATH","SNAP","PINS","SPOT","RIVN","LCID","NIO","XPEV","LI","ARM","SMCI","DELL","WDC","STX","NTAP","PSTG","ENVX","UPST","ASTS","SERV","ALGM","CCJ","FCX","VALE","X","CLF","NUE","STLD","MT","RS","CMC","ATI","HRI","URI","PWR","ETR","CEG","VST","NRG","AES","GEV","FLR","J","ACHR","JOBY","KTOS","RKLB","SPCE","LUNR","SMR","OKLO","BWXT","LEU","UEC","URG","DNN","UUUU","PLUG","BE","RUN","ENPH","SEDG","FSLR","NOVA","MAXN","SHLS","ARRY","CSIQ","JKS","DQ","SPWR"]

def get_historical_data(ticker):
    try:
        end = datetime.now()
        start = end - timedelta(days=30)
        aggs = client.get_aggs(ticker, 1, "day", from_=start.strftime("%Y-%m-%d"), to=end.strftime("%Y-%m-%d"), limit=50000)
        df = pd.DataFrame([a.__dict__ for a in aggs])
        if df.empty: return None
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp')
        df['prev_close'] = df['close'].shift(1)
        df['tr'] = pd.DataFrame({'hl': df['high'] - df['low'], 'hc': abs(df['high'] - df['prev_close']), 'lc': abs(df['low'] - df['prev_close'])}).max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()
        df['daily_dollar_move'] = df['high'] - df['low']
        
        avg_dollar = df['daily_dollar_move'].mean()
        avg_vol = df['volume'].mean()
        latest_price = df['close'].iloc[-1]
        latest_dollar_move = df['daily_dollar_move'].iloc[-1]
        latest_vol = df['volume'].iloc[-1]
        rvol = latest_vol / avg_vol if avg_vol > 0 else 0
        
        price_completion = latest_dollar_move / avg_dollar if avg_dollar > 0 else 0
        volume_completion = latest_vol / avg_vol if avg_vol > 0 else 0
        
        if 0.40 <= volume_completion <= 0.85 and price_completion < volume_completion * 1.1:
            remaining_potential = (1 - price_completion) / max(1 - volume_completion, 0.01)
        else:
            remaining_potential = 0
        
        move_per_million = avg_dollar / (avg_vol / 1_000_000) if avg_vol > 0 else 0
        
        return {
            'price': latest_price,
            'avg_$move': avg_dollar,
            'move_per_million_shares': move_per_million,
            'remaining_potential': remaining_potential,
            'volume_completion_%': round(volume_completion*100, 1),
            'price_completion_%': round(price_completion*100, 1)
        }
    except:
        return None

def analyze_stock(ticker):
    try:
        details = client.get_ticker_details(ticker)
        if not details: return None
        price = details.weighted or 0
        if not any(low <= price <= high for low, high in PRICE_RANGES.values()):
            return None
    except:
        return None
    
    hist = get_historical_data(ticker)
    if not hist or hist['avg_$move'] < 5.0:
        return None
    
    composite = hist['avg_$move'] * 0.4 + hist['move_per_million_shares'] * 0.3 + hist['remaining_potential'] * 0.3
    
    return {
        'ticker': ticker,
        'price': round(hist['price'], 2),
        'avg_$move': round(hist['avg_$move'], 2),
        'move_per_million_shares': round(hist['move_per_million_shares'], 2),
        'remaining_potential': round(hist['remaining_potential'], 2),
        'volume_completion_%': hist['volume_completion_%'],
        'price_completion_%': hist['price_completion_%'],
        'composite_score': round(composite, 1)
    }

if st.button("🚀 Run Automatic Quick Scan ($30–$520 NYSE)", type="primary", use_container_width=True):
    with st.spinner("Scanning..."):
        results = []
        def process(t):
            return analyze_stock(t)
        with ThreadPoolExecutor(max_workers=8) as executor:
            for res in executor.map(process, DEFAULT_TICKERS):
                if res:
                    results.append(res)
        st.session_state.full_results = pd.DataFrame(results)
        st.success(f"✅ Scan complete! {len(results)} stocks ranked.")

tab1, tab2, tab3 = st.tabs(["Low: $30–$136", "Mid: $137–$243", "High: $244–$520"])

for tab, (name, (low, high)) in zip([tab1, tab2, tab3], PRICE_RANGES.items()):
    with tab:
        st.subheader(f"{name} Range")
        if "full_results" not in st.session_state or st.session_state.full_results.empty:
            st.info("Click the big button above to run the scan.")
        else:
            subset = st.session_state.full_results[(st.session_state.full_results['price'] >= low) & (st.session_state.full_results['price'] <= high)].copy()
            if subset.empty:
                st.info("No stocks in this range.")
            else:
                subset = subset.sort_values("composite_score", ascending=False)
                st.dataframe(subset[['ticker', 'price', 'avg_$move', 'move_per_million_shares', 'remaining_potential', 'volume_completion_%', 'price_completion_%', 'composite_score']], use_container_width=True, hide_index=True)
                st.download_button(f"Download {name} CSV", subset.to_csv(index=False), f"ozx_{name.lower()}_scan.csv", "text/csv")

st.caption("Scans $30–$520 NYSE stocks using your exact Pier OZX volume-price imbalance metric.")
EOF
