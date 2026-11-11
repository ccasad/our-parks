import uuid

from sqlalchemy import select, text

from app.models import AuditEvent, FamilyMember
from tests.conftest import make_park, make_user, make_visit, sign_in


def member_names(db):
    db.expire_all()
    return sorted(m.name for m in db.scalars(select(FamilyMember)))


def test_any_member_can_add_a_family_member(client, db, member):
    sign_in(client, db, member)

    response = client.post("/family", data={"name": "  Sam   Example "}, follow_redirects=False)

    assert response.headers["location"] == "/family?notice=added"
    assert member_names(db) == ["Sam Example"]
    assert "Sam Example" in client.get("/family").text


def test_a_blank_name_is_refused(client, db, member):
    sign_in(client, db, member)

    response = client.post("/family", data={"name": "   "}, follow_redirects=False)

    assert response.headers["location"] == "/family?notice=empty"
    assert member_names(db) == []
    assert "Enter a name." in client.get("/family?notice=empty").text


def test_rename(client, db, member):
    person = FamilyMember(name="Sam Example")
    db.add(person)
    db.commit()
    sign_in(client, db, member)

    client.post(f"/family/{person.id}/rename", data={"name": "Samantha Example"})

    assert member_names(db) == ["Samantha Example"]


def test_remove_and_audit_without_the_name(client, db, member):
    person = FamilyMember(name="Sam Example")
    db.add(person)
    db.commit()
    person_id = person.id
    sign_in(client, db, member)

    client.post(f"/family/{person_id}/remove")

    assert member_names(db) == []
    event = db.scalars(select(AuditEvent)).one()
    assert event.event == "family_member_removed"
    assert event.detail == {"family_member_id": str(person_id)}
    assert "Sam" not in str(event.detail)


def test_a_person_on_a_visit_cannot_be_removed_but_can_be_renamed(client, db, member):
    visit = make_visit(db, make_park(db))
    person = visit.members[0]
    sign_in(client, db, member)

    response = client.post(f"/family/{person.id}/remove", follow_redirects=False)
    assert response.headers["location"] == "/family?notice=in-use"
    assert member_names(db) == ["Sam Example"]
    assert "can't be removed" in client.get("/family?notice=in-use").text

    client.post(f"/family/{person.id}/rename", data={"name": "Sam E."})
    assert member_names(db) == ["Sam E."]


def test_unknown_family_members_are_404(client, db, member):
    sign_in(client, db, member)
    missing = uuid.uuid4()

    assert client.post(f"/family/{missing}/rename", data={"name": "X"}).status_code == 404
    assert client.post(f"/family/{missing}/remove").status_code == 404


def test_the_list_is_shared_by_all_members_and_sorted(client, db, member):
    db.add_all([FamilyMember(name="zed"), FamilyMember(name="Alex")])
    db.commit()
    sign_in(client, db, make_user(db, email="other@example.com"))

    html = client.get("/family").text

    assert html.index('value="Alex"') < html.index('value="zed"')


def test_names_are_encrypted_at_rest(client, db, member):
    sign_in(client, db, member)
    client.post("/family", data={"name": "Pat Examplechild"})

    raw = db.execute(text("SELECT name FROM family_members")).scalar_one()

    assert b"Examplechild" not in bytes(raw)


def test_family_routes_need_sign_in_and_the_right_origin(client, db, member):
    assert client.get("/family", follow_redirects=False).headers["location"] == "/login"
    assert client.post("/family", data={"name": "X"}, follow_redirects=False).status_code == 303
    sign_in(client, db, member)

    response = client.post(
        "/family", data={"name": "X"}, headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert member_names(db) == []
