# Change Log

- Added CORS middleware to all FastAPI services to allow local frontends on ports 5173 and 3000.
- Added checklist.md (backend root) listing every API endpoint for tracking coverage. 

- Updated checklist.md to mark exercised auth endpoints based on recent logs. 

- Documented invite endpoints in checklist.md as powering the new senior QR join flow.

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
