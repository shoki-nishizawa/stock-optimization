import json
import yfinance as yf
import pandas as pd
import numpy as np
import concurrent.futures
import time
import os

def update_database():
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "stock_database.csv")

    print("JPXから銘柄一覧データ(data_j.xls)をダウンロードして読み込み中...")
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    df_jpx = pd.read_excel(url)
    df_jpx = df_jpx[df_jpx['33業種区分'] != '-']

    tickers_to_process = []
    ticker_info_jpx = {}

    for _, row in df_jpx.iterrows():
        code = str(row['コード']).strip()
        if len(code) == 4 and code.isdigit():
            yf_ticker = f"{code}.T"
            tickers_to_process.append(yf_ticker)
            ticker_info_jpx[yf_ticker] = {
                'name': row['銘柄名'],
                'sector': row['33業種区分'],
                'market': row['市場・商品区分']
            }

    print(f"JPX銘柄マスタから {len(tickers_to_process)} 社を取得しました。")
    print("過去1年分の価格データを一括ダウンロード中...")
    
    data = yf.download(tickers_to_process, period="1y", group_by="ticker", progress=False, actions=True, threads=False)

    valid_tickers = []
    historical_stats = {}

    is_multi = len(tickers_to_process) > 1

    for tk in tickers_to_process:
        if is_multi:
            if tk not in data.columns.levels[0]: continue
            tk_data = data[tk]
        else:
            tk_data = data
            
        if 'Close' not in tk_data: continue
        close_series = tk_data['Close'].dropna()
        if len(close_series) < 100: continue
            
        current_price = close_series.iloc[-1]
        start_price = close_series.iloc[0]
        
        if current_price > 1000000: continue
            
        annual_return = float((current_price - start_price) / start_price)
        daily_returns = close_series.pct_change().dropna()
        volatility = float(daily_returns.std() * np.sqrt(252))
        
        annual_dividend_per_share = 0.0
        if 'Dividends' in tk_data:
            annual_dividend_per_share = float(tk_data['Dividends'].sum())
            
        historical_stats[tk] = {
            'current_price': current_price,
            'annual_return': annual_return,
            'volatility': volatility,
            'annual_dividend_per_share': annual_dividend_per_share
        }
        valid_tickers.append(tk)

    print(f"有効な株価データを持つ銘柄数: {len(valid_tickers)} / {len(tickers_to_process)}")
    print("ファンダメンタルズ情報を個別に取得中（※1社ずつ取得するため数十分かかります）...")

    def fetch_fundamentals(tk):
        try:
            time.sleep(0.5) 
            info = yf.Ticker(tk).info
            return tk, info
        except Exception as e:
            return tk, {}

    fundamentals_dict = {}
    
    processed_count = 0
    total = len(valid_tickers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_fundamentals, tk): tk for tk in valid_tickers}
        for future in concurrent.futures.as_completed(futures):
            tk, info = future.result()
            fundamentals_dict[tk] = info
            
            processed_count += 1
            if processed_count % 100 == 0:
                print(f"詳細取得進捗: {processed_count} / {total} 完了")

    results = []
    
    rating_map = {
        'strong_buy': '強気買い', 'buy': '買い', 'hold': '中立',
        'underperform': 'やや弱気', 'sell': '売り', 'strong_sell': '強気売り', 'none': '-', 'None': '-'
    }

    for tk in valid_tickers:
        h_stats = historical_stats[tk]
        info = fundamentals_dict.get(tk, {})
        
        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')
        pe = trailing_pe if trailing_pe is not None else (forward_pe if forward_pe is not None else 0.0)
        
        roe = info.get('returnOnEquity', 0.0)
        if roe is None: roe = 0.0
        
        analyst_rating_raw = str(info.get('recommendationKey', 'None')).lower()
        analyst_rating = rating_map.get(analyst_rating_raw, str(analyst_rating_raw).title() if str(analyst_rating_raw) != 'none' else '-')

        results.append({
            'ticker': tk,
            'name': ticker_info_jpx[tk]['name'],
            'sector': ticker_info_jpx[tk]['sector'],
            'market': ticker_info_jpx[tk]['market'],
            'current_price': h_stats['current_price'],
            'annual_return': h_stats['annual_return'],
            'volatility': h_stats['volatility'],
            'annual_dividend_per_share': h_stats['annual_dividend_per_share'],
            'pe': pe,
            'roe': roe,
            'analyst_rating': analyst_rating
        })

    df_out = pd.DataFrame(results)
    df_out.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"🎉 データベース更新完了！ {len(df_out)}件のデータを {output_path} に保存しました。")

if __name__ == "__main__":
    update_database()
