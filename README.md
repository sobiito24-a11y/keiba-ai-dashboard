# Keiba AI Dashboard

「その日の買うべきレース一覧」を表示するための、Keiba AI Mobileとは独立したStreamlitプロジェクトです。

トップ画面からJRA/NARの収集済みHTML ZIPをアップロードすると、既存のSummary Builderで解析し、Dashboardを自動更新します。BUYは`strategy_score`順のスマホ向けカード、HOLDは折りたたみ、SKIPは件数だけを表示し、上位5レースを「今日のBEST5」にまとめます。

各カードの「詳細を見る」から、Summaryの`detail_path`が指す既存PredictionResult JSONをDashboard内で開けます。

## セットアップ

```bash
python -m venv .venv
python -m pip install -r requirements.txt
streamlit run app.py
```

## Summary JSON

- JRA Weekend: `assets/analysis/weekend_summary.json`
- NAR Daily: `assets/analysis/nar_daily_summary.json`

JSONが存在しない場合、各画面には「データがありません」と表示されます。

## HTML ZIPアップロード

トップ画面の「HTML ZIPアップロード」から次の形式を選択できます。

- `collected_html_jra_xxxxx.zip`
- `collected_html_nar_xxxxx.zip`

ZIPは一時ディレクトリへ安全に展開され、JRAは`tools/build_weekend_summary.py`、NARは`tools/build_daily_summary.py`を内部実行します。CLIを手動実行する必要はありません。

## ディレクトリ

- `pages/`: JRA Weekend、NAR Daily、既存PredictionResult JSONの詳細ページ
- `core/`: Dashboard共通の軽量Summaryローダー
- `tools/`: 将来のHTML取得・Summary生成用エントリーポイント
- `collected_html/`: 将来収集するJRA/NAR HTMLの保存先
- `results/`: 将来生成する分析結果の保存先
- `tests/`: Dashboard単体テスト

Parser、PredictionResult、AI点、印、能力評価、予想ロジックはDashboard表示の変更対象外です。
