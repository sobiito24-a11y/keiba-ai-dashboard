"""Prevent final evaluation UI from leaking back into JRA/NAR normal views."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app.py"


def segment(name, next_name):
    source = SOURCE.read_text(encoding="utf-8")
    return source.split(f"def {name}(", 1)[1].split(f"def {next_name}(", 1)[0]


def test_app_source_is_valid_python():
    ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_market_page_uses_independent_ranking_only():
    body = segment("render_market_compare_result", "render_nar_form_reference_table")
    assert "render_full_field_comparison(" in body
    assert "render_nar_form_reference_table(" in body
    assert "render_market_research_bet(" not in body
    assert "render_market_horse_cards(" not in body
    assert "render_jra_top5_result_summary(" not in body
    assert "render_nar_top5_result_summary(" not in body


def test_independent_table_has_no_final_marks_or_rank():
    body = segment("render_full_field_comparison", "ver3_conclusion_html")
    assert '"全頭横比較"' in body
    assert '"純能力順"' in body and '"コース指数順"' in body
    assert '"距離指数順"' in body and '"4角想定順"' in body
    assert "mark_key=\"_no_final_mark_display\"" in body
    assert "jra_top5_conclusion_html(" not in body
    assert "nar_top5_conclusion_html(" not in body
    assert "v1_final_rank" not in body
    assert "nar_final_rank" not in body


def test_previous_final_ranks_remain_in_legacy_audit():
    source = SOURCE.read_text(encoding="utf-8")
    audit = segment("render_market_audit_details", "render_market_user_selection")
    assert "nar_top5_rank" in audit
    assert "baseline_ver3_current_evaluation_rank" in audit


def test_old_detail_table_hides_final_mark_and_rank():
    body = segment("render_market_full_table", "render_market_horse_cards")
    assert '"印":' not in body
    assert '"今回評価順位":' not in body
    assert '"能力順位":' in body
    assert '"コース":' in body
