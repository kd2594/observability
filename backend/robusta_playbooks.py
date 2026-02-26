"""
Robusta-Compatible Event Processor & Playbook Runner

Inspired by Robusta (https://robusta.dev).
Robusta routes Kubernetes events and alerts to playbooks, which execute
automated actions — including calling Holmes for AI root cause analysis.

Architecture:
  K8s Event / Alert
    → RobustaEventProcessor.process_event()
      → Trigger matching (find playbooks whose triggers match the event)
      → Execute playbook actions in order:
          - holmes_investigate → calls HolmesRCA
          - k8s_query          → simulated kubectl calls
          - notify             → enriched alert (Slack/PD in prod)
          - recommend          → generate scaling/remediation suggestions
      → PlaybookRun (structured execution record)
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from holmes_rca import holmes

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Playbook building blocks
# ─────────────────────────────────────────────────────────────────────────────

class PlaybookTrigger:
    """
    Defines when a playbook fires.
    Equivalent to Robusta's `on_prometheus_alert`, `on_pod_oom_killed`, etc.
    """

    def __init__(self, name: str, condition: Callable[[Dict[str, Any]], bool]):
        self.name = name
        self.condition = condition

    def matches(self, event: Dict[str, Any]) -> bool:
        try:
            return bool(self.condition(event))
        except Exception:
            return False


class PlaybookAction:
    """A single step in a playbook — mirrors Robusta action functions."""

    def __init__(self, name: str, description: str, action_type: str, params: Optional[Dict] = None):
        self.name = name
        self.description = description
        # action_type: investigate | k8s_query | notify | recommend | correlate | custom
        self.action_type = action_type
        self.params = params or {}


class Playbook:
    """
    A Robusta playbook — trigger conditions + ordered list of actions.

    Equivalent Robusta YAML:
    ```yaml
    triggers:
      - on_prometheus_alert:
          alert_name: HighCPUUsage
    actions:
      - holmes_ai_analysis: {}
      - send_slack_message:
          slack_channel: "#platform-alerts"
    ```
    """

    def __init__(
        self,
        name: str,
        description: str,
        triggers: List[PlaybookTrigger],
        actions: List[PlaybookAction],
        auto_remediate: bool = False,
        tags: Optional[List[str]] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.description = description
        self.triggers = triggers
        self.actions = actions
        self.auto_remediate = auto_remediate
        self.tags = tags or []
        self.run_count = 0
        self.last_run: Optional[datetime] = None
        self.created_at = datetime.utcnow()


# ─────────────────────────────────────────────────────────────────────────────
# Playbook execution record
# ─────────────────────────────────────────────────────────────────────────────

class PlaybookRun:
    """Execution record for a single playbook invocation."""

    def __init__(self, playbook: Playbook, event: Dict[str, Any]):
        self.id = str(uuid.uuid4())[:12]
        self.playbook_id = playbook.id
        self.playbook_name = playbook.name
        self.event = event
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self.status = "running"                   # running | success | failed
        self.actions_taken: List[Dict[str, Any]] = []
        self.investigation_id: Optional[str] = None
        self.enrichment: Dict[str, Any] = {}      # enriched alert context
        self.triggered_alerts: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "playbook_name": self.playbook_name,
            "event": self.event,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at
                else None
            ),
            "status": self.status,
            "actions_taken": self.actions_taken,
            "investigation_id": self.investigation_id,
            "enrichment": self.enrichment,
            "triggered_alerts": self.triggered_alerts,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Event processor (Robusta runner equivalent)
# ─────────────────────────────────────────────────────────────────────────────

class RobustaEventProcessor:
    """
    Receives K8s events / Prometheus alerts and routes them to matching playbooks.
    Mirrors Robusta's runner process.
    """

    def __init__(self):
        self.playbooks: List[Playbook] = []
        self.runs: List[PlaybookRun] = []
        self.events: List[Dict[str, Any]] = []
        self._register_defaults()

    # ── Built-in playbooks ───────────────────────────────────────────────────
    def _register_defaults(self):
        """Register Robusta-equivalent built-in playbooks."""

        # 1. Service down → Holmes investigation
        self.register(Playbook(
            name="on_service_down",
            description=(
                "When a service goes down: fetch recent logs from Loki, "
                "run Holmes AI root cause analysis, enrich the alert."
            ),
            triggers=[
                PlaybookTrigger(
                    "on_prometheus_alert:ServiceDown",
                    lambda e: (
                        e.get("alertname") in ("ServiceDown", "InstanceDown")
                        or e.get("name") in ("ServiceDown", "InstanceDown")
                        or e.get("status") == "down"
                    ),
                )
            ],
            actions=[
                PlaybookAction("holmes_ai_analysis",   "Run Holmes AI root cause analysis",     "investigate"),
                PlaybookAction("fetch_loki_logs",      "Fetch service logs from Loki",          "k8s_query",
                               {"log_minutes": 30}),
                PlaybookAction("send_enriched_alert",  "Enrich and route alert to Alertmanager","notify"),
            ],
            tags=["service-health", "loki", "holmes"],
        ))

        # 2. High CPU → Investigate + scale suggestion
        self.register(Playbook(
            name="on_high_cpu",
            description=(
                "Investigate high CPU events; suggest autoscaling. "
                "Mirrors Robusta `cpu_throttling_analysis` playbook."
            ),
            triggers=[
                PlaybookTrigger(
                    "on_prometheus_alert:HighCPUUsage",
                    lambda e: (
                        e.get("alertname") in ("HighCPUUsage", "CPUThrottling")
                        or ("cpu" in str(e.get("metric", "")).lower() and float(e.get("value", 0)) > 80)
                    ),
                )
            ],
            actions=[
                PlaybookAction("holmes_ai_analysis",   "Run Holmes AI root cause analysis", "investigate"),
                PlaybookAction("check_hpa",            "Query HPA status via kubectl",      "k8s_query"),
                PlaybookAction("scaling_recommendation","Emit scaling recommendation",       "recommend"),
            ],
            tags=["cpu", "scaling", "holmes"],
        ))

        # 3. OOMKill → Memory investigation + remediation
        self.register(Playbook(
            name="on_oom_kill",
            description=(
                "Handle OOMKill events: fetch crash logs, analyse memory growth, "
                "recommend limit increase. Auto-remediation available."
            ),
            triggers=[
                PlaybookTrigger(
                    "on_pod_oom_killed",
                    lambda e: (
                        "oom" in e.get("alertname", "").lower()
                        or "oom" in e.get("reason", "").lower()
                        or "memory" in e.get("metric", "").lower()
                        or e.get("last_state") == "OOMKilled"
                    ),
                )
            ],
            actions=[
                PlaybookAction("holmes_ai_analysis",  "Run Holmes AI root cause analysis",      "investigate"),
                PlaybookAction("fetch_crash_logs",    "Fetch crash logs from Loki (pre-kill)",  "k8s_query",
                               {"log_minutes": 60}),
                PlaybookAction("memory_growth_analysis","Analyse memory growth trend in VM",    "correlate"),
            ],
            auto_remediate=True,
            tags=["oom", "memory", "loki", "holmes"],
        ))

        # 4. AI anomaly → Fleet-wide investigation
        self.register(Playbook(
            name="on_ai_anomaly",
            description=(
                "When the AI observability agent detects a fleet-wide anomaly, "
                "run Holmes investigation and correlate across all affected services."
            ),
            triggers=[
                PlaybookTrigger(
                    "on_ai_anomaly_detected",
                    lambda e: (
                        e.get("source") == "ai_agent"
                        or e.get("alertname") == "AIAnomalyDetected"
                    ),
                )
            ],
            actions=[
                PlaybookAction("holmes_ai_analysis",       "Run Holmes AI root cause analysis",          "investigate"),
                PlaybookAction("cross_service_correlation","Correlate anomalies across services",         "correlate"),
                PlaybookAction("notify_on_call",           "Send enriched report to on-call channel",    "notify"),
            ],
            tags=["ai", "fleet", "holmes"],
        ))

        # 5. Critical catch-all
        self.register(Playbook(
            name="on_critical_alert",
            description=(
                "For any critical severity alert: immediate Holmes investigation, "
                "create incident, notify on-call."
            ),
            triggers=[
                PlaybookTrigger(
                    "on_prometheus_alert:severity=critical",
                    lambda e: e.get("severity") == "critical",
                )
            ],
            actions=[
                PlaybookAction("holmes_ai_analysis", "Run Holmes AI root cause analysis", "investigate"),
                PlaybookAction("create_incident",    "Create incident (PagerDuty/Jira)",  "notify"),
            ],
            tags=["critical", "incident", "holmes"],
        ))

        # 6. Scrape failure → infra check
        self.register(Playbook(
            name="on_scrape_failure",
            description=(
                "When VictoriaMetrics agent reports scrape failures, "
                "check network connectivity and service health."
            ),
            triggers=[
                PlaybookTrigger(
                    "on_prometheus_alert:HighScrapeFailureRate",
                    lambda e: e.get("alertname") in ("HighScrapeFailureRate", "ScrapeFailed"),
                )
            ],
            actions=[
                PlaybookAction("network_check",  "Verify network connectivity to targets", "k8s_query"),
                PlaybookAction("holmes_ai_analysis", "Run Holmes AI root cause analysis", "investigate"),
            ],
            tags=["metrics", "vmagent", "networking"],
        ))

    def register(self, playbook: Playbook):
        self.playbooks.append(playbook)
        logger.info(f"[Robusta] Registered playbook: {playbook.name}")

    # ── Main event router ────────────────────────────────────────────────────
    async def process_event(self, event: Dict[str, Any]) -> List[PlaybookRun]:
        """
        Route an incoming event to all matching playbooks and execute them.

        Args:
            event: dict representing a K8s event or Prometheus alert.
                   Keys: alertname, service, cluster, severity, metric, value, etc.

        Returns:
            List of PlaybookRun records (one per matched playbook)
        """
        event.setdefault("received_at", datetime.utcnow().isoformat())
        event.setdefault("id", str(uuid.uuid4())[:8])
        self.events.append(event)

        alert_name = event.get("alertname", event.get("name", "unknown"))
        logger.info(f"[Robusta] Processing event: {alert_name}")

        matching = [pb for pb in self.playbooks if any(t.matches(event) for t in pb.triggers)]
        if not matching:
            logger.info(f"[Robusta] No playbooks matched for event: {alert_name}")
            return []

        runs = []
        for pb in matching:
            run = await self._run_playbook(pb, event)
            runs.append(run)
            self.runs.append(run)

        return runs

    async def _run_playbook(self, playbook: Playbook, event: Dict[str, Any]) -> PlaybookRun:
        run = PlaybookRun(playbook, event)
        playbook.run_count += 1
        playbook.last_run = datetime.utcnow()
        logger.info(f"[Robusta] Executing playbook '{playbook.name}' → run {run.id}")

        try:
            for action in playbook.actions:
                result = await self._execute_action(action, event, run)
                run.actions_taken.append(
                    {
                        "action": action.name,
                        "type": action.action_type,
                        "description": action.description,
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
            run.status = "success"

        except Exception as e:
            logger.error(f"[Robusta] Playbook '{playbook.name}' failed: {e}")
            run.status = "failed"
            run.actions_taken.append(
                {
                    "action": "error",
                    "type": "error",
                    "description": str(e),
                    "result": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

        run.completed_at = datetime.utcnow()
        logger.info(
            f"[Robusta] Playbook '{playbook.name}' → {run.status} "
            f"({(run.completed_at - run.started_at).total_seconds():.1f}s)"
        )
        return run

    async def _execute_action(
        self, action: PlaybookAction, event: Dict[str, Any], run: PlaybookRun
    ) -> str:
        """Execute one playbook action."""

        if action.action_type == "investigate":
            # Holmes investigation
            alert_for_holmes = {
                "service":     event.get("service", event.get("job", "unknown")),
                "cluster":     event.get("cluster", "local-docker"),
                "alertname":   event.get("alertname", event.get("name", "UnknownAlert")),
                "severity":    event.get("severity", "warning"),
                "description": event.get("description", event.get("summary", "")),
                "metric":      event.get("metric", ""),
                "value":       event.get("value", 0),
            }
            investigation = await holmes.investigate(alert_for_holmes)
            run.investigation_id = investigation.id
            run.enrichment["holmes_summary"]  = investigation.ai_summary
            run.enrichment["root_cause"]      = investigation.root_cause
            run.enrichment["findings"]        = investigation.findings
            run.enrichment["confidence"]      = investigation.confidence
            return (
                f"Holmes investigation {investigation.id} complete "
                f"(confidence: {investigation.confidence}): {investigation.root_cause[:80]}…"
            )

        elif action.action_type == "k8s_query":
            minutes = action.params.get("log_minutes", 30)
            return (
                f"Queried kubectl/Loki — fetched last {minutes}min of logs and pod describe output. "
                f"See investigation {run.investigation_id} for full log evidence."
            )

        elif action.action_type == "notify":
            root_cause = run.enrichment.get("root_cause", "See investigation for details")
            return (
                f"[Robusta] Alert enriched with AI context and dispatched. "
                f"Root cause summary: {root_cause[:100]}"
            )

        elif action.action_type == "recommend":
            return (
                "Scaling recommendation: current replicas=1, desired=3 (CPU threshold breached). "
                "Apply: `kubectl scale deploy <service> --replicas=3` "
                "or enable HPA: `kubectl autoscale deploy <service> --cpu-percent=70 --min=2 --max=10`"
            )

        elif action.action_type == "correlate":
            return (
                "Cross-service correlation complete: anomaly pattern detected in 2 services within "
                "the same cluster. Memory growth is linear (not bursty) — suggests memory leak, "
                "not sudden load spike."
            )

        else:
            return f"Action '{action.name}' executed successfully"

    # ── Accessors ────────────────────────────────────────────────────────────
    def list_playbooks(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": pb.id,
                "name": pb.name,
                "description": pb.description,
                "triggers": [t.name for t in pb.triggers],
                "actions": [{"name": a.name, "type": a.action_type} for a in pb.actions],
                "auto_remediate": pb.auto_remediate,
                "tags": pb.tags,
                "run_count": pb.run_count,
                "last_run": pb.last_run.isoformat() if pb.last_run else None,
                "created_at": pb.created_at.isoformat(),
            }
            for pb in self.playbooks
        ]

    def list_runs(self, limit: int = 30) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in sorted(self.runs, key=lambda r: r.started_at, reverse=True)[:limit]]

    def list_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self.events[-limit:]))


# ── Singleton ────────────────────────────────────────────────────────────────
robusta = RobustaEventProcessor()
