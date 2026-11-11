# Build log

## Done
- Make the template into Our Parks: name, tabs, icon, CLAUDE.md
- Load and cache the NPS park list (FR-1, FR-2) — Load and cache the NPS park list, daily and on demand
- Parks tab: list with search and filters (FR-3 to FR-6) — Add the Parks list with search, filters and progress
- Park page (FR-12, FR-13) — Add the park page with photos, details, links and visits
- Family members list (FR-18) — Add the family members list in More

## Next
- Log, edit and delete visits; family rating; visited badge (FR-14 to FR-16)
- Visits tab (FR-17)
- Map view with the floating List/Map toggle (FR-8 to FR-10)
- "Near me" filter (FR-7, FR-11)
- More tab: invite, refresh park data, settings (FR-19)

## Decisions
- App icon: a white pine tree (from `icon` in the build config), drawn by `scripts/make_icons.py` on a solid background from the slug (hue 244).
- MapLibre GL 5.24.1 is vendored in `app/static/vendor/` (the v6 build is ES-module only and needs separate worker files), so the map doesn't depend on a CDN.

- Park refresh: pages of 50 from the NPS API, a 40 s budget per request, progress in the `park_refreshes` row; the Parks page drives the daily load by itself (any member), only the admin can restart it from More (audited as `parks_refresh_started`). A failed attempt isn't retried on its own for an hour. The key is sent in the `X-Api-Key` header, never in a URL.
- Image and NPS.gov URLs are kept only if they are https on nps.gov (they end up in `src`/`href`).

- Filters live in the URL (`q`, `visited`, `type`, `state`, `activity`, plus `f=1` once the form is used, so "no type ticked" can mean every type while the default is National Park). Nothing personal is in them. The list swaps alone (`HX-Target: results`) while typing.
- The visits and family-member tables were created in this step (the list needs visits for the badge, rating and filter); their screens come in later items. A park NPS drops is kept while it has a visit (visits have a foreign key to parks).
- The progress line says "N of M sites visited" when zero or several types are selected.

## Needs a human
- Register a free NPS API key (nps.gov/subjects/developer) and set it as `NPS_API_KEY` in Vercel.
