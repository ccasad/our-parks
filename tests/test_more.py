from tests.conftest import make_user, sign_in


def test_admin_sees_invite_refresh_family_appearance_and_your_data(client, db, admin):
    sign_in(client, db, admin)

    html = client.get("/more").text

    assert 'href="/admin/people"' in html  # invite someone
    assert "Refresh park data" in html
    assert 'href="/family"' in html
    assert "Appearance" in html and 'name="theme"' in html
    assert 'href="/account"' in html  # Your data


def test_members_see_family_appearance_and_your_data_but_not_admin_tools(client, db, member):
    sign_in(client, db, member)

    html = client.get("/more").text

    assert 'href="/family"' in html and "Appearance" in html and 'href="/account"' in html
    assert 'href="/admin/people"' not in html
    assert "Refresh park data" not in html


def test_members_cannot_reach_the_admin_pages(client, db, member):
    sign_in(client, db, member)

    assert client.get("/admin/people").status_code == 403


def test_the_tabs_are_parks_visits_more(client, db, member):
    sign_in(client, db, make_user(db, email="x@example.com"))

    html = client.get("/more").text

    assert html.index(">Parks<") < html.index(">Visits<") < html.rindex(">More<")
