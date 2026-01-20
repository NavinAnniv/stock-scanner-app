import streamlit as st
import pandas as pd
import requests
import io
import yfinance as yf
import concurrent.futures
import time
import random

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

# --- 1. SESSION WITH BROWSER HEADERS (ANTI-BLOCKING) ---
def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive"
    })
    return session

# --- 2. ROBUST FETCH FUNCTION ---
@st.cache_data(ttl=3600)
def get_all_nifty_stocks():
    all_tickers = set()
    session = get_session()
    
    # Progress bar
    progress_text = "Fetching Sector Lists..."
    my_bar = st.progress(0, text=progress_text)
    
    sectors = list(SECTOR_MAP.items())
    for i, (sector_name, slug) in enumerate(sectors):
        try:
            url = f"https://niftyindices.com/IndexConstituent/ind_nifty{slug}list.csv"
            response = session.get(url, timeout=10)
            
            # Decode content manually if needed
            content = response.content.decode('utf-8')
            df = pd.read_csv(io.StringIO(content))
            
            symbol_col = next((col for col in df.columns if 'Symbol' in col), None)
            if symbol_col:
                symbols = df[symbol_col].tolist()
                for sym in symbols:
                    if "DUMMY" not in str(sym).upper():
                        all_tickers.add(f"{sym}.NS")
        except Exception:
            pass # Skip failed sectors silently
        
        my_bar.progress((i + 1) / len(sectors), text=f"Fetched {sector_name}...")
        time.sleep(0.1) # Tiny sleep to be polite
        
    my_bar.empty()
    return list(all_tickers)
'''
# --- 3. ANALYZE STOCK (With Retry Logic) ---
def analyze_single_stock(symbol):
    try:
        # Random sleep to prevent exact-timing blocks
        time.sleep(random.uniform(0.1, 0.5))
        
        # Create a Ticker object with our custom session
        session = get_session()
        stock = yf.Ticker(symbol, session=session)
        
        # Fast Info Fetch (avoids downloading history unless needed)
        info = stock.info
        
        # Check if data is valid (Yahoo returns empty dicts when blocked)
        if not info or 'currentPrice' not in info:
            return {"Ticker": symbol, "Error": "No Data/Blocked"}

        # Fundamentals
        price = info.get('currentPrice', 0)
        roe = info.get('returnOnEquity', 0)
        debt_eq = info.get('debtToEquity', 0)
        peg = info.get('pegRatio', float('nan'))
        pe = info.get('trailingPE', float('nan'))
        
        roe_pct = roe * 100 if roe else 0
        debt_ratio = debt_eq / 100 if debt_eq > 10 else debt_eq

        # --- SCORING LOGIC ---
        score = 0
        reasons = []
        
        # Rule 1: Quality (ROE > 12% - Relaxed slightly for robustness)
        if roe_pct > 12: 
            score += 1
            reasons.append("High ROE")
        
        # Rule 2: Safety (Debt/Eq < 1.5 - Relaxed slightly)
        if debt_ratio < 1.5: 
            score += 1
            reasons.append("Safe Debt")
        
        # Rule 3: Growth (PEG < 3 or NaN - Don't punish for missing data)
        if pd.isna(peg) or (0 < peg < 3.0): 
            score += 1
            reasons.append("Fair PEG")
            
        # Rule 4: Value (P/E < 40 - Adjusted for Indian Market premium)
        if pd.notnull(pe) and 0 < pe < 40: 
            score += 1
            reasons.append("Fair P/E")

        verdict = "Avoid"
        if score == 4: verdict = "STRONG BUY"
        elif score == 3: verdict = "Quality Buy"
        elif score == 2: verdict = "Watchlist"

        # --- TECHNICALS (Optional) ---
        # Only fetch history for good stocks to save bandwidth
        sl, tgt = "N/A", "N/A"
        if score >= 2:
            try:
                hist = stock.history(period="1mo")
                if not hist.empty and len(hist) > 14:
                    # Calculate ATR
                    hist['tr'] = np.maximum((hist['High'] - hist['Low']), 
                                          np.maximum(abs(hist['High'] - hist['Close'].shift(1)), 
                                                     abs(hist['Low'] - hist['Close'].shift(1))))
                    atr = hist['tr'].tail(14).mean()
                    sl = round(price - (2.0 * atr), 2)
                    tgt = round(price + (4.0 * atr), 2)
            except Exception:
                pass # Fail silently on technicals to keep the main result

        # Return Data
        return {
            "Ticker": symbol.replace('.NS', ''),
            "Price": price,
            "Score": f"{score}/4",
            "Verdict": verdict,
            "Stop Loss": sl,
            "Target": tgt,
            "PEG Ratio": round(peg, 2) if pd.notnull(peg) else "N/A",
            "ROE %": round(roe_pct, 1),
            "P/E": round(pe, 1) if pd.notnull(pe) else "N/A",
            "Raw_Score": score # Hidden column for sorting
        }

    except Exception as e:
        return {"Ticker": symbol, "Error": str(e)}
'''

# --- 3. ANALYZE STOCK (Fixed: Removed Session Override) ---
def analyze_single_stock(symbol):
    try:
        # Random sleep is still good to avoid hitting rate limits
        time.sleep(random.uniform(0.1, 0.5))
        
        # FIX: Do NOT pass a custom session. Let yfinance handle it internally.
        stock = yf.Ticker(symbol)
        
        # Fast Info Fetch
        info = stock.info
        
        # Check if data is valid
        if not info or 'currentPrice' not in info:
            return {"Ticker": symbol, "Error": "No Data/Blocked"}

        # Fundamentals
        price = info.get('currentPrice', 0)
        roe = info.get('returnOnEquity', 0)
        debt_eq = info.get('debtToEquity', 0)
        peg = info.get('pegRatio', float('nan'))
        pe = info.get('trailingPE', float('nan'))
        
        roe_pct = roe * 100 if roe else 0
        debt_ratio = debt_eq / 100 if debt_eq > 10 else debt_eq

        # --- SCORING LOGIC ---
        score = 0
        
        # Rule 1: Quality (ROE > 12%)
        if roe_pct > 12: score += 1
        
        # Rule 2: Safety (Debt/Eq < 1.5)
        if debt_ratio < 1.5: score += 1
        
        # Rule 3: Growth (PEG < 3 or NaN)
        if pd.isna(peg) or (0 < peg < 3.0): score += 1
            
        # Rule 4: Value (P/E < 40)
        if pd.notnull(pe) and 0 < pe < 40: score += 1

        verdict = "Avoid"
        if score == 4: verdict = "STRONG BUY"
        elif score == 3: verdict = "Quality Buy"
        elif score == 2: verdict = "Watchlist"

        # --- TECHNICALS ---
        sl, tgt = "N/A", "N/A"
        if score >= 2:
            try:
                hist = stock.history(period="1mo")
                if not hist.empty and len(hist) > 14:
                    hist['tr'] = np.maximum((hist['High'] - hist['Low']), 
                                          np.maximum(abs(hist['High'] - hist['Close'].shift(1)), 
                                                     abs(hist['Low'] - hist['Close'].shift(1))))
                    atr = hist['tr'].tail(14).mean()
                    sl = round(price - (2.0 * atr), 2)
                    tgt = round(price + (4.0 * atr), 2)
            except Exception:
                pass 

        return {
            "Ticker": symbol.replace('.NS', ''),
            "Price": price,
            "Score": f"{score}/4",
            "Verdict": verdict,
            "Stop Loss": sl,
            "Target": tgt,
            "PEG Ratio": round(peg, 2) if pd.notnull(peg) else "N/A",
            "ROE %": round(roe_pct, 1),
            "P/E": round(pe, 1) if pd.notnull(pe) else "N/A",
            "Raw_Score": score 
        }

    except Exception as e:
        return {"Ticker": symbol, "Error": str(e)}

import numpy as np # Ensure numpy is imported for ATR calc

# --- MAIN APP UI ---
st.title("📈 AI Stock Scanner: Robust Cloud Version")
st.markdown("Strategy: High ROE + Low Debt. **Optimized for Streamlit Cloud.**")

# Sidebar Controls
st.sidebar.header("Settings")
# Reduce workers to 2-4 for Cloud (prevents blocking)
workers = st.sidebar.slider("Parallel Workers (Keep Low on Cloud!)", 1, 10, 2)
show_debug = st.sidebar.checkbox("Show Debug Data (First 5 stocks)")

if st.button("🚀 Run Live Market Scan"):
    tickers = get_all_nifty_stocks()
    st.write(f"Found **{len(tickers)}** unique stocks. Scanning with {workers} workers...")
    
    results = []
    errors = []
    
    # Progress Bar
    scan_bar = st.progress(0, text="Analyzing...")
    
    # Parallel Execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(analyze_single_stock, t): t for t in tickers}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if "Error" in res:
                errors.append(res)
            elif res["Raw_Score"] >= 2: # Only save relevant ones
                results.append(res)
            
            completed += 1
            if completed % 5 == 0:
                scan_bar.progress(completed / len(tickers), text=f"Scanned {completed}/{len(tickers)}...")

    scan_bar.empty()

    # --- RESULTS DISPLAY ---
    if results:
        df = pd.DataFrame(results)
        # Sort by Score High -> Low
        df = df.sort_values(by=["Raw_Score", "ROE %"], ascending=[False, False])
        
        st.success(f"Found {len(df)} opportunities!")
        
        st.subheader("🏆 Top Picks (Score 3/4 & 4/4)")
        st.dataframe(df[df["Raw_Score"] >= 3].drop(columns=["Raw_Score"]), use_container_width=True)
        
        st.subheader("👀 Watchlist (Score 2/4)")
        st.dataframe(df[df["Raw_Score"] == 2].drop(columns=["Raw_Score"]), use_container_width=True)
    else:
        st.warning("No stocks matched the criteria. (Or Yahoo blocked the requests).")

    # --- DEBUG SECTION ---
    if show_debug and errors:
        st.write("---")
        st.error("Debug Info (Failed/Blocked Stocks):")
        st.write(pd.DataFrame(errors).head(10))
