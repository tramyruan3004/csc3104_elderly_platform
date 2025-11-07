# Project Report (07/11/2025)

## Repositories & Structure

- **cloud-project** (frontend workspace)  
  - `apps/senior-pwa`: Vite/React PWA for seniors. Handles login/signup, home dashboard, trail registration, QR scanning, rewards, leaderboard, and social pages.  
  - `apps/organizer-dashboard`: Next.js (App Router) dashboard for organisers/admins. Includes overview, trail management, participants, points ledger, rewards management, reports placeholder, and insights.  
  - `packages/ui`, `packages/utils`: shared design system/components and helper utilities.  
  - Key docs: `TODO-FLOWS.md` (feature checklist), `docs/backend-support.md` (service requirements), `to-be-tested.md` (manual test plans), `changes.md` (frontend changelog), this `Report.md`.

- **csc3104_elderly_platform** (backend mono-repo)  
  - `authentication-svc`: FastAPI + SQLAlchemy (Postgres) for user auth (seniors + organisers), JWT issuance, service tokens, org membership management, participant lookup.  
  - `trails-activities-svc`: FastAPI service managing trails, registrations, invites. Enforces roles (`attend_user`, `organiser`, etc.).  
  - `qr-checkin-svc`: FastAPI service for QR generation, scan ingest, roster, user history. Integrates with Trails for eligibility and Points for rewards. Uses Redis for rate limiting and JTI replay guard, optional NATS publishing.  
  - `points-vouchers-rules-svc`: FastAPI service for point balances, ledger, rules, vouchers, redemptions. Handles organiser adjustments and ingest from QR check-ins.  
  - `leaderboard-attendance-svc`: FastAPI + NATS consumer for system/org leaderboards and attendance rosters.  
  - Supporting docs: `checklist.md`, `changes.md`, service-specific `.env` templates, `docs/` directory for feature-specific guidance, `k8s/` manifests.

## Technologies

- **Frontend**: React 18, React Router (senior PWA), Next.js App Router (organiser dashboard), TypeScript, Tailwind-inspired UI via `@silvertrails/ui`. Data fetching via built-in `fetch`.  
- **Backend**: Python 3.11, FastAPI, SQLAlchemy async, Postgres, Redis (check-in rate limits), NATS (events), JWT w/ RS256. Containerized via Docker Compose / K8s manifests.  
- **Auth**: RSA-based JWTs minted by `authentication-svc`; organiser dashboard uses refresh tokens. Service tokens minted via `/auth/service-token` for server-to-server calls.  
- **Messaging**: NATS subject `checkins.recorded` optionally used by QR service to inform leaderboard and points services.  
- **Storage**: Postgres per service (`qr`, `trails`, `points`, `leaderboard`, etc.).

## Senior PWA Highlights

### Technologies
- React 18, Vite, React Router, TypeScript, `@silvertrails/ui`.  
- State management via `AuthContext` (tokens & profile), hooks for local state.  
- Services under `src/services/*.js` wrap REST calls (auth, trails, points, leaderboard, checkins).  
- Build: `pnpm --filter senior-pwa dev`.  
- Env vars: `VITE_*` (e.g., `VITE_TRAILS_API`, `VITE_QR_API`).

### Key Flows/Pages
- **Authentication**: signup/login forms, `AuthContext` handles storage, refresh scheduling, `/users/me` polling. Auto-logout on refresh failure.  
- **Home**: fetches trails/registrations, invite preview/join, progress indicator, upcoming vs. confirmed sections, unassigned banner.  
- **My Trails / Trail Detail**: status breakdown, join/cancel buttons, fetch + refresh data via service helpers.  
- **Join**: QR scanner + manual entry, works pre-auth, persists tokens, calls `previewInvite`/`acceptInvite`.  
- **Scan**: gating for org membership, QR + manual token submission, error handling, last check-in card, history table.  
- **Leaderboard**: system + per-org boards from leaderboard service, UI toggles.  
- **Rewards**: points balance, ledger, vouchers, redemptions, gating for unassigned seniors, CTA to `/join`.  
- **Misc**: Social placeholder, layout components, helper functions (`formatDate`, `extractTokenFromScan`, etc.).

## Organizer Dashboard Highlights

### Technologies
- Next.js 13 App Router, TypeScript, `@silvertrails/ui`, Tailwind-style classes.  
- Auth via `AuthContext` storing tokens in `localStorage`.  
- Services in `src/services/*.ts` (auth, trails, points, vouchers, leaderboard, checkins).  
- Layout with navigation tabs, hero banner, authenticated gating.  
- Build: `pnpm --filter organizer-dashboard dev`. Env via `NEXT_PUBLIC_*`.

### Key Pages
- **Overview**: derives KPIs (participants, activities, completion rate), shows recent trails, refresh button.  
- **Manage Trails**: comprehensive CRUD, invites, rosters, NRIC lookup, status workflows, pagination.  
- **Participants**: list seniors, assign to orgs, search/filter.  
- **Points**: org selector, balances summary, ledger list, manual adjustment form, refresh controls.  
- **Rewards**: voucher creation/edit/toggle, org selector, inline alerts, uses points service.  
- **Insights**: leaderboards & attendance with org filter.  
- **Reports**: placeholder for future analytics.  
- **Navigation**: Overview, Manage Trails, Participants, Points, Rewards, Reports, Insights.

## Backend Service Notes

### authentication-svc
- **Endpoints**: `/auth/signup`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/organisers/login`, `/auth/organisers/signup` (seed), `/auth/service-token`, `/users/me`, `/users/lookup`, `/users/participants`, `/orgs`, `/orgs/{org_id}/members`.  
- **Data**: Users table includes optional organiser credentials, credentials table stores NRIC passcodes + admin logins. Org membership table ties user IDs to orgs.  
- **JWT**: RS256 using generated or provided keys; service tokens minted with configurable `SERVICE_CLIENT_ID/SECRET`.  
- **Usage**: All frontend apps reference its JWKS for validation; backend services call `/auth/jwks`.

### trails-activities-svc
- **Trails**: status-aware (draft, published, closed, cancelled). Endpoints for listing, detail, attendee statuses, organiser actions (approve/confirm/reject/cancel).  
- **Registrations**: Self-registration, organiser-managed enrollments, cancellation, rejoin support (revives cancelled entries).  
- **Invites**: `/invites/trails/{trail_id}` for organiser link, `/invites/{token}` preview, `/invites/{token}/register` for seniors. Uses signed tokens with TTL.  
- **Security**: `get_claims` ensures roles; attendees limited to own orgs.  
- **Dependencies**: Called by PWA, dashboard, QR service.

### qr-checkin-svc
- **QR creation**: `/checkin/trails/{trail_id}/qr` signs HS256 tokens containing `trail_id`, `org_id`, `jti`, `exp`.  
- **Scan**: `/checkin/scan` validates rate limits (Redis), verifies token, ensures attendee membership, checks Trails registration via service-to-service call, records check-in, publishes to NATS, and awards points (either NATS or HTTP ingest with service token).  
- **History**: `/checkin/users/me`, `/checkin/trails/{trail_id}/roster`, plus PNG download.  
- **Config**: `.env` includes DB URL, auth JWKS, service credentials, NATS, Redis, QR secret TTL.  
- **Enhancements made**: Added service-token client to avoid reusing attendee tokens for points awarding; tightened org membership checks.

### points-vouchers-rules-svc
- **Points**: `/points/users/me/balance`, `/points/users/me/ledger`, `/points/orgs/{org_id}/balances`, `/points/orgs/{org_id}/ledger`, `/points/orgs/{org_id}/adjust`.  
- **Rewards**: `/vouchers` (list), `/vouchers/orgs/{org_id}` (create), `/vouchers/{id}` (update), `/vouchers/{id}/redeem`, `/vouchers/users/me/redemptions`.  
- **Rules**: `/orgs/{org_id}/rules` for org-wide checkin/manual bonus settings (no per-trail override).  
- **Ingest**: `/points/ingest/checkin` called by qr-checkin service.  
- **Models**: `UserPoints`, `PointsLedger`, `Rule`, `Voucher`, `Redemption`.  
- **Docs**: `docs/points-vouchers-rules_curl_cmd.txt` contains sample curl calls.

### leaderboard-attendance-svc
- **Leaderboard**: `/leaderboard/system`, `/leaderboard/orgs/{org_id}` used by PWA & organizer insights.  
- **Attendance**: `/attendance/trails/{trail_id}` for rosters; `/attendance/users/me` reserved (not yet used).  
- **NATS**: Consumes `checkins.recorded` to update stats; configurable rebuild interval via env.  
- **Security**: Organiser tokens required for org-specific data; attendees limited to their org.

## Key Flows

- **Senior onboarding**: Signup → login → home banner. If no org, gating prevents Rewards/Scan and directs to `/join`. Invite scanning persists tokens via `sessionStorage` and auto-joins after authentication.  
- **Organiser flows**:  
  - Generate invites in Manage Trails, share QR or link.  
  - Monitor registrants; use NRIC lookup to enrol or adjust statuses.  
  - Create QR tokens per trail and hand out to volunteers to scan seniors.  
  - Track points/ledger, manually adjust balances, maintain vouchers, and view leaderboards/attendance via Insights.  
  - Participants tab assigns seniors/admins to organisations.  
  - Overview page surfaces top-level KPIs and recent activity feed.

- **Rewards gating**: Backend ensures `/points` and `/vouchers` reject attendees without org membership; frontend displays onboarding callouts and hides functionality until assigned.

- **Automated point awards**: QR service awards points either via HTTP ingest (using cached service token) or by publishing to NATS for points service consumer. Duplicate awarding avoided by `award_checkin_points` idempotent ledger logic.

## Outstanding Considerations

- **Per-trail reward overrides**: Not yet supported; backend design documented in `docs/backend-support.md`. Requires Trail schema changes, QR payload updates, and UI fields.  
- **Testing**: Manual test checklist (`to-be-tested.md`) covers org gating, attendance points, rewards tab operations. Future work could automate these scenarios.  
- **Reports tab**: Placeholder – future opportunity for analytics/dashboards.  
- **Deployment**: K8s manifests under `k8s/` demonstrate service env requirements (DB URLs, JWKS, service credentials). Ensure secrets are set in real environments.

## Suggested Next Steps

1. **Automated regression tests**: especially around invite flows, QR scanning, rewards gating.  
2. **UX polish**: unify navigation cues between Points & Rewards (cross-links, breadcrumbs).  
3. **Per-trail rewards**: implement backend support if prioritised.  
4. **Reports tab**: define metrics (e.g., attendance trends, reward redemption rates) and power with existing services.  
5. **Monitoring/alerts**: ensure NATS consumers, Redis, service-token minting have observability (logs/metrics).

This report aggregates the current state across both repositories and should serve as a reference for further development, QA, and onboarding.
