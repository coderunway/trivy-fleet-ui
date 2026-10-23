# Synology Trivy Fleet Security Scanner & Dashboard

A lightweight, automated container vulnerability scanning solution and interactive web dashboard built specifically for Synology NAS (Container Manager / Portainer) and generic Linux Docker hosts.

---

## What is This Project?

Container security on a NAS often requires resource-heavy enterprise tooling that exhausts RAM and CPU. This project provides a decoupled, resource-conscious alternative:

- **Automated Fleet Scanner**: A background service powered by `aquasec/trivy` that scans all local container images on a 24-hour cycle and generates persistent JSON vulnerability reports.
- **Interactive Web Dashboard**: A lightweight web UI (port `8387`) powered by Chart.js displaying KPI metrics, severity breakdowns, high-risk container rankings, and a searchable/sortable CVE table.
- **On-Demand Scanning**: Select individual or multiple container images directly in the browser to trigger instant vulnerability scans without waiting for the daily schedule.
- **Decoupled Architecture**: Scanner and dashboard run as separate Docker Compose stacks sharing a persistent volume. Updating, modifying, or restarting the dashboard never disrupts an ongoing scan.

---

## Architecture & Data Flow

```text
Host Docker Daemon (/var/run/docker.sock)
       │                              │
       ▼                              ▼
┌──────────────────────┐      ┌──────────────────────────┐
│  trivy-scanner       │      │  trivy-dashboard (:8387) │
│  (Background Loop)   │      │  (Python API + UI)       │
└──────────┬───────────┘      └────────────┬─────────────┘
           │ Writes JSON                   │ Reads JSON /
           │ (Atomic mv)                   │ Triggers Scans
           ▼                               ▼
     ┌───────────────────────────────────────────┐
     │ Shared Host Volume:                       │
     │ /volume1/docker/trivy/reports/*.json      │
     └───────────────────────────────────────────┘
```

---



## Prerequisites

1. **Docker & Docker Compose**: Synology Container Manager, Portainer, or standard Docker CLI.
2. **SSH Access**: Enabled on your Synology NAS (**DSM > Control Panel > Terminal & SNMP > Enable SSH service**).
3. **Docker Socket Access**: Ensure the user running the containers has permissions to mount `/var/run/docker.sock`.

---

## Quick Start & Installation

### Step 1: Clone the Repository

SSH into your Synology NAS and clone the project into your primary Docker share:

```bash
cd /volume1/docker
git clone https://github.com/<your-username>/synology-trivy-fleet.git trivy
cd /volume1/docker/trivy
```

### Step 2: Initialize Directories & Environment

Create the persistent cache and report directories, and generate your `.env` configuration file:

```bash
mkdir -p reports cache dashboard/static
cp .env.example .env
chmod +x scanner/scan.sh
```

*(Optional)* If your Docker directory is on a different volume (e.g., `/volume2/docker`), edit `.env`:

```bash
BASE_DIR=/volume2/docker/trivy
DASHBOARD_PORT=8387
```

### Step 3: Start the Automated Scanner

Launch the background scanner stack:

```bash
cd /volume1/docker/trivy/scanner
docker compose up -d
```

Verify that the scanner is running its first cycle:

```bash
docker compose logs -f
```

*(Press `Ctrl + C` to exit log viewing).*

### Step 4: Start the Web Dashboard

Launch the dashboard stack:

```bash
cd /volume1/docker/trivy/dashboard
docker compose up -d
```

---

## Accessing & Using the Dashboard

Open your web browser on any device connected to your local network and visit:

```text
http://<SYNOLOGY_NAS_IP>:8387
```

*(Example: `http://192.168.1.50:8387`)*

### Key Features:

- **KPI Summary Cards**: Click any card (Critical, High, Medium, Low, Fix Available) to filter the table instantly.
- **Interactive Visualizations**: Click on any slice of the severity donut or any bar in the risk chart to isolate specific severities or containers.
- **Searchable Vulnerability Table**: Filter by package, CVE ID, or keyword. Direct links take you to the official NIST NVD vulnerability database.
- **On-Demand Scan Panel**: Select one or more images from the container checklist at the top and click **⚡ Scan Selected Containers** for immediate results.

---

## Configuration Reference

Settings can be customized via the `.env` file in the project root:

| Variable           | Default Value             | Description                                                      |
| :----------------- | :------------------------ | :--------------------------------------------------------------- |
| `BASE_DIR`       | `/volume1/docker/trivy` | Absolute host path to the project directory on your Synology NAS |
| `DASHBOARD_PORT` | `8387`                  | Host port used to access the web dashboard UI                    |

---

## Operations & Maintenance Cheat Sheet

### Viewing Service Logs

```bash
# Monitor background scanner activity
cd /volume1/docker/trivy/scanner && docker compose logs -f

# Monitor web dashboard server activity
cd /volume1/docker/trivy/dashboard && docker compose logs -f
```

### Restarting Services

```bash
# Restart background scanner (triggers an immediate fleet rescan)
cd /volume1/docker/trivy/scanner && docker compose restart

# Restart web dashboard (after editing UI files or templates)
cd /volume1/docker/trivy/dashboard && docker compose restart
```

### Stopping Services

```bash
# Stop background scanner
cd /volume1/docker/trivy/scanner && docker compose down

# Stop web dashboard
cd /volume1/docker/trivy/dashboard && docker compose down
```

### Updating Container Images

To pull the latest Trivy vulnerability scanning engine:

```bash
cd /volume1/docker/trivy/scanner
docker compose pull
docker compose up -d
```

---

## Troubleshooting

### 1. `context deadline exceeded` on Large Images (e.g., `n8n`, `plex`, `gitlab`)

- **Cause**: Trivy's default execution timeout is 5 minutes. Large images with thousands of nested Node.js or system dependencies exceed this limit on low-power NAS CPUs.
- **Resolution**: Both `scanner/scan.sh` and `dashboard/app.py` are preconfigured with `--timeout 30m`. If an image takes longer on your NAS model, edit `scanner/scan.sh` and bump `--timeout 30m` to `--timeout 60m`.

### 2. Scanner Exits or Loops Repeatedly

- **Cause**: Scripts running with `set -e` abort if Trivy encounters an unsupported image layer or transient network blip.
- **Resolution**: The included `scanner/scan.sh` intentionally omits `set -e` and handles errors via `|| { echo "..."; }` blocks, allowing failed scans to skip safely to the next container.

### 3. Bind Mount Failures in Synology Container Manager or Portainer

- **Cause**: Web UI stack deployers evaluate relative paths (`./scan.sh`) against their own internal directories (e.g., `/data/compose/121/...`).
- **Resolution**: Both Compose files use absolute path interpolation via `${BASE_DIR:-/volume1/docker/trivy}`. Ensure `BASE_DIR` in `.env` matches your actual storage volume path.

### 4. Database Lock Collisions During Concurrent Scans

- **Cause**: Simultaneous automated scans and on-demand scans can lock Trivy's shared SQLite/bbolt cache database.
- **Resolution**: On-demand scans from the web interface pass `--skip-db-update`, reusing the local cache kept up-to-date by the background scanner. This eliminates lock collisions and makes manual scans start instantly.
