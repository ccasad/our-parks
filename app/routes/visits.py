"""Log, edit and delete visits in the family's shared log (FR-14 to FR-17)."""

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.models import FamilyMember, Park, Visit
from app.routes.family import family_members
from app.sessions import DbSession, SignedInUser, same_origin
from app.visits import all_visits, get_park, visit_query
from app.web import render

router = APIRouter()

ParkCode = Annotated[str, Path(pattern="^[A-Za-z0-9]{1,20}$")]
NOTE_MAX = 2000


def get_visit(db: Session, visit_id: uuid.UUID) -> Visit:
    visit = db.scalar(visit_query().where(Visit.id == visit_id))
    if visit is None:
        raise HTTPException(status_code=404)
    return visit


def form_page(
    request: Request,
    db: Session,
    user,
    park: Park,
    *,
    visit: Visit | None = None,
    values: dict | None = None,
    error: str | None = None,
):
    if values is None:
        values = {
            "visit_date": (visit.visit_date if visit else date.today()).isoformat(),
            "members": [str(m.id) for m in visit.members] if visit else [],
            "rating": str(visit.rating) if visit else "",
            "note": (visit.note or "") if visit else "",
        }
    return render(
        request,
        "pages/visit_form.html",
        title="Edit visit" if visit else "Add visit",
        user=user,
        active="parks" if visit is None else "visits",
        park=park,
        visit=visit,
        members=family_members(db),
        values=values,
        error=error,
        status_code=400 if error else 200,
    )


def read_form(
    db: Session, visit_date: str, members: list[str], rating: str, note: str
) -> tuple[dict | None, list[FamilyMember], str | None]:
    """Check what was submitted. Returns (clean values, chosen people, error message)."""
    values = {"visit_date": visit_date, "members": members, "rating": rating, "note": note}
    try:
        when = date.fromisoformat(visit_date)
    except ValueError:
        return values, [], "Enter the date of the visit."
    if when > date.today() + timedelta(days=1):
        return values, [], "The date can't be in the future."
    if when.year < 1850:
        return values, [], "Enter the date of the visit."
    if rating not in ("1", "2", "3", "4", "5"):
        return values, [], "Choose a rating from 1 to 5 stars."
    try:
        ids = {uuid.UUID(m) for m in members}
    except ValueError:
        ids = set()
    chosen = list(db.scalars(select(FamilyMember).where(FamilyMember.id.in_(ids)))) if ids else []
    if not chosen or len(chosen) != len(ids):
        return values, [], "Choose at least one person who went."
    if len(note) > NOTE_MAX:
        return values, [], f"The note can be up to {NOTE_MAX} characters."
    return None, chosen, None


@router.get("/parks/{park_code}/visits/new", response_class=HTMLResponse)
def new_visit(request: Request, park_code: ParkCode, db: DbSession, user: SignedInUser):
    return form_page(request, db, user, get_park(db, park_code))


@router.post("/parks/{park_code}/visits", dependencies=[Depends(same_origin)])
def create_visit(
    request: Request,
    park_code: ParkCode,
    db: DbSession,
    user: SignedInUser,
    visit_date: Annotated[str, Form(max_length=10)] = "",
    members: Annotated[list[str] | None, Form()] = None,
    rating: Annotated[str, Form(max_length=2)] = "",
    note: Annotated[str, Form(max_length=5000)] = "",
):
    park = get_park(db, park_code)
    bad, chosen, error = read_form(db, visit_date, members or [], rating, note.strip())
    if error:
        return form_page(request, db, user, park, values=bad, error=error)
    visit = Visit(
        park_id=park.id,
        visit_date=date.fromisoformat(visit_date),
        rating=int(rating),
        note=note.strip() or None,
        created_by_id=user.id,
        members=chosen,
    )
    db.add(visit)
    db.flush()
    audit.record(db, "visit_created", user_id=user.id, visit_id=str(visit.id), park=park.park_code)
    db.commit()
    return RedirectResponse(f"/parks/{park.park_code}", status_code=303)


@router.get("/visits/{visit_id}/edit", response_class=HTMLResponse)
def edit_visit(request: Request, visit_id: uuid.UUID, db: DbSession, user: SignedInUser):
    visit = get_visit(db, visit_id)
    return form_page(request, db, user, visit.park, visit=visit)


@router.post("/visits/{visit_id}", dependencies=[Depends(same_origin)])
def update_visit(
    request: Request,
    visit_id: uuid.UUID,
    db: DbSession,
    user: SignedInUser,
    visit_date: Annotated[str, Form(max_length=10)] = "",
    members: Annotated[list[str] | None, Form()] = None,
    rating: Annotated[str, Form(max_length=2)] = "",
    note: Annotated[str, Form(max_length=5000)] = "",
):
    visit = get_visit(db, visit_id)
    bad, chosen, error = read_form(db, visit_date, members or [], rating, note.strip())
    if error:
        return form_page(request, db, user, visit.park, visit=visit, values=bad, error=error)
    visit.visit_date = date.fromisoformat(visit_date)
    visit.rating = int(rating)
    visit.note = note.strip() or None
    visit.members = chosen
    audit.record(db, "visit_updated", user_id=user.id, visit_id=str(visit.id))
    db.commit()
    return RedirectResponse(f"/parks/{visit.park.park_code}", status_code=303)


@router.get("/visits/{visit_id}/delete", response_class=HTMLResponse)
def confirm_delete(request: Request, visit_id: uuid.UUID, db: DbSession, user: SignedInUser):
    visit = get_visit(db, visit_id)
    return render(
        request,
        "pages/visit_delete.html",
        title="Delete visit",
        user=user,
        active="visits",
        visit=visit,
    )


@router.post("/visits/{visit_id}/delete", dependencies=[Depends(same_origin)])
def delete_visit(visit_id: uuid.UUID, db: DbSession, user: SignedInUser) -> RedirectResponse:
    visit = get_visit(db, visit_id)
    park_code = visit.park.park_code
    audit.record(db, "visit_deleted", user_id=user.id, visit_id=str(visit.id), park=park_code)
    db.delete(visit)
    db.commit()
    return RedirectResponse(f"/parks/{park_code}", status_code=303)


@router.get("/visits", response_class=HTMLResponse, name="visits")
def visits_page(request: Request, db: DbSession, user: SignedInUser) -> HTMLResponse:
    return render(
        request,
        "pages/visits.html",
        title="Visits",
        user=user,
        active="visits",
        visits=all_visits(db),
    )
