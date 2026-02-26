# 🎉 FlexAI Visibility Platform — Running Successfully!

## ✅ What's Running

All services are up and operational:

| Service | URL | Status |
|---------|-----|--------|
| **Frontend Dashboard** | http://localhost:3000 | ✅ Running |
| **Backend API** | http://localhost:8001 | ✅ Running |
| **API Documentation** | http://localhost:8001/docs | ✅ Running |
| **Victoria Metrics** | http://localhost:8428 | ✅ Running |
| **Grafana** | http://localhost:3001 | ✅ Running |
| **Alertmanager** | http://localhost:9093 | ✅ Running |
| **VMAlert** | http://localhost:8880 | ✅ Running |
| **Ollama (LLM)** | http://localhost:11434 | ✅ Running on host |

### 🤖 Active AI Engine
```bash
# Check which LLM engine is live
curl -s http://localhost:8001/api/ai/analyze | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('engine'), '| health:', d.get('overall_health_score'))"
# e.g.: HolmesGPT/ollama (llama3.2) | health: 87.0
```

| Engine shown | Meaning |
|---|---|
| `HolmesGPT/ollama (llama3.2)` | LLM active — full reasoning per anomaly |
| `HolmesGPT/groq (...)` | Groq cloud LLM active |
| `HolmesGPT/openai (...)` | OpenAI active |
| `RuleBasedDetector` | LLM unreachable — threshold fallback active |

## 📊 Current Metrics

The system is currently monitoring:
- **1 Cluster**: local-docker
- **6 Services**: All healthy
- **Scrape Interval**: 30 seconds
- **Metrics Retention**: 30 days

### Services Being Monitored:
1. Victoria Metrics (TSDB)
2. VMAgent (Metrics Scraper)
3. VMAlert (Alert Evaluator)
4. Alertmanager (Alert Router)
5. Node Exporter (System Metrics)
6. Visibility API (Backend)

## 🔍 Quick Commands

### Check Service Status
```bash
# View all containers
docker ps --filter "name=visibility"

# Check logs
docker logs visibility-api --tail 50
docker logs vm-single --tail 50
docker logs vmagent --tail 50
```

### Test API Endpoints
```bash
# Health check
curl http://localhost:8001/health | python3 -m json.tool

# Get clusters
curl http://localhost:8001/api/clusters | python3 -m json.tool

# Get all services
curl http://localhost:8001/api/services/all | python3 -m json.tool

# Get CPU metrics
curl http://localhost:8001/api/metrics/cpu | python3 -m json.tool

# Get memory metrics
curl http://localhost:8001/api/metrics/memory | python3 -m json.tool
```

### Test HolmesGPT AI Endpoints
```bash
# Full AI fleet analysis (anomalies + health score + insights + engine)
curl http://localhost:8001/api/ai/analyze | python3 -m json.tool

# Anomalies only
curl http://localhost:8001/api/ai/anomalies | python3 -m json.tool

# LLM-generated insights
curl http://localhost:8001/api/ai/insights | python3 -m json.tool

# Anomaly trends (last 24 h)
curl 'http://localhost:8001/api/ai/trends?hours=24' | python3 -m json.tool
```

### Query Victoria Metrics Directly
```bash
# Check service health
curl 'http://localhost:8428/api/v1/query?query=up'

# Get CPU usage
curl 'http://localhost:8428/api/v1/query?query=rate(process_cpu_seconds_total[5m])'

# Get memory usage
curl 'http://localhost:8428/api/v1/query?query=process_resident_memory_bytes'

# Count total metrics
curl 'http://localhost:8428/api/v1/series/count'
```

## 🎨 Frontend Features

The dashboard (http://localhost:3000) shows:

1. **Global Overview**
   - Total clusters count
   - Healthy/degraded/down status
   - Real-time updates

2. **Cluster Cards**
   - Click any cluster for details
   - Service health indicators
   - Last seen timestamps

3. **Detailed Metrics** (when cluster selected)
   - Service health percentage
   - CPU usage
   - Memory usage
   - Scrape duration

4. **Services Status**
   - All monitored services
   - Up/down indicators
   - Instance details

## 🔄 Managing the Platform

### Start Everything
```bash
cd visibility-platform
./start.sh
# On first run: automatically calls setup-llm.sh to install Ollama + pull model
```

### Stop Everything
```bash
./stop.sh
```

### Switch LLM Provider
```bash
./setup-llm.sh                    # Ollama (local, free, default)
./setup-llm.sh --provider groq    # Groq free cloud
./setup-llm.sh --provider openai  # OpenAI (requires billing)
./setup-llm.sh --model mistral    # Different Ollama model
```

### Restart a Specific Service
```bash
docker-compose restart backend    # Restart API
docker-compose restart frontend   # Restart UI
docker-compose restart vmagent    # Restart scraper
```

### View Logs (follow mode)
```bash
docker-compose logs -f backend
docker-compose logs -f vmagent
docker-compose logs -f victoria-metrics

# HolmesGPT-specific log lines
docker logs visibility-api 2>&1 | grep -i holmesgpt
```

### Rebuild After Code Changes
```bash
# Rebuild backend (needed after ai_agent.py changes)
docker-compose up -d --build backend

# Rebuild frontend
docker-compose up -d --build frontend

# Rebuild everything
docker-compose up -d --build
```

## 🚨 Adding Alerts

Edit the alert rules file:
```bash
nano config/alerts/basic-rules.yml
```

Then restart VMAlert:
```bash
docker-compose restart vmalert
```

Example alert:
```yaml
- alert: HighMemoryUsage
  expr: process_resident_memory_bytes > 1024 * 1024 * 1024
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High memory usage detected"
    description: "Service is using more than 1GB of memory"
```

## 📈 Adding More Metrics

To scrape additional services, edit:
```bash
nano config/prometheus-config.yml
```

Add new scrape targets:
```yaml
scrape_configs:
  - job_name: 'my-service'
    static_configs:
      - targets: ['my-service:9090']
        labels:
          service: 'my-app'
```

Then restart VMAgent:
```bash
docker-compose restart vmagent
```

## 🔗 Connecting to Production

To monitor your actual Kubernetes clusters:

1. Edit `docker-compose.yml`:
```yaml
backend:
  environment:
    - VM_URL=https://prometheus-prod-24-prod-eu-west-2.grafana.net/api/prom
    - VM_TOKEN=your-production-token
```

2. Restart backend:
```bash
docker-compose restart backend
```

3. The frontend will automatically show your production clusters!

## 🎓 Next Steps

### Immediate Actions:
1. ✅ Explore the dashboard at http://localhost:3000 — check the **AI Insights** tab
2. ✅ Try the API docs at http://localhost:8001/docs
3. ✅ Run `curl -s http://localhost:8001/api/ai/analyze | python3 -m json.tool` to see live HolmesGPT output
4. ✅ Create custom Grafana dashboards at http://localhost:3001

### Advanced:
1. **Switch LLM Provider**: `./setup-llm.sh --provider groq` for faster cloud inference
2. **Upgrade Model**: `./setup-llm.sh --model llama3.3` for larger context window
3. **Add GPU Monitoring**: Include DCGM exporter metrics in `config/prometheus-config.yml`
4. **Alert Routing**: Configure Slack/PagerDuty webhooks in `config/alertmanager-config.yml`
5. **Production Integration**: Update `VM_URL` in `docker-compose.yml` to point at real clusters

## 📚 Documentation

Full documentation available in:
- `README.md` — Quick start + LLM configuration reference
- `AI_FEATURES.md` — HolmesGPT architecture, detection layers, API reference
- `setup-llm.sh` — Automated LLM setup script (Ollama · Groq · OpenAI)
- `OBSERVABILITY_ARCHITECTURE.md` — Complete stack architecture

## 🐛 Troubleshooting

### HolmesGPT falling back to RuleBasedDetector?
```bash
# See what engine is active and why
docker logs visibility-api 2>&1 | grep -i holmesgpt

# Verify Ollama is running and model is ready
curl http://localhost:11434/api/tags
ollama list

# If Ollama isn't running, start it
ollama serve &

# Pull model if missing
ollama pull llama3.2

# Re-run full automated setup
./setup-llm.sh
```

### Frontend not loading?
```bash
docker logs visibility-ui
# Check if port 3000 is available
lsof -ti:3000
```

### Backend API errors?
```bash
docker logs visibility-api
# Test Victoria Metrics connection
docker exec visibility-api python3 -c "import requests; print(requests.get('http://victoria-metrics:8428/api/v1/query?query=up').status_code)"
```

### No metrics showing?
```bash
# Check VMAgent is scraping
docker logs vmagent
# Check Victoria Metrics has data
curl 'http://localhost:8428/api/v1/query?query=up'
```

## 🎉 Success!

Your FlexAI Visibility Platform is fully operational with:
- ✅ HolmesGPT LLM anomaly detection (Ollama / Groq / OpenAI)
- ✅ Rule-based fallback — always on, zero dependencies
- ✅ Real-time metrics collection (Victoria Metrics)
- ✅ Beautiful dashboard UI with AI Insights tab
- ✅ REST API + Swagger docs
- ✅ Alert management (Alertmanager + VMAlert)
- ✅ Time-series database (30 days retention)
- ✅ One-command setup for new users (`./setup-llm.sh`)

**Start exploring at:** http://localhost:3000 → **AI Insights** tab

Enjoy your AI-powered monitoring platform! 🚀
