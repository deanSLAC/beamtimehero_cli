"""Primary -> fallback API-key failover in the SPEC-log error checker.

The checker talks to the SLAC AI Gateway and reads the SLAC key env vars
(primary first, existing key as fallback).
"""

import pytest
import requests

import beamtimehero_cli.llm.key_pool as kp
from beamtimehero_cli.spec_logs import error_checker


@pytest.fixture(autouse=True)
def _clean_pool(monkeypatch):
    """Isolate the process-wide KeyPool registry + key env between tests."""
    kp._registry.clear()
    monkeypatch.delenv("SLAC_API_KEY_PRIMARY", raising=False)
    monkeypatch.delenv("SLAC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_KEY_COOLDOWN_S", raising=False)
    yield
    kp._registry.clear()


class FakeResp:
    def __init__(self, status_code, json_body=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_body
        self.text = text
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _completion(content):
    return {"choices": [{"message": {"content": content}}]}


def test_falls_back_to_secondary_on_429(monkeypatch):
    monkeypatch.setenv("SLAC_API_KEY_PRIMARY", "PRIMARY")
    monkeypatch.setenv("SLAC_API_KEY", "FALLBACK")

    used = []

    def fake_post(url, headers=None, json=None, timeout=None):
        auth = headers["Authorization"]
        used.append(auth)
        if auth == "Bearer PRIMARY":
            return FakeResp(429, text="rate limit exceeded", headers={"Retry-After": "1"})
        return FakeResp(200, json_body=_completion("[]"))

    monkeypatch.setattr(error_checker.requests, "post", fake_post)

    assert error_checker._call_llm("sys", "user") == "[]"
    assert used == ["Bearer PRIMARY", "Bearer FALLBACK"]

    # Primary is now cooling down: the next call skips straight to the fallback.
    used.clear()
    assert error_checker._call_llm("sys", "user") == "[]"
    assert used == ["Bearer FALLBACK"]


def test_success_body_mentioning_quota_is_not_a_lockout(monkeypatch):
    monkeypatch.setenv("SLAC_API_KEY_PRIMARY", "PRIMARY")
    monkeypatch.setenv("SLAC_API_KEY", "FALLBACK")

    used = []

    def fake_post(url, headers=None, json=None, timeout=None):
        used.append(headers["Authorization"])
        # A 200 completion whose *content* happens to mention "quota" must not
        # be misread as a lockout and trigger an needless fallback.
        return FakeResp(200, json_body=_completion("The quota subsystem is fine."))

    monkeypatch.setattr(error_checker.requests, "post", fake_post)

    assert error_checker._call_llm("sys", "user") == "The quota subsystem is fine."
    assert used == ["Bearer PRIMARY"]


def test_non_lockout_http_error_returns_none_without_fallback(monkeypatch):
    monkeypatch.setenv("SLAC_API_KEY_PRIMARY", "PRIMARY")
    monkeypatch.setenv("SLAC_API_KEY", "FALLBACK")

    used = []

    def fake_post(url, headers=None, json=None, timeout=None):
        used.append(headers["Authorization"])
        return FakeResp(400, json_body={"error": {"message": "bad request"}}, text="bad request")

    monkeypatch.setattr(error_checker.requests, "post", fake_post)

    assert error_checker._call_llm("sys", "user") is None
    assert used == ["Bearer PRIMARY"]  # 400 is not a lockout -> no fallback


def test_auth_error_is_not_a_lockout(monkeypatch):
    monkeypatch.setenv("SLAC_API_KEY_PRIMARY", "PRIMARY")
    monkeypatch.setenv("SLAC_API_KEY", "FALLBACK")

    used = []

    def fake_post(url, headers=None, json=None, timeout=None):
        used.append(headers["Authorization"])
        return FakeResp(401, json_body={"error": "unauthorized"}, text="unauthorized")

    monkeypatch.setattr(error_checker.requests, "post", fake_post)

    assert error_checker._call_llm("sys", "user") is None
    assert used == ["Bearer PRIMARY"]  # 401 excluded from lockout


def test_no_keys_skips_the_call(monkeypatch):
    called = []
    monkeypatch.setattr(
        error_checker.requests, "post", lambda *a, **k: called.append(1)
    )
    assert error_checker._call_llm("sys", "user") is None
    assert not called


def test_single_key_still_works(monkeypatch):
    # Only the existing key set (no primary) -> behaves like before.
    monkeypatch.setenv("SLAC_API_KEY", "ONLY")

    used = []

    def fake_post(url, headers=None, json=None, timeout=None):
        used.append(headers["Authorization"])
        return FakeResp(200, json_body=_completion("ok"))

    monkeypatch.setattr(error_checker.requests, "post", fake_post)

    assert error_checker._call_llm("sys", "user") == "ok"
    assert used == ["Bearer ONLY"]
