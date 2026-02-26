# AI-Powered Observability Platform — HolmesGPT Edition

## 🚀 What's New

The FlexAI Visibility Platform now uses **HolmesGPT-style LLM anomaly detection** — replacing the previous scikit-learn `IsolationForest` model with a reasoning LLM that explains *why* each anomaly is a problem, not just that it statistically deviates.

> **scikit-learn (`numpy`, `pandas`, `sklearn`) has been removed** from the dependency tree entirely.

### 1. **HolmesGPT Anomaly Detection** 🤖
- Sends a full metrics snapshot to an LLM (Ollama · Groq · OpenAI — your choice)
- Returns a human-readable `reasoning` field per anomaly explaining the exact threshold breach
- Severity grounded in SRE domain knowledge, not a contamination ratio
- 4–6 emoji-prefixed fleet insights written for the on-call engineer
- Reports the active `engine` field: e.g. `HolmesGPT/ollama (llama3.2)`

### 2. **Rule-Based Fallback** 🛡️
- `RuleBasedDetector` activates automatically when the LLM is unreachable, quota-exceeded, or returns invalid JSON
- Explicit, transparent thresholds — no black-box ML
- Same response schema as HolmesGPT so the UI never breaks

### 3. **Multi-Provider LLM Support** ⚙️
| Provider | Cost | Privacy | Setup |
|---|---|---|---|
| **Ollama** (default) | Free | 100% local | `./setup-llm.sh` |
| **Groq** | Free tier | Cloud | `./setup-llm.sh --provider groq` |
| **OpenAI** | Paid | Cloud | `./setup-llm.sh --provider openai` |

### 4. **One-Command Automation** 🎯
`setup-llm.sh` installs Ollama, pulls the model, writes `.env`, and restarts the backend automatically — zero manual steps for a new user.

### 5. **360° Fleet Health View** 📊
- **AI Health Score**: 0–100 fleet health computed by the LLM
- **Real-time Anomaly Detection**: Continuously monitors all services
- **LLM Insights**: Reasoning-backed observations, not template strings
- **Tabbed Interface**: AI Insights · Anomalies · Clusters · Traces · On-Call

---

## ⚡ Quick Start

```bash
# First time — installs Ollama, pulls llama3.2, writes .env, starts everything
chmod +x setup-llm.sh start.sh
./setup-llm.sh

# Subsequent runs
./start.sh

# Access the dashboard
open http://localhost:3000

# Check which AI engine is active
curl -s http://localhost:8001/api/ai/analyze | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(d['engine'], '| health:', d['overall_health_score'])"
```

---

## ⚙️ LLM Provider Setup

### Option A — Ollama (default, free, local)
```bash
./setup-llm.sh                      # installs Ollama + pulls llama3.2
./setup-llm.sh --model mistral      # use a different model
```

### Option B — Groq (free cloud, no credit card)
```bash
./setup-llm.sh --provider groq
# Script will prompt for your GROQ_API_KEY (get one at https://console.groq.com)
```

### Option C — OpenAI
```bash
./setup-llm.sh --provider openai
# Script will prompt for your OPENAI_API_KEY (requires billing credits)
```

### Switching provider later
```bash
./setup-llm.sh --provider groq      # rewrites .env and restarts backend
```

### Manual `.env` reference
```dotenv
LLM_PROVIDER=ollama          # ollama | groq | openai
HOLMES_MODEL=llama3.2        # model name for the active provider

OLLAMA_HOST=http://host.docker.internal:11434

GROQ_API_KEY=gsk_your_key_here
OPENAI_API_KEY=sk-your_key_here
```

---

## 📱 API Endpoints

### AI Analysis
```bash
# Full fleet analysis — anomalies, health score, insights, engine name
curl http://localhost:8001/api/ai/analyze

# Anomalies only
curl http://localhost:8001/api/ai/anomalies

# AI-generated insights
curl http://localhost:8001/api/ai/insights

# Anomaly trends
curl http://localhost:8001/api/ai/trends?hours=24
```

### Root Cause Analysis
```bash
curl -X POST http://localhost:8001/api/ai/root-cause \
  -H "Content-Type: application/json" \
  -d '{
    "anomaly": {
      "service": "vmalert",
      "cluster": "local-docker",
      "metric": "cpu",
      "severity": "high",
      "anomaly_score": -0.65
    }
  }'
```

### AI Alerts
```bash
curl -X POST http://localhost:8001/api/ai/alert \
  -H "Content-Type: application/json" \
  -d '{
    "anomaly": {
      "service": "victoria-metrics",
      "cluster": "local-docker",
      "metric": "memory",
      "severity": "critical",
      "value": 512.5
    }
  }'
```

---

## 🔧 How Detection Works

### Two-Layer Architecture

```
Metrics snapshot (Victoria Metrics)
          │
          ▼
┌─────────────────────────┐
│  Layer 1: HolmesGPT     │  ← LLM call (Ollama / Groq / OpenAI)
│  HolmesGPTAnalyzer      │  ← Returns reasoning + severity + insights
└────────────┬────────────┘
             │  fails / unavailable
             ▼
┌─────────────────────────┐
│  Layer 2: Rule-Based    │  ← Explicit threshold checks, always works
│  RuleBasedDetector      │  ← Same response schema, zero dependencies
└─────────────────────────┘
```

### Layer 1 — HolmesGPT (`HolmesGPTAnalyzer`)

1. **Prompt construction** — builds a structured metrics snapshot with service names, values, and timestamps
2. **LLM call** — sends system prompt + snapshot to the configured provider via the OpenAI-compatible REST API
3. **JSON parsing** — strips markdown fences (` ```json``` `) that some local models emit before parsing
4. **Result enrichment** — adds `engine`, `analysis_timestamp`, `data_points` fields

The system prompt instructs the LLM to:
- Identify anomalies deviating from healthy operational ranges
- Rate severity as `critical | high | medium | low`
- Compute a fleet health score 0–100
- Write 4–6 concise, emoji-prefixed insights for the on-call engineer

### Layer 2 — Rule-Based Fallback (`RuleBasedDetector`)

Explicit thresholds — no training, no variance requirement, no black-box:

| Metric | Warning | High | Critical |
|---|---|---|---|
| CPU % | >70% | >80% | >90% |
| Memory (MB) | >400 | — | >480 |
| Error rate % | >1% | >5% | >10% |
| Latency p99 (ms) | >500 | >1000 | >2000 |
| Service up flag | — | — | 0.0 (down) |

**Health score weights:**
```
health_score = 100 − (critical×15) − (high×8) − (medium×3)
```

### Response Schema (both layers)

```json
{
  "anomalies": [
    {
      "metric": "cpu",
      "service": "vmagent",
      "cluster": "local-docker",
      "value": 91.2,
      "anomaly_score": -0.85,
      "severity": "critical",
      "timestamp": "2026-02-26T14:00:00",
      "reasoning": "CPU at 91.2% exceeds the critical threshold of 90%",
      "details": { "description": "..." }
    }
  ],
  "overall_health_score": 62.0,
  "insights": ["🚨 Critical CPU spike on vmagent", "..."],
  "anomalies_detected": true,
  "engine": "HolmesGPT/ollama (llama3.2)",
  "analysis_timestamp": "2026-02-26T14:00:01",
  "data_points": 48
}
```

---

## 🎨 UI Features

### Tab 1: AI Insights
- **AI Health Score Banner** — prominent 0–100 score with colour coding
- **Engine badge** — shows `HolmesGPT/ollama (llama3.2)` or `RuleBasedDetector` so you always know which layer is active
- **LLM-generated insights** — reasoning-backed, e.g.:
  - `"🚨 vmagent CPU at 91% — critical threshold breached, check resource limits"`
  - `"⚠️ p99 latency on api-gateway at 1.8s — approaching critical threshold"`
- **Quick Stats** — clusters, analysis status, detection engine

### Tab 2: Anomalies
- **Detected anomaly list** with severity badge, service, metric, cluster, anomaly score, timestamp
- **`reasoning` field** — LLM's one-sentence explanation of each anomaly
- **Expandable detail report** — full description, correlated metrics, recommended actions
- **Trigger Alert button** — sends anomaly to Alertmanager

### Tab 3: Clusters
- Cluster health cards with service up/down counts and environment labels

---

## 💡 Example Insights

```
✅ All 12 services operating within normal ranges — no anomalies detected

🚨 vmagent CPU at 91.2% — exceeds critical threshold of 90%, check container resource limits

⚠️ api-gateway p99 latency at 1800ms — approaching critical threshold of 2000ms

🧠 memory-server RSS at 485MB — above critical threshold of 480MB, possible leak

⚡ 2 critical anomalies require immediate attention

📊 Fleet health: 62/100 — degraded
```

---

## 🎯 Use Cases

### 1. Proactive Monitoring
- HolmesGPT detects issues and explains them before pages fire
- Health score trends surface degradation patterns over time
- Fallback to rule-based ensures 24/7 coverage even if LLM is down

### 2. Incident Response
- Click anomaly → LLM `reasoning` tells you exactly what threshold was breached
- Actionable recommendations generated per anomaly type
- Trigger alerts directly into Alertmanager from the UI

### 3. Sharing / Onboarding
- New team members run `./setup-llm.sh` — fully automated, no manual steps
- Provider can be swapped at any time without touching application code

### 4. Fleet-Wide Visibility
- Single pane of glass for all clusters
- LLM correlates anomalies across services in the insights section

---

## 🔄 Auto-Refresh

| Data | Interval |
|---|---|
| AI Analysis | Every 20 seconds |
| Clusters | Every 30 seconds |
| Services | Every 15 seconds |

Click **↻** in the top-right to manually refresh.

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────┐
│   Frontend UI  (Next.js 14 + MUI)  :3000        │
└────────────────────────┬────────────────────────┘
                         │ REST
┌────────────────────────▼────────────────────────┐
│   Backend API  (FastAPI)  :8001                 │
│                                                 │
│   ai_agent.py                                   │
│   ┌─────────────────────────────────────────┐   │
│   │ Layer 1: HolmesGPTAnalyzer              │   │
│   │  provider: ollama | groq | openai       │   │
│   │  → LLM reasoning per anomaly            │   │
│   └──────────────────┬──────────────────────┘   │
│                      │ fallback                 │
│   ┌──────────────────▼──────────────────────┐   │
│   │ Layer 2: RuleBasedDetector              │   │
│   │  explicit thresholds, zero deps         │   │
│   └─────────────────────────────────────────┘   │
└──────┬───────────────────────────┬──────────────┘
       │                           │
┌──────▼───────┐          ┌────────▼───────┐
│   Victoria   │          │  Ollama :11434 │ ← runs on host
│   Metrics    │          │  (or Groq/     │
│   :8428      │          │   OpenAI API)  │
└──────────────┘          └────────────────┘
```

---

## 🐛 Troubleshooting

### Check which engine is active
```bash
curl -s http://localhost:8001/api/ai/analyze | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('engine'))"
# HolmesGPT/ollama (llama3.2)   ← LLM active
# RuleBasedDetector              ← fallback active
```

### HolmesGPT falling back to rule-based
```bash
# Check backend logs
docker logs visibility-api 2>&1 | grep -i holmesgpt

# Ollama — verify server running and model pulled
curl http://localhost:11434/api/tags
ollama list
ollama pull llama3.2

# Re-run full LLM setup
./setup-llm.sh
```

### Ollama not starting
```bash
cat /tmp/ollama.log
ollama serve &
curl http://localhost:11434/api/tags
```

### Switch provider
```bash
./setup-llm.sh --provider groq     # free, fast cloud
./setup-llm.sh --provider openai   # GPT-4o-mini
./setup-llm.sh                     # back to local Ollama
```

### AI Analysis Errors
```bash
docker logs visibility-api
docker exec visibility-api curl http://victoria-metrics:8428/health
```

### No metrics / anomalies visible
```bash
curl http://localhost:8429/api/v1/targets | jq '.data.activeTargets[] | {job, health}'
curl http://localhost:8001/api/ai/analyze | jq '.overall_health_score'
```

---

## 📈 Next Steps

### Connect to Production VictoriaMetrics
```yaml
# docker-compose.yml → backend → environment
- VM_URL=https://your-production-vm.flex.ai
- VM_TOKEN=your-bearer-token
```

### Add Custom Metrics
Edit `backend/ai_agent.py` — add your metric queries to `_fetch_metrics()`. The LLM will automatically reason over any new fields you include in the snapshot.

### Use a Larger / Smarter Model
```bash
# Upgrade Ollama model
./setup-llm.sh --model llama3.3       # larger context
./setup-llm.sh --model deepseek-r1    # reasoning-focused

# Or switch to Groq for faster cloud inference
./setup-llm.sh --provider groq --model llama-3.3-70b-versatile
```

---

## 🎉 Current Capabilities

✅ HolmesGPT LLM anomaly detection (Ollama / Groq / OpenAI)  
✅ Rule-based fallback — always on, zero dependencies  
✅ One-command setup for new users (`./setup-llm.sh`)  
✅ `reasoning` field per anomaly — no more black-box scores  
✅ Multi-provider `.env` with automatic switching  
✅ Root cause analysis via Holmes RCA (Loki + VictoriaMetrics + kubectl)  
✅ Fleet-wide visibility with 360° health dashboard  
✅ AI-triggered alerting via Alertmanager  
✅ No scikit-learn / numpy / pandas required
