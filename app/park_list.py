"""Finding parks for the list and the map: search and filters (FR-3 to FR-6)."""

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Park, Visit

DEFAULT_TYPE = "National Park"
VISITED_CHOICES = ("all", "visited", "not")


@dataclass
class Filters:
    q: str = ""
    visited: str = "all"
    types: list[str] = field(default_factory=lambda: [DEFAULT_TYPE])
    state: str = ""
    activity: str = ""

    @classmethod
    def from_query(
        cls,
        *,
        q: str | None,
        visited: str | None,
        types: list[str] | None,
        state: str | None,
        activity: str | None,
        submitted: bool,
    ) -> "Filters":
        """Types default to National Park until the filter form has been used; then exactly
        what's ticked applies, and none ticked means every type."""
        return cls(
            q=(q or "").strip()[:100],
            visited=visited if visited in VISITED_CHOICES else "all",
            types=[t for t in (types or []) if t][:50] if submitted else [DEFAULT_TYPE],
            state=(state or "").strip().upper()[:2],
            activity=(activity or "").strip()[:100],
        )

    @property
    def is_default(self) -> bool:
        return self == Filters()

    def query(self, view: str = "list") -> str:
        """The URL query that gives back these filters, for the List/Map toggle (FR-8)."""
        pairs: list[tuple[str, str]] = []
        if not self.is_default:
            pairs.append(("f", "1"))
            if self.q:
                pairs.append(("q", self.q))
            if self.visited != "all":
                pairs.append(("visited", self.visited))
            pairs.extend(("type", t) for t in self.types)
            if self.state:
                pairs.append(("state", self.state))
            if self.activity:
                pairs.append(("activity", self.activity))
        if view == "map":
            pairs.append(("view", "map"))
        return "?" + urlencode(pairs) if pairs else "/"


@dataclass
class ParkRow:
    park: Park
    visited: bool = False
    rating: int | None = None  # the latest visit's rating (FR-15)
    visits: int = 0
    miles: float | None = None

    @property
    def thumbnail(self) -> dict[str, Any] | None:
        return self.park.images[0] if self.park.images else None


@dataclass
class Result:
    rows: list[ParkRow]
    visited_count: int  # among parks of the chosen types, ignoring the other filters
    type_total: int
    progress_label: str


def plural(designation: str) -> str:
    return designation if designation.endswith("s") else designation + "s"


def visit_summary(db: Session) -> dict[Any, tuple[int, int]]:
    """park id -> (visit count, rating of the latest visit by date)."""
    summary: dict[Any, tuple[int, int]] = {}
    rows = db.execute(
        select(Visit.park_id, Visit.rating).order_by(
            Visit.visit_date, Visit.created_at
        )  # later visits overwrite earlier ones
    )
    for park_id, rating in rows:
        count, _ = summary.get(park_id, (0, 0))
        summary[park_id] = (count + 1, rating)
    return summary


def designations(db: Session) -> list[str]:
    """Every type in the stored data, National Park first."""
    names = db.scalars(select(Park.designation).distinct().order_by(Park.designation)).all()
    return sorted(names, key=lambda n: (n != DEFAULT_TYPE, n))


def states(db: Session) -> list[str]:
    codes: set[str] = set()
    for value in db.scalars(select(Park.states).distinct()):
        codes.update(s for s in value.split(",") if s)
    return sorted(codes)


def activities(db: Session) -> list[str]:
    names: set[str] = set()
    for value in db.scalars(select(Park.activities)):
        names.update(value or [])
    return sorted(names, key=str.lower)


def find_parks(db: Session, filters: Filters) -> Result:
    query = select(Park).order_by(Park.name)
    if filters.types:
        query = query.where(Park.designation.in_(filters.types))
    parks = list(db.scalars(query))
    summary = visit_summary(db)

    visited_count = sum(1 for p in parks if p.id in summary)
    if len(filters.types) == 1:
        label = f"{plural(filters.types[0])}"
    else:
        label = "sites"

    needle = filters.q.casefold()
    rows = []
    for park in parks:
        count, rating = summary.get(park.id, (0, 0))
        if needle and needle not in park.name.casefold():
            continue
        if filters.visited == "visited" and not count:
            continue
        if filters.visited == "not" and count:
            continue
        if filters.state and filters.state not in park.state_list:
            continue
        if filters.activity and filters.activity not in (park.activities or []):
            continue
        rows.append(ParkRow(park, visited=bool(count), rating=rating or None, visits=count))
    return Result(rows, visited_count, len(parks), label)


def map_points(result: Result) -> list[dict[str, Any]]:
    """What the map needs for each park with a location (FR-9, FR-10)."""
    points = []
    for row in result.rows:
        park = row.park
        if park.latitude is None or park.longitude is None:
            continue
        thumb = row.thumbnail
        points.append(
            {
                "code": park.park_code,
                "name": park.name,
                "states": ", ".join(park.state_list),
                "lat": park.latitude,
                "lon": park.longitude,
                "visited": row.visited,
                "rating": row.rating,
                "photo": thumb["url"] if thumb else None,
                "alt": thumb["alt"] if thumb else "",
                "credit": thumb["credit"] if thumb else "",
            }
        )
    return points
