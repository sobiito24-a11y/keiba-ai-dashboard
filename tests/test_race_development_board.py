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
    assert "3角は両者の補間" in board.text
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
