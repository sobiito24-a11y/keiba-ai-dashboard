"""Research race gate must not modify formal A or confuse NAR pace with JRA."""
from copy import deepcopy

from bs4 import BeautifulSoup

from core.race_explorer_columns import columns, records
from core.race_explorer_cards import pickup_html
from core.race_explorer_ui import lineup_html
from core.race_explorer_race_gate import (
    race_profile, research_plan, race_gate_html, formal_reference_html,
)


def runner(no, mode="jra", formal=False, rank=None, corner=9, course_rank=8, age="牡4"):
    facts = {
        "runs": [
            {"label": "3走前", "date": "2026-08-01", "finish": "8", "class_raw": "3勝"},
            {"label": "2走前", "date": "2026-09-01", "finish": "2", "class_raw": "OP"},
            {"label": "前走", "date": "2026-10-01", "finish": "3", "class_raw": "Jpn2"},
        ],
        "training": "B",
        "condition_records": [],
        "current_jockey": "騎手",
    }
    context = {"race_data2": "3歳以上 オープン", "race_name": "室町ステークス",
               "race_data1": "ダ1200m", "netkeiba_pace": "H"}
    return {
        "no": str(no), "name": f"馬{no}", "mode": mode, "age": age, "rank": rank,
        "formal_member": formal, "mark": "◎" if formal else "―",
        "candidate_formal_score": float(100 - (rank or 9)) if formal else None,
        "score": 60.0, "ability": 80, "ability_rank": no,
        "corner": corner, "distance": {"value": 80, "rank": 2},
        "course": {"value": 90, "rank": course_rank},
        "explorer_facts": facts, "race_context": context,
        "research_inputs": {"jockey_n": 38, "jockey_rate": 36.0},
        "sort_values": {},
    }


def test_jra_open_has_separate_research_challengers_without_rewriting_formal():
    horses = [runner(i, formal=i <= 5, rank=i if i <= 5 else 9,
                     corner=(8 if i <= 5 else 3), course_rank=(8 if i <= 5 else 2))
              for i in range(1, 10)]
    before = deepcopy(horses)
    cells = records(horses)
    plan = research_plan(horses, cells)
    selected = [horses[i]["no"] for i in plan["indices"]]
    assert plan["profile"]["focus"] == "相手関係・展開整合"
    assert len(selected) <= 6
    assert {"1", "2", "3"}.issubset(selected)
    assert {"6", "7"}.intersection(selected)
    assert any(x == "研究補完" for x in plan["roles"].values())
    assert all("final" not in h for h in horses)
    assert horses == before
    assert [x["key"] for x in columns(horses)[:5]] == ["user", "frame", "no", "name", "age"]
    assert any(x["code"] == "相" for x in plan["signs"]["6"])
    doc = BeautifulSoup(lineup_html(horses), "html.parser")
    assert doc.select_one('tr[data-horse="6"] .gate-number-sign').text == "補"
    assert "相" in doc.select_one('tr[data-horse="6"] .gate-inline-signs').text


def test_nar_keeps_all_saved_top5_and_does_not_use_h_pace_for_routing():
    horses = [runner(i, mode="nar", formal=i <= 5, rank=i if i <= 5 else 8,
                     corner=2, course_rank=2) for i in range(1, 9)]
    # NAR H can be a save default; it cannot become a confident pace signal.
    p = race_profile(horses)
    assert p["pace"] == ""
    assert p["focus"] == "現行Top5＋補完根拠"
    plan = research_plan(horses, records(horses))
    assert set(range(5)).issubset(set(plan["indices"]))
    assert len(plan["indices"]) <= 6
    text = BeautifulSoup(race_gate_html(horses, plan), "html.parser").get_text(" ")
    assert "NAR保存ペースは切替に使わない" in text
    assert not "H（ハイペース）を重視" in text


def test_missing_inputs_never_create_fake_signals_or_fixed_sixth():
    horses = [runner(i, formal=i <= 5, rank=i if i <= 5 else None)
              for i in range(1, 9)]
    for h in horses:
        h["explorer_facts"] = {}
        h["research_inputs"] = {}
        h["corner"] = None
        h["distance"] = {"value": None, "rank": None}
        h["course"] = {"value": None, "rank": None}
    plan = research_plan(horses, records(horses))
    assert len(plan["indices"]) == 5
    assert not any(role == "研究補完" for role in plan["roles"].values())


def test_research_labels_are_escaped_and_formal_scores_remain_separate():
    horses = [runner(1, formal=True, rank=1)]
    horses[0]["name"] = "<script>alert(1)</script>"
    plan = research_plan(horses, records(horses))
    full = race_gate_html(horses, plan) + pickup_html(horses, plan["indices"], plan) + formal_reference_html(horses)
    parsed = BeautifulSoup(full, "html.parser")
    assert not parsed.select("script,img,[onerror],[onclick]")
    assert parsed.select_one(".formal-reference")
    assert parsed.select_one(".pickup-card")
    assert "最終評価" not in parsed.select_one(".pickup-card").get_text(" ")
    assert "正式順位" in parsed.select_one(".formal-reference").get_text(" ")
