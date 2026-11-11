import json

import httpx2
import pytest
from sqlalchemy import select

from app import nps, refresh
from app.config import get_settings
from app.models import AuditEvent, Park, utcnow
from tests.conftest import make_user, sign_in


def raw_park(code, name="Test Park", designation="National Park", **extra):
    return {
        "parkCode": code,
        "fullName": name,
        "designation": designation,
        "states": "CA,NV",
        "latitude": "36.5",
        "longitude": "-118.5",
        "description": "A made-up park.",
        "activities": [{"id": "1", "name": "Hiking"}, {"id": "2", "name": "Camping"}],
        "images": [
            {
                "url": "https://www.nps.gov/common/photo.jpg",
                "title": "A view",
                "caption": "Trees",
                "credit": "NPS Photo",
                "altText": "Trees by a lake",
            },
            {"url": "javascript:alert(1)", "title": "bad"},
        ],
        "url": "https://www.nps.gov/" + code + "/index.htm",
        **extra,
    }


@pytest.fixture
def nps_api(monkeypatch):
    """A fake NPS with `parks` rows; `calls` records the start offsets and headers."""
    monkeypatch.setattr(get_settings(), "nps_api_key", "test-key")
    api = type("Api", (), {})()
    api.parks = [raw_park(f"p{i:03d}", name=f"Park {i}") for i in range(120)]
    api.calls = []
    api.status = 200

    def handler(request: httpx2.Request) -> httpx2.Response:
        start = int(request.url.params["start"])
        limit = int(request.url.params["limit"])
        api.calls.append((start, request.headers.get("x-api-key"), str(request.url)))
        if api.status != 200:
            return httpx2.Response(api.status, json={})
        data = api.parks[start : start + limit]
        return httpx2.Response(200, json={"total": str(len(api.parks)), "data": data})

    monkeypatch.setattr(
        nps, "http_client", lambda: httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    return api


def parks(db):
    db.expire_all()
    return list(db.scalars(select(Park).order_by(Park.park_code)))


def test_a_refresh_loads_every_park_with_the_fields_we_keep(db, nps_api):
    state = refresh.run_step(db)

    assert state.status == "done"
    assert len(parks(db)) == 120
    park = parks(db)[0]
    assert (park.name, park.designation, park.states) == ("Park 0", "National Park", "CA,NV")
    assert (park.latitude, park.longitude) == (36.5, -118.5)
    assert park.activities == ["Camping", "Hiking"]
    # The unsafe image URL is dropped; the NPS one is kept with its credit and alt text.
    assert park.images == [
        {
            "url": "https://www.nps.gov/common/photo.jpg",
            "title": "A view",
            "caption": "Trees",
            "credit": "NPS Photo",
            "alt": "Trees by a lake",
        }
    ]
    assert park.url == "https://www.nps.gov/p000/index.htm"


def test_the_api_key_is_sent_in_a_header_not_the_url(db, nps_api):
    refresh.run_step(db)

    assert {key for _, key, _ in nps_api.calls} == {"test-key"}
    assert all("test-key" not in url for _, _, url in nps_api.calls)


def test_a_slow_refresh_continues_on_the_next_request(db, nps_api, monkeypatch):
    monkeypatch.setattr(refresh, "TIME_BUDGET", -1)  # out of time after every page

    state = refresh.run_step(db)
    assert (state.status, state.next_start, state.total) == ("running", 50, 120)
    state = refresh.run_step(db)
    assert (state.status, state.next_start) == ("running", 100)
    state = refresh.run_step(db)

    assert state.status == "done"
    assert [start for start, _, _ in nps_api.calls] == [0, 50, 100]
    assert len(parks(db)) == 120


def test_a_finished_refresh_removes_parks_nps_no_longer_lists(db, nps_api):
    refresh.run_step(db)
    nps_api.parks = nps_api.parks[:100]

    refresh.run_step(db, restart=True)

    assert len(parks(db)) == 100


def test_rows_without_a_code_or_name_are_skipped(db, nps_api):
    nps_api.parks = [{"fullName": "No code"}, raw_park("ok", name=""), raw_park("good")]

    refresh.run_step(db)

    assert [p.park_code for p in parks(db)] == ["good"]


def test_nps_errors_are_saved_with_a_safe_message(db, nps_api):
    nps_api.status = 403

    state = refresh.run_step(db)

    assert state.status == "failed"
    assert state.error == "The National Park Service rejected the API key."
    assert parks(db) == []


def test_a_failure_keeps_the_parks_already_stored(db, nps_api):
    refresh.run_step(db)
    nps_api.status = 500

    refresh.run_step(db, restart=True)

    assert len(parks(db)) == 120
    assert refresh.get_state(db).status == "failed"


def test_without_a_key_nothing_is_called_and_the_admin_is_told(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "nps_api_key", None)

    assert refresh.needs_refresh(db) is False
    state = refresh.run_step(db)

    assert state.status == "failed"
    assert "API key" in state.error


def test_it_refreshes_on_the_first_visit_of_each_day(db, nps_api):
    assert refresh.needs_refresh(db) is True  # nothing stored yet
    refresh.run_step(db)
    assert refresh.needs_refresh(db) is False

    state = refresh.get_state(db)
    state.refreshed_at = utcnow() - __import__("datetime").timedelta(days=1)
    db.commit()
    assert refresh.needs_refresh(db) is True


def test_a_failed_refresh_is_not_retried_for_an_hour(db, nps_api):
    nps_api.status = 500
    refresh.run_step(db)

    assert refresh.needs_refresh(db) is False


def test_the_parks_page_drives_the_refresh_and_reloads_when_done(client, db, member, nps_api):
    sign_in(client, db, member)

    page = client.get("/")
    assert 'hx-post="/parks/refresh"' in page.text

    response = client.post("/parks/refresh")
    assert response.headers["hx-refresh"] == "true"
    assert len(parks(db)) == 120
    assert 'hx-post="/parks/refresh"' not in client.get("/").text


def test_progress_is_shown_while_it_runs(client, db, member, nps_api, monkeypatch):
    monkeypatch.setattr(refresh, "TIME_BUDGET", -1)
    sign_in(client, db, member)

    response = client.post("/parks/refresh")

    assert 'hx-trigger="load"' in response.text
    assert "50 of 120" in response.text


def test_only_the_admin_can_refresh_on_demand(client, db, member, admin, nps_api):
    sign_in(client, db, member)
    client.post("/parks/refresh")  # the daily load, open to anyone
    calls = len(nps_api.calls)

    client.post("/parks/refresh", data={"restart": "true"})
    assert len(nps_api.calls) == calls  # a member's restart is ignored

    sign_in(client, db, admin)
    response = client.post("/parks/refresh", data={"restart": "true"})
    assert response.headers["hx-refresh"] == "true"
    assert len(nps_api.calls) > calls
    assert [e.event for e in db.scalars(select(AuditEvent))] == ["parks_refresh_started"]


def test_refresh_rejects_other_sites_and_signed_out_people(client, db, member, nps_api):
    assert client.post("/parks/refresh", follow_redirects=False).status_code == 303
    sign_in(client, db, member)

    response = client.post("/parks/refresh", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert nps_api.calls == []


def test_more_shows_the_admin_the_refresh_button(client, db, admin, member):
    sign_in(client, db, admin)
    assert "Refresh park data" in client.get("/more").text
    other = make_user(db, email="m2@example.com")
    sign_in(client, db, other)
    assert "Refresh park data" not in client.get("/more").text


def test_parse_park_handles_missing_fields():
    park = nps.parse_park({"parkCode": "ABC", "fullName": "Some Site"})

    assert park["park_code"] == "abc"
    assert park["designation"] == "Other"
    assert (park["latitude"], park["longitude"], park["images"], park["activities"]) == (
        None,
        None,
        [],
        [],
    )
    assert json.dumps(park)  # plain data, ready for JSON columns
