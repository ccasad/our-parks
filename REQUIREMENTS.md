# Our Parks — Requirements

Last updated 2026-11-11

Written as if this repo is public: no personal names, health or financial details, addresses or real emails.

## Overview and goals

A family app for browsing US National Park Service sites and keeping a shared log of the ones the family has visited. Park details (descriptions, photos, activities, locations) come from the official NPS API and are cached in the app; the family adds visits with a date, who went, a 1–5 star family rating and a note. The main use is browsing: a list and a map (MapLibre GL) of parks, with search and filters for visited/not visited, park type, state, activities and distance from the user's current location.

**Goals for version 1**

- Browse every NPS site in a list and on a map, defaulting to the 63 headline National Parks.
- Search by name; filter by visited / not visited, park type, state, activity and "near me".
- Log visits (several per park) to a shared family log, with a family rating.
- See progress, e.g. "5 of 63 National Parks visited".

**Success looks like:** after a month, every park the family has been to is logged and the progress count is accurate.

## Feature to-do list

- [x] Load and cache the NPS park list (refresh daily on first open, or on demand) (FR-1, FR-2)
- [x] Parks tab: list with search and filters (type defaults to National Park), progress line (FR-3 to FR-6)
- [x] Park page (photos, description, activities, links to NPS.gov and Google Maps) (FR-12, FR-13)
- [x] Family members list (for "who went") (FR-18)
- [x] Log, edit and delete visits; family rating; visited badge (FR-14 to FR-16)
- [x] Visits tab (history, newest first) (FR-17)
- [x] Map view (MapLibre GL, OpenFreeMap tiles) with the floating List/Map toggle (FR-8 to FR-10)
- [x] "Near me" filter using the browser's current location (FR-7, FR-11)
- [ ] More tab: invite, refresh park data, settings (FR-19)
- [ ] The app's own icon: a white pine tree

## Users and access

Invite-only: an admin plus the people they invite. No public sign-up. All members share one family log.

| Role | Who | Can do |
| --- | --- | --- |
| Admin | The person who runs the app | Invite and remove people, refresh park data, everything a member can do |
| Member | Family members the admin invites | Browse parks, add, edit and delete visits and ratings in the shared family log, manage the family members list |

## Functional requirements

**Park data**

- **FR-1** The app loads every NPS site from the NPS API into its own park table. It refreshes automatically on the first visit of each day, and when the admin taps "Refresh park data" in More. The load runs in steps that each finish within 60 seconds, with progress shown. Pages always read from the stored copy.
- **FR-2** Each stored park has its park code, name, designation (type), states, latitude and longitude, short description, activities, image URLs with captions, credits and alt text, and NPS.gov URL. Images are shown from NPS's own URLs and never stored.

**Parks tab: list**

- **FR-3** The Parks tab opens in List view, filtered to type "National Park" and sorted by name. Each row shows a thumbnail, the name, the state(s), a "Visited" badge if the family has a visit, and the family rating.
- **FR-4** A progress line above the list reads "N of M &lt;type&gt; visited" for the current type filter, e.g. "5 of 63 National Parks visited".
- **FR-5** A search box filters parks by name as the user types (e.g. "yose" finds Yosemite).
- **FR-6** Filters: Visited (all / visited / not visited), Type (one or more designations, default National Park), State, and Activity. Filters and search combine; a "Clear" button resets them to the defaults.
- **FR-7** "Near me": tapping it asks the browser for the current location, then sorts parks by distance with the distance shown in miles. An optional radius (100 / 250 / 500 miles, or any) limits the results. The location is sent in the request body, never in the URL, and is never stored or logged. If permission is denied, a message explains and the list is unchanged.
- **FR-8** A floating List / Map toggle sits near the bottom of the screen above the tab bar and stays visible while scrolling. Switching views keeps the current search and filters.

**Parks tab: map**

- **FR-9** Map view uses MapLibre GL with OpenFreeMap tiles and shows a marker for each park matching the current search and filters: green for visited, grey for not visited.
- **FR-10** Tapping a marker opens a small card with the photo, name, state(s), visited badge and rating, and a link to the park page.
- **FR-11** With "Near me" on, the map centres on the user's location and shows a marker for it.

**Park page**

- **FR-12** The park page shows the NPS photos (swipeable), description, activities, and links to the park on NPS.gov and to directions in Google Maps.
- **FR-13** It shows the family rating and the family's visits, newest first, with an "Add visit" button.

**Visits**

- **FR-14** "Add visit" asks for the date (default today), who went (any of the family members, at least one), a 1–5 star rating and an optional note. After saving, the park shows as visited everywhere.
- **FR-15** The park's family rating is the rating of its latest visit by date.
- **FR-16** Any member can edit or delete any visit; delete asks for confirmation.
- **FR-17** The Visits tab lists every visit, newest first, with the park name, date, who went and rating. Tapping one opens the park page.

**Family members and More**

- **FR-18** In More, any member can add, rename and remove family members, the names offered under "who went". They're separate from sign-in accounts, so people without an account can be included. A family member who is part of a visit can't be removed; they can be renamed.
- **FR-19** More also holds: invite someone (admin), Refresh park data (admin), and the template's appearance and "Your data" settings.

Tabs: **Parks**, **Visits**, **More**.

## Data scope

- **Parks (cached from the NPS API):** as in FR-2. About 430 rows, shared by everyone, refreshed daily. Public data, no encryption needed.
- **Family members:** display names for "who went". Sensitive (may include children's names): encrypted at rest.
- **Visits:** park, visit date, who went, 1–5 rating, note, created by and when. Notes encrypted at rest.
- **Shared log:** visits and family members belong to the family as a whole; every signed-in member sees and can edit them.
- **Location:** used only for "near me" during that request; never stored or logged.

## Non-functional requirements

**Security and privacy**

- **NFR-1** All traffic over HTTPS (Vercel default).
- **NFR-2** Third-party tokens and keys (the NPS API key) are kept only in environment variables.
- **NFR-3** Sensitive records (family member names, visit notes) are encrypted at rest.
- **NFR-4** Every database query is scoped to the signed-in user's family; the park table is shared read-only data.
- **NFR-5** Third-party access is read-only.
- **NFR-6** No personal data in logs, URLs or error messages; the user's location is never stored or logged.
- **NFR-7** Sessions expire after 30 minutes idle.
- **NFR-8** An audit log records sign-ins and other sensitive actions (invites, deleting visits, removing family members).

**Performance**

- **NFR-9** Each request finishes within 60 seconds; the park refresh is split across requests.
- **NFR-10** Pages load from stored data, without calling third parties, in under 2 seconds. Map tiles and park photos load in the browser from OpenFreeMap and NPS.

**Cost and operations**

- **NFR-11** Runs on free tiers (Vercel Hobby, Neon Free, NPS API, OpenFreeMap): $0 a month.
- **NFR-12** Secrets are never committed.
- **NFR-13** A user can download or delete all their data at any time.
- **NFR-14** The app shows NPS photo credits where photos appear, and OpenFreeMap / OpenStreetMap attribution on the map.

## Out of scope and future ideas

- State parks (no single API; later a one-time load from USGS PAD-US or OpenStreetMap, with Wikipedia summaries for photos)
- Third-party reviews (Google, TripAdvisor: paid APIs)
- Per-person ratings
- A Stats tab (progress by type, parks per year, map of states)
- Uploading the family's own trip photos
- Wish list / planned trips
- Working offline

## Open questions and risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| NPS API key needed | Park data can't load without it | Admin registers a free key at nps.gov/subjects/developer and adds it as the `NPS_API_KEY` environment variable; the builder stubs the loader until then |
| OpenFreeMap is a free community service | Map tiles could be slow or unavailable | Keep the tile URL in one setting so it can be swapped; the list view works without it |
| NPS API rate limit (1,000 requests an hour) | A refresh could be throttled | A daily refresh of about 430 parks needs only a few paged requests |
