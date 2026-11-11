"""Family members: the names offered under "who went" (FR-18). Shared by every signed-in member."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.models import FamilyMember, VisitMember
from app.sessions import DbSession, SignedInUser, same_origin
from app.web import render

router = APIRouter(prefix="/family")

NOTICES = {
    "in-use": "That person is part of a visit, so they can't be removed. You can rename them.",
    "empty": "Enter a name.",
    "added": "Added.",
    "renamed": "Renamed.",
    "removed": "Removed.",
}


def family_members(db: Session) -> list[FamilyMember]:
    # Names are encrypted, so they can't be sorted in the database.
    return sorted(db.scalars(select(FamilyMember)), key=lambda m: m.name.casefold())


def get_member(db: Session, member_id: uuid.UUID) -> FamilyMember:
    member = db.get(FamilyMember, member_id)
    if member is None:
        raise HTTPException(status_code=404)
    return member


def clean_name(name: str) -> str:
    return " ".join(name.split())


@router.get("", response_class=HTMLResponse)
def family_page(
    request: Request, db: DbSession, user: SignedInUser, notice: str | None = None
) -> HTMLResponse:
    members = family_members(db)
    in_use = set(db.scalars(select(VisitMember.family_member_id)))
    return render(
        request,
        "pages/family.html",
        title="Family members",
        user=user,
        active="more",
        members=members,
        in_use=in_use,
        notice=NOTICES.get(notice or ""),
    )


@router.post("", dependencies=[Depends(same_origin)])
def add_member(
    db: DbSession, user: SignedInUser, name: Annotated[str, Form(max_length=100)]
) -> RedirectResponse:
    name = clean_name(name)
    if not name:
        return RedirectResponse("/family?notice=empty", status_code=303)
    db.add(FamilyMember(name=name))
    db.commit()
    return RedirectResponse("/family?notice=added", status_code=303)


@router.post("/{member_id}/rename", dependencies=[Depends(same_origin)])
def rename_member(
    member_id: uuid.UUID,
    db: DbSession,
    user: SignedInUser,
    name: Annotated[str, Form(max_length=100)],
) -> RedirectResponse:
    member = get_member(db, member_id)
    name = clean_name(name)
    if not name:
        return RedirectResponse("/family?notice=empty", status_code=303)
    member.name = name
    db.commit()
    return RedirectResponse("/family?notice=renamed", status_code=303)


@router.post("/{member_id}/remove", dependencies=[Depends(same_origin)])
def remove_member(member_id: uuid.UUID, db: DbSession, user: SignedInUser) -> RedirectResponse:
    member = get_member(db, member_id)
    in_use = db.scalar(select(VisitMember).where(VisitMember.family_member_id == member.id))
    if in_use is not None:
        return RedirectResponse("/family?notice=in-use", status_code=303)
    # The audit entry holds the ID only, never the name.
    audit.record(db, "family_member_removed", user_id=user.id, family_member_id=str(member.id))
    db.delete(member)
    db.commit()
    return RedirectResponse("/family?notice=removed", status_code=303)
