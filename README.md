# Keiba AI Dashboard

Keiba AI Mobileの現行予想を、複数レース・複数会場について一括実行し、会場→レースを選んでMobileと同じ画面で閲覧するStreamlitアプリです。

Dashboard専用の能力式・印式はありません。`core/jra_predictor.py`、`core/nar_predictor.py`、Market Compare、Ver3能力コア、Mobile表示関数をそのまま使用します。

## セットアップ

```bash
python -m venv .venv
python -m pip install -r requirements.txt -r requirements-test.txt
streamlit run app.py
```

`pandas`はMobileのNotebook由来処理との互換性のため`2.x`を使用します。

## 新規一括予想

1. 「新規一括予想」を選ぶ
2. 複数HTMLまたは収集ZIPをまとめて投入する
3. 「一括予想データ作成」を押す
4. 開催日、JRA/NAR、会場、レースを順に選ぶ
5. 選択したレースをMobileと同じMarket Compare画面で確認する
6. 「この開催を保存」または「全会場まとめて保存」で`.keiba`を保存する

HTMLはファイル名だけでなく、canonical、og:url、ページURL、DOM、title、race_idから分類します。Mobileと同様、`newspaper`、`speed`、`style`が予想の必須入力です。`jockey`、`oikiri`などは任意で、欠損しても必須HTMLが揃っていれば予想できます。

同一race_id・同一kindの異なるHTMLは自動上書きしません。重複エラーとしてそのレースをスキップし、他レースの処理を継続します。バイト同一の重複だけは1件へ統合します。

## 保存した予想を開く

1. 「保存した予想を開く」を選ぶ
2. `.keiba`をアップロードする
3. 会場・レースを選択する

保存済み`PredictionResult`を直接復元するため、元HTMLの再解析や最新ロジックでの再予想は行いません。保存当時の能力値、能力順位、能力帯、今回評価順位、印、妙味、オッズ、条件材料、ユーザー選択を表示します。

## `.keiba`形式

`.keiba`はZIPコンテナで、次の2ファイルだけを保持します。

- `manifest.json`: 形式、schema_version、アプリ/ロジック版、件数、SHA-256
- `snapshot.json`: 開催と全レースのPrediction Snapshot

現在の`schema_version`は`1`です。入力HTMLは含めません。結果照合用に`race_id`、`horse_no`、予想時刻、印、妙味、予想時点オッズを機械可読で保持します。

破損、空ファイル、未対応schema、重複race_id、整合性不一致、安全でないZIPパスは明示的に拒否します。

## 主な構成

- `app.py`: Mobile表示関数とDashboard入口
- `core/dashboard_application.py`: 一括予想/保存読込UI、会場・レースナビゲーション
- `core/dashboard_batch.py`: ZIP展開、HTML分類、race_idグループ化、Mobile predictor呼出し
- `core/prediction_snapshot.py`: `.keiba`生成、検証、保存時点PredictionResult復元
- `core/jra_predictor.py`, `core/nar_predictor.py`: Mobileと同一の予想入口
- `core/ver3_ability.py`, `core/market_compare.py`: Mobileと同一の能力/比較実装
- `tests/`: Dashboard既存テスト、Mobile完全回帰、一括予想/Snapshot/UI追加テスト

## テスト

```bash
python -m pytest -q
```

予想ロジックの一致対象は、能力値、能力順位、AA/A/B/C/Z、AI今回評価順位、◎○▲△☆、妙味ありです。
