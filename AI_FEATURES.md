# AI-Powered Observability Platform - Guide

## 🚀 What's New

Your FlexAI Visibility Platform now includes **AI-powered observability** with:

### 1. **AI Anomaly Detection Agent** 🤖
- Automatically analyzes metrics across all clusters
- Uses machine learning (Isolation Forest) to detect anomalies
- Provides anomaly scores and severity levels (critical, high, medium, low)
- Learns from historical data patterns

### 2. **360° Fleet Health View** 📊
- **AI Health Score**: Overall fleet health percentage based on AI analysis
- **Real-time Anomaly Detection**: Continuously monitors all services
- **Intelligent Insights**: AI-generated observations about system health
- **Tabbed Interface**: Easy navigation between AI Insights, Anomalies, and Clusters

### 3. **Root Cause Analysis** 🔍
- Click on any detected anomaly to see:
  - Probable causes with probability scores
  - Correlated metrics that might explain the issue
  - Actionable recommendations
  - Related timeline events

### 4. **AI-Triggered Alerts** 🚨
- Trigger alerts directly from detected anomalies
- Integrates with Alertmanager
- Automatic severity classification
- Alert history tracking

## 📱 New API Endpoints

### AI Analysis
```bash
# Get AI fleet-wide analysis
curl http://localhost:8001/api/ai/analyze

# Get current anomalies only
curl http://localhost:8001/api/ai/anomalies

# Get AI-generated insights
curl http://localhost:8001/api/ai/insights

# Get anomaly trends
curl http://localhost:8001/api/ai/trends?hours=24
```

### Root Cause Analysis
```bash
# Perform RCA on a specific anomaly
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
# Trigger an alert for an anomaly
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

## 🎨 UI Features

### Tab 1: AI Insights
- **AI Health Score Banner**: Prominent display of overall fleet health
- **AI-Generated Insights**: Human-readable observations like:
  - "🚨 3 critical anomalies detected - immediate attention required"
  - "⚠️ Service 'vmagent' showing 5 anomalies - possible degradation"
  - "💻 CPU-related anomalies dominant - possible resource exhaustion"
- **Quick Stats**: Clusters status, analysis status, detection status

### Tab 2: Anomalies
- **List of Detected Anomalies**: Each showing:
  - Severity badge (color-coded)
  - Service and metric name
  - Cluster information
  - Anomaly score
  - Timestamp
- **Interactive**: Click any anomaly to see detailed root cause analysis
- **Trigger Alert Button**: Manually trigger alerts for specific anomalies

### Tab 3: Clusters
- **Cluster Cards**: Traditional cluster view with health status
- Environment and service counts
- Status indicators

## 🔧 How AI Detection Works

### 1. **Data Collection**
The AI agent collects metrics from Victoria Metrics:
- CPU usage (process_cpu_seconds_total)
- Memory usage (process_resident_memory_bytes)
- Scrape duration (latency proxy)
- Custom metrics from all services

### 2. **Feature Extraction**
Converts raw metrics into feature vectors for ML analysis:
```python
[cpu_percent, memory_mb, response_time_ms, error_rate, ...]
```

### 3. **Anomaly Detection**
Uses Isolation Forest algorithm:
- Contamination rate: 10%
- Ensemble of 100 decision trees
- Adapts to your environment over time
- Scores each data point (-1 = anomaly, 1 = normal)

### 4. **Severity Classification**
Anomaly scores are converted to severity levels:
- **Critical**: score < -0.7 (immediate action required)
- **High**: score < -0.5 (attention needed)
- **Medium**: score < -0.3 (monitor closely)
- **Low**: score < 0 (informational)

### 5. **Root Cause Analysis**
When you click on an anomaly:
- Finds correlated metrics within 5-minute window
- Analyzes patterns (CPU, memory, latency, errors)
- Generates probable causes with explanations
- Provides actionable recommendations

### 6. **Health Score Calculation**
```
Health Score = 100 × (1 - anomaly_ratio) - severity_penalties
```
Where:
- Critical anomaly = -10 points
- High anomaly = -5 points
- Medium anomaly = -2 points

## 💡 Example Insights

The AI generates human-readable insights like:

1. **All Clear**
   - "✅ All systems operating normally - no anomalies detected"

2. **CPU Issues**
   - "💻 CPU-related anomalies dominant - possible resource exhaustion"
   - Recommendation: "Check CPU-intensive processes and optimize algorithms"

3. **Memory Issues**
   - "🧠 Memory anomalies detected - potential memory leak or pressure"
   - Recommendation: "Analyze memory usage patterns and identify leaks"

4. **Network/Latency**
   - "⏱️ Latency spikes detected - network or processing delays"
   - Recommendation: "Check network connectivity and downstream services"

5. **Cascading Failures**
   - "⚠️ Multiple related metrics affected - issue may be propagating"
   - Recommendation: "Implement circuit breakers and isolate affected services"

## 🎯 Use Cases

### 1. Proactive Monitoring
- AI detects issues before they become critical
- Health score trends show degradation patterns
- Early warning system for resource exhaustion

### 2. Incident Response
- Click anomaly → See root cause analysis
- Get actionable recommendations immediately
- Trigger alerts for team notification

### 3. Capacity Planning
- Track anomaly trends over time
- Identify services with recurring issues
- Plan resource scaling based on AI insights

### 4. Fleet-Wide Visibility
- Single pane of glass for all clusters
- AI correlates issues across services
- Holistic view of infrastructure health

## 🔄 Auto-Refresh

All data refreshes automatically:
- **AI Analysis**: Every 20 seconds
- **Clusters**: Every 30 seconds
- **Services**: Every 15 seconds

Click the refresh button (↻) in the top-right to manually refresh.

## 📊 Architecture

```
┌─────────────────┐
│   Frontend UI   │  ← React/Next.js with MUI
│  (Port 3000)    │  ← Real-time dashboards
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Backend API    │  ← FastAPI with AI Agent
│  (Port 8001)    │  ← /api/ai/* endpoints
└────────┬────────┘
         │
         ├─────────────┐
         ▼             ▼
┌──────────────┐  ┌──────────────┐
│   Victoria   │  │  AI Agent    │
│   Metrics    │  │  (ML Model)  │
│  (TSDB)      │  │  sklearn     │
└──────────────┘  └──────────────┘
```

## 🚀 Quick Start

```bash
# Start the platform
./start.sh

# Access the dashboard
open http://localhost:3000

# View AI analysis
curl http://localhost:8001/api/ai/analyze | jq

# Check specific anomalies
curl http://localhost:8001/api/ai/anomalies | jq
```

## 🐛 Troubleshooting

### No Anomalies Detected
- **Reason**: AI needs at least 10 data points to train
- **Solution**: Wait 2-3 minutes for data collection
- **Status**: Check "Data points: X" in Analysis Status card

### Health Score Always 100%
- **Reason**: System is genuinely healthy OR not enough variance in data
- **Solution**: Normal if all metrics are stable

### AI Analysis Errors
- **Check**: `docker logs visibility-api`
- **Common**: Victoria Metrics connection issues
- **Fix**: Ensure VM is running: `docker ps | grep vm-single`

## 📈 Next Steps

### Connect to Production
Update `docker-compose.yml`:
```yaml
backend:
  environment:
    - VM_URL=https://your-production-vm.com
    - VM_TOKEN=your-auth-token  # If required
```

### Add Custom Metrics
Edit `backend/ai_agent.py` to include your custom metrics in analysis.

### Tune Sensitivity
Adjust anomaly detection parameters in `ai_agent.py`:
```python
self.anomaly_detector = IsolationForest(
    contamination=0.1,  # Lower = fewer anomalies
    random_state=42,
    n_estimators=100     # Higher = more accurate
)
```

### Add OpenAI Integration (Optional)
The platform includes OpenAI library. You can enhance insights with GPT:
```python
import openai
# Generate natural language explanations from anomalies
```

## 🎉 Success!

You now have a fully functional **AI-Powered Observability Platform** with:
✅ Automated anomaly detection
✅ Root cause analysis
✅ Fleet-wide visibility
✅ AI-triggered alerting
✅ 360° health dashboard

Enjoy monitoring your infrastructure with AI! 🚀
