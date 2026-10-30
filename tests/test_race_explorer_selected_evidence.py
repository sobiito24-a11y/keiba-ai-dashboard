"""Keep all-runner comparison compact: evidence appears only in pickup/horse detail."""
from copy import deepcopy
import json

from bs4 import BeautifulSoup
import pytest

from core.race_explorer_columns import columns, records
from core.race_explorer_cards import detail_html, pickup_html
from core.race_explorer_ui import lineup_html, document


def sample(mode):
    metrics = dict(
        ability=dict(value=81.5, rank=2),
        course=dict(value=77, rank=3),
        distance=dict(value=65, rank=4),
        style="差", corner=4, average=66, maximum=88,
        plus="今回調教B / 近走同回り好走" if mode == "jra" else "同場好走 / 4角前方",
        caution="休養明け",
    )
    return dict(no="2", name="試験馬", age="牡2" if mode == "jra" else "牡4",
                mode=mode, mark="—", rank=2, formal_member=True,
                frame=1, candidate_formal_score=91, jockey="騎手",
                race_context=dict(race_data2="4回 京都 サラ系2歳 未勝利",
                                  race_name="レース", race_date="2026-10-30"),
                final_metrics=metrics,
                explorer_facts=dict(metrics=deepcopy(metrics),
                    training="B" if mode == "jra" else "対象外",
                    current_jockey="騎手", weight_label="56kg",
                    weight_delta_label="±0kg", rest_label="中3週",
                    runs=[dict(label="前走", date="2026-10-20", finish="2着", time_index=66)],
                    features=["同場2戦1回3着以内", "調教B" if mode == "jra" else "4角前方"],
                    plus=metrics["plus"], caution=metrics["caution"]))


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_table_has_no_materials_column_but_raw_values_and_pickup_preserved(mode):
    horse=sample(mode)
    before=deepcopy(horse)
    specs=columns([horse])
    hidden=next(x for x in specs if x["key"]=="materials")
    assert hidden.get("table_hidden") is True
    row=records([horse])["2"]
    assert row["plus"] and row["caution"] and row["materials"]
    doc=BeautifulSoup(lineup_html([horse]), "html.parser")
    assert not doc.select("th.col-materials,td.col-materials")
    assert doc.select_one("button.horse-select[data-horse-open='2']")
    assert doc.select_one("button.column-filter[data-column='name']")
    pickup=BeautifulSoup(pickup_html([horse]), "html.parser")
    assert pickup.select_one(".pickup-card[data-horse-open='2']")
    assert horse == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_selected_horse_immediately_shows_positive_and_caution_with_full_source(mode):
    horse=sample(mode)
    before=deepcopy(horse)
    doc=BeautifulSoup(detail_html(horse), "html.parser")
    section=doc.select_one(".detail-quick-evidence")
    assert section
    assert section.find_previous_sibling() is doc.select_one(".detail-header")
    assert section.select_one(".evidence-support")
    assert section.select_one(".evidence-caution")
    assert "近走同回り好走" in section.text if mode == "jra" else "同場好走" in section.text
    assert "休養明け" in section.text
    assert "今回調教B" not in section.text  # already shown in dedicated training box
    assert horse["explorer_facts"]["plus"] in doc.select_one(".detail-plus").get_text()
    assert "休養明け" in doc.select_one(".detail-caution").get_text()
    assert horse==before


def test_selection_wiring_embeds_detail_not_always_visible_on_table():
    horse=sample("jra")
    doc=BeautifulSoup(document([horse], "sample-20261030"), "html.parser")
    row=doc.select_one("tr[data-horse='2']")
    assert row is not None
    assert "近走同回り好走" not in row.get_text()
    payload=json.loads(doc.select_one("#race-data").string)
    assert 'detail-quick-evidence' in payload["cards"][0]
    assert "data-horse-open" in str(row)
    script=doc.select_one("script:not([type])")
    assert script and "function selectHorse" in script.text
    assert "shared-horse-detail" in script.text
