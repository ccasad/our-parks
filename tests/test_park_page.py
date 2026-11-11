from tests.conftest import make_park, make_visit, sign_in

IMAGES = [
    {
        "url": "https://www.nps.gov/a.jpg",
        "title": "Valley",
        "caption": "The valley at dawn",
        "credit": "Alex Example/NPS",
        "alt": "A misty valley",
    },
    {"url": "https://www.nps.gov/b.jpg", "title": "", "caption": "", "credit": "", "alt": ""},
]


def test_the_park_page_shows_photos_description_activities_and_links(client, db, member):
    make_park(
        db,
        "yose",
        "Yosemite National Park",
        images=IMAGES,
        description="Granite cliffs and waterfalls.",
        activities=["Climbing", "Hiking"],
    )
    sign_in(client, db, member)

    response = client.get("/parks/yose")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    html = response.text
    assert 'src="https://www.nps.gov/a.jpg"' in html
    assert 'alt="A misty valley"' in html
    assert "Photo: Alex Example/NPS" in html  # credit shown with the photo (NFR-14)
    assert "The valley at dawn" in html
    assert "Granite cliffs and waterfalls." in html
    assert ">Climbing<" in html and ">Hiking<" in html
    assert 'href="https://www.nps.gov/yose/index.htm"' in html
    assert "destination=37.850000,-119.570000" in html
    assert 'href="/parks/yose/visits/new"' in html


def test_an_unvisited_park_says_so(client, db, member):
    make_park(db)
    sign_in(client, db, member)

    html = client.get("/parks/yose").text

    assert "Not visited yet" in html
    assert "No visits yet" in html


def test_visits_are_listed_newest_first_with_the_latest_rating(client, db, member):
    from datetime import date

    park = make_park(db)
    make_visit(db, park, rating=5, on=date(2024, 6, 1), note="First trip")
    make_visit(db, park, rating=3, on=date(2026, 7, 4), note="Second trip")
    sign_in(client, db, member)

    html = client.get("/parks/yose").text

    assert html.index("Second trip") < html.index("First trip")
    assert "Jul 4, 2026" in html
    assert "Sam Example" in html
    assert 'aria-label="3 of 5 stars"' in html
    assert "Not visited yet" not in html


def test_a_park_without_images_or_location_still_renders(client, db, member):
    make_park(db, "x", "Plain Site", latitude=None, longitude=None, url="")
    sign_in(client, db, member)

    html = client.get("/parks/x").text

    assert "Plain Site" in html
    assert "Directions" not in html


def test_unknown_parks_are_404(client, db, member):
    sign_in(client, db, member)

    assert client.get("/parks/nope").status_code == 404
    assert client.get("/parks/bad-code!").status_code == 422


def test_the_park_page_needs_sign_in(client, db):
    make_park(db)

    assert client.get("/parks/yose", follow_redirects=False).headers["location"] == "/login"
