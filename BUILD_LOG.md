# Build log

## Done
- Make the template into Our Parks: name, tabs, icon, CLAUDE.md
- Load and cache the NPS park list (FR-1, FR-2) — Load and cache the NPS park list, daily and on demand
- Parks tab: list with search and filters (FR-3 to FR-6) — Add the Parks list with search, filters and progress
- Park page (FR-12, FR-13) — Add the park page with photos, details, links and visits
- Family members list (FR-18) — Add the family members list in More
- Log, edit and delete visits; family rating; visited badge (FR-14 to FR-16) — Log, edit and delete visits and list them on the Visits tab
- Visits tab (FR-17) — same commit as above
- Map view with the floating List/Map toggle (FR-8 to FR-10) — Add the map view and the floating List/Map toggle
- "Near me" filter using the browser's current location (FR-7, FR-11) — Add "Near me" with distances, a radius and a map centred on you
- More tab: invite, refresh park data, settings (FR-19) — Check off the More tab: invite, park refresh, family, appearance, Your data
- The app's own icon: a white pine tree — Turn the template into Our Parks: name, tabs and pine tree icon

## Next
- Nothing: every to-do item is done. Later ideas are under "Out of scope" in REQUIREMENTS.md.

## Decisions
- Export and delete: visits and family members are the family's shared log, so "Download my data" includes all of it and deleting an account leaves it (visits keep a NULL `created_by_id`).
- App icon: a white pine tree (from `icon` in the build config), drawn by `scripts/make_icons.py` on a solid background from the slug (hue 244).
- MapLibre GL 5.24.1 is vendored in `app/static/vendor/` (the v6 build is ES-module only and needs separate worker files), so the map doesn't depend on a CDN.
- Park refresh: pages of 50 from the NPS API, a 40 s budget per request, progress in the `park_refreshes` row; the Parks page drives the daily load by itself (any member), only the admin can restart it from More (audited as `parks_refresh_started`). A failed attempt isn't retried on its own for an hour. The key is sent in the `X-Api-Key` header, never in a URL.
- Image and NPS.gov URLs are kept only if they are https on nps.gov (they end up in `src`/`href`).
- Filters live in the URL (`q`, `visited`, `type`, `state`, `activity`, plus `f=1` once the form is used, so "no type ticked" can mean every type while the default is National Park). Nothing personal is in them. The list swaps alone (`HX-Target: results`) while typing.
- The visits and family-member tables were created in this step (the list needs visits for the badge, rating and filter); their screens come in later items. A park NPS drops is kept while it has a visit (visits have a foreign key to parks).
- The progress line says "N of M sites visited" when zero or several types are selected.
- Visits: delete uses a confirmation page (works without JavaScript). The date defaults to the server's date, replaced with the viewer's local date by `app.js`. Dates up to one day ahead are accepted (time zones). Audit events `visit_created`, `visit_updated`, `visit_deleted` carry IDs and the park code only.
- The family is one shared group, so "scoped to the signed-in user's family" means any signed-in member; unknown IDs return 404.
- Map: markers are DOM buttons (keyboard and screen-reader friendly); the card is built with `textContent`. The map frames the lower 48 when any parks are there (Alaska, Hawaii and territories would otherwise zoom out to the world). The OpenFreeMap credit is also written under the map, in addition to MapLibre's own attribution control. The map code and library load only when a map is on the page. Not checked in a real browser here (no browser in this environment): tests cover the data and markup only.
- Near me: `POST /parks/near` takes the filters plus `lat`/`lon`/`radius` in the body and returns the list or map data (responds with `HX-Push-Url: false`, so it never reaches the address bar). While it is on, `near_me.js` turns the form's requests into that POST and the List/Map toggle into a form post. The location lives only in disabled-until-used hidden fields on the page; it is rounded to about 100 m, never stored, never in a URL, and no log line includes it (tested). `vercel.json`'s Permissions-Policy now allows `geolocation=(self)` (it blocked it before). Parks without coordinates are left out while Near me is on. Not run in a real browser here.
- Sort (001): kept in a `sort` URL/form field rather than storage, so it resets when the app is reopened. A Near me request with no sort given defaults to Distance. Pine markers are inline SVG in a 32 px button, anchored at the tree's base. Not checked in a real browser.

## Needs a human
- Register a free NPS API key (nps.gov/subjects/developer) and set it as `NPS_API_KEY` in Vercel; until then the Parks tab shows an empty state and the admin sees a notice in More.
- Try the map and Near me in a real browser (including allowing location on a phone): this build had no browser, so only the server side and markup are tested.

## Changes
- 001-sort-and-tree-markers: Sort menu on the park list; pine-tree map markers (FR-20, FR-21, FR-3, FR-7, FR-9)
