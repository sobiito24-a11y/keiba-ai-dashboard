# Dashboard Batch Prediction Audit

Date: 2026-08-14

## Architecture

- Prediction source of truth: attached Keiba AI Mobile 0.4.1.
- Dashboard calls `core.jra_predictor.predict_jra` / `core.nar_predictor.predict_nar` with `prediction_logic_version="market"`.
- Selected-race display calls the unchanged Mobile `render_market_compare_result`.
- Dashboard-specific code is limited to batch input grouping, navigation, Snapshot persistence and restore.
- No Dashboard ability, rank, band, mark or value formula was added.

## Source identity

The following Dashboard files are byte-identical to the attached Mobile files:

- `core/ver3_ability.py`
- `core/market_compare.py`
- `core/jra_predictor.py`
- `core/nar_predictor.py`

In `app.py`, `main` is the only pre-existing Mobile function changed. Prediction and Market Compare rendering functions are source-identical.

## Input audit

Attachments inspected:

- `Keiba AI Dashboard.zip`
- `keiba_ai_mobile(1).zip`
- `collected_html_jra_0808..zip`
- `20260810.zip`

The two race archives contain 324 HTML files and 72 race_id groups (36 JRA, 36 NAR). Seventy groups have all three Mobile-required kinds (`newspaper`, `speed`, `style`). Two NAR groups contain invalid/missing style pages and are safely skipped. Result pages are identified and excluded from prediction inputs.

## Real-race execution

Four real races were run as one Dashboard batch:

- JRA 202601010501 — 札幌 1R
- JRA 202604020501 — 新潟 1R
- NAR 202635081001 — 盛岡 1R
- NAR 202642081001 — 浦和 1R

Result: 4 predicted, 0 errors. One JRA race was separately run through the Mobile single-race entry and compared against the Dashboard Snapshot for every horse. Ability value, ability rank, ability band, current-evaluation rank, mark and value flag all matched.

The four-race `.keiba` payload was saved in memory and reloaded. The loaded event Snapshot was exactly equal to the saved event Snapshot.

## `.keiba`

- Container: ZIP
- Schema: `schema_version = 1`
- Members: `manifest.json`, `snapshot.json`
- Integrity: SHA-256 of `snapshot.json`
- Unit: date × JRA/NAR × venue, with optional all-venue event file
- Source HTML: not embedded
- Restore: serialized `PredictionResult` only; predictors are not called
- User selection: stored separately without rebuilding historical prediction values

## Regression

Final command:

```bash
python -m pytest -q
```

Result: `316 passed, 16 subtests passed`.

Tracked test files deleted: 0.
