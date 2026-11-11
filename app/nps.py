"""The National Park Service API: fetch a page of sites and tidy them for storage."""

from typing import Any
from urllib.parse import urlparse

import httpx2

from app.config import get_settings

PAGE_SIZE = 50


class NpsError(Exception):
    """The park service couldn't be reached or answered badly. The message is safe to show."""


def http_client() -> httpx2.Client:
    # One factory so tests can swap in a mock transport.
    return httpx2.Client(timeout=httpx2.Timeout(15.0))


def fetch_page(client: httpx2.Client, start: int) -> tuple[int, list[dict[str, Any]]]:
    """One page of parks starting at `start`: (total parks, raw rows)."""
    key = get_settings().nps_api_key
    if not key:
        raise NpsError("NPS_API_KEY is not set")
    try:
        # The key goes in a header so it never appears in a URL or a log line.
        response = client.get(
            f"{get_settings().nps_api_url}/parks",
            params={"limit": PAGE_SIZE, "start": start, "sort": "parkCode"},
            headers={"X-Api-Key": key},
        )
    except httpx2.HTTPError as exc:
        raise NpsError("The National Park Service couldn't be reached.") from exc
    if response.status_code in (401, 403):
        raise NpsError("The National Park Service rejected the API key.")
    if response.status_code == 429:
        raise NpsError("The National Park Service is limiting requests. Try again in an hour.")
    if response.status_code != 200:
        raise NpsError("The National Park Service had a problem. Try again later.")
    try:
        body = response.json()
        return int(body["total"]), list(body["data"])
    except (ValueError, KeyError, TypeError) as exc:
        raise NpsError("The National Park Service sent something unexpected.") from exc


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number != 0 else None


def _nps_url(value: Any) -> str:
    """Only https links on nps.gov: these go into href and src attributes."""
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value.strip())
    host = parsed.hostname or ""
    if parsed.scheme == "https" and (host == "nps.gov" or host.endswith(".nps.gov")):
        return value.strip()
    return ""


def parse_park(raw: dict[str, Any]) -> dict[str, Any]:
    """The fields we keep (FR-2). Raises KeyError if there's no park code."""
    images = []
    for image in raw.get("images") or []:
        url = _nps_url(image.get("url"))
        if url:
            images.append(
                {
                    "url": url,
                    "title": image.get("title") or "",
                    "caption": image.get("caption") or "",
                    "credit": image.get("credit") or "",
                    "alt": image.get("altText") or "",
                }
            )
    return {
        "park_code": str(raw["parkCode"]).strip().lower(),
        "name": (raw.get("fullName") or raw.get("name") or "").strip(),
        "designation": (raw.get("designation") or "").strip() or "Other",
        "states": ",".join(s.strip() for s in (raw.get("states") or "").split(",") if s.strip()),
        "latitude": _number(raw.get("latitude")),
        "longitude": _number(raw.get("longitude")),
        "description": (raw.get("description") or "").strip(),
        "activities": sorted(
            {a["name"].strip() for a in raw.get("activities") or [] if a.get("name")}
        ),
        "images": images,
        "url": _nps_url(raw.get("url")),
    }
