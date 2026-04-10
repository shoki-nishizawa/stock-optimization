import json
import yfinance as yf
import pandas as pd
import numpy as np
import os
import streamlit as st

DB_PATH = "data/stock_database.csv"

def load_config(config_path="config.json"):
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@st.cache_data
def get_jpx_tickers(filter_config):
    """
    構築済みのローカルCSVデータベースから銘柄一覧と基本情報を取得し、
    条件に基づいてフィルタリングし、証券コードと企業名の辞書を返す。
    """
    if not os.path.exists(DB_PATH):
        print(f"エラー: データベース({DB_PATH})が見つかりません。先にスクリプトを実行してください。")
        # 例外を投げずに空を返し、UI側でエラー表示させる
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
        ticker_dict[row['ticker']] = row['name']
            
    print(f"データベースから条件に合致する銘柄を {len(ticker_dict)} 社抽出しました。")
    return ticker_dict

@st.cache_data
def extract_candidates(ticker_dict, strategy_config):
    """
    ローカルCSVから全銘柄のファンダメンタルズ情報を読み込み、ソートロジックを適用。
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
            
        share_price = current_price
        annual_return = float(row['annual_return'])
        volatility = float(row['volatility'])
        pe = float(row['pe']) if pd.notna(row['pe']) else 0.0
        roe = float(row['roe']) if pd.notna(row['roe']) else 0.0
        annual_dividend_per_share = float(row['annual_dividend_per_share']) if pd.notna(row['annual_dividend_per_share']) else 0.0
        analyst_rating = str(row['analyst_rating'])
        
        dividend_yield = annual_dividend_per_share / current_price if current_price > 0 else 0.0
        expected_dividend = annual_dividend_per_share
        
        expected_capital_gain = share_price * annual_return
        total_profit = expected_capital_gain + expected_dividend
        
        # 独自ファンダメンタルズスコアの算出
        if pe > 0:
            per_contribution = (15 - pe) / 100
        else:
            per_contribution = -0.10
            
        roe_contribution = roe - 0.10 if roe != 0.0 else 0.0
            
        momentum_contribution = annual_return * 0.2
        
        custom_expected_return = dividend_yield + per_contribution + roe_contribution + momentum_contribution
        custom_profit = share_price * custom_expected_return
        
        stock_stats.append({
            'ticker': tk,
            'name': ticker_dict[tk],
            'current_price': current_price,
            'share_price': int(share_price),
            'annual_return': annual_return,
            'dividend_yield': dividend_yield,
            'pe': pe,
            'roe': roe,
            'custom_return': custom_expected_return,
            'expected_capital_gain': int(expected_capital_gain),
            'expected_dividend': int(expected_dividend),
            'custom_profit': int(custom_profit),
            'share_profit': int(total_profit),
            'volatility': volatility,
            'analyst_rating': analyst_rating,
            'history': None # 後で取得する
        })
        
    sort_mode = strategy_config.get("sort_by", "return_high")
    
    if sort_mode == "volatility_high":
        stock_stats.sort(key=lambda x: x['volatility'], reverse=True)
    elif sort_mode == "fundamental_high":
        stock_stats.sort(key=lambda x: x['custom_return'], reverse=True)
        # 上位候補の価値を独自スコアベースに上書きする
        for s in stock_stats:
            s['share_profit'] = s['custom_profit']
    else:
        stock_stats.sort(key=lambda x: x['annual_return'], reverse=True)
        
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
            if is_multi:
                if tk in data.columns.levels[0] and 'Close' in data[tk]:
                    c['history'] = data[tk]['Close'].dropna()
            else:
                if 'Close' in data:
                    c['history'] = data['Close'].dropna()
    
    return candidates
