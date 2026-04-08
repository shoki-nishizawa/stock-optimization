import json
import yfinance as yf
import pandas as pd
import numpy as np
import concurrent.futures

def load_config(config_path="config.json"):
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_jpx_tickers(filter_config):
    """
    JPXの公式サイトから全上場銘柄リスト(xls)を取得し、
    条件に基づいてフィルタリングし、証券コードと企業名の辞書を返す。
    """
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    print("JPXから銘柄一覧データ(data_j.xls)をダウンロードして読み込み中...")
    df = pd.read_excel(url)
    
    # フィルタリング
    sector_filter = filter_config.get("sector", [])
    market_filter = filter_config.get("market", [])
    
    # 除外すべき特殊コードなどは除外する
    df = df[df['33業種区分'] != '-']
    
    if sector_filter:
        df = df[df['33業種区分'].isin(sector_filter)]
    if market_filter:
        df = df[df['市場・商品区分'].isin(market_filter)]
        
    # コードと企業名のマッピング作成
    ticker_dict = {}
    for _, row in df.iterrows():
        code = str(row['コード']).strip()
        # 通常の4桁コードのみを対象にする
        if len(code) == 4 and code.isdigit():
            # yfinance用の日本株ティッカー生成 (.T)
            yf_ticker = f"{code}.T"
            ticker_dict[yf_ticker] = row['銘柄名']
            
    print(f"JPX銘柄マスタから条件に合致する銘柄を {len(ticker_dict)} 社抽出しました。")
    return ticker_dict

def extract_candidates(ticker_dict, strategy_config):
    """
    抽出した銘柄の株価データをyfinanceで一括取得し、
    指定されたソート戦略(ボラティリティなど)に基づいて上位N社を返す。
    """
    tickers = list(ticker_dict.keys())
    if not tickers:
        print("条件に合致する銘柄が0でした。")
        return []

    print(f"yfinanceから {len(tickers)} 銘柄の過去1年分のデータ一括ダウンロードを開始します...")
    
    data = yf.download(tickers, period="1y", group_by="ticker", progress=False, actions=True)
    
    def fetch_info(tk):
        try:
            return tk, yf.Ticker(tk).info
        except:
            return tk, {}

    print("yfinanceからファンダメンタルズ情報（PER, ROE）を取得中...")
    info_dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_info, tk): tk for tk in tickers}
        for future in concurrent.futures.as_completed(futures):
            tk, info = future.result()
            info_dict[tk] = info
            
    stock_stats = []
    
    for tk in tickers:
        if tk not in data.columns.levels[0]:
            continue
            
        close_series = data[tk]['Close'].dropna()
        if len(close_series) < 100:
            continue
            
        current_price = close_series.iloc[-1]
        start_price = close_series.iloc[0]
        
        annual_return = float((current_price - start_price) / start_price)
        
        # 【追加】yfinance側のデータ取得バグ（突然株価が数億〜数百億に跳ね上がる現象）を除外
        if current_price > 1000000:
            continue
            
        daily_returns = close_series.pct_change().dropna()
        volatility = float(daily_returns.std() * np.sqrt(252))
        
        share_price = float(current_price)
        
        info = info_dict.get(tk, {})
        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')
        pe = trailing_pe if trailing_pe is not None else forward_pe
        roe = info.get('returnOnEquity')
        
        # 配当金(実績)の取得
        if 'Dividends' in data[tk]:
            annual_dividend_per_share = float(data[tk]['Dividends'].sum())
        else:
            annual_dividend_per_share = 0.0
            
        dividend_yield = annual_dividend_per_share / current_price if current_price > 0 else 0.0
        expected_dividend = float(annual_dividend_per_share)
        
        expected_capital_gain = float(share_price * annual_return)
        total_profit = expected_capital_gain + expected_dividend
        
        # 独自ファンダメンタルズスコアの算出
        if pe is not None and pe > 0:
            per_contribution = (15 - pe) / 100
        else:
            per_contribution = -0.10
            
        if roe is not None:
            roe_contribution = roe - 0.10
        else:
            roe_contribution = 0.0
            
        momentum_contribution = annual_return * 0.2
        
        custom_expected_return = dividend_yield + per_contribution + roe_contribution + momentum_contribution
        custom_profit = float(share_price * custom_expected_return)
        
        # アナリスト評価の取得
        analyst_rating = info.get('recommendationKey', 'None')
        rating_map = {
            'strong_buy': '強気買い',
            'buy': '買い',
            'hold': '中立',
            'underperform': 'やや弱気',
            'sell': '売り',
            'strong_sell': '強気売り',
            'None': '-'
        }
        analyst_rating_jp = rating_map.get(analyst_rating, str(analyst_rating))
        
        stock_stats.append({
            'ticker': tk,
            'name': ticker_dict[tk],
            'current_price': current_price,
            'share_price': int(share_price),
            'annual_return': annual_return,
            'dividend_yield': dividend_yield,
            'pe': pe if pe is not None else 0.0,
            'roe': roe if roe is not None else 0.0,
            'custom_return': custom_expected_return,
            'expected_capital_gain': int(expected_capital_gain),
            'expected_dividend': int(expected_dividend),
            'custom_profit': int(custom_profit),
            'share_profit': int(total_profit),
            'volatility': volatility,
            'analyst_rating': analyst_rating_jp,
            'history': close_series
        })
        
    sort_mode = strategy_config.get("sort_by", "return_high")
    
    if sort_mode == "volatility_high":
        stock_stats.sort(key=lambda x: x['volatility'], reverse=True)
        print("ソート戦略: 年率ボラティリティ（値動きの激しさ）の高い順")
    elif sort_mode == "fundamental_high":
        stock_stats.sort(key=lambda x: x['custom_return'], reverse=True)
        # 上位候補の価値（share_profit）を独自スコアベースに上書きする
        for s in stock_stats:
            s['share_profit'] = s['custom_profit']
        print("ソート戦略: ファンダメンタルズ総合スコア（独自予想利益率）の高い順")
    elif sort_mode == "return_high":
        stock_stats.sort(key=lambda x: x['annual_return'], reverse=True)
        print("ソート戦略: 過去1年間のリターンの高い順")
    else:
        stock_stats.sort(key=lambda x: x['annual_return'], reverse=True)
        
    top_n = strategy_config.get("top_n", 10)
    candidates = stock_stats[:top_n]
    
    print("-" * 50)
    print(f"【上位 {len(candidates)} 社】(最適化ソルバーに渡される候補)")
    for i, c in enumerate(candidates):
        print(f"{i+1}. {c['name']}({c['ticker']}): 現在値={c['current_price']:,.1f}円, リターン={c['annual_return']*100:.1f}%, 配当={c['dividend_yield']*100:.2f}%, PER={c['pe']:.1f}倍, ROE={c['roe']*100:.1f}%, 独自スコア予想利益率={c['custom_return']*100:.1f}%")
        
    return candidates
