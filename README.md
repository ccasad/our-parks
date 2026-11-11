# Our Parks

A family app for browsing US National Park Service sites and keeping one shared log of the parks the family has visited. Park details come from the official NPS API and are cached in the app's own table; the family adds visits with a date, who went, a 1-5 star rating and a note. Invite-only: an admin plus the people they invite, all sharing one log.

Requirements are in `REQUIREMENTS.md` (IDs FR-x, NFR-x); `BUILD_LOG.md` records what was built and the decisions taken along the way.

## Pages

| Page | Path | What it does |
| --- | --- | --- |
| Parks | `/` | List (default) or map of parks. Defaults to National Parks. Progress line ("5 of 63 National Parks visited"), search by name, filters (visited, type, state, activity), Near me, a Sort menu (name, state, rating, last visited, distance). A floating List / Map toggle keeps the search and filters. |
| Park | `/parks/{code}` | Swipeable NPS photos with credits, description, activities, links to NPS.gov and Google Maps directions, the family rating and the visits, with Add visit. |
| Add / edit visit | `/parks/{code}/visits/new`, `/visits/{id}/edit` | Date, who went (at least one), rating, optional note. Delete asks on its own page first. |
| Visits | `/visits` | Every visit, newest first. |
| More | `/more` | Family members, Park data (admin: refresh now), invite people (admin), Appearance, Your data. |
| Family members | `/family` | Add, rename and remove the names offered under "who went". Someone on a visit can't be removed. |

## Tables

| Table | Holds |
| --- | --- |
| `parks` | The NPS sites cached from the API (about 430 rows, public, shared). Images stay on NPS's servers; only their URLs, captions, credits and alt text are stored. |
| `park_refreshes` | One row: progress of the current park load, so it can span requests. |
| `family_members` | Names for "who went". Encrypted. Not sign-in accounts. |
| `visits` | One trip: park, date, rating, note (encrypted), who added it. |
| `visit_members` | Who went on each visit. A family member in a visit can't be deleted (`RESTRICT`). |

Visits and family members belong to the family as a whole, not to a user: every signed-in member sees and edits them, and they stay when someone deletes their account (a visit only forgets who added it). "Your data" downloads the whole family log.

## How it works

- **Loading parks** (`app/nps.py`, `app/refresh.py`): pages of 50 from the NPS API, as many as fit in a 40 second budget per request, with progress in `park_refreshes`. The Parks page starts the load by itself on the first visit of each UTC day (or when nothing is stored), and keeps asking for the next step while it runs. The admin can restart it from More. The API key is sent in a header, and the `NPS_API_KEY` variable is the only place it lives. A failed attempt isn't retried on its own for an hour. Parks missing from a finished load are deleted, unless the family has a visit there. Only https links on nps.gov are kept for photos and the park page.
- **List and search** (`app/park_list.py`): filtering is done in Python over the stored copy (a few hundred rows). The filters are in the URL (`q`, `visited`, `type`, `state`, `activity`, `view`); `f=1` marks the form as used, so that "no type ticked" means every type while the default is National Park. Typing swaps only the list (`HX-Target: results`).
- **Map** (`app/static/js/parks_map.js`): MapLibre GL 5 (vendored in `app/static/vendor/`) with the OpenFreeMap style from `MAP_STYLE_URL`, loaded only when a map is on the page. One button marker per park, a small pine tree (the app icon's shape), green when visited and brown when not, visited drawn on top, base anchored on the park, 32 px tap target; tapping opens a card. The credits are shown under the map as well as in the map's own attribution.
- **Sort** (`sort` in the URL, `park_list.sort_rows`): name A–Z (default), name Z–A, state, family rating, last visited, distance (only with Near me). Ties break by name. The choice lives in the page's form and the toggle/Clear links, so it survives filtering and List/Map but not reopening the app. `near_me.js` selects Distance when Near me turns on and returns to Name A–Z when it turns off.
- **Near me** (`app/static/js/near_me.js`, `POST /parks/near`): the browser's location goes in the request body only. The server uses it to work out distances (and Distance is then selected in the Sort menu) (haversine, miles) and optionally limit to 100, 250 or 500 miles, and never stores or logs it. While it is on, filter changes and the List / Map toggle are posts rather than links, so the location never reaches a URL. `Permissions-Policy` in `vercel.json` allows geolocation for this site.
- **Family rating**: the rating of a park's latest visit by date.
- **App icon**: `scripts/make_icons.py` draws the pine tree and writes every icon from one master.

## Template foundations

Everything below came with the app template.

## What's included

- **Sign-in with passkeys**, invite-only. The admin invites each person with a one-time link (`/admin/people`); the link's token is in the URL fragment, so it never reaches server logs, and only its hash is stored. A new device is set up by inviting the same email again.
- **Server-side sessions**: the cookie holds a random token, the database holds its hash. 30 minutes idle, 12 hours in all. Every state-changing route checks the `Origin` header.
- **Audit log** (`audit_events`) for sign-ins, invites, removals, exports and deletions. Never put personal data in `detail`.
- **Activity** for the admin: when each person was last active (`users.last_active_at`, set at sign-in and when the session is touched) and their sign-ins in the last 30 days, on the People page. `python -m app.cli stats` prints the same as counts only (no names), for the app factory. No page views, clicks or IP addresses are recorded; the Your data page says so.
- **Your data** (`/account`): download everything as JSON, or delete the account (type DELETE). When you add tables that belong to a user, add them to `export_data()` in `app/routes/account.py` and give them `ForeignKey("users.id", ondelete="CASCADE")`.
- **Encryption at rest**: `EncryptedText` and `EncryptedJSON` column types in `app/models.py`, keyed by `TOKEN_ENCRYPTION_KEY`.
- **Appearance**: Dark (default), Light or System, saved on the account and in a cookie.
- **PWA shell**: manifest, icons, a service worker that caches only the offline page, an offline banner. Every page is `Cache-Control: no-store`.
- **Layout**: bottom tabs on phones, a sidebar on laptops, both from `NAV_ITEMS` in `app/web.py` (up to five; keep More last). Usable at 360 px.
- **Tests** (in-memory SQLite) and a test that the migrations build the same schema as the models.
- **CI**: lint, tests and a gitleaks secret scan on every push, only for pushes by `ccasad`.

## Making a new app from it

1. Create the repo from this template with issues and the wiki off.
2. Set the app's name: `APP_NAME` (env var), `name` / `short_name` / `description` in `app/static/manifest.webmanifest`, and `name` in `pyproject.toml`.
3. Replace the placeholder icons in `app/static/icons/` (keep the file names and sizes; the maskable icon keeps its artwork inside the centre 80%).
4. Fill in `REQUIREMENTS.md` and the `CHANGE ME` lines in `CLAUDE.md`.
5. Replace `app/templates/pages/home.html` and add pages to `NAV_ITEMS`.

## Local development (Docker)

```bash
cp .env.example .env     # set DATABASE_URL to a Neon dev branch, and TOKEN_ENCRYPTION_KEY
make migrate             # create the tables
make invite-admin        # prints a one-time link to set up your passkey
make up                  # http://localhost:8000
```

| Command | What it does |
| --- | --- |
| `make up` / `make down` | Start or stop the dev server |
| `make test` | Run the tests (in-memory SQLite, never your Neon database) |
| `make lint` / `make format` | Ruff checks / auto-fix and format |
| `make css` / `make css-watch` | Rebuild `app/static/css/app.css` after changing templates (it's committed) |
| `make migration m="add x"` | Generate a migration from model changes (review it before applying) |
| `make migrate` | Apply migrations to `DATABASE_URL` |
| `make requirements` | Regenerate `requirements.txt` after changing dependencies |

## Deploying (Vercel + Neon)

Vercel deploys `main`; there's no build step. Set these in Vercel (Production): `APP_BASE_URL`, `APP_NAME`, `DATABASE_URL` (Neon pooled URL), `TOKEN_ENCRYPTION_KEY`, `ADMIN_EMAIL`, `WEBAUTHN_RP_ID` (the domain, no scheme), `NPS_API_KEY` (free, from nps.gov/subjects/developer; parks can't load without it). Apply migrations to production **before** deploying code that needs them; they never run on deploy. Then create the first admin invite with `python -m app.cli invite --admin` against the production database.

## Secrets

Never in this repo. Where each one lives:

| Variable | Where it lives | Can it be regenerated? |
| --- | --- | --- |
| `TOKEN_ENCRYPTION_KEY` | Vercel env var + 1Password ("<app> keys", App Keys vault) | **No.** A new key can't read existing data. |
| `NPS_API_KEY` | Vercel env var; nps.gov developer site | Yes (request a new key) |
| `DATABASE_URL` | Vercel env var; Neon console → Connect | Yes (reset the password in Neon) |
| `APP_BASE_URL`, `APP_NAME`, `ADMIN_EMAIL`, `WEBAUTHN_RP_ID` | Vercel env vars | Not secrets |
