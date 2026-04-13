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
selected_markets = st.sidebar.multiselect("対象市場", markets, default="プライム（内国株式）")

top_n = st.sidebar.slider("最適化にかける上位候補数", min_value=3, max_value=30, value=10)

# リスク制約セクション
st.sidebar.header("🛡️ リスク制約")
max_volatility = st.sidebar.slider("ボラティリティ上限", min_value=0.10, max_value=0.50, value=0.20, step=0.05,
                                    help="年間ボラティリティがこの値を超える銘柄を候補から除外します")
max_concentration = st.sidebar.slider("1銘柄あたりの投資上限 (%)", min_value=5, max_value=50, value=20, step=5,
                                       help="1銘柄への投資額が予算のこの割合を超えないようにします") / 100.0

if st.sidebar.button("最適化を実行", type="primary"):
    with st.spinner('データを取得・計算しています... (数秒〜数十秒かかります)'):
        # configの代わりとなる設定辞書の構築
        filter_config = {
            "sector": selected_sectors,
            "market": selected_markets
        }
        strategy_config = {
            "top_n": top_n,
            "max_volatility": max_volatility
        }
        
        # 1. 候補の抽出 (data_loader.py)
        ticker_dict = data_loader.get_jpx_tickers(filter_config)
        
        if not ticker_dict:
            st.error("条件に合致する銘柄が見つかりませんでした。条件を緩めてください。")
            st.stop()
            
        candidates = data_loader.extract_candidates(ticker_dict, strategy_config)
        
        if not candidates:
            st.error("データ取得に失敗したか、有効な候補がありませんでした。ボラティリティ上限を緩めてみてください。")
            st.stop()
            
        # 2. グラフ描画 (visualizer.py)
        st.subheader("📊 上位候補銘柄の過去1年の株価推移")
        fig = visualizer.plot_candidates(candidates, output_file=None)
        st.pyplot(fig)
        
        # 3. 最適化実行 (optimizer.py)
        st.subheader("💎 最適化されたポートフォリオ")
        risk_constraints = {
            'max_concentration': max_concentration
        }
        result = optimizer.optimize_portfolio(candidates, budget, risk_constraints)
        
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
                df_portfolio.columns = ['コード', '銘柄名', 'アナリスト評価', '購入株数', '購入金額(円)', 'PER', 'ROE', '予想利益率', '合計予想利益額(円)']
                
                # 条件付きカラーリング
                def color_per(val):
                    if val >= 15:
                        return 'color: #4A90D9; font-weight: bold'
                    else:
                        return 'color: #D94A4A; font-weight: bold'
                
                def color_roe(val):
                    if val >= 0.10:
                        return 'color: #4A90D9; font-weight: bold'
                    else:
                        return 'color: #D94A4A; font-weight: bold'
                
                def color_analyst(val):
                    rating_colors = {
                        '強気買い': 'color: #4A90D9; font-weight: bold',
                        '買い': 'color: #4A90D9; font-weight: bold',
                        '中立': 'color: #4AA84A; font-weight: bold',
                        'やや弱気': 'color: #D9A04A; font-weight: bold',
                        '売り': 'color: #D94A4A; font-weight: bold',
                    }
                    return rating_colors.get(val, 'color: #888888')
                
                # Styler適用
                styled = (df_portfolio.style
                    .applymap(color_per, subset=['PER'])
                    .applymap(color_roe, subset=['ROE'])
                    .applymap(color_analyst, subset=['アナリスト評価'])
                    .format({
                        'PER': '{:.1f}倍',
                        'ROE': lambda x: f'{x*100:.1f}%',
                        '予想利益率': lambda x: f'{x*100:.1f}%',
                        '購入金額(円)': '{:,.0f}',
                        '合計予想利益額(円)': '{:,.0f}',
                    })
                )
                
                # テーブル表示
                st.dataframe(styled, hide_index=True, use_container_width=True)
                st.success("最適化計算が完了しました！ サイドバーから条件を変えて再シミュレーションできます。")
            else:
                st.warning("予算内で買える銘柄がありませんでした。")
        else:
            st.error(result['message'])
