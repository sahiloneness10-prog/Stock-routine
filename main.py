import yfinance as yf

# ✏️ Edit this list with whatever stocks you want to track
TICKERS = ["VENU", "DUKR", "LNZA","SIDU","STLTECH.NS","HFCL.NS",TEJASNET.NS","HLIT","NBIS","PENG","NOK","SLOIF","TE","FLNC","MITK","HUMA","AAOI","BE","SWMR","AMPX","KRKNF","AXTI","COHR","VYX","NATL","FLTR.L","LODE","SATL","SNDK","MOH","HAL","PFE","EWZ","MELI","DUOL","KLAR","FIG","ASML","TATE.L","HAIN","XIACY","VWSYF","ZETA","GYM.L","GNC.L","BYDDY","BYND","DKS","OTLY","SNOW","SAP","WDAY","MKS.L","JD.L","TRN.L","NTPCGREEN.NS","HMC","GSK.L","TSM","TIMEX.BO","0HAO.IL","NVDA","BT-A.L","JDW.L","SBRY.L","ADTN" ]

for ticker in TICKERS:
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1mo")
    
    price_now = hist["Close"].iloc[-1]
    price_3d  = hist["Close"].iloc[-3]
    price_1w  = hist["Close"].iloc[-5]
    price_1m  = hist["Close"].iloc[0]

    print(f"\n📈 {ticker}")
    print(f"  3-day change : {((price_now - price_3d) / price_3d * 100):.2f}%")
    print(f"  1-week change: {((price_now - price_1w) / price_1w * 100):.2f}%")
    print(f"  1-month change:{((price_now - price_1m) / price_1m * 100):.2f}%")
