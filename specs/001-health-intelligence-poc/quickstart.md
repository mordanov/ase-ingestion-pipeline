# Quickstart: Health Intelligence Platform PoC

**Time to running demo**: ~10 minutes (local) | ~25 minutes (AWS)

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Docker + Docker Compose | 24+ | `docker compose version` |
| Python | 3.11+ | `python --version` |
| make | any | `make --version` |
| AWS CLI | 2.x (AWS deploy only) | `aws --version` |
| jq | 1.6+ (AWS deploy only) | `jq --version` |

---

## Option A: Local Development (no AWS credentials needed)

### 1. Clone and configure

```bash
cd ingestion_pipeline
cp .env.example .env
# No edits needed for local dev — LOCAL_DEV=true is the default
```

### 2. Start the full stack

```bash
make dev
# Equivalent to: docker compose up --build -d
```

This starts:
- **FastAPI app** on `http://localhost:9000` (ingestion) and `http://localhost:8000` (API)
- **PostgreSQL 15** on `localhost:5432`
- **Redis 7** on `localhost:6379`
- **Mosquitto MQTT broker** on `localhost:1883`
- **Prometheus** on `http://localhost:9090`
- **Grafana** on `http://localhost:3000` (admin / admin)

Wait for healthy status:

```bash
docker compose ps          # all services should show "healthy"
curl http://localhost:8000/health
# {"status":"ok","db":"connected","redis":"connected"}
```

### 3. Seed test devices

```bash
make seed
# POSTs 10 test devices with biometric profiles to /api/v1/devices
# Prints the generated device_ids
```

### 4. Connect the Device Simulator

```bash
cd ../simulator
cp .env.example .env
# Edit .env:
#   DEFAULT_HTTP_ENDPOINTS=local-api::http://host.docker.internal:9000/ingest
#   AWS_IOT_REGISTRATION_MODE=direct   (skip JITR for local dev)
docker compose up -d
# Open http://localhost:8001 (simulator UI)
# Start a session: 3 smartwatches, workout scenario, HTTP protocol
```

### 5. Verify end-to-end

```bash
# Check ingestion metrics
curl http://localhost:8000/metrics | grep ingest

# Get recommendations for a seeded device
DEVICE_ID=$(make print-devices | head -1)
curl -s -X POST http://localhost:8000/api/v1/devices/$DEVICE_ID/recommendations \
  -H "X-API-Key: dev-key" | jq .

# Open Grafana dashboard
open http://localhost:3000/d/health-platform
```

Expected recommendation response:
```json
{
  "recommendations": [
    { "short_text": "Have more workouts per day", "max_score": 750, "providers": ["service2"] }
  ],
  "duration_ms": 280,
  "credits_remaining": 99
}
```

### 6. Run the test suite

```bash
make test
# Runs: unit → integration (Docker Compose test env) → contract (live provider calls)
# All tests must pass before committing
```

---

## Option B: AWS Deployment

### Prerequisites

```bash
aws configure                  # or: export AWS_PROFILE=your-profile
aws sts get-caller-identity    # verify credentials
```

You also need an X.509 CA key pair for IoT device provisioning. Generate one if needed:

```bash
make gen-ca
# Creates: infra/certs/root-ca.pem + infra/certs/root-ca.key
# Keep root-ca.key SECRET — never commit it
```

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env:
#   LOCAL_DEV=false
#   AWS_REGION=eu-central-1
#   AWS_ACCOUNT_ID=123456789012
#   STACK_NAME=health-platform-poc
#   CA_CERT_FILE=infra/certs/root-ca.pem
#   CA_KEY_FILE=infra/certs/root-ca.key
#   SERVICE1_TOKEN=service1-dev
#   SERVICE2_TOKEN=<any UUID>
#   SERVICE3_ENDPOINT=https://...
#   SERVICE3_API_TOKEN=...
#   API_KEY=<strong random string>
```

### 2. Deploy all infrastructure

```bash
./infra/bootstrap.sh
```

The script deploys nested CloudFormation stacks in order and performs post-deployment steps:

```
[1/7] Uploading CloudFormation templates to S3...
[2/7] Deploying networking stack (VPC, subnets, NAT GW)...
[3/7] Deploying IAM stack (ECS task role, policies)...
[4/7] Deploying IoT stack (IoT policy, topic rule → Kinesis, JITR Lambda)...
[4b/7] Registering CA certificate with AWS IoT Core...
[5/7] Deploying streaming stack (Kinesis stream)...
[6/7] Deploying compute stack (ECR, ECS, ALB, RDS, ElastiCache)...
[7/7] Deploying observability stack (Prometheus, Grafana ECS services)...
[POST] Seeding 10 test devices...
[POST] Done. Summary:
  API endpoint:     https://health-platform-poc.eu-central-1.elb.amazonaws.com
  Grafana:          https://grafana.health-platform-poc.eu-central-1.elb.amazonaws.com
  Ingest endpoint:  https://health-platform-poc.eu-central-1.elb.amazonaws.com:9000/ingest
```

Total deploy time: ~15–20 minutes.

### 3. Configure the simulator for AWS

```bash
cd ../simulator
# Edit .env:
#   DEFAULT_HTTP_ENDPOINTS=aws-api::<API endpoint>/ingest
#   DEFAULT_MQTT_BROKER_URL=mqtts://<AWS IoT endpoint>
#   AWS_IOT_REGISTRATION_MODE=jitr
#   CA_CERT_FILE=/path/to/root-ca.pem
#   CA_KEY_FILE=/path/to/root-ca.key
docker compose up -d
```

### 4. Tear down

```bash
./infra/bootstrap.sh --destroy
# Deletes all stacks in reverse order
# WARNING: destroys all data including RDS instance
```

---

## Common Commands (Makefile)

| Command | Description |
|---------|-------------|
| `make dev` | Start local Docker Compose stack |
| `make stop` | Stop local stack |
| `make test` | Run full test suite (unit + integration + contract) |
| `make test-unit` | Unit tests only (no Docker required) |
| `make test-integration` | Integration tests (requires Docker) |
| `make test-contract` | Contract tests (requires internet — calls live providers) |
| `make seed` | Seed 10 test devices |
| `make lint` | Run ruff + mypy |
| `make migrate` | Run Alembic DB migrations |
| `make gen-ca` | Generate CA key pair for IoT provisioning |
| `make deploy` | Run `infra/bootstrap.sh` |
| `make logs` | Tail Docker Compose app logs |

---

## Troubleshooting

**`/ingest` returns 422 UNKNOWN_DEVICE`**: The simulator is sending events for devices not
registered in the platform DB. Run `make seed` first, then configure the simulator to use
the seeded device IDs, or set `AUTO_REGISTER_DEVICES=true` in `.env` (dev only).

**`/recommendations` returns 503**: All providers timed out. Check internet connectivity and
confirm provider endpoints are reachable: `curl https://a2da22tugdqsame4ckd3oohkmu0tnbne.lambda-url.eu-central-1.on.aws/services/service1 -X POST -H 'Content-Type: application/json' -d '{"height":180,"weight":80,"token":"service1-dev"}'`

**Grafana shows no data**: Prometheus scrape target may be down. Open
`http://localhost:9090/targets` and verify the FastAPI target is `UP`.

**IoT JITR not activating on AWS**: Ensure the JITR Lambda role has `iot:UpdateCertificate`
and `iot:CreateThing` permissions (managed by `iam.yaml` CloudFormation stack).
