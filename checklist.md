# API Checklist

Legend: ✅ Implemented in client • ✔️ Planned / pending implementation • ⬜ Not required / unused

## Authentication Service (http://localhost:8001)
| Endpoint | Senior PWA | Organiser Dashboard | Notes |
| --- | --- | --- | --- |
| POST /auth/signup | ✅ | ⬜ | Seniors self-signup only |
| POST /auth/login | ✅ | ⬜ | NRIC + passcode flow |
| POST /auth/refresh | ✅ | ✅ | Dashboard auto-refreshes session | Dashboard still uses static session |
| POST /auth/logout | ✅ | ✅ | Revokes tokens on logout | Dashboard clears local state only |
| GET /users/me | ✅ | ✅ | Hydrate organiser profile | Dashboard to hydrate organiser profile |
| GET /users/lookup | ⬜ | ✅ | Organiser NRIC lookup for participant UUIDs |
| GET /users/participants | ⬜ | ✅ | Participants tab lists all seniors with memberships |
| POST /auth/organisers/login | ⬜ | ✅ | Username/password login |
| POST /auth/organisers/signup | ⬜ | ✅ | Service-only seeding endpoint |
| POST /auth/service-token | ⬜ | ✔️ | For future service integrations |
| GET /auth/jwks | ⬜ | ⬜ | Consumed by other services only |
| GET /orgs | ⬜ | ✅ | Organiser dashboard lists available organisations |
| POST /orgs/{org_id}/members | ⬜ | ✅ | Assign seniors or organisers to an organisation |

## Trails & Activities Service (http://localhost:8002)
| Endpoint | Senior PWA | Organiser Dashboard | Notes |
| --- | --- | --- | --- |
| GET /trails | ✅ | ✅ | Requires auth; organiser org-filter enforced |
| GET /trails/{trail_id} | ✅ | ✅ | Detailed view |
| GET /trails/{trail_id}/registrations/by-user/{user_id} | ✅ | ✅ | Used for attendee status |
| POST /registrations/trails/{trail_id}/self | ✅ | ⬜ | Seniors self-register; cancelled entries can rejoin |
| DELETE /registrations/{registration_id} | ✅ | ⬜ | Seniors cancel |
| GET /users/me/registrations | ✅ | ✅ | Useful for organiser support |
| GET /users/me/confirmed-trails | ✅ | ✅ | |
| POST /registrations/trails/{trail_id}/by-organiser | ✔️ | ✅ | Manual enrolment form resolves NRIC -> UUID |
| POST /registrations/{registration_id}/approve | ⬜ | ✅ | Organiser-only approval workflow |
| POST /registrations/{registration_id}/confirm | ⬜ | ✅ | |
| POST /registrations/{registration_id}/reject | ⬜ | ✅ | |
| POST /registrations/{registration_id}/cancel | ✅ | ✅ | Seniors can self-cancel |
| POST /invites/trails/{trail_id} | ✔️ | ✅ | Invite flow |
| GET /invites/{token} | ✔️ | ? | |
| POST /invites/{token}/register | ✔️ | ? | |

## QR Check-in Service (http://localhost:8004)
| Endpoint | Senior PWA | Organiser Dashboard | Notes |
| --- | --- | --- | --- |
| POST /checkin/scan | ✔️ | ✔️ | PWA pending live camera test; organiser may issue tokens |
| GET /checkin/users/me | ✅ | ✔️ | Organiser may need attendee view |
| POST /checkin/trails/{trail_id}/qr | ⬜ | ✅ | Check-in panel generates organiser QR |
| GET /checkin/trails/{trail_id}/roster | ⬜ | ✅ | Roster displayed in Manage Trails |
| GET /checkin/trails/{trail_id}/qr.png | ⬜ | ✅ | Dashboard previews downloadable PNG |

## Points & Vouchers Service (http://localhost:8003)
| Endpoint | Senior PWA | Organiser Dashboard | Notes |
| --- | --- | --- | --- |
| GET /points/users/me/balance | ✅ | ✅ | Dashboard points overview page |
| GET /points/users/me/ledger | ✅ | ✅ | |
| GET /points/orgs/{org_id}/balances | ⬜ | ✅ | Organiser dashboard overview of member balances |
| POST /points/ingest/checkin | ⬜ | ✔️ | Service-to-service |
| POST /points/orgs/{org_id}/adjust | ⬜ | ✅ | Organiser manual adjustments (NRIC -> UUID lookup) |
| GET /vouchers | ✅ | ✅ | PWA fetch implemented |
| POST /vouchers/orgs/{org_id} | ⬜ | ✅ | Organiser voucher creation |
| PATCH /vouchers/{voucher_id} | ⬜ | ✅ | |
| POST /vouchers/{voucher_id}/redeem | ✅ | ⬜ | PWA redeem only |
| GET /vouchers/users/me/redemptions | ✅ | ✔️ | |
| GET /orgs/{org_id}/rules | ⬜ | ✔️ | Organiser rule management |
| POST /orgs/{org_id}/rules | ⬜ | ✔️ | |
| PATCH /orgs/{org_id}/rules/{rule_id} | ⬜ | ✔️ | |

## Leaderboard & Attendance Service (http://localhost:8005)
| Endpoint | Senior PWA | Organiser Dashboard | Notes |
| --- | --- | --- | --- |
| GET /leaderboard/system | ✅ | ✅ | PWA global leaderboard + organiser view |
| GET /leaderboard/orgs/{org_id} | ✅ | ✅ | PWA "My CC" tab + organiser-specific ranks |
| GET /attendance/users/me | ✔️ | ✔️ | PWA attendance history |
| GET /attendance/trails/{trail_id} | ⬜ | ✅ | Organiser roster |

---

## Shared / Infrastructure
| Service | Endpoint / Purpose | Usage |
| --- | --- | --- |
| Authentication | GET /auth/jwks | Internal service discovery |
| Authentication | POST /auth/service-token | Future machine-to-machine flows |

