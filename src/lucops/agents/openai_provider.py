"""Optional Responses API adapter; no SDK import or network call at import time."""

import json
import math
import os
import re
from decimal import Decimal, InvalidOperation
from threading import Lock

from .prompts import RESPONSE_FORMAT, SYSTEM_INSTRUCTIONS
from .providers import InvestigationInput
from .schemas import Hypothesis, InvestigationDraft, Recommendation

DEFAULT_MODEL = "gpt-6-luna"
MAX_CONTEXT_BYTES = 12_000
MAX_EVIDENCE = 64
MAX_OUTPUT_TOKENS = 1_200
TIMEOUT_SECONDS = 15
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_PROHIBITED_CLAIM = re.compile(
    r"\b(?:fraud|fraude|probability|probabilidade)\b|\b\d+(?:[.,]\d+)?\s*%",
    re.IGNORECASE,
)
_call_lock = Lock()
_calls_started = 0


class OpenAIProviderError(RuntimeError):
    """A safe, non-sensitive provider failure; never triggers fallback."""


class OpenAIProviderResponseError(OpenAIProviderError):
    """The provider returned a refusal, invalid output, or unsupported claims."""


def _make_client(api_key: str):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise OpenAIProviderError(
            "Optional OpenAI SDK is unavailable; install the agents extra after approval."
        ) from exc
    try:
        return OpenAI(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
    except Exception as exc:
        raise OpenAIProviderError("Could not initialize the OpenAI client.") from exc


def _safe_value(field: str, value: str | float | bool | None):
    """Restrict outbound values to bounded numbers and known machine statuses."""
    if value is None or type(value) is bool:
        return value
    if type(value) is float:
        return value if math.isfinite(value) else "[redacted]"
    if type(value) is not str or len(value) > 64:
        return "[redacted]"
    if field == "model_version":
        return value if _VERSION.fullmatch(value) else "[redacted]"
    if value in {"evaluated", "ineligible", "unavailable", "[redacted]", ""}:
        return value
    try:
        if Decimal(value).is_finite():
            return value
    except InvalidOperation:
        pass
    return "[redacted]"


def _build_context(investigation: InvestigationInput) -> str:
    """Serialize only selected minimized facts, never paths, IDs or CSV rows."""
    if len(investigation.evidence) > MAX_EVIDENCE:
        raise OpenAIProviderError("Investigation context exceeds the evidence limit.")
    facts = [
        {
            "evidence_id": item.evidence_id,
            "record_index": item.source.record_index,
            "origin": item.source.function,
            "field": item.source.field,
            "description": item.description,
            "value": _safe_value(item.source.field, item.value),
            "expected": (
                item.expected
                if item.expected
                in {
                    None,
                    "present and not empty",
                    "rule evaluation succeeded",
                    "rule check passed",
                    "unique value",
                }
                else "[redacted]"
            ),
        }
        for item in investigation.evidence
    ]
    payload = {
        "record_index": investigation.context.record_index,
        "ml_status": investigation.context.ml.status.value,
        "duplicate_record_indices": investigation.duplicates.related_record_indices,
        "batch_scope": investigation.batch_summary.scope,
        "verified_evidence": facts,
    }
    serialized = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    )
    if len(serialized.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise OpenAIProviderError("Investigation context exceeds the size limit.")
    return serialized


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _required_object(value, keys: set[str]) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("Unexpected JSON fields.")
    return value


def _required_list(value) -> list:
    if type(value) is not list or len(value) > 20:
        raise ValueError("Expected a bounded JSON array.")
    return value


def _parse_draft(output_text: str) -> InvestigationDraft:
    if not isinstance(output_text, str) or len(output_text) > 32_000:
        raise OpenAIProviderResponseError("OpenAI returned an incompatible response.")
    try:
        data = _required_object(
            json.loads(output_text, object_pairs_hook=_unique_keys),
            {"hypotheses", "recommendations", "limitations", "insufficient_evidence"},
        )
        hypotheses = tuple(
            Hypothesis(
                description=_required_object(
                    item, {"description", "evidence_ids", "status"}
                )["description"],
                evidence_ids=tuple(_required_list(item["evidence_ids"])),
                status=item["status"],
            )
            for item in _required_list(data["hypotheses"])
        )
        recommendations = tuple(
            Recommendation(
                action=_required_object(item, {"action", "evidence_ids"})["action"],
                evidence_ids=tuple(_required_list(item["evidence_ids"])),
            )
            for item in _required_list(data["recommendations"])
        )
        limitations = tuple(_required_list(data["limitations"]))
        insufficient = tuple(_required_list(data["insufficient_evidence"]))
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise OpenAIProviderResponseError(
            "OpenAI returned an incompatible response."
        ) from exc
    texts = (
        *(item.description for item in hypotheses),
        *(item.action for item in recommendations),
        *limitations,
        *insufficient,
    )
    if any(isinstance(text, str) and _PROHIBITED_CLAIM.search(text) for text in texts):
        raise OpenAIProviderResponseError(
            "OpenAI response violates the claim restrictions."
        )
    return InvestigationDraft(hypotheses, recommendations, limitations, insufficient)


def _reserve_call() -> None:
    """Process-local safeguard; an organization spending cap is still required."""
    raw_limit = os.getenv("LUCOPS_AGENT_OPENAI_MAX_CALLS", "0")
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise OpenAIProviderError("Invalid OpenAI call limit configuration.") from exc
    if not 0 <= limit <= 1_000:
        raise OpenAIProviderError("Invalid OpenAI call limit configuration.")
    global _calls_started
    with _call_lock:
        if _calls_started >= limit:
            raise OpenAIProviderError(
                "OpenAI calls are disabled or the process call limit was reached."
            )
        _calls_started += 1


class OpenAIProvider:
    """One bounded Responses request per investigation; no retries or fallback."""

    mode = "openai"

    def __init__(self, model: str | None = None):
        selected = (
            model
            if model is not None
            else os.getenv("LUCOPS_AGENT_OPENAI_MODEL", DEFAULT_MODEL)
        )
        if not isinstance(selected, str) or not _MODEL_NAME.fullmatch(selected):
            raise OpenAIProviderError("Invalid OpenAI model configuration.")
        self.model = selected
        self.name = f"openai-responses:{selected}"

    def generate(self, investigation: InvestigationInput) -> InvestigationDraft:
        user_context = _build_context(investigation)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or not api_key.strip():
            raise OpenAIProviderError(
                "OPENAI_API_KEY is not configured on the backend."
            )
        if len(api_key) > 4_096:
            raise OpenAIProviderError("Invalid OPENAI_API_KEY configuration.")
        # Resolve the optional SDK before reserving a call. Never log the key or prompt.
        client = _make_client(api_key)
        _reserve_call()
        try:
            response = client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": user_context},
                ],
                text={"format": RESPONSE_FORMAT},
                reasoning={"effort": "none"},
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
                tools=[],
                truncation="disabled",
            )
        except TimeoutError as exc:
            raise OpenAIProviderError("OpenAI request timed out.") from exc
        except Exception as exc:
            if type(exc).__name__ == "APITimeoutError":
                raise OpenAIProviderError("OpenAI request timed out.") from exc
            raise OpenAIProviderError("OpenAI request failed.") from exc
        output = getattr(response, "output", None)
        if not isinstance(output, (list, tuple)):
            raise OpenAIProviderResponseError(
                "OpenAI returned an incompatible response."
            )
        if any(
            getattr(part, "type", None) == "refusal"
            for item in output
            for part in (getattr(item, "content", None) or ())
        ):
            raise OpenAIProviderResponseError(
                "OpenAI refused the investigation request."
            )
        if getattr(response, "status", None) != "completed":
            raise OpenAIProviderResponseError("OpenAI returned an incomplete response.")
        return _parse_draft(getattr(response, "output_text", None))
