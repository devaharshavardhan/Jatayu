"""Service Registry loader - loads and exposes service metadata."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REGISTRY_PATH = Path(__file__).parent / "service_registry.json"
_registry_cache: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    global _registry_cache
    if _registry_cache is None:
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            _registry_cache = json.load(f)
    return _registry_cache


def get_all_services() -> Dict[str, Any]:
    return _load().get("services", {})


def get_service(name: str) -> Optional[Dict[str, Any]]:
    return get_all_services().get(name)


def get_remediation_policies(service: str) -> List[str]:
    svc = get_service(service)
    return svc.get("remediation_policies", []) if svc else []


def is_safe_to_auto_remediate(service: str) -> bool:
    svc = get_service(service)
    return bool(svc.get("safe_to_auto_remediate", False)) if svc else False


def get_criticality(service: str) -> str:
    svc = get_service(service)
    return svc.get("criticality", "medium") if svc else "medium"


def get_k8s_resource(service: str) -> Optional[str]:
    svc = get_service(service)
    return svc.get("k8s_resource") if svc else None


def get_namespace(service: str) -> str:
    svc = get_service(service)
    return svc.get("namespace", "default") if svc else "default"
