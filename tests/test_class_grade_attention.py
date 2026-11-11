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


def test_jra_runner_with_nar_exchange_grades_shows_both_even_without_comparable_class():
    # 京都11R・エコロレーヴに類する実績。JRAとNARのクラス水準は混同しない。
    today = context(mode="JRA", level=4, age="3歳以上", label="OP")
    last = run("前走", context(mode="NAR", level=None, age="3歳限定", venue="大井", label="Jpn2"), 4, "ダ")
    older = run("2走前", context(mode="NAR", level=None, age="3歳限定", venue="門別", label="Jpn3"), 2, "ダ")
    result = evaluate(today, [last, older], current_surface="ダ")
    assert result["label"] == "重賞好走歴"
    assert result["tags"][:2] == ["交流Jpn3 2着", "交流Jpn2 4着"]
    assert result["display"] == "交流Jpn3 2着 · 交流Jpn2 4着"
    assert "前走Jpn2 4着" in result["reason"]
    assert "2走前Jpn3 2着" in result["reason"]
    assert result["scoring_effect"] == 0


def test_class_status_is_visible_beside_grade_facts_without_bonus():
    today = context(level=2, age="3歳以上", label="2勝")
    old = run("前走", context(level=1, age="3歳以上", label="1勝"), 1)
    result = evaluate(today, [old])
    assert result["display"] == "昇級"
    same = run("前走", context(level=2, age="3歳以上", label="2勝"), 3)
    assert evaluate(today, [same])["display"] == "同級好走"
    assert evaluate(today, [same])["scoring_effect"] == 0


def test_actual_saved_run_names_win_over_inconsistent_legacy_grade_labels():
    # 2026-11-07 京都11Rの保存データでは旧クラス欄が一律Jpn1だが
    # レース名は JpnII/JpnIII。表示はレース名の明示情報を使う。
    from core.candidate_profile import facts

    row = dict(_past_class_labels=["Jpn1", "Jpn1", "Jpn1"], _past_runs=[
        dict(label="前走", race_date="2026-10-08", racecourse="東京",
             race_name="第60回東京盃競走 JpnII", class_label="G2",
             surface="ダ", distance=1200, position=4, value=95),
        dict(label="2走前", race_date="2026-08-13", racecourse="",
             race_name="第30回北海道スプリントカッ JpnIII", class_label="G3",
             surface="ダ", distance=1200, position=2, value=77),
        dict(label="3走前", race_date="2026-05-06", racecourse="",
             race_name="第27回兵庫チャンピオンシッ JpnII", class_label="G2",
             surface="ダ", distance=1400, position=4, value=82),
    ])
    info = dict(race_date="2026-11-07", racecourse="京都", surface="ダ",
                race_name="室町S", race_data2="サラ系３歳以上 オープン")
    outcome = facts(row, info)["class_attention"]
    assert "交流Jpn3 2着" in outcome["display"]
    assert "交流Jpn2 4着" in outcome["display"]
    assert "Jpn1" not in outcome["reason"]
    assert outcome["scoring_effect"] == 0
