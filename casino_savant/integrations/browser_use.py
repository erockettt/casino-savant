"""Minimal Browser Use V4 hosted-agent integration (browser-use-sdk).

Guarantees:
* The API key is read server-side from BROWSER_USE_API_KEY by the SDK; this
  module never reads, logs or returns it.
* Model: omitted by default (the service default model). `speed_first=True`
  uses "bu-ultrafast", which takes no model params. An explicit `model` /
  `model_params` from the caller is passed through unchanged.
* Every run is capped at <= $1.00 (max_cost_usd).
* Live spending requires `confirm_spend=True`; otherwise SpendNotConfirmed.
* A create is attempted ONCE. If its outcome is ambiguous (timeout, network
  error, 5xx), we raise AmbiguousCreateError and never retry: a retry could
  start a second billable run.
* Abandoned runs (timeout, interrupt, any error while waiting) are cancelled.
* Results are validated: status must be "completed", no error, non-empty
  result, and (if an output schema is given) its required keys present.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

MAX_COST_CAP_USD = 1.0
SPEED_MODEL = "bu-ultrafast"


class SpendNotConfirmed(RuntimeError):
    pass


class AmbiguousCreateError(RuntimeError):
    """The create request may or may not have started a run. Check the dashboard; do not retry blindly."""


@dataclass
class RunOutcome:
    run_id: str
    status: str
    ok: bool
    result: str | None
    output: Any
    cost_usd: str | None
    problems: list[str] = field(default_factory=list)
    cancelled_by_us: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _default_client():
    from browser_use_sdk.v4 import BrowserUse
    return BrowserUse()


def validate(summary: Any, output_schema: dict | None) -> list[str]:
    problems: list[str] = []
    status = getattr(getattr(summary, "status", None), "value", getattr(summary, "status", None))
    if status != "completed":
        problems.append(f"status is {status!r}, not 'completed'")
    if getattr(summary, "error", None):
        problems.append(f"run reported error: {summary.error}")
    result = getattr(summary, "result", None)
    output = getattr(summary, "output", None)
    if not (result and str(result).strip()) and output in (None, "", {}, []):
        problems.append("empty result")
    if output_schema and status == "completed":
        data = output
        if data is None and result:
            try:
                data = json.loads(result)
            except (TypeError, ValueError):
                data = None
        if not isinstance(data, dict):
            problems.append("structured output missing or not an object")
        else:
            missing = [k for k in output_schema.get("required", []) if k not in data]
            if missing:
                problems.append(f"structured output missing required keys: {missing}")
    return problems


def run_task(
    task: str,
    *,
    confirm_spend: bool = False,
    max_cost_usd: float = MAX_COST_CAP_USD,
    speed_first: bool = False,
    model: str | None = None,
    model_params: dict | None = None,
    output_schema: dict | None = None,
    timeout_s: float = 900,
    client_factory: Callable[[], Any] = _default_client,
) -> RunOutcome:
    if not confirm_spend:
        raise SpendNotConfirmed("Live Browser Use runs cost money; pass confirm_spend=True after the user approves.")
    if not 0 < max_cost_usd <= MAX_COST_CAP_USD:
        raise ValueError(f"max_cost_usd must be in (0, {MAX_COST_CAP_USD}]")
    if speed_first:
        if model is not None and model != SPEED_MODEL:
            raise ValueError("speed_first conflicts with an explicit model")
        if model_params:
            raise ValueError(f"{SPEED_MODEL} takes no model_params")
        model = SPEED_MODEL

    kwargs: dict[str, Any] = {"max_cost_usd": max_cost_usd}
    if model is not None:
        kwargs["model"] = model
    if model_params is not None:
        kwargs["model_params"] = model_params
    if output_schema is not None:
        kwargs["output_schema"] = output_schema

    with client_factory() as client:
        try:
            created = client.runs.create(task, **kwargs)
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "status_code", None)
            if code is not None and 400 <= code < 500 and code not in (408,):
                raise  # definite rejection (bad key, validation, no credit): nothing was started
            raise AmbiguousCreateError(
                f"Create outcome unknown ({type(e).__name__}: {e}). Check the Browser Use dashboard before trying again."
            ) from e

        run_id = str(created.id)
        cancelled = False
        try:
            summary = client.runs.wait_for_completion(run_id, timeout=timeout_s)
        except BaseException:
            try:
                client.runs.cancel(run_id)
                cancelled = True
            except Exception:  # noqa: BLE001  best effort; surface the original error
                pass
            raise
        problems = validate(summary, output_schema)
        status = getattr(summary.status, "value", summary.status)
        return RunOutcome(run_id, status, not problems, summary.result, getattr(summary, "output", None),
                          getattr(summary, "total_cost_usd", None), problems, cancelled)
