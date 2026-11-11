"""Park data: the Parks tab and loading the park list from NPS."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Path, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app import audit, refresh
from app.models import User
from app.park_list import Filters, activities, designations, find_parks, states
from app.sessions import DbSession, SignedInUser, same_origin
from app.visits import get_park, latest_rating, park_visits
from app.web import NO_STORE, render, templates

router = APIRouter()


def status_context(db: Session, user: User) -> dict:
    state = refresh.get_state(db)
    return {
        "refresh": state,
        "pending": refresh.needs_refresh(db),
        "is_admin": user.is_admin,
        "configured": refresh.configured(),
    }


@router.get("/", response_class=HTMLResponse, name="home")
def parks_page(
    request: Request,
    db: DbSession,
    user: SignedInUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    visited: Annotated[str | None, Query(max_length=10)] = None,
    types: Annotated[list[str] | None, Query(alias="type", max_length=100)] = None,
    state: Annotated[str | None, Query(max_length=2)] = None,
    activity: Annotated[str | None, Query(max_length=100)] = None,
    f: Annotated[str | None, Query(max_length=1)] = None,
) -> HTMLResponse:
    filters = Filters.from_query(
        q=q, visited=visited, types=types, state=state, activity=activity, submitted=bool(f)
    )
    result = find_parks(db, filters)
    # Typing in the search box swaps only the list, not the whole page.
    if request.headers.get("hx-target") == "results":
        return templates.TemplateResponse(
            request,
            "partials/park_list.html",
            {"filters": filters, "result": result},
            headers=NO_STORE,
        )
    context = status_context(db, user)
    db.commit()  # the refresh status row may have just been created
    return render(
        request,
        "pages/home.html",
        title="Parks",
        user=user,
        active="parks",
        filters=filters,
        result=result,
        all_types=designations(db),
        all_states=states(db),
        all_activities=activities(db),
        **context,
    )


@router.get("/parks/{park_code}", response_class=HTMLResponse)
def park_page(
    request: Request,
    db: DbSession,
    user: SignedInUser,
    park_code: Annotated[str, Path(pattern="^[A-Za-z0-9]{1,20}$")],
) -> HTMLResponse:
    park = get_park(db, park_code)
    visits = park_visits(db, park)
    directions = None
    if park.latitude is not None and park.longitude is not None:
        directions = (
            "https://www.google.com/maps/dir/?api=1&destination="
            f"{park.latitude:.6f},{park.longitude:.6f}"
        )
    return render(
        request,
        "pages/park.html",
        title=park.name,
        user=user,
        active="parks",
        park=park,
        visits=visits,
        rating=latest_rating(visits),
        directions_url=directions,
    )


@router.post("/parks/refresh", response_class=HTMLResponse, dependencies=[Depends(same_origin)])
def refresh_parks(
    request: Request,
    db: DbSession,
    user: SignedInUser,
    restart: Annotated[bool, Form()] = False,
) -> Response:
    """One step of loading the park list. The returned status asks again while it runs.

    Anyone can drive the daily load; only the admin can start one on demand.
    """
    ran = False
    if user.is_admin and restart:
        refresh.run_step(db, restart=True)
        audit.record(db, "parks_refresh_started", user_id=user.id)
        db.commit()
        ran = True
    elif refresh.needs_refresh(db):
        refresh.run_step(db)
        ran = True
    state = refresh.get_state(db)
    if state.status == "done" and ran:
        # The list on the page is out of date now; reload it.
        return Response(status_code=200, headers={**NO_STORE, "HX-Refresh": "true"})
    return templates.TemplateResponse(
        request,
        "partials/refresh_status.html",
        status_context(db, user),
        headers=NO_STORE,
    )
