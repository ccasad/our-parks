"""Reading the family's visit log."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Park, Visit


def get_park(db: Session, park_code: str) -> Park:
    park = db.scalar(select(Park).where(Park.park_code == park_code.lower()))
    if park is None:
        raise HTTPException(status_code=404)
    return park


def visit_query():
    """Visits newest first, with the park and who went loaded."""
    return (
        select(Visit)
        .options(selectinload(Visit.members), selectinload(Visit.park))
        .order_by(Visit.visit_date.desc(), Visit.created_at.desc())
    )


def park_visits(db: Session, park: Park) -> list[Visit]:
    return list(db.scalars(visit_query().where(Visit.park_id == park.id)))


def all_visits(db: Session) -> list[Visit]:
    return list(db.scalars(visit_query()))


def latest_rating(visits: list[Visit]) -> int | None:
    """The park's family rating: the latest visit by date (FR-15). `visits` is newest first."""
    return visits[0].rating if visits else None
