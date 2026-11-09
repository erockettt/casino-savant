"""Browser Use integration tests — fully mocked; no network, no key, no spending."""
from types import SimpleNamespace as NS

import pytest

from casino_savant.integrations import browser_use as bu


class FakeRuns:
    def __init__(self, *, create_exc=None, wait_exc=None, summary=None):
        self.create_exc, self.wait_exc = create_exc, wait_exc
        self.summary = summary or NS(status=NS(value="completed"), result='{"a": 1}', output={"a": 1},
                                     error=None, total_cost_usd="0.12")
        self.create_calls, self.cancelled = [], []

    def create(self, task, **kw):
        self.create_calls.append((task, kw))
        if self.create_exc:
            raise self.create_exc
        return NS(id="run-1")

    def wait_for_completion(self, run_id, timeout):
        if self.wait_exc:
            raise self.wait_exc
        return self.summary

    def cancel(self, run_id):
        self.cancelled.append(run_id)


class FakeClient:
    def __init__(self, runs):
        self.runs = runs

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def factory(runs):
    return lambda: FakeClient(runs)


class HTTPErr(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.status_code = code


def test_requires_spend_confirmation():
    runs = FakeRuns()
    with pytest.raises(bu.SpendNotConfirmed):
        bu.run_task("t", client_factory=factory(runs))
    assert runs.create_calls == []


def test_default_omits_model_and_caps_cost():
    runs = FakeRuns()
    out = bu.run_task("t", confirm_spend=True, client_factory=factory(runs))
    _, kw = runs.create_calls[0]
    assert "model" not in kw and "model_params" not in kw
    assert kw["max_cost_usd"] == 1.0
    assert out.ok and out.status == "completed"


def test_cost_cap_enforced():
    with pytest.raises(ValueError):
        bu.run_task("t", confirm_spend=True, max_cost_usd=2.0, client_factory=factory(FakeRuns()))


def test_speed_first_uses_ultrafast_without_params():
    runs = FakeRuns()
    bu.run_task("t", confirm_spend=True, speed_first=True, client_factory=factory(runs))
    assert runs.create_calls[0][1]["model"] == "bu-ultrafast"
    assert "model_params" not in runs.create_calls[0][1]
    with pytest.raises(ValueError):
        bu.run_task("t", confirm_spend=True, speed_first=True, model_params={"x": 1}, client_factory=factory(FakeRuns()))


def test_explicit_model_settings_preserved():
    runs = FakeRuns()
    bu.run_task("t", confirm_spend=True, model="claude-sonnet-5-5", model_params={"temperature": 0},
                client_factory=factory(runs))
    kw = runs.create_calls[0][1]
    assert kw["model"] == "claude-sonnet-5-5" and kw["model_params"] == {"temperature": 0}


def test_ambiguous_create_not_retried():
    runs = FakeRuns(create_exc=TimeoutError("read timed out"))
    with pytest.raises(bu.AmbiguousCreateError):
        bu.run_task("t", confirm_spend=True, client_factory=factory(runs))
    assert len(runs.create_calls) == 1
    runs5 = FakeRuns(create_exc=HTTPErr(502))
    with pytest.raises(bu.AmbiguousCreateError):
        bu.run_task("t", confirm_spend=True, client_factory=factory(runs5))
    assert len(runs5.create_calls) == 1


def test_definite_rejection_propagates():
    runs = FakeRuns(create_exc=HTTPErr(401))
    with pytest.raises(HTTPErr):
        bu.run_task("t", confirm_spend=True, client_factory=factory(runs))
    assert len(runs.create_calls) == 1


def test_abandoned_run_is_cancelled():
    runs = FakeRuns(wait_exc=TimeoutError("too slow"))
    with pytest.raises(TimeoutError):
        bu.run_task("t", confirm_spend=True, client_factory=factory(runs))
    assert runs.cancelled == ["run-1"]
    runs2 = FakeRuns(wait_exc=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        bu.run_task("t", confirm_spend=True, client_factory=factory(runs2))
    assert runs2.cancelled == ["run-1"]


@pytest.mark.parametrize("summary,needle", [
    (NS(status=NS(value="failed"), result=None, output=None, error="boom", total_cost_usd="0.3"), "not 'completed'"),
    (NS(status=NS(value="completed"), result="", output=None, error=None, total_cost_usd="0.1"), "empty result"),
    (NS(status=NS(value="completed"), result='{"x": 1}', output=None, error=None, total_cost_usd="0.1"), "missing required"),
])
def test_validation_flags_bad_results(summary, needle):
    out = bu.run_task("t", confirm_spend=True, output_schema={"type": "object", "required": ["a"]},
                      client_factory=factory(FakeRuns(summary=summary)))
    assert not out.ok and any(needle in p for p in out.problems)


def test_no_secret_in_outcome(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_API_KEY", "bu_SECRET_SHOULD_NOT_LEAK")
    out = bu.run_task("t", confirm_spend=True, client_factory=factory(FakeRuns()))
    assert "bu_SECRET" not in repr(out.to_dict())
