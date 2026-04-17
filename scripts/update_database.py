import json
import yfinance as yf
import pandas as pd
import numpy as np
import time
import os
import logging

# ログの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def update_database():
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "stock_database.csv")
    fundamentals_path = os.path.join(output_dir, "fundamentals.csv")

    logging.info("JPXから銘柄一覧データ(data_j.xls)をダウンロードして読み込み中...")
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    df_jpx = pd.read_excel(url)
    df_jpx = df_jpx[df_jpx['33業種区分'] != '-']

    tickers_to_process = []
    ticker_info_jpx = {}

    for _, row in df_jpx.iterrows():
        code = str(row['コード']).strip()
        if len(code) == 4 and code.isalnum():       # 4桁の（数字 + アルファベット）を対象にする
            yf_ticker = f"{code}.T"
            tickers_to_process.append(yf_ticker)
            ticker_info_jpx[yf_ticker] = {
                'name': row['銘柄名'],
                'sector': row['33業種区分'],
                'market': row['市場・商品区分']
            }

    logging.info(f"JPX銘柄マスタから {len(tickers_to_process)} 社を取得しました。")
    logging.info("過去1年分の価格データを一括ダウンロード中...（これは数秒〜十数秒で終わります）")
    # 一括ダウンロードできる
    data = yf.download(tickers_to_process, period="1y", group_by="ticker", progress=False, actions=True, threads=False)
    """
    tickers: str, list
    ダウンロードするTickerのリスト

    period: str
    Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
    periodを使用するか、start & end を使用するかどちらでも。

    interval: str
    Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo 
    データ取得頻度

    start: str
    データ取得開始日時。
    string型の(YYYY-MM-DD)もしくはdatetime型で指定。デフォルトは99年前。
    例えば start="2020-01-01" と指定すると、最初のデータは 2020/01/01 から始まる(inclusive)。

    end: str
    データ取得終了日時。
    string型の(YYYY-MM-DD)もしくはdatetime型で指定。デフォルトは現在。
    例えば end=”2023-01-01” と指定すると、最後のデータは “2022-12-31” で終わる。

    group_by: str
    Group by ‘ticker’ or ‘column’ (default)

    prepost: bool
    市場開始前、終了後のデータを含むか。デフォルトは False

    auto_adjust: bool
    自動で全てのOHLC(始値、高値、安値、終値)を調整するか。デフォルトはTrue

    back_adjust: bool
    取得した過去の株価データに対して、企業の配当や株式分割などのコーポレートアクションの影響を反映させるために、データ全体を後方（バックワード）に調整するオプション。
    通常、ticker.history() の auto_adjust=True により、当日の始値・高値・安値・終値は、配当や分割の影響を取り除いた「調整後」価格に変換されます。しかし、back_adjust を True にすると、単にその日の値を調整するだけでなく、過去すべての日付について、最新の株価水準と整合するように全体を一貫した基準で再計算（後方修正）する。
    例えば、ある日配当が支払われた場合、実際の市場価格は配当支払い直後に下落しますが、auto_adjust はその日の OHLC 値から配当の影響を除外します。back_adjust を有効にすると、さらに過去のデータにもその配当の影響が均一に反映され、まるで配当金を再投資したかのような「真の」価格推移に近づける効果が期待されます。ただし、この「後方修正」はあくまで疑似的なもので、全ての状況で完璧に実際のリターンや値動きを再現するわけではない。

    repair: bool
    通貨単位が誤って100倍もしくは1/100になってしまうミスを検出し、修復を試みる。デフォルトはFalse

    keepna: bool
    Yahooから返されたNaN行をそのまま返すか。デフォルトはFalse

    actions: bool
    配当金と株式を分割したデータをダウンロードする。デフォルトはFalse

    threads: bool / int
    大量データをダウンロードするためのスレッドの数を指定。デフォルトはTrueで、この場合自動で設定される。Falseだと並列ダウンロードは行われない。

    ignore_tz: bool
    異なるタイムゾーンのデータを組み合わせる際に、日時データのタイムゾーン部分を無視するかどうか。
    デフォルトは以下:
    Intraday（1日の中の短い間隔、例: 1分足や5分足など）の場合： デフォルトは False となり、タイムゾーン情報が考慮される。
    Day+（日足以上の間隔、例: 日足、週足、月足など）の場合： デフォルトは True となり、タイムゾーン情報は無視される。

    proxy: str
    Optional. Proxy server URL scheme. Default is None

    rounding: bool
    Optional. 値を小数点第2位に丸めるか。

    timeout: None or float
    この値が None でない場合、指定された秒(0.01など少数も指定可能)だけレスポンスを待ち、時間が経過したら待機を中止する。サーバーなどからの応答が指定時間内に得られない場合、そのリクエストはタイムアウト扱いとなり、無限に待ち続けることを防ぐ。

    session: None or Session
    Optional. ユーザーが自分で作成したセッションオブジェクトを渡すことで、そのセッションを用いてすべてのリクエストが行われる。これにより、セッション内で設定したカスタムヘッダーや認証情報、接続プールなどの設定が反映され、再利用が可能となる。
    ・例
    -----------------------------------------------------------------
    import requests
    session = requests.Session()
    session.headers.update({'User-Agent': 'my-custom-agent'})

    # この session を渡すことで、以降のリクエストはカスタム設定が反映される
    some_function(timeout=5, session=session)
    -----------------------------------------------------------------

    multi_level_index: bool
    Optional. 常に MultiIndex DataFrame を返すか。 デフォルトはTrue
    """

    # -銘柄ごとに投資指標を計算-
    valid_tickers = []
    historical_stats = {}

    is_multi = len(tickers_to_process) > 1

    for tk in tickers_to_process:
        # yfinanceの仕様で複数or1つの場合でデータ構造が異なる
        if is_multi:
            if tk not in data.columns.levels[0]: continue
            tk_data = data[tk]
        else:
            tk_data = data
            
        if 'Close' not in tk_data:      # Close＝終値 が存在しない銘柄はスキップ
            continue
        close_series = tk_data['Close'].dropna()
        if len(close_series) < 100:     # 100日未満のデータはスキップ
            continue
            
        current_price = close_series.iloc[-1]
        start_price = close_series.iloc[0]
        
        if pd.isna(current_price) or current_price <= 0 or current_price > 1000000:  # バグっぽい価格はスキップ
            continue
            
        annual_return = float((current_price - start_price) / start_price)  # 一年前と比較した変化率
        daily_returns = close_series.pct_change().dropna()                  # 前日からの変化率
        volatility = float(daily_returns.std() * np.sqrt(252))              # daily_returnsの標準偏差を年率換算（市場の営業日数）
        
        annual_dividend_per_share = 0.0
        if 'Dividends' in tk_data:
            annual_dividend_per_share = float(tk_data['Dividends'].sum())   # 一年間の配当金の合計
            
        historical_stats[tk] = {
            'current_price': current_price,
            'annual_return': annual_return,
            'volatility': volatility,
            'annual_dividend_per_share': annual_dividend_per_share
        }
        valid_tickers.append(tk)

    logging.info(f"有効な株価データを持つ銘柄数: {len(tickers_to_process)}個中 {len(valid_tickers)}個")

    # ファンダメンタルズCSVの読み込み
    fund_dict = {}
    if os.path.exists(fundamentals_path):
        logging.info(f"ローカルからアップロードされた {fundamentals_path} を読み込みます。")
        df_fund = pd.read_csv(fundamentals_path)
        for _, row in df_fund.iterrows():
            fund_dict[row['ticker']] = {
                'pe': row['pe'],
                'roe': row['roe'],
                'analyst_rating_raw': row['analyst_rating_raw']
            }
    else:
        logging.warning(f"{fundamentals_path} が見つかりませんでした。PEとROEは0.0として処理されます。")

    results = []
    
    rating_map = {
        'strong_buy': '強気買い',
        'buy': '買い',
        'hold': '中立',
        'underperform': 'やや弱気',
        'sell': '売り',
        'strong_sell': '強気売り',
        'none': '-',
        'NaN': '-',
        'nan': '-'
    }

    for tk in valid_tickers:
        h_stats = historical_stats[tk]
        
        # ファンダメンタルズの取得（CSVから）
        fund_info = fund_dict.get(tk, {'pe': 0.0, 'roe': 0.0, 'analyst_rating_raw': 'none'})
        pe = float(fund_info['pe']) if pd.notna(fund_info['pe']) else 0.0
        roe = float(fund_info['roe']) if pd.notna(fund_info['roe']) else 0.0
        analyst_rating_raw = str(fund_info['analyst_rating_raw'])
        # 日本語に変換
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
    logging.info(f"データベース更新完了！ {len(df_out)}件のデータを {output_path} に保存しました。")

if __name__ == "__main__":
    update_database()
