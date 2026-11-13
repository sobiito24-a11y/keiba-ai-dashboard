"""All active JRA/NAR course-turn master, exception and actual UI tests.

JRA 10 venues: official course guide; NAR 15: https://www.keiba.go.jp/guide/course/
Oi LEFT 1650: https://www.nankankeiba.com/course_info/20.do
Straight courses: Niigata turf 1000m and Obihiro ban'ei.
"""
from copy import deepcopy
import pytest
from bs4 import BeautifulSoup

from core.race_course_direction import JRA_TURNS, NAR_TURNS, course_direction
from core.race_development_board import board_html
from core.race_development_positions import layout
from core.game_race_ui import document
from tests.test_race_explorer_ui import field

JRA = {
    "札幌":"right", "函館":"right", "福島":"right", "新潟":"left",
    "東京":"left", "中山":"right", "中京":"left", "京都":"right",
    "阪神":"right", "小倉":"right",
}
NAR = {
    "帯広":"straight", "門別":"right", "盛岡":"left",
    "水沢":"right", "浦和":"left", "船橋":"left",
    "大井":"mixed", "川崎":"left", "金沢":"right",
    "笠松":"right", "名古屋":"right", "園田":"right",
    "姫路":"right", "高知":"right", "佐賀":"right",
}


def saved_view(mode, info):
    return [dict(no=i,name="保存馬"+str(i),frame=(i-1)//2+1,
                 mode=mode,start_rank=i,corner=13-i,
                 race_context=dict(info),score=100-i,rank=i,mark="—")
            for i in range(1,13)]


@pytest.mark.parametrize("venue,turn",[
    (k,v) for k,v in JRA.items()
])
def test_all_ten_jra_racecourses(venue,turn):
    assert JRA_TURNS==JRA
    info=dict(venue=venue+"競馬場",distance=1600,surface="芝")
    result=course_direction(saved_view("jra",info))
    assert result["venue"]==venue
    assert result["turn"]==turn
    assert result["label"]==("左回り" if turn=="left" else "右回り")
    assert result["source"]=="official_venue"
    assert result["has_corners"] is True


@pytest.mark.parametrize("venue,turn",[
    (k,v) for k,v in NAR.items() if k!="大井"
])
def test_fourteen_single_direction_nar_racecourses(venue,turn):
    assert NAR_TURNS==NAR
    info=dict(racecourse=venue+"競馬場",distance=1400,surface="ダ")
    result=course_direction(saved_view("nar",info))
    assert result["venue"]==venue
    assert result["turn"]==turn
    assert result["has_corners"]==(turn!="straight")


@pytest.mark.parametrize("distance,turn", [
    (1000,"right"),(1200,"right"),(1400,"right"),(1500,"right"),
    (1600,"right"),(1650,"left"),(1700,"right"),(1800,"right"),
    (2000,"right"),(2400,"right"),(2600,"right"),
])
def test_oi_both_directions_by_race_distance(distance,turn):
    info=dict(venue="大井",distance=distance,surface="ダート")
    result=course_direction(saved_view("nar",info))
    assert result["turn"]==turn
    assert result["source"]=="official_oi_distance"


def test_oi_without_distance_or_race_turn_is_ambiguous_not_right_by_guess():
    info=dict(venue="大井")
    result=course_direction(saved_view("nar",info))
    assert result["turn"]=="unknown"
    assert result["source"]=="missing_oi_course"


@pytest.mark.parametrize("info,expected",[
    (dict(venue="大井",distance=1650,course_turn="左回り"),"left"),
    (dict(venue="大井",distance=1200,turn="右"),"right"),
    (dict(venue="大井",course="ダート 外回り・左",distance=1650),"left"),
    (dict(venue="大井",distance=1600,course_turn="左回り"),"left"),
    (dict(venue="大井",distance=1600,turn="右",race_turn="左"),"unknown"),
])
def test_explicit_saved_race_course_turn_precedence(info,expected):
    result=course_direction(saved_view("nar",info))
    assert result["turn"]==expected


@pytest.mark.parametrize("venue,surface,distance,expected",[
    ("新潟","芝",1000,"straight"),
    ("新潟","芝・直線",1000,"straight"),
    ("新潟","ダート",1000,"left"),
    ("新潟","芝",1200,"left"),
    ("東京","芝",1000,"left"),
    ("帯広","ダ",200,"straight"),
])
def test_special_straight_tracks_only_when_real(venue,surface,distance,expected):
    mode="nar" if venue=="帯広" else "jra"
    info=dict(venue=venue,surface=surface,distance=distance)
    result=course_direction(saved_view(mode,info))
    assert result["turn"]==expected
    assert result["has_corners"] == (expected!="straight")


@pytest.mark.parametrize("mode,venue",[
    ("jra","北海道"),("jra","盛岡"),("nar","南関東"),
    ("nar","東京"),("nar","岩手"),("nar","海外"),
])
def test_unknown_or_wrong_league_must_not_invent_venue_turn(mode,venue):
    result=course_direction(saved_view(mode,dict(venue=venue)))
    assert result["turn"]=="unknown"
    assert result["source"]=="missing_venue"


@pytest.mark.parametrize("code,venue",[
    ("01","札幌"),("02","函館"),("03","福島"),("04","新潟"),
    ("05","東京"),("06","中山"),("07","中京"),("08","京都"),
    ("09","阪神"),("10","小倉"),
])
def test_missing_jra_venue_uses_verified_race_id_venue_code(code,venue):
    info=dict(distance=1600,surface="芝")
    horses=saved_view("jra",info)
    result=course_direction(horses, race_key="2026"+code+"010211")
    assert result["venue"]==venue
    assert result["turn"]==JRA[venue]


def test_venue_aliases_and_fullwidth_course_info():
    assert course_direction(saved_view("nar",dict(venue="ばんえい帯広")))["turn"]=="straight"
    assert course_direction(saved_view("nar",dict(venue="帯広ば")))["turn"]=="straight"
    x=course_direction(saved_view("nar",dict(venue="大井競馬場",distance_label="ダート１，６５０ｍ")))
    assert x["turn"]=="left"
    x=course_direction(saved_view("jra",dict(venue="東京",turn_direction="left")))
    assert x["source"]=="saved_race_info" and x["turn"]=="left"


@pytest.mark.parametrize("mode,venue,distance,turn",[
    ("jra","京都",1400,"right"),
    ("jra","東京",1400,"left"),
    ("nar","名古屋",1500,"right"),
    ("nar","川崎",1600,"left"),
    ("nar","大井",1650,"left"),
    ("nar","大井",1800,"right"),
    ("jra","新潟",1000,"straight"),
    ("nar","帯広",200,"straight"),
    ("nar","大井",None,"unknown"),
])
def test_board_turn_badge_css_facing_and_real_corner_exception(mode,venue,distance,turn):
    info=dict(venue=venue,surface="芝" if mode=="jra" else "ダ",distance=distance)
    horses=saved_view(mode,info)
    snapshot=deepcopy(horses)
    before=layout(horses)
    dom=BeautifulSoup(board_html(horses),"html.parser")
    section=dom.select_one("#ka-pace-board")
    assert section is not None
    assert section["data-course-turn"]==turn
    assert ("・"+course_direction(horses)["label"]) in section.select_one(".ka-pace-course-turn").text
    if turn=="straight":
        assert not dom.select("#ka-pace-scene-third .ka-pace-runner")
        assert not dom.select("#ka-pace-scene-fourth .ka-pace-runner")
        assert "直線コースのため" in dom.select_one("#ka-pace-scene-third").text
    else:
        assert len(dom.select("#ka-pace-scene-start .ka-pace-runner"))==12
        assert len(dom.select("#ka-pace-scene-fourth .ka-pace-runner"))==12
    assert horses==snapshot
    assert layout(horses)==before


def test_real_document_uses_saved_race_context_but_does_not_change_any_position():
    _,_,info,view=field("nar",12)
    info["venue"]="大井"
    info["distance"]=1650
    for h in view:
        h["race_context"]=dict(info)
        h["start_rank"]=int(h["no"])
        h["corner"]=13-int(h["no"])
    before=deepcopy(view)
    dom=BeautifulSoup(document(view,info["race_id"]),"html.parser")
    assert dom.select_one("#ka-pace-board")["data-course-turn"]=="left"
    assert dom.select_one(".ka-pace-course-turn").text=="大井・左回り"
    assert len(dom.select("#lineup-workspace tr[data-horse]"))==12
    assert view==before


def test_venue_css_mirrors_only_svg_not_horse_number_or_name():
    from pathlib import Path
    css=(Path(__file__).resolve().parents[1] /
         "core/game_ui_assets/race_development.css").read_text(encoding="utf-8")
    assert '.ka-pace-board[data-course-turn="left"] .ka-pace-horse-svg{transform:scaleX(1)}' in css
    assert '.ka-pace-board[data-course-turn="straight"] .ka-pace-horse-svg{transform:scaleX(1)}' in css
    assert '.ka-pace-board[data-course-turn="unknown"] .ka-pace-horse-svg{opacity:.72}' in css
    assert "transform:scaleX(-1)" in css
    assert ".ka-pace-number" in css


def test_saved_kawasaki_lead_12_faces_right_and_appears_rightmost():
    """Regression from the user's screenshot: start ranks 12,7,3,9 in that order.

    The prior drawing erroneously put #12 at left despite right-facing
    horses at Kawasaki. Keep the same predicted ranks/bands.
    """
    import re
    horses = saved_view("nar", dict(venue="川崎", distance=1400, surface="ダ"))
    top_numbers = (12, 7, 3, 9)
    for i, no in enumerate(top_numbers, 1):
        next(h for h in horses if h["no"] == no)["start_rank"] = i
    for i, no in enumerate((1, 2, 4, 5, 6, 8, 10, 11), 5):
        next(h for h in horses if h["no"] == no)["start_rank"] = i
    before = deepcopy(horses)
    document = BeautifulSoup(board_html(horses), "html.parser")
    board = document.select_one("#ka-pace-board")
    assert board["data-course-turn"] == "left"
    assert "隊列の先頭側 →" in board.select_one(".ka-pace-forward-hint").text
    lead_pack = sorted(layout(horses, course_turn="left")["start"]["runners"],
                       key=lambda h: h["start"])[:4]
    assert [h["no"] for h in lead_pack] == [12, 7, 3, 9]
    assert all(lead_pack[i]["x"] > lead_pack[i + 1]["x"] for i in range(3))
    # Verify the actual rendered coordinates, not merely the projection.
    page = board.select_one("#ka-pace-scene-start")
    rendered = {}
    for h in page.select(".ka-pace-runner"):
        rendered[int(h["data-pace-runner"])] = float(
            re.search(r"--px:([0-9.]+)%", h["style"]).group(1))
    assert [rendered[no] for no in top_numbers] == [h["x"] for h in lead_pack]
    assert rendered[12] > rendered[7] > rendered[3] > rendered[9]
    assert horses == before


@pytest.mark.parametrize("mode,venue,distance,surface,side", [
    ("jra", "東京", 1600, "芝", "right"),
    ("jra", "京都", 1600, "芝", "left"),
    ("jra", "新潟", 1000, "芝", "right"),
    ("nar", "川崎", 1400, "ダ", "right"),
    ("nar", "船橋", 1600, "ダ", "right"),
    ("nar", "名古屋", 1500, "ダ", "left"),
    ("nar", "大井", 1650, "ダ", "right"),
    ("nar", "大井", 1800, "ダ", "left"),
])
def test_all_three_stage_front_horse_horizontal_side_matches_facing(
        mode, venue, distance, surface, side):
    info = dict(venue=venue, distance=distance, surface=surface)
    horses = saved_view(mode, info)
    prior = deepcopy(horses)
    turn = course_direction(horses)["turn"]
    formations = layout(horses, course_turn=turn)
    for stage in ("start", "third", "fourth"):
        if turn == "straight" and stage != "start":
            continue
        group = formations[stage]["runners"]
        front = [h for h in group if h["band"] == 0]
        if len(front) < 2:
            continue
        # A lower predicted rank must sit ahead in the direction the
        # silhouettes are facing. This is a visual convention, not a
        # measured lateral lane or a claim about exact horse lengths.
        front.sort(key=lambda h: h[stage])
        coordinates = [h["x"] for h in front]
        if side == "right":
            assert coordinates == sorted(coordinates, reverse=True)
        else:
            assert coordinates == sorted(coordinates)
    assert horses == prior
