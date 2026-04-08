import matplotlib.pyplot as plt
import japanize_matplotlib
import os

def plot_candidates(candidates, output_file="candidate_trends.png"):
    print("-" * 50)
    if output_file:
        print(f"【可視化】過去1年間の株価推移グラフを描画して {output_file} に保存しています...")
    else:
        print(f"【可視化】過去1年間の株価推移グラフを描画しています...")
        
    # グラフのサイズ設定
    fig = plt.figure(figsize=(10, 6))
    
    for c in candidates:
        series = c.get('history')
        if series is None or len(series) == 0:
            continue
            
        # 比較しやすいように各銘柄の直近1年前(初日)の価格を 100 として正規化
        normalized = (series / series.iloc[0]) * 100
        
        # 折れ線グラフのプロット
        plt.plot(normalized.index, normalized.values, label=f"{c['name']} ({c['ticker']})")
        
    plt.title("投資候補銘柄の過去1年間の推移")
    plt.xlabel("日付")
    plt.ylabel("相対価格 (%)")
    
    # 凡例をグラフの外側に配置
    plt.legend(loc="upper left", bbox_to_anchor=(1, 1))
    
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()
    
    # 画像ファイルとして保存
    if output_file:
        plt.savefig(output_file, bbox_inches="tight", dpi=150)
        print(f"グラフの保存が完了しました。（保存先: {output_file}）")
        
    # plt.close() は行わずにfig変数を返す
    return fig
