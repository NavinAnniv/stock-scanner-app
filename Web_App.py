import streamlit as st
import pandas as pd
import requests
import io
import yfinance as yf
import concurrent.futures
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Buffett Stock Scanner", layout="wide")

# --- SECTOR MAP ---
SECTOR_MAP = {
    'auto': 'auto', 'bank': 'bank', 'it': 'it', 'pharma': 'pharma',
    'fmcg': 'fmcg', 'metal': 'metal', 'realty': 'realty', 'energy': 'energy',
    'media': 'media', 'psu bank': 'psubank', 'private bank': 'privatebank',
    'financial services': 'financel', 'healthcare': 'healthcare',
    'consumer durables': 'consumerdurables', 'oil and gas': 'oilandgas'
}

# --- CACHING (Prevents re-scanning on every click) ---
@st.cache_data(ttl=600)  # Cache clears every 10 minutes automatically
def get_all_nifty_stocks():
    all_tickers = set()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # Progress bar for sector fetching
    progress_text = "Fetching Sector Lists from NSE..."
    my_bar = st.progress(0, text=progress_text)
    
    sectors = list(SECTOR_MAP.items())
    total = len(sectors)
    
    for i, (sector_name, slug) in enumerate(sectors):
        try:
            url = f"https://niftyindices.com/IndexConstituent/ind_nifty{slug}list.csv"
            response = requests.get(url, headers=headers)
            df = pd.read_csv(io.StringIO(response.text))
            
            symbol_col = next((col for col in df.columns if 'Symbol' in col), None)
            if symbol_col:
                symbols = df[symbol_col].tolist()
                for sym in symbols:
                    if "DUMMY" not in str(sym).upper():
                        all_tickers.add(f"{sym}.NS")
        except Exception:
            continue
        
        # Update progress
        my_bar.progress((i + 1) / total, text=f"Fetched {sector_name}...")
        
    my_bar.empty() # Clear bar when done
    return list(all_tickers)

def get_technical_levels(stock_obj):
    try:
        hist = stock_obj.history(period="1mo")
        if len(hist) < 14: return None, None, None

        hist['h-l'] = hist['High'] - hist['Low']
        hist['h-pc'] = abs(hist['High'] - hist['Close'].shift(1))
        hist['l-pc'] = abs(hist['Low'] - hist['Close'].shift(1))
        hist['tr'] = hist[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        atr = hist['tr'].tail(14).mean()
        
        current_close = hist['Close'].iloc[-1]
        
        # Stop = 2x ATR | Target = 4x ATR
        stop_loss = current_close - (2.0 * atr)
        target = current_close + (4.0 * atr)
        
        return round(stop_loss, 2), round(target, 2), round(atr, 2)
    except:
        return None, None, None

def analyze_single_stock(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        if not info or 'currentPrice' not in info: return None

        # Fundamentals
        price = info.get('currentPrice', 0)
        roe = info.get('returnOnEquity', 0)
        debt_eq = info.get('debtToEquity', 0)
        peg = info.get('pegRatio', float('nan'))
        pe = info.get('trailingPE', float('nan'))
        
        roe_pct = roe * 100 if roe else 0
        debt_ratio = debt_eq / 100 if debt_eq > 10 else debt_eq

        # Scoring
        score = 0
        if roe_pct > 15: score += 1
        if debt_ratio < 1.0: score += 1
        if pd.notnull(peg) and 0 < peg < 2.0: score += 1
        if pd.notnull(pe) and 0 < pe < 30: score += 1

        verdict = "Avoid"
        if score == 4: verdict = "STRONG BUY"
        elif score == 3: verdict = "Quality Buy"
        elif score == 2: verdict = "Watchlist"
        
        # Technicals (Only for good stocks)
        sl, tgt = "N/A", "N/A"
        if score >= 2:
            sl_val, tgt_val, _ = get_technical_levels(stock)
            if sl_val:
                sl, tgt = sl_val, tgt_val

        if score >= 2:
            return {
                "Ticker": symbol.replace('.NS', ''),
                "Price": price,
                "Score": f"{score}/4",
                "Verdict": verdict,
                "Stop Loss": sl,
                "Target": tgt,
                "Risk/Reward": "1:2",
                "PEG Ratio": round(peg, 2) if pd.notnull(peg) else "N/A",
                "ROE %": round(roe_pct, 1),
                "P/E": round(pe, 1) if pd.notnull(pe) else "N/A"
            }
        return None
    except:
        return None

# --- MAIN APP UI ---
st.title("📈 AI Stock Scanner: Buffett Strategy + Technicals")
st.markdown("""
**Strategy:** High ROE (>15%) + Low Debt (<1.0) + Fair Valuation.
**Exit Plan:** Stop Loss is 2x ATR. Target is 4x ATR.
""")

# Button to trigger scan
if st.button("🚀 Run Live Market Scan"):
    
    # 1. Get Tickers
    tickers = get_all_nifty_stocks()
    st.write(f"Found **{len(tickers)}** unique stocks across all sectors.")
    
    # 2. Analyze (with Spinner)
    results = []
    with st.spinner('Analyzing Fundamentals & Technicals... (This takes ~30 seconds)'):
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(analyze_single_stock, t) for t in tickers]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res:
                    results.append(res)
    
    # 3. Display Results
    if results:
        df = pd.DataFrame(results)
        
        # Sort logic: Score high -> PEG low
        # We need a helper column for sorting because "N/A" strings break sort
        df['Sort_PEG'] = pd.to_numeric(df['PEG Ratio'], errors='coerce').fillna(999)
        df = df.sort_values(by=["Score", "Sort_PEG"], ascending=[False, True]).drop(columns=['Sort_PEG'])

        # Separate Tables
        winners = df[df['Verdict'].isin(["STRONG BUY", "Quality Buy"])]
        watchlist = df[df['Verdict'] == "Watchlist"]

        st.subheader("🏆 Actionable Buy List")
        st.dataframe(winners, use_container_width=True, height=400)
        
        st.subheader("👀 Watchlist (Mixed Signals)")
        st.dataframe(watchlist, use_container_width=True)
        
    else:
        st.warning("No stocks matched the criteria.")