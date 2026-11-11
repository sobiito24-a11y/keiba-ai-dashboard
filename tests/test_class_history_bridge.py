from core.class_history_bridge import verified_past_context, class_transition


def ctx(level=None, age="不明", venue="高知", family="NAR"):
    return dict(class_family=family, class_level_v2=level,
                class_label_v2="不明" if level is None else "C" + str(14-level),
                age_restriction_v2=age, race_discipline_v2="flat", venue_v2=venue)


def setup():
    target = dict(mode="nar", horse_id="2022101234", prediction_created_at="2026-11-08T06:30:00")
    past = dict(race_id="202654101001", venue="高知", class_context=ctx(level=12))
    header = dict(race_id="202654101001", mode="nar", venue="高知",
                  saved_at="2026-10-10T08:00:00", horse_ids=["2022101234"],
                  class_context=ctx(level=12, age="一般"))
    return target, past, header


def test_prior_saved_header_recovers_missing_nar_age():
    target, past, header = setup()
    c, reason = verified_past_context(target=target, past=past, prior_race=header)
    assert reason == "verified_saved_header"
    assert c["age_restriction_v2"] == "一般"
    assert class_transition(ctx(level=13, age="一般"), c)[0] == "昇級"


def test_later_saved_header_is_not_allowed():
    target, past, header = setup()
    header["saved_at"] = "2026-11-09T00:00:00"
    c, reason = verified_past_context(target=target, past=past, prior_race=header)
    assert reason == "header_not_available_as_of_prediction"
    assert c["age_restriction_v2"] == "不明"


def test_identity_and_venue_are_required():
    target, past, header = setup()
    header["horse_ids"] = ["other"]
    assert verified_past_context(target=target, past=past, prior_race=header)[1] == "horse_not_in_prior_race"
    header["horse_ids"] = ["2022101234"]
    header["venue"] = "佐賀"
    assert verified_past_context(target=target, past=past, prior_race=header)[1] == "venue_conflict"


def test_conflicting_age_remains_unresolved():
    target, past, header = setup()
    past["class_context"]["age_restriction_v2"] = "3歳限定"
    c, reason = verified_past_context(target=target, past=past, prior_race=header)
    assert reason == "conflicting_class_evidence"
    assert c["age_restriction_v2"] == "3歳限定"


def test_nar_venue_and_age_comparability_are_strict():
    assert class_transition(ctx(13, "一般", "高知"), ctx(12, "一般", "佐賀"))[0] == "比較不能"
    assert class_transition(ctx(13, "一般"), ctx(12, "不明"))[0] == "比較不能"
    assert class_transition(ctx(13, "一般"), ctx(13, "一般"))[0] == "同級"


def test_jra_family_is_separate():
    a, b = ctx(2, "3歳以上", family="JRA"), ctx(1, "3歳以上", family="JRA")
    assert class_transition(a, b)[0] == "昇級"
    assert class_transition(a, ctx(1, "3歳以上", family="NAR"))[0] == "比較不能"
