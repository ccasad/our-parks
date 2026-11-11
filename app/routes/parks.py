"""Park data: the Parks tab and loading the park list from NPS."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app import audit, refresh
from app.models import User
from app.sessions import DbSession, SignedInUser, same_origin
from app.web import NO_STORE, templates

router = APIRouter()


def status_context(db: Session, user: User) -> dict:
    state = refresh.get_state(db)
    return {
        "refresh": state,
        "pending": refresh.needs_refresh(db),
        "is_admin": user.is_admin,
        "configured": refresh.configured(),
    }


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
