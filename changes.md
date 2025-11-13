# Change Log

- Added shared observability helpers so voucher redemptions, manual point adjustments, check-in awards, and QR token/scan events emit structured audit logs plus Prometheus counters (`points-vouchers-rules-svc/app/observability.py`, `app/services/points.py`, `app/routers/vouchers.py`, `qr-checkin-svc/app/observability.py`, `app/routers/checkins.py`).
- Trail registration flows now handle unlimited-capacity events cleanly and every registration/trail response includes the required timestamp metadata, fixing invite acceptance and the senior trails tabs (`trails-activities-svc/app/routers/registrations.py`, `app/routers/invites.py`, `app/routers/users.py`).

- QR scan API now prioritises the activity metadata embedded in the signed token, ignoring mismatched client payloads so per-activity QR codes always record the intended activity (`qr-checkin-svc/app/routers/checkins.py`).
- QR token lifespan now stretches to the trail's end time (with a configurable grace window and max cap) so organisers can mint a code once per event instead of refreshing mid-session (`qr-checkin-svc/app/routers/checkins.py`, `app/deps.py`, `app/core/config.py`).
- Added CORS middleware to all FastAPI services to allow local frontends on ports 5173 and 3000.
- Added CORS middleware to all FastAPI services to allow local frontends on ports 5173 and 3000.
- Added checklist.md (backend root) listing every API endpoint for tracking coverage. 

- Updated checklist.md to mark exercised auth endpoints based on recent logs. 

- Documented invite endpoints in checklist.md as powering the new senior QR join flow.

- Points/vouchers services now reject attendees without an organisation assignment, and QR check-ins ensure the scanning senior belongs to the targeted organisation (`points-vouchers-rules-svc/app/routers/points.py`, `.../vouchers.py`, `qr-checkin-svc/app/routers/checkins.py`).
- QR check-in service acquires a service token to call `/points/ingest/checkin` whenever NATS awarding is disabled, ensuring attendance automatically grants points without organiser intervention (`qr-checkin-svc/app/core/config.py`, `app/services/auth_client.py`, `app/deps.py`, `.env`, `k8s/all.yaml`).
- Added `docs/backend-support.md` to capture the inter-service requirements for scan-to-join and organiser bulk balance/leaderboard flows.
- Organiser dashboard overview metrics now source their values from live participants/trails data, replacing the temporary hardcoded numbers (`cloud-project/apps/organizer-dashboard/src/app/page.tsx`).
- Introduced an organiser rewards management tab with voucher listing/creation/status controls plus the supporting API helpers (`cloud-project/apps/organizer-dashboard/src/app/rewards/page.tsx`, `src/services/vouchers.ts`, `src/app/layout.tsx`).
- Navigation now exposes distinct Points vs. Rewards tabs so ledger adjustments and voucher management live on separate screens (`cloud-project/apps/organizer-dashboard/src/app/layout.tsx`, `src/app/points/page.tsx`, `src/app/rewards/page.tsx`).
- Documented the outstanding backend work needed for per-trail reward overrides and clarified that the feature is currently unavailable (`cloud-project/docs/backend-support.md`).

- Created 	esting branch in parent repo and all submodules; updated .gitmodules to track the new branches. 

- Added organiser username/password support in authentication service (new optional credential fields, /auth/organisers/signup and /auth/organisers/login endpoints). Requires database migration to add admin credential columns.
- Trails & Activities service now enforces authenticated access for listings, honours requested initial status, and emits paginated attendee payloads (updated `trails-activities-svc/app/routers/trails.py`, `app/schemas.py`, plus new tests in `tests/test_trails_service.py`).
- Aligned Trails service role checks with actual auth roles (`attend_user`, `organiser`, `service`, `admin`) and removed the implicit `confirmed` filter from attendee listings so organisers can action pending registrations (`trails-activities-svc/app/routers/trails.py`).
- Organiser dashboard now integrates the QR Check-in service: create trail QR tokens, download server-rendered QR PNGs, and view live check-in rosters from Manage Trails (new client helpers in `apps/organizer-dashboard/src/services/checkins.ts` and UI updates in `apps/organizer-dashboard/src/app/manageTrails/page.tsx`).
- Updated checklist.md to reflect organiser dashboard coverage for trail detail endpoints and removed duplicate row.

- Authentication service now exposes `GET /users/lookup` for organiser NRIC searches, with role checks and attendee validation (`authentication-svc/app/routers/users.py`).
- Points service manual-adjust endpoint now accepts JSON payloads and returns clearer errors; organiser dashboard resolves NRICs to user IDs via the new lookup API (`points-vouchers-rules-svc/app/routers/points.py`, `app/schemas.py`, dashboard `src/services/points.ts`).

- Documented authentication Alembic workflow in docs/alembic.md to help new contributors run migrations.
- Attendance roster endpoint now requires explicit org scope and filters results by organisation (`leaderboard-attendance-svc/app/routers/attendance.py`).
- Trails listing now scopes attendee queries to their organisations and restricts visible statuses, while still supporting organiser and service filtering (`trails-activities-svc/app/routers/trails.py`).
- Added organiser-facing participant management: backend now exposes organisation listing, participant enumeration, and flexible membership assignment (`authentication-svc/app/routers/orgs.py`, `authentication-svc/app/routers/users.py`); organiser dashboard Participants tab consumes these endpoints (`cloud-project/apps/organizer-dashboard/src/app/participants/page.tsx`, `src/services/auth.ts`).
- Authored a consolidated setup guide at `csc3104_elderly_platform/Instructions.md` covering Docker services, Alembic migrations, and frontend startup steps.
- Senior PWA leaderboard now renders both system-wide and community rankings; adds organisation selector for multi-affiliated seniors and shares refreshed UI blocks across tabs (`cloud-project/apps/senior-pwa/src/pages/Leaderboard.jsx`).
- Implemented attendee-friendly Points & Vouchers APIs: scoped balance/ledger access, filtered voucher listings, enriched redemption payloads, and census ordering to support the senior PWA rewards view (`points-vouchers-rules-svc/app/routers/points.py`, `.../vouchers.py`, `.../schemas.py`).
- Added organiser endpoint to page through organisation-wide point balances (`points-vouchers-rules-svc/app/routers/points.py`).
- Self-registration endpoints now revive cancelled/rejected records instead of erroring, enabling seniors and organisers to rejoin trails without duplicate rows (`trails-activities-svc/app/routers/registrations.py`).
- Trails invites now cache the generated fallback secret so preview/register endpoints validate freshly minted tokens even when `INVITE_SECRET` is unset (`trails-activities-svc/app/core/config.py`).
- QR check-in tokens now allow seniors to retry a scan until the check-in actually succeeds: the service reserves a QR JTI and only burns it once the record is written, releasing the reservation on any failure (`qr-checkin-svc/app/core/redis.py`, `qr-checkin-svc/app/routers/checkins.py`). This prevents wasted tokens while still blocking replayed scans.
- Organiser dashboard now renders and lets you download QR codes for invite links, so `/join` can be accessed by scanning a poster instead of copying URLs (`cloud-project/apps/organizer-dashboard/src/app/manageTrails/page.tsx`, `apps/organizer-dashboard/package.json`).
- Seniors can now self-join any organisation immediately after signup: `/orgs` is readable by attendees, `/orgs/{id}/self-join` lets them add themselves, and both the Home banner and `/scan` page surface the picker that triggers the new endpoint (`authentication-svc/app/deps.py`, `.../routers/orgs.py`, `cloud-project/apps/senior-pwa/src/services/auth.js`, `.../pages/Home.jsx`, `.../pages/Scan.jsx`).
- Rewards can now be free: voucher creation, validation, and redemption accept a `points_cost` of zero, and the senior Rewards page shows the redemption code immediately after a claim (`points-vouchers-rules-svc/app/models.py`, `app/schemas.py`, `app/routers/vouchers.py`, `cloud-project/apps/organizer-dashboard/src/app/rewards/page.tsx`, `apps/senior-pwa/src/pages/Rewards.jsx`).
- Added organiser reporting APIs: auth service now returns organisation member counts, trails service exposes `/trails/reports/orgs/{id}/overview`, attendance service streams aggregated check-in summaries, and points service provides period-based award/redeem totals plus recent redemptions (`authentication-svc/app/routers/orgs.py`, `leaderboard-attendance-svc/app/routers/reports.py`, `trails-activities-svc/app/routers/trails.py`, `points-vouchers-rules-svc/app/routers/points.py`, corresponding schema updates).
- Organizer dashboard Insights tab now consumes the live reporting endpoints to render snapshot cards (membership, attendance, trails, and points activity) alongside the existing leaderboard and roster views (`cloud-project/apps/organizer-dashboard/src/services/*.ts`, `apps/organizer-dashboard/src/app/insights/page.tsx`).
- 2025-11-13 15:30: Fixed the `/trails/reports/orgs/{org_id}/overview` query so Postgres can aggregate upcoming trails without grouping every column (select only the required fields and rebuild the summary list), then marked the related TODO-FLOWS item as completed.
- Trails service now returns the `created_by` organiser for every `TrailRead` response and exposes `GET /users/me/organiser-trails` so dashboards can list the trails an organiser has created (`trails-activities-svc/app/schemas.py`, `app/routers/trails.py`, `app/routers/users.py`).
- Registration payloads (and the attendee list API) now include `trail_id`, `org_id`, and timestamp metadata with optional sorting, and vouchers expose `created_at`/`updated_at`, enabling organiser dashboards to show approval/reward timelines (`trails-activities-svc/app/schemas.py`, `app/routers/trails.py`, `app/routers/registrations.py`, `points-vouchers-rules-svc/app/schemas.py`, `app/routers/vouchers.py`).
- Organisation stats endpoint now allows admin/service roles (with scoped memberships honoured) to query `/orgs/{org_id}/stats`, preventing 403 errors when dashboards browse other organisations (`authentication-svc/app/routers/orgs.py`).
