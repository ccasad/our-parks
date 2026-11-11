"""Your data: download everything, or delete your account."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.config import get_settings
from app.models import FamilyMember, User, Visit
from app.sessions import SESSION_COOKIE, DbSession, SignedInUser, same_origin
from app.visits import all_visits
from app.web import render

router = APIRouter()

NOTICES = {
    "only-admin": "You're the only admin. Make someone else an admin before deleting your account."
}


def iso(moment: datetime | None) -> str | None:
    return moment.astimezone(UTC).isoformat() if moment else None


def export_data(db: Session, user: User) -> dict[str, Any]:
    """Everything stored for this user, without secrets (no tokens, no passkey keys).

    Visits and family members belong to the whole family, not to one person, so all of
    them are included, and they stay when someone deletes their account.
    """
    visits = all_visits(db)
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "app": get_settings().app_name,
        "account": {
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "theme": user.theme,
            "created_at": iso(user.created_at),
            "last_active_at": iso(user.last_active_at),
            "passkeys": len(user.passkeys),
        },
        # The family log is shared by every member, so the download holds all of it.
        "family_members": [
            {"id": str(m.id), "name": m.name}
            for m in sorted(db.scalars(select(FamilyMember)), key=lambda m: m.name.casefold())
        ],
        "visits": [visit_export(visit, user) for visit in visits],
    }


def visit_export(visit: Visit, user: User) -> dict[str, Any]:
    return {
        "id": str(visit.id),
        "park_code": visit.park.park_code,
        "park": visit.park.name,
        "date": visit.visit_date.isoformat(),
        "who_went": sorted(m.name for m in visit.members),
        "rating": visit.rating,
        "note": visit.note,
        "added_by_you": visit.created_by_id == user.id,
        "created_at": iso(visit.created_at),
    }


def only_admin(db: Session, user: User) -> bool:
    if not user.is_admin:
        return False
    admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin"))
    return admins <= 1


@router.get("/account", response_class=HTMLResponse)
def account(
    request: Request, db: DbSession, user: SignedInUser, notice: str | None = None
) -> HTMLResponse:
    return render(
        request,
        "pages/account.html",
        title="Your data",
        user=user,
        active="more",
        can_delete=not only_admin(db, user),
        notice=NOTICES.get(notice or ""),
    )


@router.get("/account/export")
def export(db: DbSession, user: SignedInUser) -> Response:
    data = export_data(db, user)
    audit.record(db, "data_exported", user_id=user.id)
    db.commit()
    slug = "".join(c if c.isalnum() else "-" for c in get_settings().app_name.lower()).strip("-")
    filename = f"{slug or 'app'}-{datetime.now(UTC):%Y-%m-%d}.json"
    return Response(
        json.dumps(data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/account/delete", dependencies=[Depends(same_origin)])
def delete_account(
    db: DbSession, user: SignedInUser, confirm: Annotated[str, Form(max_length=20)] = ""
) -> RedirectResponse:
    if confirm.strip().upper() != "DELETE":
        return RedirectResponse("/account", status_code=303)
    if only_admin(db, user):
        return RedirectResponse("/account?notice=only-admin", status_code=303)
    # The audit trail keeps the event without saying who it was.
    audit.record(db, "account_deleted")
    # Cascades to passkeys and sessions. The family log (visits, family members) is shared,
    # so it stays; visits only forget who added them (created_by_id is set to NULL).
    db.delete(user)
    db.commit()
    response = RedirectResponse("/login?notice=deleted", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
