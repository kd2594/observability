# FlexAI Visibility Platform

> **AI-powered observability dashboard** for FlexAI GPU infrastructure — real-time anomaly detection, Holmes AI root cause analysis, Robusta playbook automation, distributed tracing, and on-call management in a single pane of glass.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FlexAI Visibility Platform                           │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Next.js Frontend  :3000                           │  │
│  │                                                                      │  │
│  │  ┌────────────┐ ┌──────────┐ ┌──────────────┐ ┌────────┐ ┌───────┐ │  │
│  │  │ AI Insights│ │Anomalies │ │Holmes Invest.│ │Robusta │ │OnCall │ │  │
│  │  │ + Notifs   │ │(60% score│ │+ RCA Dialog  │ │Playbook│ │Slack/ │ │  │
│  │  │ Slack/SMS  │ │ detailed)│ │ loki+metrics │ │Run Hist│ │Twilio │ │  │
│  │  └────────────┘ └──────────┘ └──────────────┘ └────────┘ └───────┘ │  │
│  └──────────────────────────┬───────────────────────────────────────────┘  │
│                             │ REST + WebSocket                             │
│  ┌──────────────────────────▼───────────────────────────────────────────┐  │
│  │               FastAPI Backend  :8001                                 │  │
│  │                                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │  │
│  │  │  ai_agent.py │  │ holmes_rca.py│  │  robusta_playbooks.py    │   │  │
│  │  │ IsolationFrst│  │ Loki+VMetric │  │  Slack / Twilio / Scale  │   │  │
│  │  │ anomaly det. │  │ kubectl ctx  │  │  Auto-remediation        │   │  │
│  │  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘   │  │
│  └─────────┼─────────────────┼───────────────────────┼─────────────────┘  │
│            │                 │                         │                    │
│  ┌─────────▼──────┐  ┌───────▼────────┐  ┌───────────▼──────────────────┐ │
│  │Victoria Metrics│  │   Loki :3100   │  │       Redis :6380            │ │
│  │   (TSDB):8428  │  │  Log Aggreg.   │  │  Session / Cache             │ │
│  └────────▲───────┘  └───────▲────────┘  └──────────────────────────────┘ │
│           │                  │                                              │
│  ┌────────┴───────┐  ┌───────┴────────┐  ┌──────────────────────────────┐ │
│  │ VMAgent :8429  │  │Promtail        │  │  OTel Collector :4317/4318   │ │
│  │ Metric scraper │  │Docker log ship │  │  Traces → Jaeger :16686      │ │
│  └────────▲───────┘  └───────▲────────┘  └──────────────────────────────┘ │
│           │                  │                                              │
│  ┌────────┴───────┐  ┌───────┴────────┐  ┌──────────────────────────────┐ │
│  │ VMAlert :8880  │  │ Docker Logs    │  │  Grafana :3001               │ │
│  │ Alert rules    │  │ (containers)   │  │  Dashboards / Explore        │ │
│  └────────┬───────┘  └────────────────┘  └──────────────────────────────┘ │
│           │                                                                 │
│  ┌────────▼───────┐                                                        │
│  │Alertmanager    │ ──→ webhook → Backend → Robusta playbooks              │
│  │   :9093        │ ──→ Slack / PagerDuty                                 │
│  └────────────────┘                                                        │
└─────────────────────────────────────────────────────────────────────────────┘

Data flows:
  Metrics:  Node Exporter / vmagent → VictoriaMetrics → Backend AI Agent
  Logs:     Docker containers → Promtail → Loki → Holmes RCA
  Traces:   FastAPI (OTel) → OTel Collector → Jaeger
  Alerts:   VMAlert → Alertmanager → Backend webhook → Robusta → Slack/Twilio
  AI RCA:   Anomaly detected → Holmes (Loki+VMetrics+kubectl) → Summary
```

---

## Prerequisites

| Requirement | Minimum |
|---|---|
| Docker Desktop | 4.x+ |
| RAM allocated to Docker | **6 GB** (8 GB recommended) |
| Free disk space | 5 GB |
| macOS / Linux | ✅ |
| Windows (WSL2) | ✅ |

---

## Running Locally

### 1. Clone and enter the directory

```bash
git clone <your-repo>
cd infra-main/visibility-platform
```

### 2. Start all services

```bash
chmod +x start.sh
./start.sh
```

This brings up **13 containers** in dependency order:

| Container | Image | Role |
|---|---|---|
| `visibility-ui` | Next.js 14 (custom) | Dashboard frontend |
| `visibility-api` | FastAPI (custom) | AI + Holmes + Robusta backend |
| `vm-single` | VictoriaMetrics v1.97 | Time-series database |
| `vmagent` | VMAgent v1.97 | Metrics scraper / forwarder |
| `vmalert` | VMAlert v1.97 | Alert rule evaluator |
| `alertmanager` | prom/alertmanager v0.27 | Alert routing |
| `grafana` | Grafana 10.2.3 | Dashboards |
| `loki` | Grafana Loki 2.9.4 | Log aggregation |
| `promtail` | Grafana Promtail 2.9.4 | Log shipper |
| `jaeger` | jaegertracing/all-in-one 1.55 | Distributed tracing |
| `otel-collector` | OTel Contrib 0.96 | Trace/metric collector |
| `visibility-redis` | Redis Alpine | API caching |
| `node-exporter` | prom/node-exporter v1.7 | Host metrics |

### 3. Access the services

| Service | URL | Credentials |
|---|---|---|
| **🖥️ Main Dashboard** | http://localhost:3000 | — |
| **⚙️ Backend API** | http://localhost:8001 | — |
| **📖 API Docs (Swagger)** | http://localhost:8001/docs | — |
| **📊 Grafana** | http://localhost:3001 | admin / admin |
| **🗄️ VictoriaMetrics** | http://localhost:8428 | — |
| **🔔 Alertmanager** | http://localhost:9093 | — |
| **🔍 Jaeger UI** | http://localhost:16686 | — |
| **📦 VMAgent targets** | http://localhost:8429/targets | — |

### 4. Stop everything

```bash
./stop.sh
```

---

## Dashboard Tabs

| Tab | What it shows |
|---|---|
| **AI Insights** | AI-generated fleet insights, Fleet Health Breakdown bar, Slack + Twilio notification feed |
| **Anomalies** | All detected anomalies with severity, anomaly score, expandable Detail Report (metrics snapshot, RCA, recommended actions) |
| **Holmes Investigations** | Per-anomaly AI RCA — queries Loki (logs) + VictoriaMetrics (metrics) + kubectl (K8s context) |
| **Robusta Playbooks** | Registered playbooks + expandable Run History (Slack notify → Holmes trigger → Twilio SMS → auto-remediation) |
| **Clusters** | Per-cluster health cards with service up/down counts |
| **Traces** | Distributed trace table (Jaeger) with duration, span count, error count + embedded Jaeger UI |
| **On Call** | Active incidents, escalation chain (L1→L4), recent pages (ACK status), 7-day shift schedule |

---

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Point at a local or remote VictoriaMetrics
export VM_URL=http://localhost:8428
export REDIS_HOST=localhost
export REDIS_PORT=6380
export LOKI_URL=http://localhost:3100

uvicorn main:app --reload --port 8001
```

### Frontend

```bash
cd frontend
npm install

# Point at local backend
echo "NEXT_PUBLIC_API_URL=http://localhost:8001" > .env.local

npm run dev        # dev server at http://localhost:3000
```

> **Important:** After editing `frontend/app/page.tsx`, the Docker image must be **rebuilt** (not just restarted) because Next.js compiles at build time:
> ```bash
> docker compose up -d --build frontend
> ```

---

## Project Structure

```
visibility-platform/
├── docker-compose.yml              # Orchestrates all 13 services
├── start.sh / stop.sh              # Convenience scripts
├── backend/
│   ├── main.py                     # FastAPI app + all API routes
│   ├── ai_agent.py                 # IsolationForest anomaly detection + 60% health score
│   ├── holmes_rca.py               # Holmes AI — Loki + VictoriaMetrics + kubectl RCA
│   ├── robusta_playbooks.py        # Playbook engine — Slack / Twilio / auto-remediate
│   ├── notifier.py                 # Notification helpers
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx                # Main dashboard (all 7 tabs)
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── package.json
│   └── Dockerfile
└── config/
    ├── prometheus-config.yml       # VMAgent scrape targets
    ├── alertmanager-config.yml     # Alert routing rules
    ├── grafana-datasources.yml     # VictoriaMetrics datasource
    ├── loki-config.yml             # Loki storage config
    ├── promtail-config.yml         # Docker log shipping
    ├── otel-collector-config.yml   # OTel → Jaeger pipeline
    └── alerts/
        └── basic-rules.yml         # VMAlert alert rules
```

---

## Key API Endpoints

### AI & Anomaly Detection
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/ai/analyze` | Run anomaly detection, returns health score + anomaly list |

### Clusters & Services
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/clusters` | List all clusters with status |
| `GET` | `/api/services/all` | List all services |

### Holmes (RCA)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/holmes/investigate` | Start a new investigation |
| `GET` | `/api/holmes/investigations` | List all investigations |
| `GET` | `/api/holmes/investigations/{id}` | Get investigation detail |

### Robusta (Playbooks)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/robusta/playbooks` | List registered playbooks |
| `GET` | `/api/robusta/runs` | Run history |
| `POST` | `/api/robusta/event` | Trigger playbook from event |

### Traces
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/traces` | Fetch traces from Jaeger |
| `GET` | `/api/traces/services` | List traced services |

### Webhooks
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/webhook/alerts` | Alertmanager → backend |
| `POST` | `/webhook/robusta` | Alertmanager → Robusta playbooks |

### Streaming
| Protocol | Endpoint | Description |
|---|---|---|
| `WebSocket` | `/ws/live-metrics` | Real-time metrics push |

---

## Troubleshooting

### Frontend not updating after code changes
```bash
# Must rebuild — Next.js compiles at Docker image build time
docker compose up -d --build frontend
```

### Frontend crash-loops (`ENOENT: .next/BUILD_ID`)
```bash
# Stale cache — force full no-cache rebuild
docker compose build --no-cache frontend
docker compose up -d frontend
```

### Backend can't reach VictoriaMetrics
```bash
docker logs visibility-api
docker exec visibility-api curl http://victoria-metrics:8428/health
```

### No metrics / anomalies visible
```bash
# Check VMAgent scrape targets
curl http://localhost:8429/api/v1/targets | jq '.data.activeTargets[] | {job, health}'

# Manually trigger AI analysis
curl http://localhost:8001/api/ai/analyze | jq '.overall_health_score'
```

### No traces in Jaeger
```bash
# Generate traffic to create traces
curl http://localhost:8001/api/clusters
open http://localhost:16686
```

### Services won't start (port conflicts)
```bash
# Find what's using a port
lsof -i :3000
lsof -i :8001

# Full reset
docker compose down -v
docker compose up -d
```

---

## Connecting to Production VictoriaMetrics

```yaml
# docker-compose.yml → backend → environment
- VM_URL=https://your-victoria-metrics.flex.ai
- VM_TOKEN=your-bearer-token
```

Then rebuild:
```bash
docker compose up -d --build backend
```

---

## License

Internal FlexAI tool — not for public distribution.
