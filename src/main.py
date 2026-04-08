import data_loader
import optimizer
import visualizer

def main():
    try:
        config = data_loader.load_config("src/config.json")
    except Exception as e:
        print("config.json の読み込みに失敗しました。", e)
        return
        
    budget = config.get("budget", 1_000_000)
    filter_config = config.get("filter", {})
    strategy_config = config.get("strategy", {})
    
    # 1. JPXから全件抽出してフィルタ
    ticker_dict = data_loader.get_jpx_tickers(filter_config)
    
    # 2. yfinanceから過去データ取得 & 指標計算 & TOP N絞り込み
    candidates = data_loader.extract_candidates(ticker_dict, strategy_config)
    
    if not candidates:
        return
        
    # 3. リストに上がった候補を可視化
    visualizer.plot_candidates(candidates, "candidate_trends.png")
        
    # 4. ナップサック問題による最適化 (OR-Tools)
    optimizer.optimize_portfolio(candidates, budget)

if __name__ == "__main__":
    main()
