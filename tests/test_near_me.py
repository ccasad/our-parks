import logging
import re

from sqlalchemy import text

from app.park_list import miles_between
from tests.conftest import make_park, make_user, sign_in
from tests.test_map import points

# Made-up spot near the middle of Nevada
HERE = {"lat": "38.500", "lon": "-117.250"}
RESULTS = {"HX-Request": "true", "HX-Target": "results"}


def names(html):
    return re.findall(r"<p [^>]*data-park-name>([^<]+)</p>", html)


def parks(db):
    make_park(db, "yose", "Yosemite National Park", latitude=37.85, longitude=-119.57)
    make_park(db, "deva", "Death Valley National Park", latitude=36.5, longitude=-117.1)
    make_park(db, "grba", "Great Basin National Park", latitude=38.98, longitude=-114.3)
    make_park(db, "acad", "Acadia National Park", latitude=44.35, longitude=-68.21)
    make_park(db, "none", "Unplaced National Park", latitude=None, longitude=None)


def test_distance_between_two_points():
    # Los Angeles to New York is about 2,450 miles
    assert 2400 < miles_between(34.05, -118.24, 40.71, -74.0) < 2500
    assert miles_between(10, 10, 10, 10) == 0


def test_parks_are_sorted_nearest_first_with_miles(client, db, member):
    parks(db)
    sign_in(client, db, member)

    response = client.post("/parks/near", data=HERE)

    placed = {
        "Yosemite National Park": (37.85, -119.57),
        "Death Valley National Park": (36.5, -117.1),
        "Great Basin National Park": (38.98, -114.3),
        "Acadia National Park": (44.35, -68.21),
    }
    expected = sorted(placed, key=lambda n: miles_between(38.5, -117.25, *placed[n]))
    assert names(response.text) == expected
    assert expected[-1] == "Acadia National Park"
    assert "Unplaced National Park" not in response.text  # no location, no distance
    assert re.search(r"· [\d,]+ mi", response.text)


def test_the_radius_limits_the_results(client, db, member):
    parks(db)
    sign_in(client, db, member)

    within_250 = names(client.post("/parks/near", data={**HERE, "radius": "250"}).text)
    within_100 = names(client.post("/parks/near", data={**HERE, "radius": "100"}).text)
    anywhere = names(client.post("/parks/near", data={**HERE, "radius": "any"}).text)

    assert "Acadia National Park" not in within_250
    assert len(within_250) == 3
    assert within_100 == []
    assert len(anywhere) == 4


def test_near_me_combines_with_search_and_filters(client, db, member):
    parks(db)
    sign_in(client, db, member)

    html = client.post("/parks/near", data={**HERE, "q": "basin", "f": "1"}).text

    assert names(html) == ["Great Basin National Park"]


def test_near_me_swaps_only_the_list_and_is_kept_out_of_the_address_bar(client, db, member):
    parks(db)
    sign_in(client, db, member)

    response = client.post("/parks/near", data=HERE, headers=RESULTS)

    assert "<html" not in response.text
    assert response.headers["hx-push-url"] == "false"
    assert response.headers["cache-control"] == "no-store"
    assert "38.5" not in response.headers.get("location", "")


def test_a_full_page_keeps_near_me_on_with_the_location_only_in_form_fields(client, db, member):
    parks(db)
    sign_in(client, db, member)

    html = client.post("/parks/near", data={**HERE, "radius": "250", "view": "map"}).text

    assert 'aria-pressed="true"' in html
    assert 'name="lat" value="38.5"' in html
    assert 'value="250" selected' in html
    assert 'id="map"' in html


def test_the_map_centres_on_the_person(client, db, member):
    parks(db)
    sign_in(client, db, member)

    html = client.post("/parks/near", data={**HERE, "view": "map"}, headers=RESULTS).text

    raw = re.search(r'id="map-data">(.*?)</script>', html, re.DOTALL).group(1)
    assert '"near":{"lat":38.5,"lon":-117.25}' in raw.replace(" ", "")
    assert len(points(html)) == 4


def test_without_near_me_the_map_has_no_location(client, db, member):
    parks(db)
    sign_in(client, db, member)

    assert '"near":null' in client.get("/?view=map").text.replace(" ", "")


def test_the_location_is_never_logged_or_stored(client, db, member, caplog):
    parks(db)
    sign_in(client, db, member)

    with caplog.at_level(logging.DEBUG):
        client.post("/parks/near", data={"lat": "38.12345", "lon": "-117.54321"})

    assert "38.12345" not in caplog.text and "117.54321" not in caplog.text
    # No table holds it: search every text column of every table.
    for (table,) in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")):
        for row in db.execute(text(f'SELECT * FROM "{table}"')):
            assert "38.12345" not in str(row) and "117.54321" not in str(row)


def test_bad_locations_are_refused(client, db, member):
    parks(db)
    sign_in(client, db, member)

    for bad in (
        {"lat": "91", "lon": "0"},
        {"lat": "0", "lon": "181"},
        {"lat": "abc", "lon": "0"},
        {"lat": "10"},
    ):
        assert client.post("/parks/near", data=bad).status_code == 422


def test_near_me_needs_sign_in_and_the_right_origin(client, db, member):
    parks(db)
    assert client.post("/parks/near", data=HERE, follow_redirects=False).status_code == 303
    sign_in(client, db, member)

    other_site = {"Origin": "https://evil.example"}
    assert client.post("/parks/near", data=HERE, headers=other_site).status_code == 403


def test_the_page_has_the_near_me_button_and_radius_choices(client, db, member):
    parks(db)
    sign_in(client, db, member)

    html = client.get("/").text

    assert "data-near-toggle" in html
    for label in ("Any distance", "100 miles", "250 miles", "500 miles"):
        assert label in html
    # Off by default: the location fields are disabled, so they are never submitted.
    assert re.search(r'name="lat" value="" disabled', html)


def test_near_me_is_the_same_for_every_member(client, db, member):
    parks(db)
    sign_in(client, db, make_user(db, email="other@example.com"))

    assert names(client.post("/parks/near", data=HERE).text)


def test_the_browser_may_use_the_location(client):
    import json
    from pathlib import Path

    headers = json.loads(Path("vercel.json").read_text())["headers"][0]["headers"]
    policy = next(h["value"] for h in headers if h["key"] == "Permissions-Policy")
    assert "geolocation=(self)" in policy
