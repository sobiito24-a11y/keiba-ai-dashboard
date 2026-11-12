from copy import deepcopy
from bs4 import BeautifulSoup

from core.research_six_dimensions import evaluate, detail_html, _jurisdiction


def sample_horse():
    return dict(
        no="8", name="転入馬<test>", mode="nar", score="100", mark="◎", ability_rank=1,
        race_context=dict(race_date="2026-11-14", venue="名古屋",
                          surface="ダート", distance="1400m", netkeiba_pace="M"),
        age="牝3", start_rank=2, corner=3, style="先行",
        research_inputs=dict(jockey_n=40, jockey_rate=38),
        research_sabcd_weight_class=dict(grade="A", score=.6,
                                          materials=dict(weight_delta=-2,
                                                         weight_vs_field=-3.5)),
        profile=dict(class_shift="判定不可（中央と地方のクラス体系）",
                     runs=[
                         dict(date="2026-11-10", venue="名古屋", surface="ダ", distance="1400m", finish="2着", time_index=51, class_raw="C4"),
                         dict(date="2026-11-02", venue="東京", surface="ダ", distance="1600m", finish="9着", time_index=98, class_raw="1勝クラス"),
                         dict(date="2026-10-12", venue="中京", surface="ダ", distance="1400m", finish="2着", time_index=105, class_raw="未勝利"),
                     ]),
    )


def test_venue_classification_is_explicit_not_guessed():
    assert _jurisdiction("東京競馬場") == "jra"
    assert _jurisdiction("名古屋") == "nar"
    assert _jurisdiction("未知の海外競馬場") is None


def test_central_to_nar_transfer_does_not_compare_time_indices_or_demote():
    h = sample_horse()
    original = deepcopy(h)
    report = evaluate(h)
    assert report["transfer_evidence"] is True
    assert report["local_count"] == 1
    assert report["other_circuit_count"] == 2
    assert report["factors"]["recent"]["grade"] == "—"
    assert report["factors"]["course"]["grade"] == "—"
    assert report["factors"]["distance"]["grade"] == "—"
    assert "中央指数 98/105" in report["factors"]["recent"]["reason"]
    assert "直接合算・比較しません" in report["factors"]["recent"]["reason"]
    assert report["factors"]["conditions"]["grade"] == "—"
    assert report["factors"]["jockey"]["grade"] == "A"
    assert report["factors"]["development"]["grade"] == "A"
    assert h == original
    assert h["mark"] == "◎" and h["research_sabcd_weight_class"]["grade"] == "A"


def test_two_verified_local_runs_allow_provisional_local_grades():
    h = sample_horse()
    h["profile"]["runs"][1] = dict(date="2026-11-02", venue="名古屋",
        surface="ダ", distance="1400m", finish="1着", time_index=42)
    result = evaluate(h)
    assert result["local_count"] == 2
    assert result["factors"]["distance"]["grade"] == "A"
    assert result["factors"]["course"]["grade"] == "A"
    assert result["factors"]["recent"]["grade"] == "A"


def test_unknown_jockey_not_low_grade():
    h = sample_horse()
    h["research_inputs"]["jockey_n"] = None
    assert evaluate(h)["factors"]["jockey"]["grade"] == "—"


def test_future_results_are_not_features_and_style_mismatch_is_visible():
    h = sample_horse()
    h["profile"]["runs"].insert(0, dict(date="2026-11-15", venue="名古屋", finish="1着", time_index=130))
    h["start_rank"] = 9
    assert "位置?" in evaluate(h)["factors"]["development"]["reason"]
    assert evaluate(h)["factors"]["development"]["grade"] == "—"
    assert evaluate(h)["recent_source_count"] == 3


def test_details_are_six_compact_cards_and_escape_untrusted_content():
    h = sample_horse()
    html = BeautifulSoup(detail_html(h), "html.parser")
    assert len(html.select(".six-factor-item")) == 6
    assert len(html.select(".six-factor-more > summary")) == 6
    assert html.select_one(".six-factor-transfer") is not None
    assert "<test>" not in str(html)
    assert html.select_one(".detail-six-factors h4").text.startswith("6項目")


def test_incomplete_context_never_yields_wrong_D():
    h = sample_horse()
    h["race_context"].pop("race_date")
    grades = evaluate(h)["factors"]
    assert all(grades[key]["grade"] == "—" for key in ("distance", "course", "recent"))


def test_older_central_history_beyond_last_three_is_kept_separate():
    h = sample_horse()
    # Last 3 starts are local, but the saved original horse record also
    # contains an earlier JRA run.  A 3-run-only view would lose this fact.
    h["profile"]["runs"] = [
        dict(date="2026-11-10", venue="名古屋", surface="ダ", distance="1400m", finish="2着", time_index=51),
        dict(date="2026-11-02", venue="名古屋", surface="ダ", distance="1400m", finish="1着", time_index=42),
        dict(date="2026-10-12", venue="名古屋", surface="ダ", distance="1400m", finish="3着", time_index=48),
    ]
    h["profile"]["extended_history"] = [
        dict(date="2026-08-12", venue="東京", surface="ダ", distance="1400m", finish="8着", time_index=107),
    ]
    data = evaluate(h)
    assert data["transfer_evidence"] is True
    assert data["other_circuit_count"] == 1
    assert data["local_count"] == 3
    assert "中央指数 107" in data["factors"]["recent"]["reason"]
    assert data["factors"]["recent"]["grade"] == "A"  # All three placed, but latest was 2nd


def test_saved_source_older_runs_are_filtered_before_the_current_race():
    from datetime import date
    from core.candidate_profile import _saved_extended_history
    raw = dict(_past_runs=[
        dict(race_date="2026-11-10", racecourse="名古屋", surface="ダ", distance=1400, position=2, value=45),
        dict(race_date="2026-10-22", racecourse="名古屋", surface="ダ", distance=1400, position=1, value=44),
        dict(race_date="2026-09-18", racecourse="名古屋", surface="ダ", distance=1400, position=3, value=40),
        dict(race_date="2026-08-12", racecourse="東京", surface="ダ", distance=1400, position=9, value=107),
        dict(race_date="2026-11-15", racecourse="東京", surface="ダ", distance=1400, position=1, value=120),
    ])
    saved = _saved_extended_history(raw, date(2026, 11, 14))
    assert len(saved) == 4
    assert saved[-1]["venue"] == "東京"
    assert saved[-1]["time_index"] == "107"
    assert all(str(row["date"]) < "2026-11-14" for row in saved)
