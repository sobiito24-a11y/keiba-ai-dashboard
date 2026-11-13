"""Three-stage visual formation is read-only, deterministic and JRA/NAR shared."""
from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from core.race_development_positions import _bands, layout
from core.race_development_board import board_html
from core.game_race_ui import document
from tests.test_race_explorer_ui import field

ROOT=Path(__file__).resolve().parents[1]


def _horses(count=18, mode="jra"):
    _,_,_,horses=field(mode,count)
    for i,horse in enumerate(horses,1):
        horse["start_rank"]=i
        horse["corner"]=count+1-i
    return horses


@pytest.mark.parametrize("mode,n",[
    ("jra",18),("jra",12),("nar",18),("nar",12),("nar",7),("nar",1)])
def test_every_runner_in_three_stage_formation_and_source_read_only(mode,n):
    horses=_horses(n,mode)
    before=deepcopy(horses)
    result=layout(horses)
    assert set(result)=={"start","third","fourth"}
    assert len(result["start"]["runners"])==n
    assert len(result["third"]["runners"])==n
    assert len(result["fourth"]["runners"])==n
    assert result["start"]["runners"][0]["no"]==1
    assert result["fourth"]["runners"][0]["no"]==n
    assert all(result[key]["runners"][i]["rank_display"]==i+1 for i in range(n)
               for key in ("start","third","fourth"))
    assert not result["start"]["interpolation"]
    assert result["third"]["interpolation"]
    assert not result["fourth"]["interpolation"]
    for key in ("start","third","fourth"):
        markers=result[key]["runners"]
        assert len(set(h["no"] for h in markers))==n
        for h in markers:
            assert 7<=h["x"]<=93
            assert 0<=h["y"]<=85
        for band in range(6):
            members=sorted((h for h in markers if h["band"]==band),
                           key=lambda h:h["x"])
            assert all(members[i+1]["x"]-members[i]["x"]>=10
                       for i in range(len(members)-1))
    assert horses==before


def test_tapered_not_uniform_grid_at_eighteen():
    assert _bands(18)==[6,4,3,2,2,1]
    markers=layout(_horses())["start"]["runners"]
    assert [sum(h["band"]==i for h in markers) for i in range(6)]==[6,4,3,2,2,1]


def test_missing_start_fourth_and_invalid_ranks_never_fabricated():
    horses=_horses(12)
    horses[0]["start_rank"]=None
    horses[1]["corner"]=None
    horses[2]["start_rank"]=0
    horses[3]["corner"]=float("nan")
    horses[4]["start_rank"]=True
    horses[5]["corner"]=14  # Outside the 12-runner field
    result=layout(horses)
    start_numbers={h["no"] for h in result["start"]["runners"]}
    fourth_numbers={h["no"] for h in result["fourth"]["runners"]}
    third_numbers={h["no"] for h in result["third"]["runners"]}
    assert not {1,3,5}.intersection(start_numbers)
    assert not {2,4,6}.intersection(fourth_numbers)
    assert third_numbers == start_numbers.intersection(fourth_numbers)
    assert result["third"]["missing"]
    html=BeautifulSoup(board_html(horses),"html.parser")
    assert html.select_one("#ka-pace-scene-third .ka-pace-unavailable")
    assert len(html.select("#ka-pace-scene-third [data-pace-runner]"))==len(third_numbers)


@pytest.mark.parametrize("mode",["jra","nar"])
def test_real_table_has_board_immediately_underneath_and_before_details(mode):
    _,_,info,horses=field(mode,18)
    # Provide explicit saved pre-race positions on the projection, not
    # result rows. Diagram must be completely separated from score inputs.
    for i,h in enumerate(horses,1):
        h["start_rank"]=i
        h["corner"]=19-i
    original=deepcopy(horses)
    document_html=document(horses,info["race_id"])
    dom=BeautifulSoup(document_html,"html.parser")
    board=dom.select_one("#ka-pace-board")
    assert board is not None
    lineup=dom.select_one("#lineup-workspace")
    details=dom.select_one("#detail-analysis")
    assert lineup is not None and details is not None
    nodes=list(dom.select_one("main").children)
    assert nodes.index(lineup)<nodes.index(board)<nodes.index(details)
    assert [h.get("data-pace-stage") for h in board.select('[role="tab"]')]==[
        "start","third","fourth"]
    assert [h.text for h in board.select('[role="tab"]')]==[
        "スタート後","3コーナー","4コーナー"]
    assert [x.get("aria-selected") for x in board.select('[role="tab"]')]==[
        "true","false","false"]
    scenes=board.select('[role="tabpanel"]')
    assert len(scenes)==3
    assert not scenes[0].has_attr("hidden")
    assert all(x.has_attr("hidden") for x in scenes[1:])
    for scene in scenes:
        runners=scene.select("[data-pace-runner]")
        assert len(runners)==18
        assert len({x["data-pace-runner"] for x in runners})==18
        assert all(x.select_one("svg.ka-pace-horse-svg") for x in runners)
        assert all(x.select_one(".ka-pace-number") for x in runners)
        assert all(x.select_one(".ka-pace-horse-name") for x in runners)
        assert all("番手" in x["aria-label"] for x in runners)
    assert "3角は保存済みの3角予測順位を優先" in board.text
    assert "3角の表示元：保存予測 0頭／補間 18頭" in board.text
    assert "AIランク・印・純能力には一切加点しません" in board.text
    assert "race_development.css" not in document_html  # inlined asset
    assert "ka-pace-turf" in document_html
    assert "data-pace-stage" in document_html
    assert horses==original


def test_missing_every_position_does_not_fall_back_to_horse_number():
    _,_,_,horses=field("nar",10)
    before=deepcopy(horses)
    assert all(h["start_rank"] is None for h in horses)
    dom=BeautifulSoup(board_html(horses),"html.parser")
    assert not dom.select("#ka-pace-scene-start .ka-pace-runner")
    assert "この区間の位置予測は未取得です" in dom.select_one(
        "#ka-pace-scene-start").text
    assert len(dom.select("#ka-pace-scene-fourth .ka-pace-runner"))==10
    assert not dom.select("#ka-pace-scene-third .ka-pace-runner")
    assert horses==before


def test_original_horse_svg_and_accessible_controls_are_local_and_safe():
    css=(ROOT/"core/game_ui_assets/race_development.css").read_text(encoding="utf-8")
    js=(ROOT/"core/game_ui_assets/race_development.js").read_text(encoding="utf-8")
    assert "ka-pace-stage-tabs" in css and "ka-pace-runner" in css
    assert "[hidden]" in css and "prefers-reduced-motion" not in css
    assert "aria-selected" in js and "ArrowRight" in js and "click" in js
    assert "fetch(" not in js and "innerHTML" not in js
    view=[dict(no=1,name='馬<sample>&"test',frame=3,start_rank=1,corner=1)]
    html=BeautifulSoup(board_html(view),"html.parser")
    runner=html.select_one("[data-pace-runner]")
    assert runner["data-pace-full-name"]=='馬<sample>&"test'
    assert html.select_one("img") is None
    assert not html.select("[onload],[onclick],[onerror]")


def test_horse_faces_left_without_mirroring_numbers_or_forecast_positions():
    css=(ROOT/"core/game_ui_assets/race_development.css").read_text(encoding="utf-8")
    assert ".ka-pace-horse-svg{display:block;width:46px;height:25px;transform:scaleX(-1)" in css
    assert ".ka-pace-runner-figure" in css
    assert ".ka-pace-number" in css
    view=_horses(12,"nar")
    before=deepcopy(view)
    positions=layout(view)
    assert positions["start"]["runners"][0]["no"]==1
    assert positions["fourth"]["runners"][0]["no"]==12
    assert view==before



@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_saved_third_corner_forecast_overrides_interpolation_at_all_stages(mode):
    horses = _horses(12, mode)
    before = deepcopy(horses)
    # The 3-corner forecast can differ significantly from the midpoint.
    horses[0]["third_rank"] = 12
    horses[1]["third_rank"] = 1
    horses[2]["third_rank"] = 5
    untouched = deepcopy(horses)
    formation = layout(horses)
    third = {h["no"]: h for h in formation["third"]["runners"]}
    assert third[1]["third"] == 12
    assert third[2]["third"] == 1
    assert third[3]["third"] == 5
    assert [third[n]["rank_display"] for n in (1, 2, 3)] == [12, 1, 5]
    assert all(third[n]["third_source"] == "saved" for n in (1, 2, 3))
    assert formation["third"]["saved_count"] == 3
    assert formation["third"]["interpolated_count"] == 9
    assert formation["third"]["interpolation"] is True
    dom = BeautifulSoup(board_html(horses), "html.parser")
    panel = dom.select_one("#ka-pace-scene-third")
    assert "保存予測 3頭／補間 9頭" in panel.text
    for num in (1, 2, 3):
        runner = panel.select_one(f'[data-pace-runner="{num}"]')
        assert runner["data-pace-third-source"] == "saved"
        assert "保存3角予測" in runner["aria-label"]
    assert "補間による参考位置" in panel.select_one(
        '[data-pace-runner="4"]')["aria-label"]
    assert horses == untouched
    assert all(h.get("third_rank") is None for h in before)


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_all_saved_third_corners_never_interpolated(mode):
    horses = _horses(8, mode)
    for i, h in enumerate(horses, 1):
        h["third_rank"] = 9 - i
    initial = deepcopy(horses)
    positions = layout(horses)
    third = positions["third"]
    assert third["interpolation"] is False
    assert third["saved_count"] == 8
    assert third["interpolated_count"] == 0
    assert third["runners"][0]["no"] == 8
    assert all(h["third_source"] == "saved" for h in third["runners"])
    doc = BeautifulSoup(board_html(horses), "html.parser")
    assert "保存予測 8頭／補間 0頭" in doc.text
    assert "全頭、保存された3角予測の順位を使っています" in doc.text
    assert horses == initial


@pytest.mark.parametrize("invalid", [None, 0, -1, True, 1.5, "未取得", float("nan"), 99])
def test_invalid_saved_third_uses_only_valid_start_and_fourth_fallback(invalid):
    view = _horses(12, "nar")
    view[0]["third_rank"] = invalid
    expected = 0.45 * 1 + 0.55 * 12
    third = {h["no"]: h for h in layout(view)["third"]["runners"]}
    assert abs(third[1]["third"] - expected) < 1e-8
    assert third[1]["third_source"] == "interpolated"
    view[0]["start_rank"] = None
    third = {h["no"]: h for h in layout(view)["third"]["runners"]}
    assert 1 not in third
    assert 1 in [h["no"] for h in layout(view)["third"]["missing"]]


def test_saved_third_rank_can_display_when_start_or_fourth_are_missing():
    view = _horses(12)
    view[0]["start_rank"] = None
    view[0]["corner"] = None
    view[0]["third_rank"] = 2
    third = {h["no"]: h for h in layout(view)["third"]["runners"]}
    assert third[1]["third"] == 2
    assert third[1]["third_source"] == "saved"
    assert 1 not in [h["no"] for h in layout(view)["third"]["missing"]]
    assert "序盤：未取得" in BeautifulSoup(board_html(view), "html.parser").select_one(
        '#ka-pace-scene-third [data-pace-runner="1"]')["aria-label"]
