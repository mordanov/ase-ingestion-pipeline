# Deployment — PoC on EC2

All application services run on a **single EC2 instance** inside Docker Compose. Infrastructure is defined as CloudFormation and provisioned with one shell script. Continuous deployment is handled by GitHub Actions.

---

## What Gets Deployed

One Amazon Linux 2023 instance (`t3.medium` — 2 vCPU / 4 GB RAM) running every service as a Docker container:

| Service | Port | Purpose |
|---|---|---|
| FastAPI app | `9000` (public) | Ingestion, recommendations, ML, admin APIs |
| React frontend | `3200` | Dashboard (Nginx) |
| PostgreSQL | internal only | Primary database |
| Redis | internal only | Feature embedding cache |
| Mosquitto | `1883` / `8883` | MQTT broker (plain / TLS) |
| Grafana | `3100` | Metrics dashboards |
| Prometheus | `9090` | Metrics scraping |
| Delta compactor | internal cron | Compacts Delta Lake every 15 min |

A static **Elastic IP** is attached so the address survives instance reboots. DNS (`ingestion-pipeline.aleksandr-mordanov.click`) is managed in a separate Route 53 stack; pass the Elastic IP as `IngestionPipelineIp` to that stack after deploy.

---

## Provision the Instance (first time only)

**Prerequisites:** AWS CLI configured, a key pair created in the target region.

```bash
# Minimal — uses default VPC, restricts SSH to your IP
KEY_NAME=my-key \
SSH_CIDR=$(curl -s https://checkip.amazonaws.com)/32 \
REGION=us-west-2 \
  ./infra/scripts/deploy-ec2.sh
```

The script:
1. Validates AWS credentials (`sts get-caller-identity`).
2. Auto-detects the default VPC if `VPC_ID` is not set.
3. Creates (or updates) the CloudFormation stack `health-ingestion-poc-ec2`.
4. Waits for `CREATE_COMPLETE` / `UPDATE_COMPLETE`.
5. Prints the Elastic IP, instance ID, and SSH command.

**What CloudFormation provisions:**
- IAM role + instance profile with `AmazonSSMManagedInstanceCore` (enables SSM Session Manager as a no-key fallback)
- Security group with the ports listed above
- Elastic IP + association
- EC2 instance with UserData that installs Git, Docker, and Docker Compose v2.27 on first boot

The UserData script runs once at launch and takes ~2 minutes. Subsequent deploys via GitHub Actions do not re-run it.

**Common overrides:**

```bash
INSTANCE_TYPE=t3.large        # more RAM for heavier ML workloads
VOLUME_SIZE=60                # larger disk for Delta Lake data
SSH_CIDR=127.0.0.1/32        # disable SSH, use SSM only
DRY_RUN=1                     # print commands without executing
```

---

## First-Time App Setup (after instance is ready)

SSH in and clone the repo manually once:

```bash
ssh ec2-user@<elastic-ip>

# On the instance:
git clone https://<GH_TOKEN>@github.com/<org>/ingestion_pipeline ~/platform
cd ~/platform
cp .env.example .env          # fill in POSTGRES_PASSWORD, API_KEY, etc.
sudo docker compose up -d --build
sudo docker compose exec app alembic upgrade head   # run migrations
```

After this, all subsequent deployments are fully automated via CI/CD.

---

## Continuous Deployment (GitHub Actions)

Every push to `main` that passes all CI checks triggers the deploy job in `.github/workflows/ci.yml`.

```
push to main
     │
     ├─ pre-commit   ─┐
     ├─ test-backend  ├──▶ all pass ──▶ deploy
     └─ test-frontend ┘
```

The deploy job SSHes into the instance and runs:

```bash
cd ~/platform
git pull origin main
sudo docker compose up -d --build
sudo docker compose exec -T app alembic upgrade head
```

A `concurrency` guard (`cancel-in-progress: false`) ensures two deployments never overlap. The deploy job only runs on `push` events, not on pull requests.

**Required GitHub Secrets:**

| Secret | Value |
|---|---|
| `EC2_HOST` | Elastic IP from CloudFormation output |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_KEY` | Contents of the `.pem` private key |
| `GH_TOKEN` | GitHub PAT with `repo` read scope (for private repo clone) |

---

## Teardown

```bash
ACTION=teardown ./infra/scripts/deploy-ec2.sh
```

The script prompts for the stack name before deletion. All resources (instance, EIP, security group, IAM role) are removed. **Data is not backed up automatically** — snapshot the EBS volume or dump PostgreSQL first if the data matters.

---

## Limitations (PoC scope)

| Area | Current state |
|---|---|
| Single point of failure | One instance — instance failure = full outage |
| No TLS on the API | Port 9000 is plain HTTP |
| Secrets management | `.env` file on disk, manually maintained |
| Data durability | EBS `DeleteOnTermination: true` — instance termination loses all data |
| Scaling | Vertical only (`INSTANCE_TYPE` override) |
| SSH CIDR default | `0.0.0.0/0` — restrict to your IP in any real environment |
