# 🎉 FlexAI Visibility Platform - Running Successfully!

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
cd /Users/krishnadamarla/Library/CloudStorage/GoogleDrive-krishna.damarla@flex.ai/My\ Drive/GitHub\ Code/infra-main/visibility-platform
./start.sh
```

### Stop Everything
```bash
./stop.sh
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
```

### Rebuild After Code Changes
```bash
# Rebuild backend
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
1. ✅ Explore the dashboard at http://localhost:3000
2. ✅ Try the API docs at http://localhost:8001/docs
3. ✅ Create custom Grafana dashboards at http://localhost:3001

### Advanced:
1. **Add GPU Monitoring**: Include DCGM exporter metrics
2. **Custom Dashboards**: Create specific views in Grafana
3. **Alert Routing**: Configure Slack/PagerDuty webhooks
4. **Cost Analytics**: Integrate cloud provider APIs
5. **Production Integration**: Connect to real K8s clusters

## 📚 Documentation

Full documentation available in:
- `OBSERVABILITY_ARCHITECTURE.md` - Complete architecture explanation
- `LOCAL_OBSERVABILITY_SETUP.md` - Detailed setup guide
- `VISIBILITY_UI_PROTOTYPE.md` - UI development guide
- `README.md` - Quick start guide

## 🐛 Troubleshooting

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

Your FlexAI Visibility Platform is fully operational! You now have:
- ✅ Real-time metrics collection
- ✅ Beautiful dashboard UI
- ✅ REST API for integrations
- ✅ Alert management system
- ✅ Time-series database (30 days retention)

**Start exploring at:** http://localhost:3000

Enjoy your monitoring platform! 🚀
