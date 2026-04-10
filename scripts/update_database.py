import json
import yfinance as yf
import pandas as pd
import numpy as np
import time
import os

def update_database():
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "stock_database.csv")
    fundamentals_path = os.path.join(output_dir, "fundamentals.csv")

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
    print("過去1年分の価格データを一括ダウンロード中...（これは数秒〜十数秒で終わります）")
    
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
        
        if pd.isna(current_price) or current_price <= 0 or current_price > 1000000: continue
            
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

    # ファンダメンタルズCSVの読み込み
    fund_dict = {}
    if os.path.exists(fundamentals_path):
        print(f"ローカルからアップロードされた {fundamentals_path} を読み込みます。")
        df_fund = pd.read_csv(fundamentals_path)
        for _, row in df_fund.iterrows():
            fund_dict[row['ticker']] = {
                'pe': row['pe'],
                'roe': row['roe'],
                'analyst_rating_raw': row['analyst_rating_raw']
            }
    else:
        print(f"⚠️ {fundamentals_path} が見つかりませんでした。PEとROEは0.0として処理されます。")

    results = []
    
    rating_map = {
        'strong_buy': '強気買い', 'buy': '買い', 'hold': '中立',
        'underperform': 'やや弱気', 'sell': '売り', 'strong_sell': '強気売り', 'none': '-', 'NaN': '-', 'nan': '-'
    }

    for tk in valid_tickers:
        h_stats = historical_stats[tk]
        
        # ファンダメンタルズの取得（CSVから）
        fund_info = fund_dict.get(tk, {'pe': 0.0, 'roe': 0.0, 'analyst_rating_raw': 'none'})
        pe = float(fund_info['pe']) if pd.notna(fund_info['pe']) else 0.0
        roe = float(fund_info['roe']) if pd.notna(fund_info['roe']) else 0.0
        analyst_rating_raw = str(fund_info['analyst_rating_raw'])
        analyst_rating = rating_map.get(analyst_rating_raw, analyst_rating_raw.title() if analyst_rating_raw not in ['none', 'nan', 'NaN'] else '-')

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
    print("このスクリプトは yf.Ticker(tk).info へのアクセスを行わないため、非常に高速に終了します！")

if __name__ == "__main__":
    update_database()
