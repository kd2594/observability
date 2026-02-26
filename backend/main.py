from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_api_client import PrometheusConnect
from prometheus_client import Counter, Histogram, generate_latest
from datetime import datetime, timedelta
import asyncio
import redis
import json
import os
from typing import List, Dict
import logging
import httpx
from ai_agent import ai_agent
from holmes_rca import holmes
from robusta_playbooks import robusta

# ── OpenTelemetry setup ────────────────────────────────────────────────
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    _OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    _OTEL_SERVICE  = os.getenv("OTEL_SERVICE_NAME", "visibility-api")
    _DEPLOY_ENV    = os.getenv("DEPLOYMENT_ENV", "docker-compose")

    _resource = Resource.create({
        "service.name":            _OTEL_SERVICE,
        "deployment.environment":  _DEPLOY_ENV,
        "service.version":         "1.0.0",
    })
    _provider = TracerProvider(resource=_resource)
    _exporter = OTLPSpanExporter(endpoint=f"{_OTEL_ENDPOINT}/v1/traces")
    _provider.add_span_processor(BatchSpanProcessor(_exporter))
    trace.set_tracer_provider(_provider)

    # Auto-instrument httpx (outbound calls to VictoriaMetrics etc.) + Redis
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    # Inject trace_id into every log line so Loki → Jaeger links work
    LoggingInstrumentor().instrument(set_logging_format=True)

    _otel_enabled = True
except ImportError:
    _otel_enabled = False
# ─────────────────────────────────────────────────────────────

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FlexAI Visibility API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument FastAPI — must happen after app + middleware are created
if _otel_enabled:
    FastAPIInstrumentor.instrument_app(app)
    logger.info(f"OpenTelemetry tracing enabled → {os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://otel-collector:4318')}")

# Prometheus metrics for the API itself
api_requests = Counter('api_requests_total', 'Total API requests', ['endpoint', 'method'])
api_duration = Histogram('api_request_duration_seconds', 'API request duration', ['endpoint'])

# Victoria Metrics connection
VM_URL = os.getenv("VM_URL", "http://victoria-metrics:8428")
logger.info(f"Connecting to Victoria Metrics at: {VM_URL}")

vm_client = PrometheusConnect(url=VM_URL, disable_ssl=True)

# Redis for caching
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=2)
    redis_client.ping()
    logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.warning(f"Could not connect to Redis: {e}. Running without cache.")
    redis_client = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to websocket: {e}")
                self.disconnect(connection)

manager = ConnectionManager()


def get_from_cache(key: str):
    """Get value from Redis cache"""
    if not redis_client:
        return None
    try:
        value = redis_client.get(key)
        return json.loads(value) if value else None
    except Exception as e:
        logger.warning(f"Cache get error: {e}")
        return None


def set_in_cache(key: str, value: any, ttl: int = 30):
    """Set value in Redis cache with TTL"""
    if not redis_client:
        return
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.warning(f"Cache set error: {e}")


def safe_query(query: str, default=None):
    """Safely execute PromQL query"""
    try:
        result = vm_client.custom_query(query)
        return result
    except Exception as e:
        logger.error(f"Query error for '{query}': {e}")
        return default or []


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    api_requests.labels(endpoint='/', method='GET').inc()
    return {
        "message": "FlexAI Visibility API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint for the API itself"""
    return generate_latest()


@app.get("/api/clusters")
async def get_clusters():
    """Get list of all clusters with health status"""
    api_requests.labels(endpoint='/api/clusters', method='GET').inc()
    
    # Check cache first
    cached = get_from_cache("clusters:list")
    if cached:
        logger.info("Returning cached clusters list")
        return cached
    
    # Query Victoria Metrics
    query = 'up'
    result = safe_query(query)
    
    clusters = {}
    for metric in result:
        cluster_name = metric['metric'].get('cluster', 'local-docker')
        job = metric['metric'].get('job', 'unknown')
        is_up = metric['value'][1] == '1'
        
        if cluster_name not in clusters:
            clusters[cluster_name] = {
                'name': cluster_name,
                'status': 'healthy',
                'services_up': 0,
                'services_down': 0,
                'last_seen': datetime.fromtimestamp(float(metric['value'][0])).isoformat(),
                'environment': 'production' if 'prod' in cluster_name.lower() else 'development'
            }
        
        if is_up:
            clusters[cluster_name]['services_up'] += 1
        else:
            clusters[cluster_name]['services_down'] += 1
            clusters[cluster_name]['status'] = 'degraded'
    
    # If no services are up, mark as down
    for cluster in clusters.values():
        if cluster['services_up'] == 0:
            cluster['status'] = 'down'
    
    clusters_list = list(clusters.values())
    
    # Cache for 30 seconds
    set_in_cache("clusters:list", clusters_list, 30)
    
    logger.info(f"Found {len(clusters_list)} clusters")
    return clusters_list


@app.get("/api/clusters/{cluster_name}/metrics")
async def get_cluster_metrics(cluster_name: str):
    """Get detailed metrics for a specific cluster"""
    api_requests.labels(endpoint='/api/clusters/metrics', method='GET').inc()
    
    cache_key = f"cluster:metrics:{cluster_name}"
    cached = get_from_cache(cache_key)
    if cached:
        logger.info(f"Returning cached metrics for {cluster_name}")
        return cached
    
    # Query metrics
    queries = {
        'total_services': f'count(up{{cluster="{cluster_name}"}})',
        'services_up': f'count(up{{cluster="{cluster_name}"}} == 1)',
        'cpu_usage_percent': f'avg(rate(process_cpu_seconds_total{{cluster="{cluster_name}"}}[5m])) * 100',
        'memory_usage_mb': f'sum(process_resident_memory_bytes{{cluster="{cluster_name}"}}) / 1024 / 1024',
        'scrape_duration': f'avg(scrape_duration_seconds{{cluster="{cluster_name}"}})',
    }
    
    metrics = {}
    for name, query in queries.items():
        result = safe_query(query)
        try:
            metrics[name] = float(result[0]['value'][1]) if result else 0
        except (IndexError, KeyError, ValueError):
            metrics[name] = 0
    
    # Calculate derived metrics
    metrics['services_down'] = metrics['total_services'] - metrics['services_up']
    metrics['health_percentage'] = (metrics['services_up'] / metrics['total_services'] * 100) if metrics['total_services'] > 0 else 0
    
    # Cache for 15 seconds
    set_in_cache(cache_key, metrics, 15)
    
    logger.info(f"Returning metrics for {cluster_name}")
    return metrics


@app.get("/api/services/all")
async def get_all_services():
    """Get all services across all clusters"""
    api_requests.labels(endpoint='/api/services/all', method='GET').inc()
    
    query = 'up'
    result = safe_query(query)
    
    services = []
    for metric in result:
        services.append({
            'cluster': metric['metric'].get('cluster', 'local-docker'),
            'job': metric['metric'].get('job', 'unknown'),
            'instance': metric['metric'].get('instance', 'unknown'),
            'status': 'up' if metric['value'][1] == '1' else 'down',
            'timestamp': datetime.fromtimestamp(float(metric['value'][0])).isoformat()
        })
    
    return {'services': services, 'total': len(services)}


@app.get("/api/metrics/cpu")
async def get_cpu_metrics():
    """Get CPU usage metrics"""
    api_requests.labels(endpoint='/api/metrics/cpu', method='GET').inc()
    
    query = 'rate(process_cpu_seconds_total[5m]) * 100'
    result = safe_query(query)
    
    cpu_metrics = []
    for metric in result:
        cpu_metrics.append({
            'cluster': metric['metric'].get('cluster', 'local-docker'),
            'job': metric['metric'].get('job', 'unknown'),
            'instance': metric['metric'].get('instance', 'unknown'),
            'cpu_percent': float(metric['value'][1]),
            'timestamp': datetime.fromtimestamp(float(metric['value'][0])).isoformat()
        })
    
    return {'metrics': cpu_metrics, 'total': len(cpu_metrics)}


@app.get("/api/metrics/memory")
async def get_memory_metrics():
    """Get memory usage metrics"""
    api_requests.labels(endpoint='/api/metrics/memory', method='GET').inc()
    
    query = 'process_resident_memory_bytes / 1024 / 1024'
    result = safe_query(query)
    
    memory_metrics = []
    for metric in result:
        memory_metrics.append({
            'cluster': metric['metric'].get('cluster', 'local-docker'),
            'job': metric['metric'].get('job', 'unknown'),
            'instance': metric['metric'].get('instance', 'unknown'),
            'memory_mb': float(metric['value'][1]),
            'timestamp': datetime.fromtimestamp(float(metric['value'][0])).isoformat()
        })
    
    return {'metrics': memory_metrics, 'total': len(memory_metrics)}


@app.get("/api/alerts/active")
async def get_active_alerts():
    """Get currently firing alerts"""
    api_requests.labels(endpoint='/api/alerts/active', method='GET').inc()
    
    query = 'ALERTS{alertstate="firing"}'
    result = safe_query(query)
    
    alerts = []
    for metric in result:
        alerts.append({
            'name': metric['metric'].get('alertname', 'Unknown'),
            'severity': metric['metric'].get('severity', 'info'),
            'cluster': metric['metric'].get('cluster', 'unknown'),
            'job': metric['metric'].get('job', 'unknown'),
            'description': metric['metric'].get('description', 'No description'),
            'fired_at': datetime.fromtimestamp(float(metric['value'][0])).isoformat()
        })
    
    logger.info(f"Found {len(alerts)} active alerts")
    return {'alerts': alerts, 'total': len(alerts)}


@app.post("/webhook/alerts")
async def receive_alert_webhook(request: Request):
    """Receive alerts from Alertmanager"""
    try:
        data = await request.json()
        logger.info(f"Received alert webhook: {json.dumps(data, indent=2)}")
        
        # Broadcast to WebSocket clients
        await manager.broadcast({
            'type': 'alert',
            'timestamp': datetime.now().isoformat(),
            'data': data
        })
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/webhook/alerts/critical")
async def receive_critical_alert_webhook(request: Request):
    """Receive critical alerts from Alertmanager"""
    try:
        data = await request.json()
        logger.warning(f"Received CRITICAL alert: {json.dumps(data, indent=2)}")
        
        # Broadcast to WebSocket clients
        await manager.broadcast({
            'type': 'critical_alert',
            'timestamp': datetime.now().isoformat(),
            'data': data
        })
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing critical webhook: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# WebSocket for Real-Time Updates
# ============================================================================

@app.websocket("/ws/live-metrics")
async def websocket_live_metrics(websocket: WebSocket):
    """Stream live metrics via WebSocket"""
    await manager.connect(websocket)
    
    try:
        while True:
            # Query latest metrics
            clusters = await get_clusters()
            
            # Add timestamp
            data = {
                'type': 'clusters_update',
                'timestamp': datetime.now().isoformat(),
                'data': clusters
            }
            
            await websocket.send_json(data)
            await asyncio.sleep(5)  # Update every 5 seconds
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Check Victoria Metrics connection
    try:
        result = safe_query('up')
        vm_status = "healthy" if result else "unhealthy"
    except:
        vm_status = "unhealthy"
    
    # Check Redis connection
    redis_status = "healthy"
    if redis_client:
        try:
            redis_client.ping()
        except:
            redis_status = "unhealthy"
    else:
        redis_status = "disabled"
    
    overall_status = "healthy" if vm_status == "healthy" else "degraded"
    
    return {
        'status': overall_status,
        'victoria_metrics': vm_status,
        'redis': redis_status,
        'timestamp': datetime.now().isoformat(),
        'vm_url': VM_URL
    }


# ==================== AI-POWERED OBSERVABILITY ENDPOINTS ====================

@app.get("/api/ai/analyze")
async def analyze_fleet_health():
    """
    AI-powered fleet-wide analysis
    Analyzes all metrics across clusters to detect anomalies
    """
    api_requests.labels(endpoint='/api/ai/analyze', method='GET').inc()
    
    try:
        # Gather all metrics from all services
        all_metrics = []
        
        # Query CPU metrics
        cpu_query = 'rate(process_cpu_seconds_total[5m]) * 100'
        cpu_data = vm_client.custom_query(query=cpu_query)
        
        for result in cpu_data:
            metric = result.get('metric', {})
            value = result.get('value', [0, 0])[1]
            all_metrics.append({
                'metric': 'cpu',
                'service': metric.get('job', 'unknown'),
                'cluster': metric.get('cluster', 'unknown'),
                'value': float(value),
                'cpu_percent': float(value),
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # Query memory metrics
        memory_query = 'process_resident_memory_bytes / 1024 / 1024'
        memory_data = vm_client.custom_query(query=memory_query)
        
        for result in memory_data:
            metric = result.get('metric', {})
            value = result.get('value', [0, 0])[1]
            all_metrics.append({
                'metric': 'memory',
                'service': metric.get('job', 'unknown'),
                'cluster': metric.get('cluster', 'unknown'),
                'value': float(value),
                'memory_mb': float(value),
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # Query scrape duration (latency proxy)
        scrape_query = 'scrape_duration_seconds * 1000'
        scrape_data = vm_client.custom_query(query=scrape_query)
        
        for result in scrape_data:
            metric = result.get('metric', {})
            value = result.get('value', [0, 0])[1]
            all_metrics.append({
                'metric': 'latency',
                'service': metric.get('job', 'unknown'),
                'cluster': metric.get('cluster', 'unknown'),
                'value': float(value),
                'response_time_ms': float(value),
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # AI Analysis
        analysis = ai_agent.analyze_metrics(all_metrics)
        
        # Cache results
        if redis_client:
            try:
                redis_client.setex(
                    'ai_analysis',
                    15,  # 15 seconds cache
                    json.dumps(analysis)
                )
            except Exception as e:
                logger.warning(f"Could not cache AI analysis: {e}")
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error in AI analysis: {e}")
        return {
            'anomalies_detected': False,
            'anomalies': [],
            'overall_health_score': 60.0,
            'insights': [f'Analysis temporarily unavailable: {str(e)}'],
            'error': str(e)
        }


@app.get("/api/ai/anomalies")
async def get_current_anomalies():
    """
    Get currently detected anomalies
    """
    api_requests.labels(endpoint='/api/ai/anomalies', method='GET').inc()
    
    # Try cache first
    if redis_client:
        try:
            cached = redis_client.get('ai_analysis')
            if cached:
                analysis = json.loads(cached)
                return {
                    'anomalies': analysis.get('anomalies', []),
                    'count': len(analysis.get('anomalies', [])),
                    'cached': True
                }
        except Exception:
            pass
    
    # Run fresh analysis
    analysis = await analyze_fleet_health()
    return {
        'anomalies': analysis.get('anomalies', []),
        'count': len(analysis.get('anomalies', [])),
        'cached': False
    }


@app.post("/api/ai/root-cause")
async def analyze_root_cause(request: Request):
    """
    Perform root cause analysis for a specific anomaly
    """
    api_requests.labels(endpoint='/api/ai/root-cause', method='POST').inc()
    
    try:
        body = await request.json()
        anomaly = body.get('anomaly', {})
        
        # Get related metrics from the same time window
        related_metrics = []
        
        # Query metrics from Victoria Metrics
        query = f'up{{cluster="{anomaly.get("cluster", "local-docker")}"}}[5m]'
        try:
            results = vm_client.custom_query(query=query)
            for result in results:
                metric = result.get('metric', {})
                value = result.get('value', [0, 0])[1]
                related_metrics.append({
                    'metric': metric.get('__name__', 'unknown'),
                    'service': metric.get('job', 'unknown'),
                    'value': float(value),
                    'timestamp': datetime.utcnow().isoformat()
                })
        except Exception as e:
            logger.warning(f"Could not fetch related metrics: {e}")
        
        # Perform root cause analysis
        rca = ai_agent.perform_root_cause_analysis(anomaly, related_metrics)
        
        return rca
        
    except Exception as e:
        logger.error(f"Error in root cause analysis: {e}")
        return {
            'error': str(e),
            'anomaly_id': 'unknown',
            'probable_causes': [],
            'recommendations': ['Unable to perform analysis - check logs']
        }


@app.get("/api/ai/trends")
async def get_anomaly_trends(hours: int = 24):
    """
    Get anomaly trends over time
    """
    api_requests.labels(endpoint='/api/ai/trends', method='GET').inc()
    
    try:
        trends = ai_agent.get_anomaly_trends(hours=hours)
        return trends
    except Exception as e:
        logger.error(f"Error getting trends: {e}")
        return {
            'trend': 'unknown',
            'error': str(e)
        }


@app.get("/api/ai/insights")
async def get_ai_insights():
    """
    Get AI-generated insights about fleet health
    """
    api_requests.labels(endpoint='/api/ai/insights', method='GET').inc()
    
    # Try cache first
    if redis_client:
        try:
            cached = redis_client.get('ai_analysis')
            if cached:
                analysis = json.loads(cached)
                return {
                    'insights': analysis.get('insights', []),
                    'health_score': analysis.get('overall_health_score', 60.0),
                    'anomaly_count': len(analysis.get('anomalies', [])),
                    'cached': True
                }
        except Exception:
            pass
    
    # Run fresh analysis
    analysis = await analyze_fleet_health()
    return {
        'insights': analysis.get('insights', []),
        'health_score': analysis.get('overall_health_score', 60.0),
        'anomaly_count': len(analysis.get('anomalies', [])),
        'cached': False
    }


@app.post("/api/ai/alert")
async def trigger_ai_alert(request: Request):
    """
    Trigger an alert based on AI detection
    Integrates with Alertmanager
    """
    api_requests.labels(endpoint='/api/ai/alert', method='POST').inc()
    
    try:
        body = await request.json()
        anomaly = body.get('anomaly', {})
        
        # Create alert payload
        alert = {
            'status': 'firing',
            'labels': {
                'alertname': 'AIAnomalyDetected',
                'severity': anomaly.get('severity', 'warning'),
                'service': anomaly.get('service', 'unknown'),
                'cluster': anomaly.get('cluster', 'unknown'),
                'source': 'ai_agent'
            },
            'annotations': {
                'summary': f"AI detected anomaly in {anomaly.get('service', 'service')}",
                'description': f"Anomaly score: {anomaly.get('anomaly_score', 0)}, Metric: {anomaly.get('metric', 'unknown')}",
                'ai_insight': 'Automated anomaly detection triggered this alert'
            },
            'startsAt': datetime.utcnow().isoformat() + 'Z',
            'generatorURL': 'http://visibility-api:8000/api/ai/analyze'
        }
        
        logger.info(f"AI Alert triggered: {alert}")
        
        # Store in cache for alert history
        if redis_client:
            try:
                alert_key = f"ai_alert:{datetime.utcnow().timestamp()}"
                redis_client.setex(alert_key, 3600, json.dumps(alert))
            except Exception as e:
                logger.warning(f"Could not cache alert: {e}")
        
        return {
            'success': True,
            'alert': alert,
            'message': 'AI alert triggered successfully'
        }
        
    except Exception as e:
        logger.error(f"Error triggering AI alert: {e}")
        return {
            'success': False,
            'error': str(e)
        }


# ============================================================================
# Holmes AI Investigation Endpoints (Robusta HolmesGPT-compatible)
# ============================================================================

@app.post("/api/holmes/investigate")
async def holmes_investigate(request: Request):
    """
    Trigger a Holmes AI investigation for an alert/anomaly.
    Holmes queries Loki (logs) + VictoriaMetrics (metrics) + K8s context
    then produces a structured root cause analysis report.
    """
    api_requests.labels(endpoint='/api/holmes/investigate', method='POST').inc()
    try:
        body = await request.json()
        alert = body.get("alert", body)  # accept alert directly or wrapped
        investigation = await holmes.investigate(alert)
        return investigation.to_dict()
    except Exception as e:
        logger.error(f"Holmes investigation error: {e}")
        return {"status": "failed", "error": str(e)}


@app.get("/api/holmes/investigations")
async def list_holmes_investigations(limit: int = 20):
    """List all past Holmes investigations, newest first."""
    api_requests.labels(endpoint='/api/holmes/investigations', method='GET').inc()
    return {
        "investigations": holmes.list_all(limit=limit),
        "total": len(holmes.investigations),
    }


@app.get("/api/holmes/investigations/{inv_id}")
async def get_holmes_investigation(inv_id: str):
    """Get a specific Holmes investigation by ID."""
    api_requests.labels(endpoint='/api/holmes/investigations/id', method='GET').inc()
    inv = holmes.get(inv_id)
    if not inv:
        return {"error": f"Investigation {inv_id} not found"}
    return inv.to_dict()


# ============================================================================
# Robusta Event Processor & Playbook Endpoints
# ============================================================================

@app.post("/api/robusta/event")
async def robusta_receive_event(request: Request):
    """
    Receive a K8s event or Prometheus alert.
    Robusta routes it to matching playbooks, which trigger Holmes investigations,
    fetch logs from Loki, and enrich the alert with AI context.
    """
    api_requests.labels(endpoint='/api/robusta/event', method='POST').inc()
    try:
        event = await request.json()
        runs = await robusta.process_event(event)

        # Broadcast enriched alert to WebSocket clients
        if runs:
            best_run = runs[0]
            await manager.broadcast({
                "type": "robusta_playbook_run",
                "timestamp": datetime.now().isoformat(),
                "playbook": best_run.playbook_name,
                "investigation_id": best_run.investigation_id,
                "enrichment": best_run.enrichment,
                "status": best_run.status,
            })

        return {
            "status": "processed",
            "playbooks_triggered": len(runs),
            "runs": [r.to_dict() for r in runs],
        }
    except Exception as e:
        logger.error(f"Robusta event processing error: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/robusta/playbooks")
async def list_robusta_playbooks():
    """List all registered Robusta playbooks with trigger and action details."""
    api_requests.labels(endpoint='/api/robusta/playbooks', method='GET').inc()
    return {
        "playbooks": robusta.list_playbooks(),
        "total": len(robusta.playbooks),
    }


@app.get("/api/robusta/runs")
async def list_robusta_runs(limit: int = 30):
    """List recent Robusta playbook run history."""
    api_requests.labels(endpoint='/api/robusta/runs', method='GET').inc()
    return {
        "runs": robusta.list_runs(limit=limit),
        "total": len(robusta.runs),
    }


@app.get("/api/robusta/events")
async def list_robusta_events(limit: int = 50):
    """List recent events received by Robusta."""
    api_requests.labels(endpoint='/api/robusta/events', method='GET').inc()
    return {
        "events": robusta.list_events(limit=limit),
        "total": len(robusta.events),
    }


# Alertmanager → Robusta webhook (so Alertmanager alerts trigger playbooks)
@app.post("/webhook/robusta")
async def alertmanager_to_robusta(request: Request):
    """
    Alertmanager fires alerts here → Robusta processes them → Holmes investigates.
    Add this URL as a receiver in alertmanager-config.yml.
    """
    try:
        data = await request.json()
        alerts = data.get("alerts", [])
        all_runs = []
        for alert in alerts:
            event = {
                "alertname": alert.get("labels", {}).get("alertname", "Unknown"),
                "service":   alert.get("labels", {}).get("job", "unknown"),
                "cluster":   alert.get("labels", {}).get("cluster", "local-docker"),
                "severity":  alert.get("labels", {}).get("severity", "warning"),
                "description": alert.get("annotations", {}).get("description", ""),
                "status":    alert.get("status", "firing"),
                "source":    "alertmanager",
            }
            runs = await robusta.process_event(event)
            all_runs.extend(runs)
        return {"status": "processed", "alerts_received": len(alerts), "runs": len(all_runs)}
    except Exception as e:
        logger.error(f"Robusta webhook error: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# Jaeger Tracing Proxy Endpoints
# ============================================================================

JAEGER_URL = os.getenv("JAEGER_URL", "http://jaeger:16686")


@app.get("/api/traces/services")
async def get_trace_services():
    """List all services known to Jaeger"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{JAEGER_URL}/api/services")
            return resp.json()
    except Exception as e:
        logger.error(f"Jaeger services error: {e}")
        return {"data": [], "errors": [str(e)]}


@app.get("/api/traces")
async def get_traces(
    service: str = "visibility-api",
    limit: int = 20,
    lookback: str = "1h",
    operation: str = "",
):
    """Proxy Jaeger trace search — returns recent traces for a service"""
    try:
        params: dict = {"service": service, "limit": limit, "lookback": lookback}
        if operation:
            params["operation"] = operation
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{JAEGER_URL}/api/traces", params=params)
            return resp.json()
    except Exception as e:
        logger.error(f"Jaeger traces error: {e}")
        return {"data": [], "errors": [str(e)]}


@app.get("/api/traces/{trace_id}")
async def get_trace_detail(trace_id: str):
    """Fetch a single trace by ID from Jaeger"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{JAEGER_URL}/api/traces/{trace_id}")
            return resp.json()
    except Exception as e:
        logger.error(f"Jaeger trace detail error: {e}")
        return {"data": [], "errors": [str(e)]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
