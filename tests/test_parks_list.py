from tests.conftest import make_park, make_user, make_visit, sign_in


def names(html):
    """Park names in the order they appear in the list."""
    import re

    return re.findall(r"<p [^>]*data-park-name>([^<]+)</p>", html)


def setup_parks(db):
    return {
        "yose": make_park(db, "yose", "Yosemite National Park", states="CA", activities=["Hiking"]),
        "zion": make_park(
            db, "zion", "Zion National Park", states="UT", activities=["Hiking", "Climbing"]
        ),
        "grca": make_park(
            db, "grca", "Grand Canyon National Park", states="AZ", activities=["Rafting"]
        ),
        "deva": make_park(
            db, "deva", "Death Valley National Park", states="CA,NV", activities=["Camping"]
        ),
        "muir": make_park(
            db,
            "muir",
            "Muir Woods National Monument",
            designation="National Monument",
            states="CA",
            images=[
                {
                    "url": "https://www.nps.gov/m.jpg",
                    "title": "",
                    "caption": "",
                    "credit": "NPS Photo",
                    "alt": "Redwoods",
                }
            ],
        ),
    }


def test_the_list_defaults_to_national_parks_sorted_by_name(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)

    html = client.get("/").text

    assert names(html) == [
        "Death Valley National Park",
        "Grand Canyon National Park",
        "Yosemite National Park",
        "Zion National Park",
    ]
    assert "Muir Woods" not in html


def test_rows_show_states_visited_badge_and_family_rating(client, db, member):
    parks = setup_parks(db)
    make_visit(db, parks["deva"], rating=5)
    sign_in(client, db, member)

    html = client.get("/").text

    assert "CA, NV" in html
    assert html.count("bg-emerald-100") == 1
    assert 'aria-label="5 of 5 stars"' in html


def test_the_family_rating_is_the_latest_visit_by_date(client, db, member):
    from datetime import date

    parks = setup_parks(db)
    make_visit(db, parks["zion"], rating=2, on=date(2026, 8, 1))
    make_visit(db, parks["zion"], rating=5, on=date(2024, 8, 1))  # logged later, but older
    sign_in(client, db, member)

    html = client.get("/").text

    assert 'aria-label="2 of 5 stars"' in html
    assert 'aria-label="5 of 5 stars"' not in html


def test_progress_line_counts_the_current_type(client, db, member):
    parks = setup_parks(db)
    make_visit(db, parks["zion"])
    make_visit(db, parks["zion"])  # two visits, still one park
    make_visit(db, parks["muir"])
    sign_in(client, db, member)

    assert "1 of 4 National Parks visited" in client.get("/").text
    assert "1 of 1 National Monuments visited" in client.get("/?f=1&type=National+Monument").text
    assert "2 of 5 sites visited" in client.get("/?f=1").text


def test_progress_ignores_search_and_other_filters(client, db, member):
    parks = setup_parks(db)
    make_visit(db, parks["zion"])
    sign_in(client, db, member)

    html = client.get("/?f=1&type=National+Park&q=yose&visited=not").text

    assert names(html) == ["Yosemite National Park"]
    assert "1 of 4 National Parks visited" in html


def test_search_finds_parks_by_part_of_the_name(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)

    assert names(client.get("/?q=yose").text) == ["Yosemite National Park"]
    assert names(client.get("/?q=CANYON").text) == ["Grand Canyon National Park"]
    assert "No parks match" in client.get("/?q=nothing").text


def test_visited_filter(client, db, member):
    parks = setup_parks(db)
    make_visit(db, parks["zion"])
    sign_in(client, db, member)

    assert names(client.get("/?visited=visited").text) == ["Zion National Park"]
    assert "Zion National Park" not in names(client.get("/?visited=not").text)
    assert len(names(client.get("/?visited=all").text)) == 4


def test_type_filter_takes_several_types_or_none(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)

    both = names(client.get("/?f=1&type=National+Monument&type=National+Park").text)
    assert len(both) == 5
    assert len(names(client.get("/?f=1").text)) == 5  # nothing ticked: every type
    assert names(client.get("/?f=1&type=National+Monument").text) == [
        "Muir Woods National Monument"
    ]


def test_state_and_activity_filters_combine_with_search(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)

    assert names(client.get("/?state=ut").text) == ["Zion National Park"]
    assert len(names(client.get("/?state=CA").text)) == 2  # Yosemite and Death Valley
    assert names(client.get("/?activity=Climbing").text) == ["Zion National Park"]
    assert names(client.get("/?activity=Hiking&state=CA").text) == ["Yosemite National Park"]
    assert names(client.get("/?activity=Hiking&state=CA&q=zion").text) == []


def test_the_filter_form_swaps_only_the_list(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)

    response = client.get("/?q=zion", headers={"HX-Request": "true", "HX-Target": "results"})

    assert "<html" not in response.text
    assert names(response.text) == ["Zion National Park"]


def test_clear_goes_back_to_the_defaults(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)

    html = client.get("/?f=1&type=National+Monument&q=muir").text

    assert 'href="/" class="inline-flex' in html  # the Clear button
    assert len(names(client.get("/").text)) == 4


def test_a_thumbnail_shows_with_its_credit(client, db, member):
    setup_parks(db)
    sign_in(client, db, member)

    html = client.get("/?f=1&type=National+Monument").text

    assert 'src="https://www.nps.gov/m.jpg"' in html
    assert 'alt="Redwoods"' in html
    assert "Photo: NPS Photo" in html


def test_park_names_are_escaped(client, db, member):
    make_park(db, "evil", "<script>alert(1)</script> Park")
    sign_in(client, db, member)

    html = client.get("/").text

    assert "<script>alert(1)" not in html
    assert names(html)[0].startswith("&lt;script&gt;")


def test_the_parks_page_needs_sign_in(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


def test_the_list_is_the_same_for_every_member(client, db, member):
    parks = setup_parks(db)
    make_visit(db, parks["zion"], user=member)
    other = make_user(db, email="other@example.com")
    sign_in(client, db, other)

    assert "Zion National Park" in client.get("/?visited=visited").text
