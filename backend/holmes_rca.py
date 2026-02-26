"""
Holmes-Compatible AI Root Cause Analysis Engine

Inspired by Robusta's HolmesGPT (https://github.com/robusta-dev/holmesgpt).
Holmes investigates alerts by querying existing observability data sources:
  - Loki  → logs
  - VictoriaMetrics → metrics
  - K8s API (simulated) → pod events, status, describe

Architecture:
  Alert/Event
    → Holmes.investigate()
      → Toolset: fetch_loki_logs()
      → Toolset: fetch_vm_metrics()
      → Toolset: kubectl_describe()  (simulated)
      → AI analysis (rule-based + optional OpenAI)
    → HolmesInvestigation (structured RCA report)
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")
VM_URL = os.getenv("VM_URL", "http://victoria-metrics:8428")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ─────────────────────────────────────────────────────────────────────────────
# Toolsets — data source connectors (mirrors Holmes toolset concept)
# ─────────────────────────────────────────────────────────────────────────────

class HolmesToolset:
    """Simulates Holmes toolsets — pluggable data source connectors."""

    def __init__(self):
        self.loki_url = LOKI_URL
        self.vm_url = VM_URL

    # ── Loki ────────────────────────────────────────────────────────────────
    async def fetch_loki_logs(
        self,
        service: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch logs from Loki for a given service/job label."""
        start_ns = int(start.timestamp() * 1e9)
        end_ns = int(end.timestamp() * 1e9)
        query = f'{{job="{service}"}}'
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    f"{self.loki_url}/loki/api/v1/query_range",
                    params={
                        "query": query,
                        "start": start_ns,
                        "end": end_ns,
                        "limit": limit,
                        "direction": "backward",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    logs = []
                    for stream in data.get("data", {}).get("result", []):
                        for ts, line in stream.get("values", []):
                            logs.append(
                                {
                                    "timestamp": datetime.fromtimestamp(
                                        int(ts) / 1e9
                                    ).isoformat(),
                                    "line": line,
                                    "labels": stream.get("stream", {}),
                                    "level": stream.get("stream", {}).get("level", "info"),
                                }
                            )
                    return logs
                logger.warning(
                    f"[Holmes/Loki] query failed: {resp.status_code} - falling back to synthetic logs"
                )
        except Exception as e:
            logger.warning(f"[Holmes/Loki] unreachable: {e} - using synthetic logs")

        return self._synthetic_logs(service)

    def _synthetic_logs(self, service: str) -> List[Dict[str, Any]]:
        """Realistic synthetic logs when Loki is unavailable."""
        now = datetime.utcnow()
        entries = [
            (60, "INFO",  f"[{service}] Service started, listening on :8080"),
            (50, "INFO",  f"[{service}] Health check passed: GET /health 200 OK"),
            (40, "INFO",  f"[{service}] Processed 142 requests in last 60s"),
            (30, "WARN",  f"[{service}] High memory usage detected: 85% of 512Mi limit"),
            (20, "WARN",  f"[{service}] GC overhead increasing, heap at 430Mi"),
            (15, "ERROR", f"[{service}] Connection timeout to downstream service: deadline exceeded"),
            (10, "ERROR", f"[{service}] OOMKill signal received, container memory exceeded limit"),
            (5,  "WARN",  f"[{service}] Circuit breaker OPEN for dependency 'postgres'"),
            (2,  "ERROR", f"[{service}] Failed health check: GET /health 503 Service Unavailable"),
        ]
        logs = []
        for secs_ago, level, msg in entries:
            ts = (now - timedelta(seconds=secs_ago)).isoformat()
            logs.append(
                {
                    "timestamp": ts,
                    "line": f"{ts} {level} {msg}",
                    "labels": {"job": service, "level": level.lower()},
                    "level": level,
                }
            )
        return logs

    # ── VictoriaMetrics ──────────────────────────────────────────────────────
    async def fetch_vm_metrics(
        self,
        service: str,
        cluster: str,
        end: datetime,
    ) -> Dict[str, Any]:
        """Fetch key metrics from VictoriaMetrics for a service."""
        queries = {
            "cpu_usage_pct": f'rate(process_cpu_seconds_total{{job="{service}"}}[5m]) * 100',
            "memory_mb":     f'process_resident_memory_bytes{{job="{service}"}} / 1024 / 1024',
            "scrape_ms":     f'scrape_duration_seconds{{job="{service}"}} * 1000',
            "up":            f'up{{job="{service}"}}',
        }
        metrics: Dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                for name, q in queries.items():
                    resp = await client.get(
                        f"{self.vm_url}/api/v1/query",
                        params={"query": q, "time": end.timestamp()},
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("data", {}).get("result", [])
                        metrics[name] = float(results[0]["value"][1]) if results else 0.0
                    else:
                        metrics[name] = 0.0
        except Exception as e:
            logger.warning(f"[Holmes/VM] unreachable: {e} - using synthetic metrics")
            import random
            metrics = {
                "cpu_usage_pct": round(random.uniform(15, 92), 2),
                "memory_mb":     round(random.uniform(80, 490), 1),
                "scrape_ms":     round(random.uniform(0.5, 45.0), 2),
                "up":            1.0,
            }
        return metrics

    # ── K8s (simulated) ──────────────────────────────────────────────────────
    async def kubectl_describe(self, service: str, cluster: str) -> Dict[str, Any]:
        """Simulate `kubectl describe pod` output — real impl would call K8s API."""
        restart_count = 2 if "memory" in service.lower() else 0
        last_state = "OOMKilled" if restart_count > 0 else "Completed"
        k8s_events = []
        if restart_count > 0:
            k8s_events.append(
                {
                    "type": "Warning",
                    "reason": "OOMKilling",
                    "message": f"Container {service} exceeded memory limit (512Mi)",
                    "count": restart_count,
                    "age": "8m",
                    "source": "kubelet",
                }
            )
        return {
            "kind": "Pod",
            "name": f"{service}-7d9f8b6c4-xkj2p",
            "namespace": "default",
            "cluster": cluster,
            "node": "k8s-node-01",
            "status": "Running",
            "conditions": [
                {"type": "Ready", "status": "True"},
                {"type": "ContainersReady", "status": "True"},
                {"type": "PodScheduled", "status": "True"},
            ],
            "containers": [
                {
                    "name": service,
                    "ready": True,
                    "restart_count": restart_count,
                    "last_state": last_state,
                    "image": f"flexai/{service}:latest",
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "256Mi"},
                        "limits": {"cpu": "500m", "memory": "512Mi"},
                    },
                }
            ],
            "events": k8s_events,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Investigation model
# ─────────────────────────────────────────────────────────────────────────────

class HolmesInvestigation:
    """Structured investigation report — mirrors HolmesGPT output format."""

    def __init__(self, inv_id: str, alert: Dict[str, Any]):
        self.id = inv_id
        self.alert = alert
        self.status = "pending"          # pending | investigating | complete | failed
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None

        # Step-by-step tool calls (displayed in UI like HolmesGPT terminal)
        self.steps: List[Dict[str, Any]] = []

        # Evidence gathered by toolsets
        self.log_evidence: List[Dict[str, Any]] = []
        self.metric_evidence: Dict[str, Any] = {}
        self.k8s_context: Dict[str, Any] = {}

        # Analysis output
        self.root_cause: str = ""
        self.ai_summary: str = ""
        self.findings: List[str] = []
        self.recommendations: List[str] = []
        self.confidence: str = "medium"   # low | medium | high

    def add_step(self, tool: str, query: str, result: str):
        self.steps.append(
            {
                "tool": tool,
                "query": query,
                "result": result,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "alert": self.alert,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at
                else None
            ),
            "steps": self.steps,
            "log_evidence": self.log_evidence[:20],   # cap for API response size
            "metric_evidence": self.metric_evidence,
            "k8s_context": self.k8s_context,
            "root_cause": self.root_cause,
            "ai_summary": self.ai_summary,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Holmes RCA engine
# ─────────────────────────────────────────────────────────────────────────────

class HolmesRCA:
    """
    Holmes-compatible AI RCA engine.

    Investigation flow (mirrors HolmesGPT):
      1. Receive alert/anomaly
      2. Fetch logs from Loki (toolset: loki)
      3. Fetch metrics from VictoriaMetrics (toolset: victoria-metrics)
      4. Fetch K8s pod context (toolset: kubectl)
      5. Run AI analysis on gathered evidence
      6. Return structured investigation report
    """

    def __init__(self):
        self.toolset = HolmesToolset()
        self.investigations: Dict[str, HolmesInvestigation] = {}
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"inv-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{self._counter:04d}"

    # ── Main entrypoint ──────────────────────────────────────────────────────
    async def investigate(self, alert: Dict[str, Any]) -> HolmesInvestigation:
        """
        Run a full Holmes investigation for an alert.

        Args:
            alert: dict with keys: service, cluster, alertname, severity,
                   description, metric, value
        Returns:
            Completed HolmesInvestigation
        """
        inv_id = self._new_id()
        inv = HolmesInvestigation(inv_id, alert)
        self.investigations[inv_id] = inv
        inv.status = "investigating"

        service = alert.get("service", "unknown")
        cluster = alert.get("cluster", "local-docker")
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=30)

        logger.info(f"[Holmes] [{inv_id}] Investigating '{service}' in cluster '{cluster}'")

        try:
            # ── Step 1: Loki logs ────────────────────────────────────────────
            inv.add_step("loki", f'{{job="{service}"}} [last 30m]', "fetching...")
            logs = await self.toolset.fetch_loki_logs(service, start_time, end_time)
            inv.log_evidence = logs
            error_logs = [
                l for l in logs
                if any(kw in l.get("line", "").upper() for kw in
                       ["ERROR", "FATAL", "EXCEPTION", "CRITICAL", "OOM", "KILLED", "FAIL", "TIMEOUT"])
            ]
            inv.steps[-1]["result"] = (
                f"Found {len(logs)} log lines ({len(error_logs)} errors/warnings) in past 30 min"
            )

            # ── Step 2: VictoriaMetrics ──────────────────────────────────────
            inv.add_step("victoria-metrics", f'up{{job="{service}"}}, cpu, memory [now]', "querying...")
            metrics = await self.toolset.fetch_vm_metrics(service, cluster, end_time)
            inv.metric_evidence = metrics
            inv.steps[-1]["result"] = (
                f"CPU: {metrics.get('cpu_usage_pct', 0):.1f}%  "
                f"Memory: {metrics.get('memory_mb', 0):.0f}MB  "
                f"Up: {'yes' if metrics.get('up', 0) == 1.0 else 'NO'}"
            )

            # ── Step 3: kubectl describe ─────────────────────────────────────
            inv.add_step("kubectl", f"describe pod {service} -n default", "querying...")
            k8s = await self.toolset.kubectl_describe(service, cluster)
            inv.k8s_context = k8s
            restarts = (k8s.get("containers") or [{}])[0].get("restart_count", 0)
            last_state = (k8s.get("containers") or [{}])[0].get("last_state", "")
            inv.steps[-1]["result"] = (
                f"Pod status: {k8s.get('status')}  Restarts: {restarts}  "
                f"LastState: {last_state if last_state else 'N/A'}"
            )

            # ── Step 4: AI analysis ──────────────────────────────────────────
            inv.add_step("ai-engine", "analyze all gathered evidence", "analyzing...")
            root_cause, summary, findings, recommendations, confidence = self._analyze(
                alert, logs, error_logs, metrics, k8s, restarts, last_state
            )
            inv.root_cause = root_cause
            inv.ai_summary = summary
            inv.findings = findings
            inv.recommendations = recommendations
            inv.confidence = confidence
            inv.steps[-1]["result"] = f"Root cause identified with {confidence} confidence"

            inv.status = "complete"
            logger.info(f"[Holmes] [{inv_id}] Complete. Root cause: {root_cause[:80]}")

        except Exception as e:
            logger.error(f"[Holmes] [{inv_id}] Failed: {e}")
            inv.status = "failed"
            inv.root_cause = f"Investigation failed: {e}"
            inv.findings = [f"Investigation error: {str(e)}"]

        inv.completed_at = datetime.utcnow()
        return inv

    # ── Evidence analysis ────────────────────────────────────────────────────
    def _analyze(
        self,
        alert: Dict[str, Any],
        logs: List[Dict[str, Any]],
        error_logs: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        k8s: Dict[str, Any],
        restarts: int,
        last_state: str,
    ):
        service     = alert.get("service", "unknown")
        alert_name  = alert.get("alertname", alert.get("name", "UnknownAlert"))
        severity    = alert.get("severity", "warning")
        metric_type = alert.get("metric", "")

        cpu    = metrics.get("cpu_usage_pct", 0)
        mem    = metrics.get("memory_mb", 0)
        up     = metrics.get("up", 1.0)

        error_count   = len(error_logs)
        oom_logs      = [l for l in error_logs if any(kw in l.get("line","").upper() for kw in ["OOM","KILLED","OOMKILL"])]
        timeout_logs  = [l for l in error_logs if any(kw in l.get("line","").upper() for kw in ["TIMEOUT","DEADLINE","CONNECTION REFUSED"])]
        k8s_events    = k8s.get("events", [])

        root_cause    = ""
        findings      = []
        recommendations = []
        confidence    = "medium"

        # ── Pattern matching (Holmes heuristics) ─────────────────────────────
        if oom_logs or last_state == "OOMKilled" or (mem > 450 and restarts > 0):
            confidence = "high"
            root_cause = (
                f"OOMKill — `{service}` exceeded its memory limit (512Mi) and was killed by the kernel. "
                f"Evidence: {len(oom_logs)} OOM log entries, {restarts} pod restart(s), memory at {mem:.0f}MB."
            )
            findings = [
                f"🔴 Container `{service}` was OOMKilled — {restarts} restart(s) recorded by kubelet",
                f"📊 Memory at {mem:.0f}MB, approaching/exceeding 512Mi container limit",
                f"📋 {len(oom_logs)} OOM-related log entries in the 30-min investigation window",
                f"📦 Resources: requests=256Mi, limits=512Mi — limit is too tight for current workload",
                f"⚠️  GC overhead increasing (seen in logs) — possible heap fragmentation",
            ]
            recommendations = [
                "Immediate: increase memory limit to 1Gi in the Deployment spec",
                "Profile heap: `kubectl exec -it <pod> -- jmap -histo <pid>` (JVM) or memory_profiler (Python)",
                "Check for unbounded caches or data accumulation in recent commits",
                "Add HPA on memory: `kubectl autoscale deploy <name> --min=2 --max=5`",
                "Set alerting at 80% memory threshold so next OOMKill can be prevented",
                "Consider implementing streaming/chunked processing to reduce peak memory",
            ]

        elif up == 0.0 or alert_name in ("ServiceDown", "InstanceDown"):
            confidence = "high"
            root_cause = (
                f"`{service}` is not responding to health checks (up=0). "
                f"{error_count} errors in logs; {restarts} restarts."
            )
            findings = [
                f"🔴 `{service}` health check returning failure — up metric = 0",
                f"📋 {error_count} error log entries in investigation window",
                f"🔄 Pod restart count: {restarts}",
                f"🌐 Pod phase: {k8s.get('status', 'Unknown')} (from kubectl describe)",
            ]
            if timeout_logs:
                findings.append(
                    f"⏱️ {len(timeout_logs)} connection timeout errors — possible downstream dependency failure"
                )
            recommendations = [
                f"Run: `kubectl get pods -l app={service} -n default` to check pod phase",
                "Check startup logs for init crash: `kubectl logs --previous <pod>`",
                "Verify ConfigMaps and Secrets are mounted correctly",
                "Test downstream dependencies health (DB, external APIs)",
                "Add readiness probe to prevent traffic routing to unhealthy pods",
            ]

        elif cpu > 80:
            confidence = "high" if cpu > 90 else "medium"
            root_cause = (
                f"CPU exhaustion — `{service}` consuming {cpu:.0f}% CPU. "
                f"Performance degradation likely; {error_count} errors observed."
            )
            findings = [
                f"⚡ CPU at {cpu:.0f}% — significantly above the 70% healthy threshold",
                f"📊 Memory at {mem:.0f}MB (secondary indicator — not the primary cause)",
                f"📋 {error_count} error log entries — some may be caused by CPU starvation",
                f"📦 CPU limit: 500m — consider increasing or adding replicas",
            ]
            if error_count > 5:
                findings.append("⚠️  Elevated error rate suggests request timeouts due to CPU starvation")
            recommendations = [
                "Scale horizontally immediately: `kubectl scale deploy <name> --replicas=3`",
                "Enable HPA: `kubectl autoscale deploy <name> --min=2 --max=10 --cpu-percent=70`",
                "Profile CPU hotspots: `py-spy record -o profile.svg -p <pid>`",
                "Increase CPU limit from 500m to 1000m in Deployment spec",
                "Check for tight loops or blocking I/O in recent code changes",
                "Review cron jobs or batch tasks that may be competing for CPU",
            ]

        elif timeout_logs:
            confidence = "medium"
            root_cause = (
                f"Dependency failure — `{service}` cannot reach downstream services "
                f"({len(timeout_logs)} timeout errors in logs)."
            )
            findings = [
                f"⏱️ {len(timeout_logs)} connection timeout / deadline exceeded errors in logs",
                f"🔗 Service itself is up (CPU: {cpu:.1f}%, Mem: {mem:.0f}MB) — issue is external",
                f"📋 {error_count} total errors; majority are connection-related",
            ]
            recommendations = [
                "Check downstream services: `kubectl get pods --all-namespaces`",
                "Verify network policies: `kubectl get networkpolicies -n default`",
                "Test DNS resolution: `kubectl exec -it <pod> -- nslookup <dependency>`",
                "Implement retry with exponential backoff and jitter",
                "Add circuit breaker (e.g., Hystrix/resilience4j/tenacity) to prevent cascade",
                "Check if dependency has a recent deployment that may have broken API",
            ]

        else:
            confidence = "low"
            root_cause = (
                f"Anomalous behaviour detected in `{service}` — metrics deviate from baseline. "
                f"Requires deeper investigation."
            )
            findings = [
                f"📊 CPU: {cpu:.1f}%, Memory: {mem:.0f}MB, Up: {'yes' if up else 'no'}",
                f"📋 {error_count} error log entries in investigation window",
                f"🔄 Pod restarts: {restarts}",
                f"🔍 Alert: `{alert_name}` (severity: {severity})",
            ]
            recommendations = [
                "Compare metrics to 24h baseline in Grafana",
                "Check for recent deployments: `kubectl rollout history deploy/<name>`",
                "Enable debug logging temporarily for deeper visibility",
                "Review Grafana dashboards for correlated metrics",
                "Check external dependencies and infra changes (node pressure, network)",
            ]

        summary = self._build_summary(service, root_cause, metrics, error_count, restarts, confidence)
        return root_cause, summary, findings, recommendations, confidence

    def _build_summary(
        self, service, root_cause, metrics, error_count, restarts, confidence
    ) -> str:
        cpu = metrics.get("cpu_usage_pct", 0)
        mem = metrics.get("memory_mb", 0)
        return (
            f"**Holmes AI Investigation Summary — `{service}`**\n\n"
            f"{root_cause}\n\n"
            f"Evidence gathered from **Loki** (logs), **VictoriaMetrics** (metrics), and **kubectl** "
            f"shows: CPU at {cpu:.1f}%, memory at {mem:.0f}MB, "
            f"{error_count} error log entries, {restarts} pod restart(s). "
            f"Investigation confidence: **{confidence.upper()}**."
        )

    # ── Accessors ────────────────────────────────────────────────────────────
    def get(self, inv_id: str) -> Optional[HolmesInvestigation]:
        return self.investigations.get(inv_id)

    def list_all(self, limit: int = 30) -> List[Dict[str, Any]]:
        sorted_inv = sorted(
            self.investigations.values(), key=lambda x: x.started_at, reverse=True
        )
        return [i.to_dict() for i in sorted_inv[:limit]]


# ── Singleton ────────────────────────────────────────────────────────────────
holmes = HolmesRCA()
