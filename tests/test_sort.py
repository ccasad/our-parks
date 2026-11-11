from datetime import date

from tests.conftest import make_visit, sign_in
from tests.test_near_me import HERE
from tests.test_parks_list import names, setup_parks

DEVA = "Death Valley National Park"
GRCA = "Grand Canyon National Park"
YOSE = "Yosemite National Park"
ZION = "Zion National Park"


def test_default_is_name_a_to_z_and_the_control_shows_it(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)
    html = client.get("/").text
    assert names(html) == [DEVA, GRCA, YOSE, ZION]
    assert '<option value="name" selected>' in html
    assert "data-sort" in html


def test_name_z_to_a(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)
    assert names(client.get("/?sort=name_desc").text) == [ZION, YOSE, GRCA, DEVA]


def test_state_sorts_by_first_state_then_name(client, db, member):
    setup_parks(db)  # DEVA CA,NV; GRCA AZ; YOSE CA; ZION UT
    sign_in(client, db, member)
    assert names(client.get("/?sort=state").text) == [GRCA, DEVA, YOSE, ZION]


def test_rating_highest_first_unrated_last_ties_by_name(client, db, member):
    parks = setup_parks(db)
    make_visit(db, parks["zion"], rating=5)
    make_visit(db, parks["grca"], rating=5)
    make_visit(db, parks["yose"], rating=3)
    db.commit()
    sign_in(client, db, member)
    assert names(client.get("/?sort=rating").text) == [GRCA, ZION, YOSE, DEVA]


def test_last_visited_most_recent_first_never_visited_last(client, db, member):
    parks = setup_parks(db)
    make_visit(db, parks["yose"], on=date(2024, 5, 1))
    make_visit(db, parks["zion"], on=date(2025, 5, 1))
    make_visit(db, parks["zion"], on=date(2020, 5, 1))
    make_visit(db, parks["deva"], on=date(2022, 5, 1))
    db.commit()
    sign_in(client, db, member)
    assert names(client.get("/?sort=recent").text) == [ZION, YOSE, DEVA, GRCA]


def test_distance_is_ignored_without_near_me_and_offered_only_with_it(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)
    html = client.get("/?sort=distance").text
    assert names(html) == [DEVA, GRCA, YOSE, ZION]
    assert '<option value="distance"  hidden disabled>' in html or "hidden disabled" in html
    near = client.post("/parks/near", data={**HERE, "sort": "distance"}).text
    assert "hidden disabled" not in near
    assert '<option value="distance" selected>' in near


def test_near_me_selects_distance_and_other_sorts_still_work_with_it(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)
    by_distance = names(client.post("/parks/near", data=HERE).text)
    assert by_distance[0] == DEVA  # closest to the middle of Nevada
    assert names(client.post("/parks/near", data={**HERE, "sort": "name_desc"}).text) == [
        ZION,
        YOSE,
        GRCA,
        DEVA,
    ]


def test_sort_is_kept_by_the_list_map_toggle_and_clear(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)
    html = client.get("/?sort=rating").text
    assert 'href="?sort=rating&amp;view=map"' in html
    assert 'href="/?sort=rating"' in html  # Clear keeps the sort
    map_html = client.get("/?sort=rating&view=map").text
    assert '<input type="hidden" name="sort" value="rating">' in map_html
    assert 'href="?sort=rating"' in map_html  # back to List


def test_an_unknown_sort_falls_back_to_name(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)
    assert names(client.get("/?sort=bogus").text) == [DEVA, GRCA, YOSE, ZION]


def test_the_map_has_pine_tree_markers():
    from pathlib import Path

    js = Path("app/static/js/parks_map.js").read_text()
    css = Path("app/static/css/input.css").read_text()
    assert 'anchor: "bottom"' in js
    assert "width: 32px; height: 32px" in css
    assert ".park-marker.is-unvisited { z-index: 1; color: #78350f" in css
