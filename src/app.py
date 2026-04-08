import streamlit as st
import pandas as pd
import data_loader
import optimizer
import visualizer

# Streamlitのページ設定
st.set_page_config(page_title="日本株ポートフォリオ最適化", page_icon="📈", layout="wide")

st.title("📈 日本株ポートフォリオ最適化ツール")
st.markdown("予算と投資戦略を設定すると、AIソルバー（OR-Tools）が最も期待利益の大きい銘柄の組み合わせを計算します。")

# サイドバー設定
st.sidebar.header("⚙️ 最適化設定")

budget = st.sidebar.number_input("投資予算 (円)", min_value=0, value=100000, step=10000)

sectors = ["医薬品", "情報・通信業", "電気機器", "銀行業", "サービス業", "輸送用機器", "小売業"]
selected_sectors = st.sidebar.multiselect("対象セクター (未選択で全業種)", sectors, default=None)

markets = ["プライム（内国株式）", "スタンダード（内国株式）", "グロース（内国株式）"]
selected_markets = st.sidebar.multiselect("対象市場", markets, default=None)

sort_options = {
    "ファンダメンタルズ総合スコアが高い順 (おすすめ)": "fundamental_high",
    "ボラティリティが高い順 (リスク・リターン重視)": "volatility_high",
    "過去1年リターンが高い順 (実績重視)": "return_high"
}
selected_sort_label = st.sidebar.selectbox("スクリーニング基準", list(sort_options.keys()))

top_n = st.sidebar.slider("最適化にかける上位候補数", min_value=3, max_value=30, value=10)

if st.sidebar.button("最適化を実行", type="primary"):
    with st.spinner('データを取得・計算しています... (数秒〜数十秒かかります)'):
        # configの代わりとなる設定辞書の構築
        filter_config = {
            "sector": selected_sectors,
            "market": selected_markets
        }
        strategy_config = {
            "sort_by": sort_options[selected_sort_label],
            "top_n": top_n
        }
        
        # 1. 候補の抽出 (data_loader.py)
        ticker_dict = data_loader.get_jpx_tickers(filter_config)
        
        if not ticker_dict:
            st.error("条件に合致する銘柄が見つかりませんでした。条件を緩めてください。")
            st.stop()
            
        candidates = data_loader.extract_candidates(ticker_dict, strategy_config)
        
        if not candidates:
            st.error("データ取得に失敗したか、有効な候補がありませんでした。")
            st.stop()
            
        # 2. グラフ描画 (visualizer.py)
        st.subheader("📊 上位候補銘柄の過去1年の株価推移")
        fig = visualizer.plot_candidates(candidates, output_file=None)
        st.pyplot(fig)
        
        # 3. 最適化実行 (optimizer.py)
        st.subheader("💎 最適化されたポートフォリオ")
        result = optimizer.optimize_portfolio(candidates, budget)
        
        if result['success']:
            # メトリクス表示
            col1, col2, col3 = st.columns(3)
            col1.metric("合計購入金額", f"¥{result['total_invested']:,}")
            col2.metric("見込み単年期待利益", f"¥{result['expected_profit']:,}")
            col3.metric("予算残高", f"¥{result['remaining_budget']:,}")
            
            # DataFrame化して見た目を整える
            df_portfolio = pd.DataFrame(result['portfolio'])
            
            if not df_portfolio.empty:
                df_portfolio = df_portfolio[['ticker', 'name', 'analyst_rating', 'shares', 'cost', 'pe', 'roe', 'custom_return', 'profit']]
                
                # フォーマット調整
                df_portfolio['pe'] = df_portfolio['pe'].apply(lambda x: f"{x:.1f}倍")
                df_portfolio['roe'] = df_portfolio['roe'].apply(lambda x: f"{x*100:.1f}%")
                df_portfolio['custom_return'] = df_portfolio['custom_return'].apply(lambda x: f"{x*100:.1f}%")
                
                df_portfolio.columns = ['コード', '銘柄名', 'アナリスト評価', '購入株数', '購入金額(円)', 'PER', 'ROE', '予想利益率', '合計予想利益額(円)']
                
                # テーブル表示
                st.dataframe(df_portfolio, hide_index=True, use_container_width=True)
                st.success("最適化計算が完了しました！ サイドバーから条件を変えて再シミュレーションできます。")
            else:
                st.warning("予算内で買える銘柄がありませんでした。")
        else:
            st.error(result['message'])
