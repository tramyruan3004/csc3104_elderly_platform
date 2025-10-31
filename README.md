# Five Services — Trails Platform

A microservices playground implementing authentication, organisations, trails/activities, QR check-ins, points & vouchers, and leaderboards — wired together with JWT, JWKS, NATS and Redis, and backed by Postgres (one DB per service). Ready for **Docker Compose** (local dev) and **Kubernetes** (kind/minikube).

## Table of Contents

- [Repo layout](#repo-layout)
- [What each service does](#what-each-service-does)
- [How services talk (architecture)](#how-services-talk-architecture)
- [Prerequisites](#prerequisites)
- [Quick start method1 (Docker Compose)](#quick-start-docker-compose)
- [Quick start method2 (Kubernetes with kind)](#quick-start-kubernetes-with-kind)
- [Environments & key variables](#environments--key-variables)
- [Health checks / Smoke tests](#health-checks--smoke-tests)
- [Seeding the Cluster (Load sample data)](#seeding-the-cluster-sample-data)
- [Common workflows](#common-workflows)
- [Git submodules 101](#git-submodules-101)
- [Troubleshooting](#troubleshooting)


## Repo layout
```bash
five-services/
├─ authentication-svc/ # Users, organisations, JWT auth, JWKS
│ ├─ app/
│ ├─ requirements.txt
│ └─ Dockerfile
├─ trails-activities-svc/ # Trails/activities, registrations, invitations
│ ├─ app/
│ ├─ requirements.txt
│ └─ Dockerfile
├─ qr-checkin-svc/ # Signed QR generation & scan, attendance; Redis rate-limit; publishes to NATS
│ ├─ app/
│ ├─ requirements.txt
│ └─ Dockerfile
├─ points-vouchers-rules-svc/ # Points ledger, rules, vouchers; consumes NATS check-in events
│ ├─ app/
│ ├─ requirements.txt
│ └─ Dockerfile
├─ leaderboard-attendance-svc/ # Materialized ranks, organiser attendance views; consumes NATS
│ ├─ app/
│ ├─ requirements.txt
│ └─ Dockerfile
├─ k8s/
│ ├─ all.yaml # Namespace, NATS, Redis, 5x Postgres, 5x services
│ └─ ingress.yaml # Single ingress routing for all services (optional)
└─ docker-compose.yml # Local dev stack (NATS, Redis, 5x Postgres, 5x services)
```

## What each service does

### 1) `authentication-svc`
- **Accounts & Orgs**: user sign-up/login with NRIC + passcode; organiser/admin can create organisations.
- **JWT**: Access tokens (RS256) + refresh tokens.
- **JWKS**: `/auth/jwks` exposes the public key so other services can validate tokens.
- **DB**: `authentication` (users, organisations, refresh_tokens).

### 2) `trails-activities-svc`
- **Trails**: CRUD trails under an organisation (capacity, schedule).
- **Registrations**: attend_user self-register; organisers can approve/confirm until capacity is full.
- **Registration Status**: lookup by user/trail.
- **Invitations**: create signed invitation URLs for a trail.
- **DB**: `trails` (trails, registrations, invites).

### 3) `qr-checkin-svc`
- **Signed QR**: short-TTL HMAC payloads for check-in sessions.
- **Validate scans**: verify signature, ensure TTL/window valid, write attendance to its DB.
- **Publishes NATS**: emits `checkins.recorded` event.
- **Redis**: optional rate limiting & dedupe.
- **DB**: `qr` (checkin_sessions, scans).

### 4) `points-vouchers-rules-svc`
- **Points**: award points based on rules (consumes `checkins.recorded`).
- **Vouchers**: create/redeem vouchers; org-scoped.
- **Rules**: simple rules config (e.g., X points per check-in).
- **DB**: `points` (ledger, balances, rules, vouchers).

### 5) `leaderboard-attendance-svc`
- **Leaderboards**: system-wide & per-organisation, materialised and periodically rebuilt.
- **Attendance Views**: list confirmed attendees by trail/org.
- **Consumes NATS**: reacts to check-ins/awards to update ranks.
- **DB**: `leaderboard` (attendance rollups, ranks).

**Infra**
- **NATS**: lightweight event bus (pub/sub).
- **Redis**: rate-limit/cache/dedupe.
- **Postgres**: one per service to keep schemas decoupled.

## How services talk (architecture)

- **Auth → Others**: All protected endpoints expect a `Bearer` **JWT**. Services verify the token using **JWKS** from `authentication-svc` (`/auth/jwks`) and the `iss` claim.
- **Trails & Registrations**: `trails-activities-svc` enforces org scoping and capacity logic.
- **QR → NATS**: When a scan is accepted, `qr-checkin-svc` *publishes* `checkins.recorded` with `{ user_id, trail_id, org_id, ts }`.
- **Points & Leaderboard ← NATS**: `points-vouchers-rules-svc` and `leaderboard-attendance-svc` *subscribe* and update their DBs.
- **Redis**: `qr-checkin-svc` optionally uses Redis for rate limiting/dup detection.

## Prerequisites

- Docker Desktop (or Docker Engine)
- **For Kubernetes path**:
  - `kubectl`
  - **kind** (recommended) or Minikube
  - (Optional) `helm` (for ingress-nginx install)


## Quick start (Docker Compose)

> Easiest way to run all 5 services + NATS + Redis + 5 Postgres locally.

1) From repo root:
```bash
docker compose build
docker compose up -d
docker compose logs -f
```

2) Verify health if service is on/ running:
```bash
curl -s http://localhost:8001/health
curl -s http://localhost:8002/health
curl -s http://localhost:8003/health
curl -s http://localhost:8004/health
curl -s http://localhost:8005/health
```

3) Rebuild a single service:
```bash
docker compose build qr-checkin-svc
docker compose up -d qr-checkin-svc
```

4) Stop:
```bash
docker compose down
# Optional: prune dangling images to save space
docker image prune -f
```
## Quick start (Kubernetes with kind)

> Recommended local cluster flow. Uses k8s/all.yaml to deploy infra + DBs + apps. Add ingress for a single entry point.

1) Create cluster:
```bash
kind create cluster --name play --config k8s/kind-config.yaml
```

2) Install ingress-nginx to listen on hostPort 80
```bash
# install ingress-nginx (helm)
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.kind=DaemonSet \
  --set controller.hostPort.enabled=true \
  --set controller.service.type=ClusterIP
```
> Why these flags?
- `DaemonSet` + `hostPort.enabled=true` makes the controller bind directly to the node’s port `80`.
- Your kind config maps host 8080 → node 80, so no `kubectl port-forward` is needed.
- `service.type=ClusterIP` is fine because we’re using hostPort, not a LoadBalancer/NodePort.

Wait for it to be ready:
```bash
# apply ingress routes
kubectl -n ingress-nginx get pods
```

3) Build + load images locally:
```bash
docker build -t authentication-svc:latest ./authentication-svc
docker build -t trails-activities-svc:latest ./trails-activities-svc
docker build -t qr-checkin-svc:latest ./qr-checkin-svc
docker build -t points-vouchers-rules-svc:latest ./points-vouchers-rules-svc
docker build -t leaderboard-attendance-svc:latest ./leaderboard-attendance-svc

kind load docker-image authentication-svc:latest --name play
kind load docker-image trails-activities-svc:latest --name play
kind load docker-image qr-checkin-svc:latest --name play
kind load docker-image points-vouchers-rules-svc:latest --name play
kind load docker-image leaderboard-attendance-svc:latest --name play
```

4) Apply manifests:
```bash
kubectl apply -f k8s/all.yaml
kubectl -n play get pods
kubectl -n play get svc

kubectl apply -f k8s/ingress.yaml
```

5) Health via ingress with a specified port (single endpoint) - need to wait a while:
```bash
curl -i http://localhost:8080/auth/health
curl -i http://localhost:8080/trails/health
curl -i http://localhost:8080/points/health
curl -i http://localhost:8080/qr/health
curl -i http://localhost:8080/leaderboard/health
```
6) (Optional) to load sample data 
Go to [#seeding-the-cluster-sample-data.](#seeding-the-cluster-sample-data)

**After reboot:**
- Start Docker Desktop
- `kind get clusters` (ensure `play` exists)
- If the cluster was recreated, redo steps 2–5.

**After make any changes to rerun/ redeploy**
```bash
kubectl apply -f k8s/all.yaml
kubectl apply -f k8s/ingress.yaml
# optional
kubectl apply -f k8s/seed.yaml

# Restart the deployments
kubectl rollout restart deployment -n play authentication-svc
kubectl rollout restart deployment -n play trails-activities-svc
kubectl rollout restart deployment -n play points-vouchers-rules-svc
kubectl rollout restart deployment -n play qr-checkin-svc
kubectl rollout restart deployment -n play leaderboard-attendance-svc
# OR all at once:
kubectl get deploy -n play -o name | xargs kubectl rollout restart -n play

# Watch pod status until all services are ready
kubectl get pods -n play -w
```

## Environments & key variables
Each service accepts env vars via compose or K8s manifests. Defaults are dev-friendly (ephemeral JWT keys in `authentication-svc`, no secrets mounted).

**Common:**
- `AUTH_JWKS_URL` — e.g., `http://authentication-svc:8001/auth/jwks`
- `TOKEN_ISSUER` — usually `authentication-svc`
- `DATABASE_URL` — async psycopg: `postgresql+psycopg_async://user:pwd@host:5432/db`

**authentication-svc:**
- `ACCESS_TOKEN_EXP_MINUTES` — default `60`
- `REFRESH_TOKEN_EXP_MINUTES` — default `10080` (7 days)
- `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` — optional; leave empty for auto-generated dev keys

**qr-checkin-svc:**
- `QR_SECRET` — HMAC secret for QR payloads (dev default used, change in production)
- `QR_TTL_SECONDS` — default `120`
- `REDIS_URL` — e.g., `redis://redis:6379/0`
- `RL_ENABLED` — enable/disable rate limiting
- `RL_WINDOW_SECONDS` — rate-limit time window
- `RL_MAX_REQS` — max requests per window
- `NATS_URLS` — NATS server URL(s)
- `NATS_SUBJECT_CHECKIN` — NATS subject for publishing check-in events
- `USE_NATS_FOR_POINTS` — set to `"true"` to publish check-ins to NATS only

**points-vouchers-rules-svc:**
- `ENABLE_NATS_CONSUMER` — `"true"` to enable NATS event consumption
- `NATS_URLS` — NATS server URL(s)
- `NATS_SUBJECT_CHECKIN` — NATS subject for listening to check-in events

**leaderboard-attendance-svc:**
- `ENABLE_NATS_CONSUMER` — `"true"` to enable NATS event consumption
- `NATS_URLS` — NATS server URL(s)
- `NATS_SUBJECT_CHECKIN` — NATS subject for listening to check-in events
- `SCORING_MODE` — scoring type, e.g., `checkins`
- `RANKS_REBUILD_INTERVAL_SEC` — leaderboard rebuild interval in seconds (e.g., `60`)

## 🩺 Health Checks / Smoke Tests

**With Compose (direct ports):**
```bash
http://localhost:8001/health
http://localhost:8002/health
http://localhost:8003/health
http://localhost:8004/health
http://localhost:8005/health
```

**With K8s Ingress (one entry):**
```bash
http://localhost:8080/auth/health
http://localhost:8080/trails/health
http://localhost:8080/points/health
http://localhost:8080/qr/health
http://localhost:8080/leaderboard/health
```

## 🔁 Common Workflows
**Build & restart one service (Compose)**
```bash
docker compose build trails-activities-svc
docker compose up -d trails-activities-svc
```

**Rebuild image & roll out (K8s + kind)**
```bash
docker build -t qr-checkin-svc:latest ./qr-checkin-svc
kind load docker-image qr-checkin-svc:latest --name play
kubectl -n play rollout restart deploy/qr-checkin-svc
kubectl -n play rollout status deploy/qr-checkin-svc
```

**Follow logs (K8s)**
```bash
kubectl -n play logs deploy/points-vouchers-rules-svc -c app -f
```

## Seeding the Cluster (Load sample data)
**Files `k8s/seed.yaml`**
Contains:
- `ConfigMap/seed-script` with `seed.sh` (the script).
- `Job/seed-data` which runs the script once.

> Note: ConfigMap volumes are read-only—the Job runs the script via `/bin/sh /seed/seed.sh` (no `chmod`).

**One-time Setup Checks**
Ensure the `play` namespace and services are up:
```bash
kubectl get ns
kubectl -n play get pods
kubectl -n play get svc
```
If using NATS-driven points:
- `qr-checkin-svc` must have `USE_NATS_FOR_POINTS=true`
- `points-vouchers-rules-svc` must have `ENABLE_NATS_CONSUMER=true`
- Both must share valid `NATS_URLS` and subject.
(These are already set in the provided manifests if you used the repo defaults.)

**Run (or Re-run) the Seed**
Jobs don’t automatically re-run on apply. Delete and recreate:
```bash
# (Re)create the Job
kubectl -n play delete job/seed-data || true
kubectl apply -f k8s/seed.yaml

# watch logs
kubectl -n play logs -f job/seed-data
```

**Common “works for me” checks**
If the job fails early:
```bash
kubectl -n play describe job/seed-data
kubectl -n play get pods -l job-name=seed-data
kubectl -n play describe pod <seed-pod-name>
```

If the script can’t reach services, confirm health from inside the cluster:
```bash
kubectl -n play run curl --image=alpine:3.20 -it --rm -- sh -lc '
  apk add --no-cache curl >/dev/null
  for u in \
    http://authentication-svc.play.svc.cluster.local:8001/health \
    http://trails-activities-svc.play.svc.cluster.local:8002/health \
    http://points-vouchers-rules-svc.play.svc.cluster.local:8003/health \
    http://qr-checkin-svc.play.svc.cluster.local:8004/health \
    http://leaderboard-attendance-svc.play.svc.cluster.local:8005/health
  ; do echo "GET $u"; curl -sf $u || exit 1; echo; done
'
```

## 🧩 Git Submodules 101
> Only relevant if some service folders are separate repos referenced as submodules.
If this repo is purely self-contained, you can skip this section.

**Clone a repo with submodules**
```bash
git clone <repo-url>
cd five-services
git submodule update --init --recursive
```

**Pull latest changes for all submodules**
```bash
git submodule update --remote --merge --recursive
# OR for a fresh sync:
git submodule foreach --recursive 'git fetch && git checkout main && git pull'
```

**Add a new submodule (example)**
```bash
git submodule add https://github.com/you/qr-checkin-svc.git qr-checkin-svc
git commit -m "Add qr-checkin-svc as submodule"
```

**Push changes in a submodule**
```bash
cd qr-checkin-svc
# make code changes, then:
git add .
git commit -m "Feature X"
git push origin main
# then go back to parent and commit the new submodule SHA
cd ..
git add qr-checkin-svc
git commit -m "Bump qr-checkin-svc submodule pointer"
git push
```

**Remove a submodule**
```bash
git submodule deinit -f qr-checkin-svc
git rm -f qr-checkin-svc
rm -rf .git/modules/qr-checkin-svc
git commit -m "Remove submodule qr-checkin-svc"
```

## ⚙️ Troubleshooting
**🐳 ImagePullBackOff on K8s**
The cluster can’t find your images.
If using `kind`, run:
```bash
kind load docker-image <image>:latest --name play
```
Or push your images to a registry and set:
```bash
imagePullPolicy: Always
```

**🔐 JWT / JWKS validation fails**
- Ensure AUTH_JWKS_URL points to the cluster service DNS (K8s) or localhost ports (Compose)
- Ensure tokens have iss=authentication-svc

**🧠 psycopg_async lib error**
And ensure your env uses:
```bash
DATABASE_URL=postgresql+psycopg_async://user:pwd@host:5432/db
```

**⚡ Duplicate ports in Docker Desktop**
Avoid running Docker Compose and Kubernetes port-forwards on the same ports simultaneously.
Prefer K8s ingress for a single unified endpoint (`8080`).

**🧹 Dangling `<none>` images**
Safe cleanup:
```bash
docker image prune -f
```
Full cleanup (careful, removes all):
```bash
docker system prune -a
```

**Ephemeral psql pod - access to db**
```bash
# wait until the pod is Running
kubectl -n play get pods -l app=auth-db

# exec a shell and run psql inside the container
kubectl -n play exec -it deploy/auth-db -- bash -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -h localhost'
```
  curl -s http://localhost:8080/auth/auth/signup \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Kelvin Spark",
      "nric": "K1234567W",
      "passcode": "23081999",
      "role": "attend_user"
    }' | jq

  curl -s http://localhost:8080/auth/auth/signup \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Tony Ark",
      "nric": "O1234567N",
      "passcode": "23081999",
      "role": "organiser"
    }' | jq

  LOGIN_JSON_ORG=$(curl -s http://localhost:8080/auth/auth/login \
    -H "Content-Type: application/json" \
    -d '{"nric":"O1234567N","passcode":"23081999"}')

  ACCESS_ORG=$(echo "$LOGIN_JSON_ORG" | jq -r '.tokens.access_token')

  curl -s http://localhost:8080/auth/orgs \
    -H "Authorization: Bearer $ACCESS_ORG" \
    -H "Content-Type: application/json" \
    -d '{"name": "Avengers Exploration"}' | jq

  ORG_ID="133680a4-ceba-4bab-bc22-7cc7757bdcf7" 

  curl -s http://localhost:8080/trails/trails/orgs/$ORG_ID \
    -H "Authorization: Bearer $ACCESS_ORG" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "Punggol District Exploration",
        "description": "A short engaging tour to explore the latest technological District",
        "starts_at": "2025-11-27T06:00:00Z",
        "ends_at": "2025-11-30T09:00:00Z",
        "location": "Punggol Coast",
        "capacity": 5
    }' | jq

  LOGIN_JSON_ATT=$(curl -s http://localhost:8080/auth/auth/login \
    -H "Content-Type: application/json" \
    -d '{"nric":"K1234567W","passcode":"23081999"}')

  ACCESS_ATT=$(echo "$LOGIN_JSON_ATT" | jq -r '.tokens.access_token')
  
  TRAIL_ID="4ba8b293-4a09-43c3-997f-d134ba7c91bc"

  curl -s http://localhost:8080/trails/registrations/trails/$TRAIL_ID/self \
    -H "Authorization: Bearer $ACCESS_ATT" \
    -H "Content-Type: application/json" \
    -d '{"note":"first timer"}' | jq