# Project Setup & Operations Guide

This repository hosts the backend services (`csc3104_elderly_platform`) and, alongside it, the frontend apps located in the sibling `cloud-project` workspace. Use this document as the single reference for bringing every service up, applying database migrations, and running the web clients end-to-end.

---

## 1. Prerequisites

Ensure the following tools are installed locally:

- **Docker Desktop** (v4.x or newer).
- **Git** (2.40+).
- **Node.js** ≥ 18.17 and **pnpm** ≥ 8 (`npm install -g pnpm`).
- **Python** ≥ 3.11 (optional; only needed if you run services outside Docker).
- **PowerShell** 7 (default on Windows 11). All shell snippets below target PowerShell (`pwsh`).

Keep the repository structure as follows:

```text
<workspace-root>/
  csc3104_elderly_platform/
  cloud-project/
```

---

## 2. Backend Services (Docker Compose)

All backend services run via Docker Compose from the backend root.

```powershell
cd c:\Users\syahm\Documents\GitHub\csc3104_elderly_platform
```

### 2.1 Environment Variables

- Default Compose values suit local development.
- If you need overrides, copy `.env.example` (if present) to `.env` and edit before starting the stack.

### 2.2 Start Core Services

```powershell
docker compose build authentication-svc trails-activities-svc qr-checkin-svc points-vouchers-rules-svc leaderboard-attendance-svc
docker compose up -d authentication-svc trails-activities-svc qr-checkin-svc points-vouchers-rules-svc leaderboard-attendance-svc
```

This launches:

| Service | Port | Description |
|---------|------|-------------|
| `authentication-svc` | `8001` | Accounts, organisations, auth tokens |
| `trails-activities-svc` | `8002` | Trails, registrations, invites |
| `points-vouchers-rules-svc` | `8003` | Points ledger, vouchers |
| `qr-checkin-svc` | `8004` | On-site check-ins |
| `leaderboard-attendance-svc` | `8005` | Attendance metrics |

> Need to rebuild after code changes? Re-run with `docker compose up -d --build <service> ...`.

### 2.3 Logs & Health Checks

- Follow logs for a particular container: `docker compose logs -f authentication-svc`.
- FastAPI docs (health check) are at `http://localhost:<port>/docs` (repeat for each service).

### 2.4 Stop & Cleanup (If needed)

```powershell
docker compose down
```

Add `-v` to prune database volumes if you want a clean slate (`docker compose down -v`).

---

## 3. Database Migrations (Alembic)

Each service with database state ships with migrations under its `alembic/` directory. Use **Python 3.11** (the same version our containers run) when executing Alembic. The authentication database is exposed on `localhost:55321`; make sure any local `.env` matches that port so host-based tooling points at the running Postgres. The authentication service bundles Alembic in its requirements, so you can run migrations either inside the container or from the host with Python 3.11.

### 3.1 Apply Latest Migrations

#### Option A – Run from the host (recommended when coding locally)

```powershell
cd c:\Users\syahm\Documents\GitHub\csc3104_elderly_platform\authentication-svc
python3.11 -m alembic upgrade head

OR

python -m alembic upgrade head
```

The command prints the Postgres impl + transactional DDL messages when successful.

#### Option B – Run inside the container

```powershell
# From csc3104_elderly_platform root
docker compose exec authentication-svc bash -c "cd /app && python3.11 -m alembic -c alembic.ini upgrade head"
```

This copies the exact runtime environment used in Docker. Repeat for other services (e.g. `trails-activities-svc`) by changing the container name and working directory.

### 3.2 Create a New Migration (Not required)

1. Modify SQLAlchemy models in the target service.
2. Autogenerate a revision:
   ```powershell
   docker compose exec authentication-svc alembic revision --autogenerate -m "describe change"
   ```
3. Inspect the generated script under `alembic/versions/` and adjust.
4. Apply with `alembic upgrade head`.
5. Commit the migration file along with model updates.

### 3.3 Seed the default organiser & organisation

After migrating a fresh database (for example after `docker compose down -v`), run the helper script so there is at least one organiser tied to an organisation:

```powershell
cd c:\Users\syahm\Documents\GitHub\csc3104_elderly_platform\authentication-svc
python3.11 create_admin.py

OR

python create_admin.py
```

The script is idempotent: it creates (or reuses) the organiser using username `admin`/`password`, ensures the demo organisation exists, and links the organiser to it.

### 3.4 Downgrade (Optional)

```powershell
docker compose exec authentication-svc alembic downgrade -1
```

Use cautiously—downgrades may drop data based on the migration logic.

---

## 4. Frontend Applications (`cloud-project`)

Although the frontends live in a separate workspace, their setup is part of end-to-end testing.

```powershell
cd c:\Users\syahm\Documents\GitHub\cloud-project
pnpm install
```

### 4.1 Organizer Dashboard (Next.js)

```powershell
# Terminal 1
cd apps\organizer-dashboard
pnpm dev
```

- Visits `http://localhost:3000`.
- Requires backend services running.
- Uses `.env.local` overrides for `NEXT_PUBLIC_*` URLs (see `.env.example`).

### 4.2 Senior PWA (Vite + React)

```powershell
# Terminal 2
cd ..\senior-pwa
pnpm dev
```

- Default dev server at `http://localhost:5173`.
- Configure API base URLs via `.env.local` as needed.

### 4.3 Shared Packages

Reusable components and utilities reside under `cloud-project/packages/`. Restart the dev servers after editing shared code to pick up changes.

---

## 5. Testing & Troubleshooting

- **Auth sanity check:**
  ```powershell
  curl.exe -s http://localhost:8001/auth/organisers/login \`n  -H "Content-Type: application/json" \`n  --data '{"username":"admin","password":"password"}'
  ```
  Replace credentials with real values.

- **Rebuild container after code change:**
  ```powershell
  docker compose up -d --build authentication-svc
  ```

- **Reset data:**
  ```powershell
  docker compose down -v
  docker compose up -d ...
  docker compose exec <svc> alembic upgrade head
  ```

- **Frontend cannot reach backend:** Verify `.env.local` host/port values and confirm services are listening on `localhost`.

---

## 6. Quick Start Checklist

1. `docker compose up -d ...` from `csc3104_elderly_platform`.
2. Run Alembic migrations (`python3.11 -m alembic upgrade head` locally or `docker compose exec` inside the container).
3. `python3.11 create_admin.py` inside `authentication-svc` to seed the organiser + organisation.
4. `pnpm install` inside `cloud-project`.
5. `pnpm --filter organizer-dashboard dev` and `pnpm --filter senior-pwa dev` in separate terminals.
6. Load `http://localhost:3000` (organiser) and `http://localhost:5173` (senior) to verify everything works.
