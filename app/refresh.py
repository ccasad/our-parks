"""Load the park list from NPS into the parks table, in steps that each fit in one request.

Progress is saved in the single `park_refreshes` row. Each step fetches pages until the
time budget is used up, then returns "running" and the browser asks again (FR-1, NFR-9).
Parks not seen in a finished run are deleted, so the stored copy mirrors NPS.
"""

import time
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import nps
from app.config import get_settings
from app.models import Park, ParkRefresh, utcnow

# Below Vercel's 60 second limit, checked between pages.
TIME_BUDGET = 40.0
# A running refresh nobody has continued for this long is abandoned, and starts over.
STALE_AFTER = timedelta(minutes=10)
# After a failed attempt, wait before trying again on its own.
RETRY_AFTER = timedelta(hours=1)


def get_state(db: Session) -> ParkRefresh:
    state = db.get(ParkRefresh, 1)
    if state is None:
        state = ParkRefresh(id=1)
        db.add(state)
        db.flush()
    return state


def configured() -> bool:
    return bool(get_settings().nps_api_key)


def is_running(state: ParkRefresh) -> bool:
    return state.status == "running" and state.started_at is not None


def needs_refresh(db: Session) -> bool:
    """True on the first visit of each day (UTC), or when no parks are stored yet."""
    if not configured():
        return False
    state = get_state(db)
    now = utcnow()
    if state.status == "running" and state.attempted_at and now - state.attempted_at < STALE_AFTER:
        return True  # in progress: keep going
    if state.status == "failed" and state.attempted_at and now - state.attempted_at < RETRY_AFTER:
        return False
    if state.refreshed_at is None:
        return True
    return state.refreshed_at.date() < now.date()


def park_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Park)) or 0


def run_step(db: Session, *, restart: bool = False) -> ParkRefresh:
    """Do one request's worth of loading and return the saved state."""
    state = get_state(db)
    now = utcnow()
    if not configured():
        state.status = "failed"
        state.error = "No NPS API key is set. The admin needs to add one."
        db.commit()
        return state

    stale = state.attempted_at is None or now - state.attempted_at > STALE_AFTER
    if restart or state.status != "running" or stale:
        state.status = "running"
        state.started_at = now
        state.next_start = 0
        state.total = None
        state.error = None
    state.attempted_at = now
    db.commit()

    deadline = time.monotonic() + TIME_BUDGET
    try:
        with nps.http_client() as client:
            while True:
                total, rows = nps.fetch_page(client, state.next_start)
                state.total = total
                _store(db, rows)
                state.next_start += len(rows)
                state.attempted_at = utcnow()
                if not rows or state.next_start >= total:
                    _finish(db, state)
                    break
                db.commit()
                if time.monotonic() >= deadline:
                    break
    except nps.NpsError as exc:
        db.rollback()
        state = get_state(db)
        state.status = "failed"
        state.error = str(exc)
        state.attempted_at = utcnow()
    db.commit()
    return state


def _store(db: Session, rows: list[dict]) -> None:
    parsed = []
    for raw in rows:
        try:
            park = nps.parse_park(raw)
        except (KeyError, AttributeError, TypeError):
            continue  # one odd row shouldn't stop the whole load
        if park["name"]:
            parsed.append(park)
    existing = {
        park.park_code: park
        for park in db.scalars(
            select(Park).where(Park.park_code.in_([p["park_code"] for p in parsed]))
        )
    }
    for fields in parsed:
        park = existing.get(fields["park_code"])
        if park is None:
            park = Park(**fields)
            db.add(park)
            existing[park.park_code] = park
        else:
            for key, value in fields.items():
                setattr(park, key, value)
        park.fetched_at = utcnow()
    db.flush()


def _finish(db: Session, state: ParkRefresh) -> None:
    # Anything not touched since this run began is gone from NPS.
    if state.started_at is not None and state.next_start > 0:
        db.execute(delete(Park).where(Park.fetched_at < state.started_at))
    state.status = "done"
    state.error = None
    state.refreshed_at = utcnow()
    state.attempted_at = state.refreshed_at
