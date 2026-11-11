from copy import deepcopy

from core.class_grade_attention import evaluate


def context(mode="JRA", level=2, age="3歳以上", venue="東京",
            discipline="flat", label="2勝"):
    return dict(class_family=mode, class_level_v2=level,
                age_restriction_v2=age, venue_v2=venue,
                race_discipline_v2=discipline, class_label_v2=label)


def run(label, ctx, finish=2, surface="芝"):
    return dict(label=label, class_context=ctx, finish=finish, surface=surface)


def test_upper_class_placing_is_highlighted_without_points():
    current = context()
    previous = run("前走", context(level=6, label="G3"), 3)
    original = deepcopy(previous)
    result = evaluate(current, [previous], current_surface="芝")
    assert result["label"] == "格上3着内"
    assert "前走G3 3着" in result["reason"]
    assert result["scoring_effect"] == 0
    assert previous == original


def test_grade_achievement_remains_history_if_age_group_does_not_match():
    current = context()
    prior = run("前走", context(level=8, age="3歳限定", label="G1"), 2)
    result = evaluate(current, [prior], current_surface="芝")
    assert result["label"] == "重賞好走歴"
    assert result["scoring_effect"] == 0


def test_nar_cross_venue_levels_are_not_compared():
    today = context(mode="NAR", level=12, age="一般", venue="佐賀", label="C2")
    old = run("前走", context(mode="NAR", level=10, age="一般", venue="門別", label="C3"))
    assert evaluate(today, [old])["label"] == "比較資料不足"


def test_unknown_age_is_not_a_verified_class_transition():
    today = context(mode="NAR", level=13, age="一般", venue="佐賀", label="C1")
    old = run("前走", context(mode="NAR", level=12, age="不明", venue="佐賀", label="C2"))
    assert evaluate(today, [old])["label"] == "比較資料不足"


def test_promotion_notice_requires_comparable_immediate_past():
    today = context(level=2, label="2勝")
    old = run("前走", context(level=1, label="1勝"), finish=1)
    assert evaluate(today, [old])["label"] == "前走から昇級"
    other = run("2走前", context(level=1, label="1勝"), finish=1)
    assert evaluate(today, [other])["label"] == "特記事項なし"


def test_same_class_placing_without_fabricated_ability_adjustment():
    today = context()
    old = run("2走前", context(), finish=3)
    result = evaluate(today, [old])
    assert result["label"] == "同級3着内"
    assert "2走前2勝 3着" in result["reason"]


def test_grade_appearance_is_not_grade_good_run():
    today = context(level=2)
    old = run("前走", context(level=8, age="3歳限定", label="G1"), finish=12)
    assert evaluate(today, [old])["label"] == "重賞出走歴"


def test_different_surface_is_disclosed():
    today = context()
    old = run("前走", context(level=8, age="3歳限定", label="G1"), finish=2, surface="ダ")
    result = evaluate(today, [old], current_surface="芝")
    assert "馬場違い" in result["reason"]
