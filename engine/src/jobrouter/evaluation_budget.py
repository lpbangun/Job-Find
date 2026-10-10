"""Opt-in, one-process mission reservations shared by existing engine components.

Reservations are conservative and never refunded, including failures. This is
not a cross-process sandbox, a token meter, or a complete evaluation executor.
"""
import copy
import math
import re
import threading
import time


class EvaluationBudgetError(RuntimeError):
    pass


class EvaluationBudget:
    def __init__(self, limits, seconds=900, clock=time.monotonic):
        if not isinstance(limits, dict) or not limits or any(
            not isinstance(k, str) or not k or isinstance(v, bool)
            or not isinstance(v, int) or v < 1 for k, v in limits.items()
        ):
            raise ValueError("Positive named integer limits required")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Positive finite mission duration required")
        self._limits = dict(limits)
        self._used = {k: 0 for k in limits}
        self._clock = clock
        self._started = clock()
        self._deadline = self._started + seconds
        self._events = []
        self._lock = threading.Lock()

    def reserve(self, charges, operation):
        if not isinstance(charges, dict) or not charges or any(
            k not in self._limits or isinstance(v, bool) or not isinstance(v, int) or v < 1
            for k, v in charges.items()
        ) or not isinstance(operation, str) or not operation:
            raise ValueError("Valid charges and operation required")
        with self._lock:
            stamp = self._clock()
            reason = "Mission deadline exhausted" if stamp >= self._deadline else next(
                (f"Shared {k} budget exhausted" for k, v in charges.items()
                 if self._used[k] + v > self._limits[k]), None)
            event = {"sequence": len(self._events) + 1, "operation": operation,
                     "charges": dict(charges), "elapsed_seconds": stamp - self._started,
                     "status": "denied" if reason else "reserved"}
            if reason:
                event["reason"] = reason
            else:
                for k, v in charges.items():
                    self._used[k] += v
            self._events.append(event)
            if reason:
                raise EvaluationBudgetError(reason)
            return event["sequence"]

    def snapshot(self):
        with self._lock:
            return copy.deepcopy({"limits": self._limits, "reserved": self._used,
                                  "events": self._events,
                                  "accounting": "conservative reservations; not actual usage"})


def validate_development_manifest(manifest):
    """Check declared freeze fields only; cannot authenticate host attestations."""
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    if manifest.get("split") != "development" or manifest.get("synthetic_profiles") is not True:
        raise ValueError("Only synthetic development runs supported")
    if manifest.get("arms") != ["jobfind", "standalone_web_search"]:
        raise ValueError("Paired JobFind/baseline arms required")
    ids = manifest.get("brief_ids")
    if not isinstance(ids, list) or not ids or any(
        not isinstance(i, str) or not re.fullmatch(r"D(?:0[1-9]|[1-3][0-9]|40)", i) for i in ids
    ) or len(ids) != len(set(ids)):
        raise ValueError("Unique existing development brief IDs required")
    for key in ("protocol_sha256", "source_sha256", "inputs_sha256", "configuration_sha256"):
        if not isinstance(manifest.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", manifest[key]):
            raise ValueError(f"Missing or invalid {key}")
    models = manifest.get("served_models")
    if not isinstance(models, list) or not models or any(
        not isinstance(m, str) or not m.strip() or m.strip().lower() in
        ("unknown", "unavailable", "strong", "fast", "null") for m in models
    ):
        raise ValueError("Actual served-model versions required, not routing labels")
    expected = {"seconds": 900, "search_calls": 20, "http_attempts": 120,
                "candidates": 60, "model_calls": 121, "model_tokens": 200000,
                "parallel": 4, "origin_delay_seconds": 1}
    if manifest.get("limits") != expected or any(type(v) is not int for v in manifest["limits"].values()):
        raise ValueError("Protocol resource limits must match exactly")
    capabilities = manifest.get("verified_capabilities", {})
    required = ("shared_budget", "model_token_cap", "served_model_provenance",
                "accounted_search", "shared_origin_pacing", "shared_concurrency",
                "interruptible_deadline", "independent_judges")
    if not isinstance(capabilities, dict) or any(capabilities.get(k) is not True for k in required):
        raise ValueError("Execution capabilities remain unverified")
    evidence = manifest.get("capability_evidence_sha256", {})
    if not isinstance(evidence, dict) or any(not isinstance(evidence.get(k), str)
        or not re.fullmatch(r"[0-9a-f]{64}", evidence[k]) for k in required):
        raise ValueError("Capability evidence hashes required")
    return copy.deepcopy(manifest)
