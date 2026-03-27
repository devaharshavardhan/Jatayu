from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

from app.services import dataset_service, publish_service, kafka_view_service

router = APIRouter()

# In-memory remediation approval store
_approval_store: dict = {}

_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "registry" / "service_registry.json"
_GRAPH_PATH = Path(__file__).resolve().parent.parent.parent / "dependency_graph.json"


# --- Dataset / Snapshot endpoints --------------------------------------------

@router.get("/scenarios")
def get_scenarios():
    return {"scenarios": dataset_service.list_scenarios()}


@router.get("/runs/{scenario}")
def get_runs(scenario: str):
    return {"runs": dataset_service.list_runs(scenario)}


@router.get("/snapshots/{scenario}/{run_id}")
def get_snapshots(scenario: str, run_id: str):
    return {"snapshots": dataset_service.list_snapshots(scenario, run_id)}


@router.get("/snapshot/{scenario}/{run_id}/{snapshot_id}")
def get_snapshot_files(scenario: str, run_id: str, snapshot_id: str):
    data = dataset_service.load_snapshot_files(scenario, run_id, snapshot_id)
    return {"data": data}


# --- Publish endpoints -------------------------------------------------------

@router.post("/publish/snapshot")
def publish_snapshot_endpoint(payload: dict = Body(...)):
    scenario = payload.get("scenario")
    run_id = payload.get("run_id")
    snapshot_id = payload.get("snapshot_id")
    if not (scenario and run_id and snapshot_id):
        raise HTTPException(status_code=400, detail="scenario, run_id, snapshot_id required")
    snap_path = dataset_service.snapshot_path(scenario, run_id, snapshot_id)
    summary = publish_service.publish_snapshot_dir(snap_path)
    return {"summary": summary}


@router.post("/publish/next")
def publish_next_endpoint(payload: dict = Body(...)):
    scenario = payload.get("scenario")
    run_id = payload.get("run_id")
    current_snapshot_id = payload.get("current_snapshot_id")
    snapshots = dataset_service.list_snapshots(scenario, run_id)
    if current_snapshot_id and current_snapshot_id in snapshots:
        idx = snapshots.index(current_snapshot_id) + 1
    else:
        idx = 0
    if idx >= len(snapshots):
        return {"summary": {}, "next_snapshot": None, "message": "No more snapshots"}
    next_snapshot = snapshots[idx]
    snap_path = dataset_service.snapshot_path(scenario, run_id, next_snapshot)
    summary = publish_service.publish_snapshot_dir(snap_path)
    return {"summary": summary, "next_snapshot": next_snapshot}


@router.post("/publish/all")
def publish_all_endpoint(payload: dict = Body(...)):
    scenario = payload.get("scenario")
    run_id = payload.get("run_id")
    if not (scenario and run_id):
        raise HTTPException(status_code=400, detail="scenario and run_id required")
    run_path = Path(dataset_service.snapshot_path(scenario, run_id, "")).parent
    summary = publish_service.publish_run_snapshots(run_path)
    return {"summary": summary}


# --- Kafka inspector ---------------------------------------------------------

@router.get("/topic/{topic_name}")
def topic_messages(topic_name: str, max_messages: int = 20):
    result = kafka_view_service.get_recent_messages(topic_name, max_messages=max_messages)
    return result


# --- Dashboard state (legacy + extended) -------------------------------------

@router.get("/dashboard/state")
def dashboard_state(
    scenario: Optional[str] = None,
    run_id: Optional[str] = None,
    snapshot_id: Optional[str] = None,
):
    alerts = kafka_view_service.get_recent_messages("jatayu.agent.monitoring.alerts", 20)
    risks = kafka_view_service.get_recent_messages("jatayu.agent.prediction.risks", 20)
    features = kafka_view_service.get_recent_messages("jatayu.telemetry.service_features", 10)
    health = kafka_view_service.get_recent_messages("jatayu.telemetry.service_health", 10)
    return {
        "scenario": scenario,
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "alerts": alerts,
        "risks": risks,
        "features": features,
        "health": health,
    }


# --- Full Pipeline State -----------------------------------------------------

@router.get("/pipeline/state")
def pipeline_state():
    """Return the latest messages from every agent topic for the pipeline view."""
    return {
        "ingestion": kafka_view_service.get_recent_messages("jatayu.snapshot.context", 5),
        "telemetry_health": kafka_view_service.get_recent_messages("jatayu.telemetry.service_health", 10),
        "telemetry_features": kafka_view_service.get_recent_messages("jatayu.telemetry.service_features", 10),
        "monitoring_alerts": kafka_view_service.get_recent_messages("jatayu.agent.monitoring.alerts", 10),
        "monitoring_incidents": kafka_view_service.get_recent_messages("jatayu.agent.monitoring.incidents", 10),
        "prediction_risks": kafka_view_service.get_recent_messages("jatayu.agent.prediction.risks", 10),
        "rca_results": kafka_view_service.get_recent_messages("jatayu.agent.rca.results", 5),
        "decision_intents": kafka_view_service.get_recent_messages("jatayu.agent.decision.intents", 5),
        "remediation_results": kafka_view_service.get_recent_messages("jatayu.agent.remediation.results", 5),
        "incidents": kafka_view_service.get_recent_messages("jatayu.agent.reporting.incidents", 5),
    }


# --- Agent-specific endpoints ------------------------------------------------

@router.get("/rca/results")
def get_rca_results(max: int = 10):
    return kafka_view_service.get_recent_messages("jatayu.agent.rca.results", max)


@router.get("/decisions")
def get_decisions(max: int = 10):
    return kafka_view_service.get_recent_messages("jatayu.agent.decision.intents", max)


@router.get("/remediation")
def get_remediation(max: int = 10):
    return kafka_view_service.get_recent_messages("jatayu.agent.remediation.results", max)


@router.get("/incidents")
def get_incidents(max: int = 10):
    return kafka_view_service.get_recent_messages("jatayu.agent.reporting.incidents", max)


@router.get("/incidents/monitoring")
def get_monitoring_incidents(max: int = 20):
    """Get rich incidents with 5 telemetry snapshots from monitoring agent."""
    return kafka_view_service.get_recent_messages("jatayu.agent.monitoring.incidents", max)


# --- Service Registry --------------------------------------------------------

@router.get("/registry")
def get_registry():
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Service registry not found")


@router.get("/registry/{service_name}")
def get_service_entry(service_name: str):
    try:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
        svc = registry.get("services", {}).get(service_name)
        if not svc:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not in registry")
        return {"service": service_name, "metadata": svc}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Service registry not found")


# --- Dependency Graph --------------------------------------------------------

@router.get("/graph")
def get_dependency_graph():
    try:
        with open(_GRAPH_PATH, "r", encoding="utf-8") as f:
            graph = json.load(f)
        return {"graph": graph}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dependency graph not found")


# --- Metrics Time Series (for charts) ----------------------------------------

@router.get("/metrics/timeseries")
def get_metrics_timeseries(scenario: str, run_id: str):
    """Return per-snapshot time-series metrics for chart visualization."""
    snapshots = dataset_service.list_snapshots(scenario, run_id)
    if not snapshots:
        return {"labels": [], "cpu": {}, "memory": {}, "error_rate": {}, "latency": {}, "services": []}

    tracked_services = [
        "frontend", "cartservice", "checkoutservice", "recommendationservice",
        "productcatalogservice", "paymentservice", "shippingservice",
        "emailservice", "currencyservice", "adservice", "redis-cart",
    ]

    labels = []
    cpu_data: dict = {s: [] for s in tracked_services}
    memory_data: dict = {s: [] for s in tracked_services}
    error_rate_data: dict = {s: [] for s in tracked_services}
    latency_data: dict = {s: [] for s in tracked_services}
    restart_data: dict = {s: [] for s in tracked_services}

    for snap_id in snapshots:
        data = dataset_service.load_snapshot_files(scenario, run_id, snap_id)
        metrics_list = data.get("pod_metrics.json") or []
        features_list = data.get("service_features.json") or []

        metrics_map = {m["service"]: m for m in (metrics_list if isinstance(metrics_list, list) else []) if isinstance(m, dict)}
        features_map = {f["service"]: f for f in (features_list if isinstance(features_list, list) else []) if isinstance(f, dict)}

        labels.append(snap_id)

        for svc in tracked_services:
            m = metrics_map.get(svc, {})
            f = features_map.get(svc, {})
            cpu_data[svc].append(m.get("cpu_millicores") or f.get("cpu_millicores") or 0)
            memory_data[svc].append(m.get("memory_mib") or f.get("memory_mib") or 0)
            error_rate_data[svc].append(f.get("http_error_count") or 0)
            lat = f.get("avg_latency_ms")
            latency_data[svc].append(lat if lat is not None else 0)
            restart_data[svc].append(f.get("restart_count") or 0)

    return {
        "labels": labels,
        "cpu": cpu_data,
        "memory": memory_data,
        "error_rate": error_rate_data,
        "latency": latency_data,
        "restarts": restart_data,
        "services": tracked_services,
    }


# --- Remediation Approval Panel -----------------------------------------------

@router.post("/remediation/approve")
def approve_remediation(payload: dict = Body(...)):
    """Accept or reject a pending remediation action."""
    incident_id = payload.get("incident_id")
    action = payload.get("action")
    approved = bool(payload.get("approved", False))
    reason = payload.get("reason", "")

    if not incident_id or not action:
        raise HTTPException(status_code=400, detail="incident_id and action are required")

    _approval_store[incident_id] = {
        "incident_id": incident_id,
        "action": action,
        "approved": approved,
        "reason": reason,
        "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "approved" if approved else "rejected",
    }

    return {
        "status": "approved" if approved else "rejected",
        "incident_id": incident_id,
        "action": action,
        "message": f"Remediation '{action}' {'approved' if approved else 'rejected'} for {incident_id}",
    }


@router.get("/remediation/approvals")
def get_remediation_approvals():
    """Get all remediation approval decisions."""
    return {"approvals": list(_approval_store.values())}


# --- Incident Snapshot Detail ------------------------------------------------

@router.get("/incidents/snapshots")
def get_incident_snapshots_for_run(scenario: str, run_id: str):
    """Get all 5 snapshots for a run, formatted as incident snapshot data."""
    snapshots = dataset_service.list_snapshots(scenario, run_id)
    result = []
    for snap_id in snapshots[:5]:
        data = dataset_service.load_snapshot_files(scenario, run_id, snap_id)
        metrics = data.get("pod_metrics.json") or []
        health = data.get("service_health.json") or []
        events = data.get("k8s_events.json") or []
        logs = data.get("log_events.json") or []
        result.append({
            "snapshot_id": snap_id,
            "metrics": metrics[:10] if isinstance(metrics, list) else [],
            "health": health[:10] if isinstance(health, list) else [],
            "events": events[:5] if isinstance(events, list) else [],
            "logs": logs[:5] if isinstance(logs, list) else [],
        })
    return {"snapshots": result, "count": len(result)}


# --- Prediction Summary -------------------------------------------------------

@router.get("/prediction/summary")
def get_prediction_summary():
    """Get latest prediction risks summarized for the prediction panel."""
    risks_data = kafka_view_service.get_recent_messages("jatayu.agent.prediction.risks", 30)
    messages = risks_data.get("messages", [])

    # Deduplicate: keep latest per service
    latest: dict = {}
    for msg in messages:
        if isinstance(msg, dict) and msg.get("service"):
            latest[msg["service"]] = msg

    services_summary = []
    for svc, risk in sorted(latest.items(), key=lambda x: -x[1].get("risk_score", 0)):
        services_summary.append({
            "service": svc,
            "risk_score": risk.get("risk_score", 0),
            "risk_level": risk.get("risk_level", "low"),
            "predicted_failure_type": risk.get("predicted_failure_type", "none"),
            "probability": risk.get("risk_score", 0),
            "trend": risk.get("trend", "stable"),
            "time_to_failure": risk.get("time_to_failure", "unknown"),
            "rationale": (risk.get("rationale") or [])[:3],
        })

    return {"predictions": services_summary, "count": len(services_summary)}
