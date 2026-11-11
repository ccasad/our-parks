import json
import re

from tests.conftest import make_park, make_visit, sign_in


def points(html):
    raw = re.search(r'<script type="application/json" id="map-data">(.*?)</script>', html, re.DOTALL)
    return json.loads(raw.group(1))["points"]


def test_the_toggle_is_on_the_parks_page_and_defaults_to_list(client, db, member):
    make_park(db)
    sign_in(client, db, member)

    html = client.get("/").text

    assert 'data-view-toggle="list"' in html and 'data-view-toggle="map"' in html
    assert 'href="?view=map"' in html
    assert 'id="map"' not in html  # list view has no map


def test_the_toggle_keeps_search_and_filters(client, db, member):
    make_park(db)
    sign_in(client, db, member)

    html = client.get(
        "/?f=1&q=yose&visited=not&type=National+Monument&state=CA&activity=Hiking"
    ).text

    link = re.search(r'href="([^"]+)" data-view-toggle="map"', html).group(1).replace("&amp;", "&")
    assert link.startswith("?f=1&q=yose&visited=not&type=National+Monument&state=CA")
    assert "activity=Hiking" in link and link.endswith("view=map")
    back = client.get("/" + link).text
    assert re.search(r'href="([^"]+)" data-view-toggle="list"', back).group(1).replace(
        "&amp;", "&"
    ) == link.removesuffix("&view=map")


def test_map_view_has_the_map_container_the_style_and_attribution(client, db, member):
    make_park(db)
    sign_in(client, db, member)

    html = client.get("/?view=map").text

    assert 'id="map"' in html
    assert 'data-style="https://tiles.openfreemap.org/styles/liberty"' in html
    assert "OpenFreeMap" in html and "OpenStreetMap" in html  # NFR-14
    assert 'aria-current="true"' in html


def test_a_marker_for_each_matching_park_green_when_visited(client, db, member):
    yose = make_park(db, "yose", "Yosemite National Park")
    make_park(db, "zion", "Zion National Park", latitude=37.3, longitude=-113.0)
    make_park(db, "nowhere", "No Location Park", latitude=None, longitude=None)
    make_park(db, "muir", "Muir Woods", designation="National Monument")
    make_visit(db, yose, rating=4)
    sign_in(client, db, member)

    found = {p["code"]: p for p in points(client.get("/?view=map").text)}

    assert set(found) == {"yose", "zion"}  # national parks with a location
    assert found["yose"]["visited"] is True and found["yose"]["rating"] == 4
    assert found["zion"]["visited"] is False and found["zion"]["rating"] is None
    assert (found["zion"]["lat"], found["zion"]["lon"]) == (37.3, -113.0)


def test_the_map_follows_search_and_filters(client, db, member):
    make_park(db, "yose", "Yosemite National Park")
    make_park(db, "zion", "Zion National Park", states="UT")
    sign_in(client, db, member)

    assert [p["code"] for p in points(client.get("/?view=map&q=zion").text)] == ["zion"]
    assert [p["code"] for p in points(client.get("/?f=1&view=map&state=CA").text)] == ["yose"]


def test_filtering_the_map_swaps_only_the_data(client, db, member):
    make_park(db, "yose", "Yosemite National Park")
    make_park(db, "zion", "Zion National Park")
    sign_in(client, db, member)

    response = client.get(
        "/?view=map&q=yose", headers={"HX-Request": "true", "HX-Target": "results"}
    )

    assert "<html" not in response.text
    assert [p["code"] for p in points(response.text)] == ["yose"]
    assert "1 of 2" not in response.text and "0 of 2 National Parks visited" in response.text


def test_park_data_cannot_break_out_of_the_map_script(client, db, member):
    make_park(db, "evil", "</script><script>alert(1)</script>")
    sign_in(client, db, member)

    html = client.get("/?view=map").text

    assert "</script><script>alert(1)" not in html
    assert points(html)[0]["name"] == "</script><script>alert(1)</script>"


def test_unknown_views_fall_back_to_the_list(client, db, member):
    sign_in(client, db, member)

    assert 'id="map"' not in client.get("/?view=satellite").text


def test_the_map_script_is_served(client):
    assert client.get("/static/js/parks_map.js").status_code == 200
    assert client.get("/static/vendor/maplibre-gl.js").status_code == 200
    assert client.get("/static/vendor/maplibre-gl.css").status_code == 200
