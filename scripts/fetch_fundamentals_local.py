import pandas as pd
import yfinance as yf
import concurrent.futures
import time
import os

def fetch_fundamentals_local():
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "fundamentals.csv")

    print("JPXから銘柄一覧データ(data_j.xls)をダウンロード中...")
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df_jpx = pd.read_excel(url)
    except Exception as e:
        print(f"JPXリストの取得に失敗しました: {e}")
        return

    df_jpx = df_jpx[df_jpx['33業種区分'] != '-']

    tickers_to_process = []
    
    for _, row in df_jpx.iterrows():
        code = str(row['コード']).strip()
        if len(code) == 4 and code.isdigit():
            tickers_to_process.append(f"{code}.T")

    print(f"対象銘柄数: {len(tickers_to_process)} 社")
    print("各企業の詳細なファンダメンタルズ情報をYahoo Financeから取得します。")
    print("【注意】この処理には数十分かかります。完了するまでPCをスリープさせないでください！")

    def fetch_info(tk):
        try:
            time.sleep(0.5) # Yahoo側の負荷を抑えるための待機時間
            info = yf.Ticker(tk).info
            
            trailing_pe = info.get('trailingPE')
            forward_pe = info.get('forwardPE')
            pe = trailing_pe if trailing_pe is not None else (forward_pe if forward_pe is not None else 0.0)
            
            roe = info.get('returnOnEquity', 0.0)
            if roe is None: roe = 0.0
            
            analyst_rating_raw = str(info.get('recommendationKey', 'None')).lower()
            return tk, pe, roe, analyst_rating_raw
        except Exception:
            return tk, 0.0, 0.0, 'none'

    results = []
    processed = 0
    total = len(tickers_to_process)

    # 家庭用ネットワークからのアクセスなのでブロックされにくいですが、念のためスレッド数を絞ります
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_info, tk): tk for tk in tickers_to_process}
        for future in concurrent.futures.as_completed(futures):
            tk, pe, roe, analyst_rating_raw = future.result()
            results.append({
                'ticker': tk,
                'pe': pe,
                'roe': roe,
                'analyst_rating_raw': analyst_rating_raw
            })
            processed += 1
            if processed % 100 == 0 or processed == total:
                print(f"進捗: {processed} / {total} 完了")

    df_fund = pd.DataFrame(results)
    df_fund.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n🎉 ファンダメンタルズデータの取得が完了しました！")
    print(f"結果を {output_path} に保存しました。")
    print("ターミナルで `git add data/fundamentals.csv` と `git commit -m \"Update fundamentals\"` を実行し、プッシュしてください。")

if __name__ == "__main__":
    fetch_fundamentals_local()
