from __future__ import annotations

import pytest

from core.jra_notebook_logic import normalize_jra_jockey_name_for_compare, same_jra_jockey_for_compare


@pytest.mark.parametrize("current,previous", [
    ("松山", "松山弘平"), ("Ｃ．ルメール", "C.ルメール"),
    ("M.デムーロ", "ミルコ・デムーロ"), ("川田", "川田将雅"),
    ("坂井瑠星（継）", "坂井"), ("▲団野", "団野大成"),
])
def test_jra_same_jockey_text_variants_are_continued(current, previous):
    assert same_jra_jockey_for_compare(current, previous)


@pytest.mark.parametrize("current,previous", [
    ("横山武史", "横山典弘"), ("岩田康誠", "岩田望来"),
    ("鮫島克駿", "鮫島良太"), ("山田敬士", "山本聡哉"),
])
def test_jra_different_jockeys_remain_changes(current, previous):
    assert not same_jra_jockey_for_compare(current, previous)


def test_normalization_does_not_mutate_raw_display_value():
    raw = " Ｃ．ルメール（継） "
    assert normalize_jra_jockey_name_for_compare(raw) == "ルメール"
    assert raw == " Ｃ．ルメール（継） "
