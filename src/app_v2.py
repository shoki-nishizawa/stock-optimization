import streamlit as st
import pandas as pd
import data_loader_v2
import optimizer_v2
import visualizer

# Streamlitのページ設定
st.set_page_config(page_title="日本株ポートフォリオ最適化 v2.0", page_icon="📈", layout="wide")

st.title("📈 日本株ポートフォリオ最適化ツール Version 2.0")
st.markdown("AI予測スコア（安全性・成長性）と配当利回りを考慮し、クオリティ・高配当戦略に基づいた最適なポートフォリオを計算します。")

# サイドバー設定
st.sidebar.header("⚙️ 最適化設定")

budget = st.sidebar.number_input("投資予算 (円)", min_value=0, value=100000, step=10000)

sectors = [
    '水産・農林業', '鉱業', '建設業', '食料品', '繊維製品', 'パルプ・紙', '化学', '医薬品', 
    '石油・石炭製品', 'ゴム製品', 'ガラス・土石製品', '鉄鋼', '非鉄金属', '金属製品', '機械', 
    '電気機器', '輸送用機器', '精密機器', 'その他製品', '電気・ガス業', '陸運業', '海運業', '空運業', 
    '倉庫・運輸関連業', '情報・通信業', '卸売業', '小売業', '銀行業', '証券、商品先物取引業', 
    '保険業', 'その他金融業', '不動産業', 'サービス業'
]
selected_sectors = st.sidebar.multiselect("対象セクター (未選択で全業種)", sectors, default=None)

markets = ["プライム（内国株式）", "スタンダード（内国株式）", "グロース（内国株式）"]
selected_markets = st.sidebar.multiselect("対象市場", markets, default="プライム（内国株式）")

top_n = st.sidebar.slider("最適化にかける上位候補数", min_value=3, max_value=30, value=10)

# リスク制約セクション
st.sidebar.header("🛡️ リスク制約")
max_volatility = st.sidebar.slider("ボラティリティ上限", min_value=0.10, max_value=0.50, value=0.20, step=0.05,
                                    help="年間ボラティリティ(株価変動率)がこの値を超える銘柄を候補から除外します")
max_concentration = st.sidebar.slider("1銘柄あたりの投資上限 (%)", min_value=5, max_value=50, value=20, step=5,
                                       help="1銘柄への投資額が予算のこの割合を超えないようにします") / 100.0

st.sidebar.header("🤖 AI推論設定")
lgbm_threshold = st.sidebar.slider("AI(LGBM)の合格ライン", min_value=0.1, max_value=0.8, value=0.5, step=0.05,
                                   help="LGBMモデルによる「勝ち」確率の閾値です。厳しすぎて銘柄が残らない場合は下げてください。")

if st.sidebar.button("最適化を実行", type="primary"):
    
    # プログレスバーとテキスト用のプレースホルダーを作成
    progress_text = st.empty()
    progress_bar = st.progress(0.0)
    
    def update_progress(text, value):
        progress_text.text(f"⏳ {text}")
        progress_bar.progress(float(value))
        
    with st.spinner('AIスコアを動的に推論しています... (数十秒〜数分かかります)'):
        filter_config = {
            "sector": selected_sectors,
            "market": selected_markets
        }
        strategy_config = {
            "top_n": top_n,
            "max_volatility": max_volatility,
            "lgbm_threshold": lgbm_threshold
        }
        
        # 1. 候補の抽出 (data_loader_v2.py)
        ticker_dict = data_loader_v2.get_jpx_tickers(filter_config)
        
        if not ticker_dict:
            st.error("条件に合致する銘柄が見つかりませんでした。条件を緩めてください。")
            st.stop()
            
        candidates = data_loader_v2.extract_candidates(
            ticker_dict, 
            strategy_config, 
            _progress_callback=update_progress
        )
        
        # 処理完了したらプログレスバーを消去
        progress_text.empty()
        progress_bar.empty()
        
        if not candidates:
            st.error("初期スクリーニングで全滅したか、AI（LGBM）の推論を突破（勝ち判定）した銘柄が1つもありませんでした。セクターやボラティリティ上限などの条件を変更してみてください。")
            st.stop()
            
        # 2. グラフ描画 (visualizer.py は既存を使い回す)
        st.subheader("📊 上位候補銘柄の過去1年の株価推移")
        fig = visualizer.plot_candidates(candidates)
        st.pyplot(fig)
        
        # 3. 最適化実行 (optimizer_v2.py)
        st.subheader("💎 最適化されたポートフォリオ (クオリティ・高配当)")
        risk_constraints = {
            'max_concentration': max_concentration
        }
        result = optimizer_v2.optimize_portfolio(candidates, budget, risk_constraints)
        
        if result['success']:
            
            # メトリクス表示
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("合計購入金額", f"¥{result['total_invested']:,}")
            col2.metric("見込み単年期待利益", f"¥{result['expected_profit']:,}")
            col3.metric("見込み合計配当金", f"¥{result['expected_total_dividend']:,}")
            col4.metric("予算残高", f"¥{result['remaining_budget']:,}")
            
            # DataFrame化して見た目を整える
            df_portfolio = pd.DataFrame(result['portfolio'])
            
            if not df_portfolio.empty:
                df_display = df_portfolio[['ticker', 'name', 'share_price', 'shares', 'cost', 'combined_score', 'dividend_yield', 'expected_dividend', 'pe', 'roe']].copy()
                df_display.columns = ['コード', '銘柄名', '現在株価(円)', '購入株数', '購入金額(円)', 'AIスコア', '予想配当利回り', '予想配当総額(円)', 'PER', 'ROE']
                
                # 条件付きカラーリング
                def color_score(val):
                    if val >= 0.7:
                        return 'color: #4AA84A; font-weight: bold'
                    elif val >= 0.4:
                        return 'color: #4A90D9; font-weight: bold'
                    else:
                        return 'color: #D94A4A; font-weight: bold'

                def color_yield(val):
                    if val >= 0.04:
                        return 'color: #4AA84A; font-weight: bold'
                    elif val >= 0.02:
                        return 'color: #4A90D9; font-weight: bold'
                    else:
                        return 'color: #888888'

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
                
                # 表示形式を整える
                styled = (df_display.style
                    .map(color_score, subset=['AIスコア'])
                    .map(color_yield, subset=['予想配当利回り'])
                    .map(color_per, subset=['PER'])
                    .map(color_roe, subset=['ROE'])
                    .format({
                        '現在株価(円)': '{:,.0f}',
                        '購入金額(円)': '{:,.0f}',
                        'AIスコア': '{:.2f}',
                        '予想配当利回り': lambda x: f'{x*100:.2f}%',
                        '予想配当総額(円)': '{:,.0f}',
                        'PER': '{:.1f}倍',
                        'ROE': lambda x: f'{x*100:.1f}%',
                    })
                )
                
                # テーブル表示
                st.dataframe(styled, hide_index=True, width='stretch', height=400)
                st.success("最適化計算が完了しました！ AIスコアと配当金を両立したポートフォリオが構築されました。")
                
                st.markdown("---")
                st.subheader("💡 銘柄ごとのAI詳細レポート")
                for _, row in df_portfolio.iterrows():
                    with st.expander(f"{row['ticker']} {row['name']} (AIスコア: {row['combined_score']:.2f})"):
                        st.write(row['llm_summary'])
                        
                st.info("⚠️ **免責事項 / 注意書き**\n\n本ツールが算出する「期待利益」および「ポートフォリオ」は、過去の実績や独自のアルゴリズムに基づくあくまでシミュレーション結果であり、将来の運用成果を一切保証するものではありません。実際の投資判断は、必ずご自身のリスク許容度に合わせて**自己責任**でお願いいたします。")
            else:
                st.warning("予算内で買える銘柄がありませんでした。")
        else:
            st.error(result['message'])
