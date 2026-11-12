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

## 朝の自動予想

Mobile側のnetkeiba HTML collectorとDashboard側の一括予想処理を使い、HTML収集から`.keiba`作成まで1コマンドで実行できます。Dashboard専用の予想ロジックは追加せず、通常画面と同じ`prediction_logic_version="market"`でPrediction Snapshotを作成します。

地方のみ:

```bash
python tools\morning_pipeline.py ^
  --today ^
  --mode nar ^
  --data-root "C:\Users\28011\Documents\Codex\Keiba_AI_Data\morning"
```

JRAのみ:

```bash
python tools\morning_pipeline.py ^
  --today ^
  --mode jra ^
  --data-root "C:\Users\28011\Documents\Codex\Keiba_AI_Data\morning"
```

全部:

```bash
python tools\morning_pipeline.py ^
  --today ^
  --mode all ^
  --data-root "C:\Users\28011\Documents\Codex\Keiba_AI_Data\morning"
```

保存先は日付ごとに分かれます。

```text
Keiba_AI_Data/
  morning/
    20260908/
      html/
        jra/
        nar/
      logs/
      20260908_all.keiba
```

実行終了後は、Dashboardを起動し、「保存した予想を開く」から`YYYYMMDD_all.keiba`を開いて閲覧します。既存HTMLは通常再利用し、再取得・再作成する場合だけ`--overwrite`を指定します。

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

## NAR公式・当日オッズ（無料・発走前の参考表示）

NARを選択して「オッズ更新」を押すと、地方競馬情報サイトが提供する
**当日オッズZIP**をその操作時だけダウンロードし、表示中の競馬場／開催日／Rを照合して、
単勝・複勝・馬連・ワイドを読取ります。
出馬表・純能力・総合SABCD・正式印・予想／保存スナップショットは変更しません。

- [NAR公式・本日のレース（データダウンロード）](https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop)
- [公式・CSV/ZIP説明書](https://www.keiba.go.jp/pdf/manual/data_pdf_manual.pdf)
- [利用規約](https://www.keiba.go.jp/terms.html)をご確認ください。操作はユーザーの明示的な押下時のみで、
  自動巡回・常時監視・データの再配布は行いません。個人の確認目的の機能です。
- NAR当日ZIPは約2分ごとに更新されます。取得したZIPはその端末のStreamlitセッション内で
  120秒間だけ再利用し、複数レースを切り替えても公式サイトへのアクセスを増やしません。
- CSVには馬名・個別オッズ発表時刻がありません。
  出走馬番号は予想の保存済み馬番と照合し、**ZIPファイル名の作成時刻は
  個別価格の発表時刻と同一とは保証しません**。現在価格・確定価格と誤表示しないよう注意しています。
- 不明・未発売・取消・競走後などの価格は正確な最新価格とみなせません。
  見えているオッズも締切まで変動するため、馬券購入前には公式販売画面と照合してください。
- NAR公式へのアクセスが遮断された、公式のCSV仕様が変わったなどの場合は更新できません。
  その場合は公式サイトから**当日の「オッズ情報」ZIP**を自分でダウンロードし、
  アプリの「オッズファイルを一括取込」からアップロードできます。JRAでは従来どおり
  接続設定またはHTML／JSON／画像による取込が必要です。
- 現在のオッズ取得は購入や期待値の実証を意味せず、買い目提案／自動投票は行いません。
