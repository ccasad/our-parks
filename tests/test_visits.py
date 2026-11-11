import uuid
from datetime import date, timedelta

from sqlalchemy import select, text

from app.models import AuditEvent, FamilyMember, Visit
from tests.conftest import make_park, make_user, make_visit, sign_in


def visits(db):
    db.expire_all()
    return list(db.scalars(select(Visit)))


def people(db, *names):
    found = [FamilyMember(name=n) for n in names]
    db.add_all(found)
    db.commit()
    return found


def test_the_add_visit_form_offers_the_family_and_todays_date(client, db, member):
    make_park(db)
    people(db, "Alex Example", "Sam Example")
    sign_in(client, db, member)

    html = client.get("/parks/yose/visits/new").text

    assert "Alex Example" in html and "Sam Example" in html
    assert f'value="{date.today().isoformat()}"' in html
    assert 'name="rating"' in html and 'name="note"' in html


def test_with_no_family_members_the_form_points_to_the_family_page(client, db, member):
    make_park(db)
    sign_in(client, db, member)

    assert 'href="/family"' in client.get("/parks/yose/visits/new").text


def test_adding_a_visit_makes_the_park_visited_everywhere(client, db, member):
    park = make_park(db)
    alex, sam = people(db, "Alex Example", "Sam Example")
    sign_in(client, db, member)

    response = client.post(
        "/parks/yose/visits",
        data={
            "visit_date": "2026-07-04",
            "members": [str(alex.id), str(sam.id)],
            "rating": "5",
            "note": "  Saw a bear.  ",
        },
        follow_redirects=False,
    )

    assert response.headers["location"] == "/parks/yose"
    (visit,) = visits(db)
    assert (visit.park_id, visit.visit_date, visit.rating) == (park.id, date(2026, 7, 4), 5)
    assert visit.note == "Saw a bear."
    assert {m.name for m in visit.members} == {"Alex Example", "Sam Example"}
    assert visit.created_by_id == member.id
    assert "bg-emerald-100" in client.get("/").text  # Visited badge in the list
    assert "1 of 1 National Parks visited" in client.get("/").text
    assert "Saw a bear." in client.get("/parks/yose").text
    assert "Saw a bear." in client.get("/visits").text
    assert [e.event for e in db.scalars(select(AuditEvent))] == ["visit_created"]


def test_the_note_is_optional(client, db, member):
    make_park(db)
    (alex,) = people(db, "Alex Example")
    sign_in(client, db, member)

    client.post(
        "/parks/yose/visits",
        data={"visit_date": "2026-07-04", "members": [str(alex.id)], "rating": "3"},
    )

    assert visits(db)[0].note is None


def test_bad_forms_are_refused_with_a_message_and_keep_what_was_typed(client, db, member):
    make_park(db)
    (alex,) = people(db, "Alex Example")
    sign_in(client, db, member)
    good = {"visit_date": "2026-07-04", "members": [str(alex.id)], "rating": "4", "note": "Kept"}

    cases = [
        ({"members": []}, "Choose at least one person"),
        ({"members": [str(uuid.uuid4())]}, "Choose at least one person"),
        ({"members": ["nonsense"]}, "Choose at least one person"),
        ({"rating": ""}, "Choose a rating"),
        ({"rating": "6"}, "Choose a rating"),
        ({"rating": "0"}, "Choose a rating"),
        ({"visit_date": "not a date"}, "Enter the date"),
        ({"visit_date": ""}, "Enter the date"),
        ({"visit_date": (date.today() + timedelta(days=30)).isoformat()}, "in the future"),
        ({"note": "x" * 2001}, "up to 2000 characters"),
    ]
    for change, message in cases:
        response = client.post("/parks/yose/visits", data={**good, **change})
        assert response.status_code == 400, change
        assert message in response.text, change
    assert visits(db) == []

    response = client.post("/parks/yose/visits", data={**good, "rating": ""})
    assert ">Kept</textarea>" in response.text
    assert 'value="2026-07-04"' in response.text
    assert f'value="{alex.id}" class="size-5" checked' in response.text


def test_edit_a_visit(client, db, member):
    park = make_park(db)
    visit = make_visit(db, park, rating=2, note="Old")
    (alex,) = people(db, "Alex Example")
    sign_in(client, db, member)

    page = client.get(f"/visits/{visit.id}/edit").text
    assert ">Old</textarea>" in page
    assert "Delete" in page

    response = client.post(
        f"/visits/{visit.id}",
        data={
            "visit_date": "2025-01-02",
            "members": [str(alex.id)],
            "rating": "5",
            "note": "New",
        },
        follow_redirects=False,
    )

    assert response.headers["location"] == "/parks/yose"
    (saved,) = visits(db)
    assert (saved.visit_date, saved.rating, saved.note) == (date(2025, 1, 2), 5, "New")
    assert [m.name for m in saved.members] == ["Alex Example"]
    assert "visit_updated" in [e.event for e in db.scalars(select(AuditEvent))]


def test_editing_a_visit_by_someone_else_is_allowed(client, db, member):
    # The log is shared: any member can edit any visit (FR-16).
    park = make_park(db)
    visit = make_visit(db, park, user=make_user(db, email="other@example.com"))
    sign_in(client, db, member)

    assert client.get(f"/visits/{visit.id}/edit").status_code == 200


def test_delete_asks_first_then_deletes(client, db, member):
    visit = make_visit(db, make_park(db))
    visit_id = visit.id
    sign_in(client, db, member)

    page = client.get(f"/visits/{visit_id}/delete")
    assert "Delete this visit?" in page.text
    assert len(visits(db)) == 1  # nothing deleted by looking

    response = client.post(f"/visits/{visit_id}/delete", follow_redirects=False)

    assert response.headers["location"] == "/parks/yose"
    assert visits(db) == []
    event = db.scalars(select(AuditEvent)).one()
    assert event.event == "visit_deleted"
    assert event.detail == {"visit_id": str(visit_id), "park": "yose"}
    # The person stays in the family list, and the park is no longer visited.
    assert db.scalars(select(FamilyMember)).one().name == "Sam Example"
    assert "Not visited yet" in client.get("/parks/yose").text


def test_unknown_visits_are_404(client, db, member):
    make_park(db)
    sign_in(client, db, member)
    missing = uuid.uuid4()

    assert client.get(f"/visits/{missing}/edit").status_code == 404
    assert client.get(f"/visits/{missing}/delete").status_code == 404
    assert client.post(f"/visits/{missing}", data={}).status_code == 404
    assert client.post(f"/visits/{missing}/delete").status_code == 404
    assert client.get("/parks/nope/visits/new").status_code == 404
    assert client.post("/parks/nope/visits", data={}).status_code == 404


def test_visit_routes_need_sign_in_and_the_right_origin(client, db, member):
    visit = make_visit(db, make_park(db))
    for path in ("/parks/yose/visits/new", f"/visits/{visit.id}/edit", "/visits"):
        assert client.get(path, follow_redirects=False).headers["location"] == "/login"
    assert client.post(f"/visits/{visit.id}/delete", follow_redirects=False).status_code == 303
    assert len(visits(db)) == 1

    sign_in(client, db, member)
    other_site = {"Origin": "https://evil.example"}
    assert client.post(f"/visits/{visit.id}/delete", headers=other_site).status_code == 403
    assert client.post(f"/visits/{visit.id}", data={}, headers=other_site).status_code == 403
    assert client.post("/parks/yose/visits", data={}, headers=other_site).status_code == 403
    assert len(visits(db)) == 1


def test_notes_are_encrypted_at_rest(client, db, member):
    make_visit(db, make_park(db), note="Secret picnic spot")

    raw = db.execute(text("SELECT note FROM visits")).scalar_one()

    assert b"picnic" not in bytes(raw)


def test_the_visits_tab_lists_newest_first_with_links_to_the_park(client, db, member):
    yose = make_park(db)
    zion = make_park(db, "zion", "Zion National Park")
    make_visit(db, yose, on=date(2024, 5, 1), rating=3)
    make_visit(db, zion, on=date(2026, 5, 1), rating=5)
    sign_in(client, db, member)

    html = client.get("/visits").text

    assert html.index("Zion National Park") < html.index("Yosemite National Park")
    assert 'href="/parks/zion"' in html
    assert "May 1, 2026" in html and "Sam Example" in html
    assert 'aria-label="5 of 5 stars"' in html


def test_the_visits_tab_is_empty_at_first(client, db, member):
    sign_in(client, db, member)

    assert "No visits yet" in client.get("/visits").text
