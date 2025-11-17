# 🌟 Elderly Activity Trail & Bonding — Full System

The **Elderly Activity Trail & Bonding Platform** is a full microservices system powering:
- 👵 **Senior PWA** — User-facing progressive web app  
- 🧑‍💼 **Organizer Dashboard** — Admin & staff management dashboard  
- ⚙️ **Backend Microservices** — Authentication, Trails, QR Check-In, Points, Leaderboard  
- 🗄️ **Databases, NATS, Redis**  
- 🚀 **Docker Compose** and **Kubernetes (kind + ingress-nginx)** deployment options  

This README gives you the **complete instructions** to run the entire system end-to-end.

---

## Table of Contents

- Project Structure
- What each service does
- Prerequisites
- Backend (Docker Compose)
- Backend (Kubernetes with kind + ingress-nginx)
- Frontend (cloud-project)
- Quick End-to-End Test

## Project Structure
```bash
project-root/
  │
  ├── backend/ # Backend microservices + Docker + Kubernetes
  │ ├── authentication-svc/
  │ ├── trails-activities-svc/
  │ ├── points-vouchers-rules-svc/
  │ ├── qr-checkin-svc/
  │ ├── leaderboard-attendance-svc/
  │ ├── k8s/
  │ │ ├── all.yaml
  │ │ ├── ingress.yaml
  │ │ └── kind-config.yaml
  │ └── docker-compose.yml
  └── frontend/ # Organiser dashboard + Senior Portal (pnpm) 
  │ ├── apps/
  │ │ ├── organizer-dashboard/ # Next.js 14
  │ │ └── senior-pwa/ # Vite + React
  │ ├── packages/
  │ └── pnpm-lock.yaml
  └──
```

## What each service does

### 1) `authentication-svc`
- Handles user sign-up/login with **NRIC + passcode**
- Issues **JWT access tokens** and **refresh tokens**
- Exposes **JWKS** at `/auth/jwks` so other services can validate tokens
- Manages:
  - Users  
  - Organisations  
  - Refresh tokens  
- Database: `authentication`

### 2) `trails-activities-svc`
- CRUD: create, update, publish, close trails
- Registration management (approve / confirm / capacity rules)
- Invitation & signed invite URL generation
- Organisation-scoped records
- Database: `trails`

### 3) `qr-checkin-svc`
- Generates signed QR codes (short TTL HMAC)
- Validates QR scans  
- Records check-ins into DB  
- Publishes **NATS events**: `checkins.recorded`
- Uses Redis for rate-limiting & deduplication
- Database: `qr`

### 4) `points-vouchers-rules-svc`
- Consumes NATS `checkins.recorded` events  
- Awards points using rule engine  
- Handles voucher creation, redemption  
- Organisation-scoped points system
- Database: `points`

### 5) `leaderboard-attendance-svc`
- Subscribes to NATS check-in / point-award events
- Maintains real-time **leaderboards**
- Generates **attendance rollups** per trail & per organisation
- Database: `leaderboard`

**Infra**
- **NATS**: lightweight event bus (pub/sub).
- **Redis**: rate-limit/cache/dedupe.
- **Postgres**: one per service to keep schemas decoupled.

## Prerequisites

- **Git** (2.40+).
- **Node.js** ≥ 18.17 and **pnpm** ≥ 8 (`npm install -g pnpm`).
- **Python** ≥ 3.11 (optional; only needed if you run services outside Docker).
- **PowerShell** 7 (default on Windows 11). All shell snippets below target PowerShell (`pwsh`).
- **Docker Desktop** (v4.x or newer).
- **For Kubernetes path**:
  - **kind** (recommended) 
  - **helm** (for ingress-nginx install)

## Backend (Docker Compose)

> This is the recommended local production-like environment.

1) From project root:
```bash
cd backend
docker compose build authentication-svc trails-activities-svc qr-checkin-svc points-vouchers-rules-svc leaderboard-attendance-svc
docker compose up -d authentication-svc trails-activities-svc qr-checkin-svc points-vouchers-rules-svc leaderboard-attendance-svc
```

2) This launches:
```bash
| Service | Port | Description |
|---------|------|-------------|
| `authentication-svc` | `8001` | Accounts, organisations, auth tokens |
| `trails-activities-svc` | `8002` | Trails, registrations, invites |
| `points-vouchers-rules-svc` | `8003` | Points ledger, vouchers |
| `qr-checkin-svc` | `8004` | On-site check-ins |
| `leaderboard-attendance-svc` | `8005` | Attendance metrics |
```

3) Verify health if service is on/ running:
```bash
curl -s http://localhost:8001/health
curl -s http://localhost:8002/health
curl -s http://localhost:8003/health
curl -s http://localhost:8004/health
curl -s http://localhost:8005/health
```

- Follow logs for a particular container: `docker compose logs -f authentication-svc`.
- FastAPI docs (health check) are at `http://localhost:<port>/docs` (repeat for each service).

4) Rebuild a single service:
```bash
docker compose build <service>
docker compose up -d <service>
```

5) Stop:
```bash
docker compose down
# Optional: prune dangling images to save space
docker image prune -f
```

## Backend (Kubernetes with kind + ingress-nginx)

> Recommended local cluster flow. Uses k8s/all.yaml to deploy infra + DBs + apps. Add ingress for a single entry point.

1) Create cluster from project root:
```bash
cd backend
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
kubectl -n play get pods -w
```
> Wait for all pods to reach Running (1/1).

5) Apply ingress routing
```bash
kubectl apply -f k8s/ingress.yaml
```

6) Health via ingress with a specified port (single endpoint) - need to wait a while:
```bash
curl -i http://localhost:8080/auth/health
curl -i http://localhost:8080/trails/health
curl -i http://localhost:8080/points/health
curl -i http://localhost:8080/qr/health
curl -i http://localhost:8080/leaderboard/health
```

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

## Frontend (cloud-project)

Install workspace dependencies:
```bash
cd frontend
pnpm install
```

# Organizer Dashboard (Next.js)

1) Start the dashboard:
```bash
cd frontend/apps/organizer-dashboard
pnpm dev
```
> Open 👉 http://localhost:3000

2) Required .env.local for Docker
```bash
NEXT_PUBLIC_AUTH_API=http://localhost:8001
NEXT_PUBLIC_TRAILS_API=http://localhost:8002
NEXT_PUBLIC_POINTS_API=http://localhost:8003
NEXT_PUBLIC_QR_API=http://localhost:8004
NEXT_PUBLIC_LEADERBOARD_API=http://localhost:8005
```

3) Required .env.local for Kubernetes
```bash
NEXT_PUBLIC_AUTH_API=http://localhost:8080/auth
NEXT_PUBLIC_TRAILS_API=http://localhost:8080/trails
NEXT_PUBLIC_POINTS_API=http://localhost:8080/points
NEXT_PUBLIC_QR_API=http://localhost:8080/qr
NEXT_PUBLIC_LEADERBOARD_API=http://localhost:8080/leaderboard
```

# Senior PWA (Vite)

1) Start the dashboard:
```bash
cd frontend/apps/organizer-dashboard
pnpm dev
```
> Open 👉 http://localhost:5173

2) Required .env.local for Docker
```bash
VITE_AUTH_API=http://localhost:8001
VITE_TRAILS_API=http://localhost:8002
VITE_POINTS_API=http://localhost:8003
VITE_QR_API=http://localhost:8004
VITE_LEADERBOARD_API=http://localhost:8005
```

3) Required .env.local for Kubernetes
```bash
VITE_AUTH_API=http://localhost:8080/auth
VITE_TRAILS_API=http://localhost:8080/trails
VITE_POINTS_API=http://localhost:8080/points
VITE_QR_API=http://localhost:8080/qr
VITE_LEADERBOARD_API=http://localhost:8080/leaderboard
```

## Quick End-to-End Test
Once everything is up:
`Organizer Login → Create Organisation → Create Trail`
`Senior Login → Register → Check-In → Points Update → Leaderboard Update`

> example:
1. Organizer logs in → creates organisation
2. Creates trail
3. Senior logs in via PWA → registers
4. Senior checks in via QR
5. Points awarded
6. Leaderboard updates in realtime

All communication flows through:
- JWT + JWKS
- NATS events
- Postgres micro-databases
- Kubernetes ingress