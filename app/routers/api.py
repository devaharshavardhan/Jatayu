from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

from app.services import dataset_service, publish_service, kafka_view_service

router = APIRouter()

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
