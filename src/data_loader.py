import yfinance as yf   # 株価取得
import pandas as pd
import numpy as np
import os
import streamlit as st

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
def extract_candidates(ticker_dict, strategy_config):
    """
    ローカルCSVから、第一段階でフィルタリングされた銘柄（ticker_dict）のファンダメンタルズ情報を読み込み、独自のスコア計算とソートロジックを適用。
    最終的な上位N社だけリアルタイムに過去1年分の株価履歴（グラフ用）を取得して返す。
    """
    if not os.path.exists(DB_PATH) or not ticker_dict:
        return []
        
    tickers = list(ticker_dict.keys())
    df = pd.read_csv(DB_PATH)
    df = df[df['ticker'].isin(tickers)]
    
    if df.empty:
        return []

    stock_stats = []
    
    for _, row in df.iterrows():
        tk = row['ticker']
        current_price = float(row['current_price'])
        
        # 株価バグ等で異常な値の場合は除外
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
        
        dividend_yield = annual_dividend_per_share / current_price  # 予想配当利回り
        expected_dividend = annual_dividend_per_share               # 予想配当額

        expected_capital_gain = share_price * annual_return         # 株価上昇による利益
        total_profit = expected_capital_gain + expected_dividend    # 予想総利益
        
        # 独自ファンダメンタルズスコアの算出
        if pe > 0:
            per_contribution = (15 - pe) / 100      # PER(株価収益率)は15倍を基準。0.01倍して％スケールに合わせる
        else:
            per_contribution = -0.10
            
        roe_contribution = roe - 0.10 if roe != 0.0 else 0.0  # ROE(自己資本利益率)は10%を基準
            
        momentum_contribution = annual_return * 0.2  # 株価上昇率に0.2倍の係数をかけて調整
        
        custom_score_rate = dividend_yield + per_contribution + roe_contribution + momentum_contribution    # コスパのスコア
        custom_score_per_share = share_price * custom_score_rate    # 一株当たりのスコア（これをソルバーで最大化する）
        
        stock_stats.append({
            'ticker': tk,
            'name': ticker_dict[tk],
            'current_price': current_price,
            'share_price': int(share_price),
            'annual_return': annual_return,
            'dividend_yield': dividend_yield,
            'pe': pe,
            'roe': roe,
            'custom_score_rate': custom_score_rate,
            'expected_capital_gain': int(expected_capital_gain),
            'expected_dividend': int(expected_dividend),
            'custom_score_per_share': int(custom_score_per_share),
            'share_profit': int(total_profit),
            'volatility': volatility,
            'analyst_rating': analyst_rating,
            'history': None # 後で取得する
        })
        
    # ── ボラティリティ・プレフィルタ（第二段階の設定を第一段階に反映）──
    max_volatility = strategy_config.get("max_volatility", None)
    if max_volatility is not None:
        before_count = len(stock_stats)
        stock_stats = [s for s in stock_stats if s['volatility'] <= max_volatility]
        filtered = before_count - len(stock_stats)
        if filtered > 0:
            print(f"  ⚠ ボラティリティ > {max_volatility} の銘柄を {filtered} 社除外")
    
    # ── スコアでソート ──
    stock_stats.sort(key=lambda x: x['custom_score_rate'], reverse=True)    
        
    top_n = strategy_config.get("top_n", 10)
    candidates = stock_stats[:top_n]
    
    # グラフ表示用に、選ばれた上位N社だけyfinanceで過去履歴をリアルタイム取得する（この処理は一瞬で終わる）
    top_tickers = [c['ticker'] for c in candidates]
    if top_tickers:
        print(f"上位 {len(top_tickers)} 銘柄のグラフ用履歴データを取得中...")
        data = yf.download(top_tickers, period="1y", group_by="ticker", progress=False, actions=False, threads=False)
        is_multi = len(top_tickers) > 1
        
        for c in candidates:
            tk = c['ticker']
            # 銘柄が1つの場合と複数で取得した場合で処理を分ける（yfinanceの仕様）
            if is_multi:    
                if tk in data.columns.levels[0] and 'Close' in data[tk]:
                    c['history'] = data[tk]['Close'].dropna()
            else:
                if 'Close' in data:
                    c['history'] = data['Close'].dropna()
    
    return candidates
