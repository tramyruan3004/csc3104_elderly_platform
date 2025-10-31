# QR & Check-in Service

FastAPI microservice that issues signed short‑TTL QR payloads and validates scans. On successful scan it publishes a `checkin.recorded` event to NATS JetStream with organiser scoping and replay protection via Redis nonces.

## Features
- Issue signed QR payloads (HMAC‑SHA256)
- Validate scans with TTL + nonce single‑use (Redis SETNX)
- Publish `checkin.recorded` events to NATS
- JWT AuthN/Z: organiser issues, senior scans
- Prometheus metrics and health endpoint

## Quickstart (Docker Compose)

Prereqs: Docker Desktop (WSL2), Python 3.11+ if running helpers.

```powershell
# From qr-checkin-svc folder
docker compose up --build -d

# Logs
docker compose logs -f qrcheckin

# Health
curl http://localhost:8100/health
```

### Generate organiser and senior tokens (dev)
```powershell
# organiser token
python -c "import jwt,datetime; s='dev-jwt-secret'; p={'sub':'organiser-1','role':'organiser','organiser_id':'org1','exp':datetime.datetime.now(datetime.UTC)+datetime.timedelta(hours=1)}; print(jwt.encode(p,s,algorithm='HS256'))"
# senior token
python -c "import jwt,datetime; s='dev-jwt-secret'; p={'sub':'senior-1','role':'senior','exp':datetime.datetime.now(datetime.UTC)+datetime.timedelta(hours=1)}; print(jwt.encode(p,s,algorithm='HS256'))"
```

### 1) Issue a QR payload (organiser)
```powershell
$headers = @{ Authorization = 'Bearer <ORGANISER_TOKEN>' }
$body = @{ activity_id = 'a1'; ttl_seconds = 120 } | ConvertTo-Json
curl -Method POST -Headers $headers -ContentType 'application/json' -Body $body http://localhost:8100/qr/issue
```
Response:
```json
{
  "activity_id": "a1",
  "organiser_id": "org1",
  "exp": 1734038400,
  "nonce": "b2e0...",
  "sig": "base64url-hmac"
}
```

### 2) Scan (senior)
```powershell
# Use the payload from issue step + your senior token (user_id is derived from token.sub)
$headers = @{ Authorization = 'Bearer <SENIOR_TOKEN>' }
$body = @{ activity_id='a1'; organiser_id='org1'; exp=1734038400; nonce='...'; sig='...' } | ConvertTo-Json
curl -Method POST -Headers $headers -ContentType 'application/json' -Body $body http://localhost:8100/checkin/scan
```
Response 200:
```json
{"status":"ok","published":true}
```

Duplicate scan with same nonce returns 409.

## Environment

```bash
# JWT
JWT_SECRET=dev-jwt-secret
JWT_ALGORITHM=HS256

# QR signing
QR_HMAC_SECRET=dev-qr-hmac

# NATS
NATS_URL=nats://localhost:4222
SUBJECT_CHECKIN=checkin.recorded

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

## Run tests
```powershell
pip install -r requirements.txt
pytest
```

## Kubernetes (Docker Desktop)
```powershell
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl port-forward svc/qrcheckin-svc 8100:80
```

---

This service complements `leaderboard-attendance-svc` by emitting `checkin.recorded` used downstream; it does not share a database with that service.
