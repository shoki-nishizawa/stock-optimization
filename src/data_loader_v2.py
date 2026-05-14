import yfinance as yf   # 株価取得
import pandas as pd
import numpy as np
import os
import streamlit as st

# Import the new dynamic inference pipeline
from inference_pipeline import run_inference_pipeline

DB_PATH = "data/stock_database.csv"

@st.cache_data
def get_jpx_tickers(filter_config):
    """
    構築済みのローカルCSVデータベースから銘柄一覧と基本情報を取得し、
    条件（filter_config）に基づいてフィルタリングし、証券コードと企業名の辞書を返す。
    """
    if not os.path.exists(DB_PATH):
        print(f"エラー: データベース({DB_PATH})が見つかりません。")
        return {}

    df = pd.read_csv(DB_PATH)
    
    # フィルタリング
    sector_filter = filter_config.get("sector", [])
    market_filter = filter_config.get("market", [])
    
    if sector_filter:
        df = df[df['sector'].isin(sector_filter)]
    if market_filter:
        df = df[df['market'].isin(market_filter)]
        
    ticker_dict = {}
    for _, row in df.iterrows():
        ticker_dict[row['ticker']] = row['name']    # 証券コード: 企業名 の辞書を作成
            
    print(f"データベースから条件に合致する銘柄を {len(ticker_dict)} 社抽出しました。")
    return ticker_dict

@st.cache_data
def extract_candidates(ticker_dict, strategy_config, _progress_callback=None):
    """
    Ver 2.0: AIスコア（LGBM+LLM）を動的に推論し、配当金×AIスコアに基づく新しい最適化指標を算出。
    """
    if not os.path.exists(DB_PATH) or not ticker_dict:
        return []
        
    tickers = list(ticker_dict.keys())
    df = pd.read_csv(DB_PATH)
    df = df[df['ticker'].isin(tickers)]
    
    if df.empty:
        return []

    # Rename 'ticker' back to 'secCode' for the pipeline, or just use 'ticker'
    # Wait, the pipeline expects 'secCode'.
    # Our DB_PATH has 'ticker' e.g. '7203.T'. So secCode should be just '7203'
    df['secCode'] = df['ticker'].astype(str).str[:4]
    
    # ボラティリティ・プレフィルタ
    max_volatility = strategy_config.get("max_volatility", None)
    if max_volatility is not None:
        before_count = len(df)
        df = df[df['volatility'] <= max_volatility]
        filtered = before_count - len(df)
        if filtered > 0:
            print(f"  ⚠ ボラティリティ > {max_volatility} の銘柄を {filtered} 社除外")

    if df.empty:
        st.error("最初の条件（指定セクター、ボラティリティ上限など）に合致する銘柄が1件もありませんでした。条件を緩めてください。")
        st.stop()

    # プレフィルタ後の銘柄数が多いと推論に非常に時間がかかるため制限
    if len(df) > 100:
        st.warning(f"ボラティリティ等で絞り込んだ後も候補が {len(df)} 社と多すぎます。推論に時間がかかりすぎるため、対象セクターを更に絞るなどして100社未満にしてください。")
        st.stop()

    # 動的推論の実行
    if _progress_callback:
        _progress_callback("AI推論パイプラインを開始します...", 0.0)
        
    lgbm_threshold = strategy_config.get("lgbm_threshold", 0.5)
    df = run_inference_pipeline(df, progress_callback=_progress_callback, threshold=lgbm_threshold)

    if df.empty:
        st.error("AI（LGBM）の推論結果、今後の株価上昇が見込める（勝ちと判定された）銘柄が1つもありませんでした。対象セクターを変更するなどしてみてください。")
        st.stop()

    # Ensure columns exist even if pipeline failed partially
    if 'combined_score' not in df.columns:
        df['combined_score'] = 0.0
    if 'llm_summary' not in df.columns:
        df['llm_summary'] = "データなし"

    df['combined_score'] = df['combined_score'].fillna(0.0)
    df['llm_summary'] = df['llm_summary'].fillna("データなし")

    if _progress_callback:
        _progress_callback("yfinanceから最新のリアルタイム株価を取得中...", 1.0)
        
    try:
        tickers = df['ticker'].tolist()
        live_data = yf.Tickers(' '.join(tickers))
        for i, row in df.iterrows():
            tk = row['ticker']
            info = live_data.tickers[tk].info
            if info:
                df.at[i, 'current_price'] = info.get('currentPrice', info.get('regularMarketPrice', row['current_price']))
                if 'trailingPE' in info and info['trailingPE'] is not None:
                    df.at[i, 'pe'] = info['trailingPE']
                if 'returnOnEquity' in info and info['returnOnEquity'] is not None:
                    df.at[i, 'roe'] = info['returnOnEquity']
                if 'dividendRate' in info and info['dividendRate'] is not None:
                    df.at[i, 'annual_dividend_per_share'] = info['dividendRate']
    except Exception as e:
        print(f"yfinance latest price fetch failed: {e}")

    stock_stats = []
    
    for _, row in df.iterrows():
        tk = row['ticker']
        current_price = float(row['current_price'])
        
        if pd.isna(current_price) or current_price <= 0 or current_price > 1000000:
            continue
            
        share_price               = current_price
        annual_return             = float(row['annual_return'])
        volatility                = float(row['volatility'])
        pe                        = float(row['pe']) if pd.notna(row['pe']) else 0.0
        if pe == float('inf') or pe == float('-inf'):
            pe = 0.0
        
        roe                       = float(row['roe']) if pd.notna(row['roe']) else 0.0
        if roe == float('inf') or roe == float('-inf'):
            roe = 0.0
        annual_dividend_per_share = float(row['annual_dividend_per_share']) if pd.notna(row['annual_dividend_per_share']) else 0.0
        analyst_rating            = str(row['analyst_rating'])
        
        dividend_yield = annual_dividend_per_share / current_price if current_price > 0 else 0.0
        expected_dividend = annual_dividend_per_share               

        expected_capital_gain = share_price * annual_return         
        total_profit = expected_capital_gain + expected_dividend    
        
        # Version 2.0 新指標: AIスコア × 予想配当額
        combined_score = float(row['combined_score'])
        llm_summary = str(row['llm_summary'])
        
        # OR-Toolsで最大化するための整数係数 (1株あたりのAI調整後配当額)
        # ※ 負のスコアの場合はマイナス評価になるため、ソルバーは買わないようになります
        # ※ combined_scoreが0以上の場合はそのまま使用、マイナスの場合は0扱いにするか？
        #    ここではそのまま掛ける（ペナルティになる）
        ai_adjusted_dividend_per_share = int(expected_dividend * combined_score)
        
        stock_stats.append({
            'ticker': tk,
            'name': ticker_dict[tk],
            'current_price': current_price,
            'share_price': int(share_price),
            'annual_return': annual_return,
            'dividend_yield': dividend_yield,
            'pe': pe,
            'roe': roe,
            'combined_score': combined_score,
            'llm_summary': llm_summary,
            'ai_adjusted_dividend_per_share': ai_adjusted_dividend_per_share,
            'expected_capital_gain': int(expected_capital_gain),
            'expected_dividend': int(expected_dividend),
            'share_profit': int(total_profit),
            'volatility': volatility,
            'analyst_rating': analyst_rating,
            'history': None 
        })
    
    # ── ソート基準の変更: Version 2.0では ai_adjusted_dividend_per_share をベースにする ──
    # ここではソルバーに渡す上位候補を決めるため、調整後配当金が高い順に並べる
    stock_stats.sort(key=lambda x: x['ai_adjusted_dividend_per_share'], reverse=True)    
        
    top_n = strategy_config.get("top_n", 10)
    candidates = stock_stats[:top_n]
    
    # グラフ表示用に履歴取得
    top_tickers = [c['ticker'] for c in candidates]
    if top_tickers:
        if _progress_callback:
            _progress_callback(f"上位 {len(top_tickers)} 銘柄のグラフ用履歴データを取得中...", 0.95)
        print(f"上位 {len(top_tickers)} 銘柄のグラフ用履歴データを取得中...")
        data = yf.download(top_tickers, period="1y", group_by="ticker", progress=False, actions=False, threads=False)
        is_multi = len(top_tickers) > 1
        
        for c in candidates:
            tk = c['ticker']
            if is_multi:    
                if tk in data.columns.levels[0] and 'Close' in data[tk]:
                    c['history'] = data[tk]['Close'].dropna()
            else:
                if 'Close' in data:
                    c['history'] = data['Close'].dropna()
    
    if _progress_callback:
        _progress_callback("データ準備完了", 1.0)
    return candidates

