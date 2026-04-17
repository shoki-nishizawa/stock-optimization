import pandas as pd
import yfinance as yf
import concurrent.futures   # 並列処理
import time
import os
import logging
import sys

# ログの設定（コンソールに出力され、GitHub Actionsのログにも時刻付きで記録される）
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_fundamentals_local():
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "fundamentals.csv")

    logging.info("JPXから銘柄一覧データ(data_j.xls)をダウンロード中...")
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df_jpx = pd.read_excel(url)
    except Exception as e:
        logging.error(f"JPXリストの取得に失敗しました: {e}")
        sys.exit(1) # GitHub Actionsをここでエラー終了(失敗)させる
    # 業種区分が「-」の銘柄を除外
    df_jpx = df_jpx[df_jpx['33業種区分'] != '-']

    tickers_to_process = []
    
    for _, row in df_jpx.iterrows():
        code = str(row['コード']).strip()
        if len(code) == 4 and code.isalnum():       # 4桁の（数字 + アルファベット）を対象にする
            tickers_to_process.append(f"{code}.T")  # 日本の株式は.Tを付ける

    # 既に取得済みのデータを読み込む（リジューム機能）
    existing_data = {}
    if os.path.exists(output_path):
        try:
            df_existing = pd.read_csv(output_path)
            for _, row in df_existing.iterrows():
                # 完全にエラーだった銘柄(0.0, 0.0, none) 以外はスキップ対象にする
                if not (row['pe'] == 0.0 and row['roe'] == 0.0 and row['analyst_rating_raw'] == 'none'):
                    existing_data[row['ticker']] = row.to_dict()
        except Exception as e:  # ファイルはあるが読み込めない場合
            logging.warning(f"既存データの読み込みに失敗しました（新規取得として続行します）: {e}")

    tickers_to_fetch = [tk for tk in tickers_to_process if tk not in existing_data]

    logging.info(f"全対象銘柄数: {len(tickers_to_process)} 社")
    logging.info(f"取得済み: {len(existing_data)} 社")
    logging.info(f"今回新規取得対象: {len(tickers_to_fetch)} 社")
    
    if len(tickers_to_fetch) == 0:
        logging.info("新規に取得する銘柄はありませんでした。")
        return

    logging.info("各企業の詳細なファンダメンタルズ情報をYahoo Financeから取得します...")

    def fetch_info(tk):
        try:
            time.sleep(1.0) # Yahoo側のブロックを避けるために待機時間を1秒に延長
            info = yf.Ticker(tk).info
            
            trailing_pe = info.get('trailingPE')    # 実績PER
            forward_pe = info.get('forwardPE')      # 予想PER
            pe = trailing_pe if trailing_pe is not None else (forward_pe if forward_pe is not None else 0.0)
            
            roe = info.get('returnOnEquity', 0.0)
            if roe is None:
                roe = 0.0
            
            analyst_rating_raw = str(info.get('recommendationKey', 'None')).lower() # 後で使いやすいように小文字にしておく
            return tk, pe, roe, analyst_rating_raw

        except Exception as e:
            if "401" in str(e) or "Crumb" in str(e):
                # 401ブロックされた場合は全体を止めるための例外を投げる
                raise Exception(f"API Blocked: {tk}")
            
            # その他の個別エラー（1社だけデータがない等）は一旦ゼロとして扱い続行
            logging.warning(f"銘柄 {tk} の個別データ取得に失敗しました: {e}")
            return tk, 0.0, 0.0, 'none'

    results = list(existing_data.values()) # 既に取得済みの分を結果にセットしておく
    processed = 0
    total = len(tickers_to_fetch)
    blocked_by_api = False

    if total > 0:
        # データ取得速度とAPIブロックの折衷案⇒スレッド数2、待機時間1秒
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(fetch_info, tk) for tk in tickers_to_fetch]     # 銘柄ごとに並列処理
            for future in concurrent.futures.as_completed(futures):                    # 完了した順に処理
                try:
                    tk, pe, roe, analyst_rating_raw = future.result()   # 1銘柄分の結果を取得
                    results.append({
                        'ticker': tk,
                        'pe': pe,
                        'roe': roe,
                        'analyst_rating_raw': analyst_rating_raw
                    })
                    processed += 1
                    if processed % 100 == 0 or processed == total:
                        logging.info(f"進捗: {processed} / {total} 処理済み")
                except Exception as e:
                    if "API Blocked" in str(e):
                        logging.error("🚨 Yahoo Financeにアクセスブロック(401等)されたため、これ以上の通信を直ちに中止します。")
                        blocked_by_api = True
                        # キューに溜まっている未処理のタスクをキャンセル
                        for f in futures:
                            f.cancel()
                        break

    # 途中でブロックされたとしても、そこまでに取得できた分は無駄にせずCSVに保存する
    df_fund = pd.DataFrame(results)
    df_fund.to_csv(output_path, index=False, encoding='utf-8-sig')
    logging.info(f"取得結果を {output_path} に保存しました。")

    if blocked_by_api:
        logging.error("APIのブロックにより処理が強制終了されました。")
        sys.exit(1) # GitHub Actionsを意図的に失敗(Failed)させる
    else:
        logging.info("全ファンダメンタルズデータの取得が正常に完了しました！")

if __name__ == "__main__":
    fetch_fundamentals_local()
