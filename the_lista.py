import yfinance as yf
import pandas as pd
import numpy as np
import time
import streamlit as st

# 1. PAGE CONFIGURATION (Must be the first Streamlit command)
st.set_page_config(page_title="The Lista", layout="wide")
pd.set_option('display.width', 360)

# 2. VARIABLES
history_period = '3y'
history_interval = '1d'
framesize = 20
bollinger_mult = 2.5

# FIX 1: Removed erroneous leading space before 'tickers'
tickers = [
    "AALLON.HE", "ADMCM.HE", "ADMIN.HE", "AIFORIA.HE", "ALEX.HE", "ARVOSK.HE"
]


# 3. DATA FETCHING FUNCTIONS (Cached for 1 hour to ensure fresh prices)
@st.cache_data(ttl=3600)
def fetchMasterData(tickers_list, h_period, h_interval):
    df = pd.DataFrame()
    for ticker_symbol in tickers_list:
        oTicker = yf.Ticker(ticker_symbol)
        dfHistory = oTicker.history(period=h_period, interval=h_interval).add_prefix(ticker_symbol + "_")
        
        if not dfHistory.empty:
            df = df.merge(dfHistory, how='outer', left_index=True, right_index=True)
            
        time.sleep(0.5) # Pause to prevent rate limits
    return df
    
def calculateMetrics(df, tickers_list, f_size, b_mult):
    dfTmp = pd.DataFrame()
    for ticker in tickers_list:
        dfTmp[ticker + '_SMA'] = df[ticker + '_Close'].rolling(window=f_size).mean()
        dfTmp[ticker + '_SD'] = df[ticker + '_Close'].rolling(window=f_size).std()
        dfTmp[ticker + '_BOLLINGER_U'] = dfTmp[ticker + '_SMA'] + (b_mult * dfTmp[ticker + '_SD'])
        dfTmp[ticker + '_BOLLINGER_L'] = dfTmp[ticker + '_SMA'] - (b_mult * dfTmp[ticker + '_SD'])
    return df.merge(dfTmp, how='inner', left_index=True, right_index=True)

@st.cache_data(ttl=3600)
def get_stock_info(tickers_list, _df_hist):
    info_df = pd.DataFrame(columns = ["Name @PreviousClose", "ROE", "PE", "PB", "DIV", "BBPos"])
    
    for ticker_symbol in tickers_list:
        oTicker = yf.Ticker(ticker_symbol)
        
        try:
            info = oTicker.info
        except Exception:
            info = {}
            
        prev_close = info.get("previousClose", np.nan)
        sma = _df_hist[ticker_symbol + "_SMA"].iloc[-1] if ticker_symbol + "_SMA" in _df_hist else np.nan
        boll_l = _df_hist[ticker_symbol + "_BOLLINGER_L"].iloc[-1] if ticker_symbol + "_BOLLINGER_L" in _df_hist else np.nan
        
        bbpos = np.nan
        if not pd.isna(prev_close) and not pd.isna(sma) and not pd.isna(boll_l) and (sma - boll_l) != 0:
             bbpos = (prev_close - sma) / (sma - boll_l)

        info_df.loc[ticker_symbol] = [
            info.get("shortName", ticker_symbol) + " @" + str(prev_close),
            info.get("returnOnEquity", np.nan),
            info.get("trailingPE", np.nan),
            info.get("priceToBook", np.nan),
            info.get("trailingAnnualDividendYield", np.nan),
            bbpos
        ]
        
        time.sleep(0.5) # Pause to prevent rate limits
    return info_df

# 4. EXECUTE DATA FETCHING
dfHist = fetchMasterData(tickers, history_period, history_interval)
dfHist = calculateMetrics(dfHist.copy(deep=True), tickers, framesize, bollinger_mult)
dfInfo = get_stock_info(tickers, dfHist)

# 5. CALCULATE RANKINGS
metrics = {"ROE": False, "DIV": False}
for col, ascend in metrics.items():
    rank_col = f"{col}_Rank"
    dfInfo[rank_col] = (dfInfo[col].rank(method="min", ascending=ascend, na_option="bottom").astype(int))

pe_for_rank = dfInfo['PE'].where(dfInfo['PE'] > 0, np.inf)
pb_for_rank = dfInfo['PB'].where(dfInfo['PB'] > 0, np.inf)

dfInfo['PE_Rank'] = (pe_for_rank.rank(method='min', ascending=True, na_option='bottom').astype(int))
dfInfo['PB_Rank'] = (pb_for_rank.rank(method='min', ascending=True, na_option='bottom').astype(int))

rank_cols = ["PE_Rank", "PB_Rank", "ROE_Rank", "DIV_Rank"]
dfInfo["Total_Rank"] = dfInfo[rank_cols].sum(axis=1)
dfInfo = dfInfo.sort_values("Total_Rank", ascending=True)

# 6. FORMAT TABLE FOR DISPLAY
df_print = dfInfo.copy()
df_print['PE'] = df_print['PE'].apply(lambda x: "-" if pd.isna(x) else f"{x:.2f}")
df_print['PB'] = df_print['PB'].apply(lambda x: "-" if pd.isna(x) else f"{x:.2f}")
df_print['ROE'] = df_print['ROE'].apply(lambda x: "-" if pd.isna(x) else f"{x * 100:.2f} %")
df_print['BBPos'] = df_print['BBPos'].apply(lambda x: "-" if pd.isna(x) else f"{x * 100:.2f} %")
df_print['DIV'] = df_print['DIV'].apply(lambda x: "-" if pd.isna(x) else f"{x * 100:.2f} %")

# FIX 2: Added missing Streamlit UI rendering
st.title("📈 The Lista")
st.caption(f"Bollinger Band: {framesize}-day SMA ± {bollinger_mult}σ  |  Data cached for 1 hour")

display_cols = ["Name @PreviousClose", "ROE", "PE", "PB", "DIV", "BBPos", "Total_Rank"]
st.dataframe(
    df_print[display_cols],
    use_container_width=True,
    height=400
)

st.markdown("---")
st.markdown(
    "**BBPos**: Distance from SMA relative to lower Bollinger Band. "
    "Negative = below SMA (potential value). **Total_Rank**: sum of PE, PB, ROE, DIV ranks (lower is better)."
)