# Keiba AI Dashboard

「その日の買うべきレース一覧」を表示するための、Keiba AI Mobileとは独立したStreamlitプロジェクトです。

このPhaseではDashboardの土台とSummary JSONの読込画面だけを用意しています。HTML取得、HTML解析、Summary生成、レース一覧、Mobile詳細への遷移はまだ実装していません。

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

## ディレクトリ

- `pages/`: JRA WeekendとNAR Dailyの独立ページ
- `core/`: Dashboard共通の軽量Summaryローダー
- `tools/`: 将来のHTML取得・Summary生成用エントリーポイント
- `collected_html/`: 将来収集するJRA/NAR HTMLの保存先
- `results/`: 将来生成する分析結果の保存先
- `tests/`: Dashboard単体テスト

Keiba AI MobileのParser、PredictionResult、AI点、印、能力評価、予想ロジックはこのプロジェクトへ含めません。
