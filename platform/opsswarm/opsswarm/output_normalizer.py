from __future__ import annotations

import json
from typing import Any


_CONFIDENCE_WORDS = {
    "very_low": 0.1,
    "very low": 0.1,
    "low": 0.3,
    "medium": 0.6,
    "moderate": 0.6,
    "high": 0.9,
    "very_high": 0.95,
    "very high": 0.95,
}


def _as_text(value: Any) -> str:
    """Convert structured LLM output into a deterministic, readable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        # Prefer the human-readable field when a structured object contains one.
        for key in ("description", "action", "question", "summary", "observation", "finding", "message"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, (list, tuple, set)):
        return json.dumps(list(value), ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_as_text(item) for item in value if item is not None]
    return [_as_text(value)]


def _as_confidence(value: Any, default: float = 0.0) -> float:
    """Normalize textual LLM confidence variants without changing numeric semantics."""
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in _CONFIDENCE_WORDS:
            return _CONFIDENCE_WORDS[raw]
        if raw.endswith("%"):
            try:
                return float(raw[:-1].strip()) / 100.0
            except ValueError:
                return default
        try:
            return float(raw)
        except ValueError:
            return default
    return default


def normalize_finding(data: Any) -> dict[str, Any]:
    out = dict(data or {})
    out["evidence"] = _as_text_list(out.get("evidence"))
    out["confidence"] = _as_confidence(out.get("confidence"), 0.0)
    raw = out.get("raw")
    if raw is None:
        out["raw"] = {}
    elif not isinstance(raw, dict):
        out["raw"] = {"value": raw}
    return out


def normalize_root_cause(data: Any) -> dict[str, Any]:
    out = dict(data or {})
    out["causal_chain"] = _as_text_list(out.get("causal_chain"))
    out["evidence_refs"] = _as_text_list(out.get("evidence_refs"))
    out["remediation_options"] = _as_text_list(out.get("remediation_options"))
    out["corrective_actions"] = _as_text_list(out.get("corrective_actions"))
    out["confidence"] = _as_confidence(out.get("confidence"), 0.0)

    question = out.get("human_input_question")
    if question is not None and not isinstance(question, str):
        out["human_input_question"] = _as_text(question) or None
    return out


def normalize_recovery_plan(data: Any) -> dict[str, Any]:
    out = dict(data or {})
    if "confidence" in out:
        out["confidence"] = _as_confidence(out.get("confidence"), 0.0)

    if "options" in out:
        options = []
        for item in out.get("options") or []:
            if not isinstance(item, dict):
                options.append(item)
                continue
            option = dict(item)
            if "capabilities" in option:
                option["capabilities"] = _as_text_list(option.get("capabilities"))
            options.append(option)
        out["options"] = options

    question = out.get("business_input_question")
    if question is not None and not isinstance(question, str):
        out["business_input_question"] = _as_text(question) or None
    return out


def normalize_execution_result(data: Any) -> dict[str, Any]:
    out = dict(data or {})
    out["evidence"] = _as_text_list(out.get("evidence"))
    raw = out.get("raw")
    if raw is None:
        out["raw"] = {}
    elif not isinstance(raw, dict):
        out["raw"] = {"value": raw}
    return out


def normalize_verification_result(data: Any) -> dict[str, Any]:
    out = dict(data or {})
    out["evidence"] = _as_text_list(out.get("evidence"))
    out["confidence"] = _as_confidence(out.get("confidence"), 0.0)
    raw = out.get("raw")
    if raw is None:
        out["raw"] = {}
    elif not isinstance(raw, dict):
        out["raw"] = {"value": raw}
    return out
