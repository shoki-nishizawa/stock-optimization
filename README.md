# 日本株 ポートフォリオ最適化ツール

投資予算・対象セクター・市場区分・リスク制約を設定するだけで、日本の上場企業（約3,800社）の中から**期待利益を最大化する銘柄と購入株数の組み合わせ**を、Google OR-Tools（整数計画法）による数理最適化で自動算出するシステムです。

Streamlit Webダッシュボード上でリアルタイムにシミュレーション＆可視化が行えるほか、CLI（コマンドライン）からの一括実行も可能です。

## 主な機能

- **二段階ポートフォリオ最適化**
  - 第一段階: 独自ファンダメンタルズスコア（PER割安度・ROE・配当利回り・モメンタム）でスクリーニングし、ボラティリティ上限を適用して候補銘柄を抽出
  - 第二段階: OR-Tools CP-SATソルバーにより、予算制約・集中投資制限の下で期待利益を最大化
- **リスク制約の適用**
  - ボラティリティ上限: 年間ボラティリティの閾値を超える銘柄を候補から除外
  - 集中投資制限: 1銘柄あたりの投資額を予算の一定割合以下に制限
- **ハイブリッドデータ自動更新**: ファンダメンタルズは月次、株価データは日次でGitHub Actionsにより自動更新
- **直感的なWebダッシュボード**: Streamlitによるインタラクティブなシミュレーションとグラフ表示
- **株価推移グラフの自動生成**: 上位候補銘柄の過去1年間の株価推移（正規化比較チャート）

---

## 使い方

### 方法1: Webダッシュボード（Streamlit）

```bash
# 仮想環境と依存ライブラリがインストールされた状態で
cd stock-optimization
streamlit run src/app.py
```

ブラウザが自動的に開き、サイドバーから以下の項目をGUIで設定できます。

| 項目 | 説明 |
|---|---|
| 投資予算 (円) | ポートフォリオに充てる総額 |
| 対象セクター | 33業種区分から選択（未選択で全業種） |
| 対象市場 | プライム / スタンダード / グロースから選択 |
| 上位候補数 | ファンダメンタルズスコア上位何社をソルバーに渡すか |
| ボラティリティ上限 | この値を超える銘柄を候補から除外（デフォルト: 0.20） |
| 集中投資制限 (%) | 1銘柄への投資額が予算のこの割合を超えないようにする（デフォルト: 20%） |

「最適化を実行」ボタンを押すと、候補銘柄の株価推移グラフ＋最適化されたポートフォリオ表（PER・ROE・アナリスト評価付き）が表示されます。

### 方法2: CLI（コマンドライン）

```bash
cd stock-optimization
python src/main.py
```

`src/config.json` の内容に基づいてスクリーニング・最適化が実行され、結果がコンソールに出力されます。同時に株価推移グラフ `candidate_trends.png` が保存されます。

---

## 設定ファイル (`src/config.json`)

CLI実行時に使用される設定ファイルです。

```json
{
  "budget": 2000000,
  "filter": {
    "sector": ["医薬品"],
    "market": ["プライム（内国株式）"]
  },
  "strategy": {
    "top_n": 10,
    "max_volatility": 0.2
  },
  "risk_constraints": {
    "max_concentration": 0.2
  }
}
```

### 各項目の説明

| キー | 型 | 説明 |
|---|---|---|
| `budget` | 整数 | 投資に回す総予算（円） |
| `filter.sector` | 文字列リスト | 対象の33業種区分（空リスト `[]` で全業種） |
| `filter.market` | 文字列リスト | 対象の市場区分（空リスト `[]` で全市場） |
| `strategy.top_n` | 整数 | スコア上位何社を最適化ソルバーに渡すか |
| `strategy.max_volatility` | 小数 | ボラティリティ上限（例: `0.2` = 年間20%超の銘柄を除外） |
| `risk_constraints.max_concentration` | 小数 | 集中投資制限（例: `0.2` = 1銘柄あたり予算の20%まで） |

#### 指定可能なセクター例
`"医薬品"`, `"情報・通信業"`, `"電気機器"`, `"銀行業"`, `"サービス業"`, `"輸送用機器"`, `"小売業"` など

#### 指定可能な市場区分
`"プライム（内国株式）"`, `"スタンダード（内国株式）"`, `"グロース（内国株式）"`

---

## データ更新の仕組み（GitHub Actions）

Yahoo Finance APIの厳しいレート制限を回避するため、**ハイブリッドアーキテクチャ**を採用しています。

| ワークフロー | 実行頻度 | 内容 |
|---|---|---|
| `fetch_fundamentals_monthly.yml` | 月1回（毎月1日）+ 手動実行可 | PER・ROE・アナリスト評価を全銘柄分取得し `data/fundamentals.csv` に保存。エラー時も途中結果をコミット（自己修復リジューム対応） |
| `update_data.yml` | 毎日（日本時間 午前4時）+ 手動実行可 | JPX銘柄マスタと過去1年の株価データを一括取得し、`fundamentals.csv` とマージして `data/stock_database.csv` を生成 |

---

## Docker / デプロイ

```bash
# Dockerでのローカル実行
docker build -t stock-opt .
docker run -p 8501:8501 stock-opt
```

Renderなどのクラウドサービスへのデプロイにも対応しています（`dockerfile` を参照）。

---

## ディレクトリ構成

```text
stock-optimization/
├── .github/
│   └── workflows/
│       ├── fetch_fundamentals_monthly.yml  # 月次ファンダデータ自動取得（リジューム対応）
│       └── update_data.yml                 # 日次株価データ取得＋DB統合
├── data/
│   ├── fundamentals.csv                    # PER/ROE/アナリスト評価の生データ
│   └── stock_database.csv                  # 全情報統合済みの分析用DB（アプリが読み込むファイル）
├── scripts/
│   ├── fetch_fundamentals_local.py         # Yahoo Financeからのファンダデータ取得（リジューム機能付き）
│   └── update_database.py                  # 株価取得＋fundamentals.csvとのマージ
├── src/
│   ├── app.py                              # Streamlit Webダッシュボード
│   ├── config.json                         # CLI実行用の設定ファイル
│   ├── data_loader.py                      # DB読み込み＋ファンダスコア算出＋候補抽出
│   ├── main.py                             # CLIエントリーポイント
│   ├── optimizer.py                        # OR-Tools CP-SATによるポートフォリオ最適化
│   └── visualizer.py                       # 株価推移の正規化比較グラフ描画
├── dockerfile                              # Docker/Renderデプロイ用
├── requirements.txt                        # Python依存ライブラリ一覧
└── README.md
```
