"""UI-only class/rest notes must not change prediction scores or saved rows."""
from copy import deepcopy

import pytest
from bs4 import BeautifulSoup

from core.rest_interval_attention import attention
from core.race_explorer_ui import _cell


@pytest.mark.parametrize("days,grade,expected,kind", [
    (69, "C", None, None),
    (70, "C", "調教C/D注意", "caution"),
    (179, "D", "調教C/D注意", "caution"),
    (70, "B", "調教A/B確認", "info"),
    (179, "A", "調教A/B確認", "info"),
    (180, "C", "長休×調教C/D", "caution"),
    (365, "D", "長休×調教C/D", "caution"),
    (180, "B", "長休×調教A/B", "info"),
    (365, "A", "長休×調教A/B", "info"),
    (70, None, "調教未取得", "info"),
    (180, None, "長休・調教未取得", "info"),
    (180, "対象外", "長休・調教未取得", "info"),
])
def test_jra_interval_with_actual_saved_training(days, grade, expected, kind):
    result = attention(days, "jra", grade)
    if expected is None:
        assert result is None
    else:
        assert result[0] == expected
        assert result[1] == kind
        assert "減点なし" in result[2] or "加点なし" in result[2] or "機械的減点なし" in result[2] or "判定できません" in result[2]


@pytest.mark.parametrize("days,expected", [
    (0, None), (69, None), (89, None),
    (90, "3ヶ月超・条件確認"),
    (179, "3ヶ月超・条件確認"),
    (180, "半年超・条件確認"),
    (364, "半年超・条件確認"),
    (365, "1年以上・状態確認"),
])
def test_nar_interval_never_infers_jra_training(days, expected):
    result = attention(days, "nar", "D")
    assert (result[0] if result else None) == expected
    if result:
        assert result[1] == "info"
        assert "一律減点なし" in result[2] or "軽視せず" in result[2] or "休養日数だけで消さず" in result[2]


@pytest.mark.parametrize("days,mode", [
    (None, "jra"), ("180", "jra"), (True, "jra"),
    (-1, "nar"), (float("nan"), "jra"), (float("inf"), "nar"),
    (20000, "nar"), (180, "invalid"),
])
def test_missing_or_invalid_rest_is_never_guessed(days, mode):
    assert attention(days, mode, "C") is None


@pytest.mark.parametrize("mode,days,grade,label", [
    ("jra", 180, "D", "長休×調教C/D"),
    ("jra", 75, "A", "調教A/B確認"),
    ("nar", 190, None, "半年超・条件確認"),
])
def test_existing_interval_cell_preserved_and_notice_is_small(mode, days, grade, label):
    horse = {"mode": mode, "no": 8, "name": "例示馬", "score": 42}
    cells = {"rest_days": days, "rest_label": f"{days}日ぶり",
             "training": grade, "ability": 88}
    original = deepcopy((horse, cells))
    snippet = _cell(horse, cells, "rest_days")
    tag = BeautifulSoup(snippet, "html.parser")
    assert f"{days}日ぶり" in tag.text
    assert f"{days}日" in tag.text
    note = tag.select_one("small.rest-attention")
    assert note is not None and note.text == label
    assert " title=" in snippet and "rest-attention-" in snippet
    assert (horse, cells) == original


def test_no_rest_note_without_verified_interval_and_no_scoring_mutation():
    horse = {"mode": "jra", "no": 5, "name": "例", "score": 99}
    cells = {"rest_days": None, "rest_label": "未取得", "training": "C"}
    assert "rest-attention" not in _cell(horse, cells, "rest_days")
    cells = {"rest_days": 35, "rest_label": "中4週", "training": "D"}
    assert "rest-attention" not in _cell(horse, cells, "rest_days")
    assert horse["score"] == 99
