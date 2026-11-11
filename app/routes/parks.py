"""Park data: the Parks tab and loading the park list from NPS."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Path, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app import audit, refresh
from app.config import get_settings
from app.models import User
from app.park_list import (
    RADII,
    SORTS,
    Filters,
    activities,
    clean_sort,
    designations,
    find_parks,
    map_points,
    states,
)
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


def show_parks(
    request: Request,
    db: Session,
    user: User,
    filters: Filters,
    view: str | None,
    near: tuple[float, float] | None = None,
    radius: int | None = None,
    sort: str | None = None,
) -> HTMLResponse:
    sort = clean_sort(sort, near is not None)
    result = find_parks(db, filters, near=near, radius=radius, sort=sort)
    view = "map" if view == "map" else "list"
    context = {
        "filters": filters,
        "result": result,
        "view": view,
        "points": map_points(result),
        "near": near,
        "radius": radius,
        "sort": sort,
        "sorts": SORTS,
    }
    # Typing in the search box swaps only the list (or the map's data), not the whole page.
    if request.headers.get("hx-target") == "results":
        template = "partials/park_map_data.html" if view == "map" else "partials/park_list.html"
        headers = dict(NO_STORE)
        if near is not None:
            # The request came from a POST to /parks/near; never put that in the address bar.
            headers["HX-Push-Url"] = "false"
        return templates.TemplateResponse(request, template, context, headers=headers)
    status = status_context(db, user)
    db.commit()  # the refresh status row may have just been created
    return render(
        request,
        "pages/home.html",
        title="Parks",
        user=user,
        active="parks",
        map_style_url=get_settings().map_style_url,
        all_types=designations(db),
        all_states=states(db),
        all_activities=activities(db),
        **context,
        **status,
    )


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
    view: Annotated[str | None, Query(max_length=4)] = None,
    sort: Annotated[str | None, Query(max_length=10)] = None,
) -> HTMLResponse:
    filters = Filters.from_query(
        q=q, visited=visited, types=types, state=state, activity=activity, submitted=bool(f)
    )
    return show_parks(request, db, user, filters, view, sort=sort)


@router.post("/parks/near", response_class=HTMLResponse, dependencies=[Depends(same_origin)])
def parks_near(
    request: Request,
    db: DbSession,
    user: SignedInUser,
    lat: Annotated[float, Form(ge=-90, le=90)],
    lon: Annotated[float, Form(ge=-180, le=180)],
    q: Annotated[str | None, Form(max_length=100)] = None,
    visited: Annotated[str | None, Form(max_length=10)] = None,
    types: Annotated[list[str] | None, Form(alias="type")] = None,
    state: Annotated[str | None, Form(max_length=2)] = None,
    activity: Annotated[str | None, Form(max_length=100)] = None,
    f: Annotated[str | None, Form(max_length=1)] = None,
    view: Annotated[str | None, Form(max_length=4)] = None,
    radius: Annotated[str | None, Form(max_length=4)] = None,
    sort: Annotated[str | None, Form(max_length=10)] = None,
) -> HTMLResponse:
    """The list or map sorted by distance from where the person is (FR-7, FR-11).

    A POST so the location travels in the request body, never the URL. It is used to
    work out distances for this response and is not stored or logged.
    """
    filters = Filters.from_query(
        q=q, visited=visited, types=types, state=state, activity=activity, submitted=bool(f)
    )
    miles = int(radius) if radius and radius.isdigit() and int(radius) in RADII else None
    return show_parks(request, db, user, filters, view, near=(lat, lon), radius=miles, sort=sort)


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
