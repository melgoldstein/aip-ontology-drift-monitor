from pathlib import Path
import numpy as np
import pytest
from pydantic import ValidationError
from ontology_drift.drift_engine import compare
from ontology_drift.schemas import DriftPolicy, ActionRequest, DriftReport
from ontology_drift.action_circuit_breaker import ActionCircuitBreaker

POLICY = DriftPolicy(property_name="radar_range")


def test_incomplete_healthy_report_rejected():
    with pytest.raises(ValidationError, match="measured metrics"):
        DriftReport(
            property_name="range",
            status="healthy",
            reference_count=0,
            observed_count=0,
            reason="unchecked",
        )


def test_shift_and_identity():
    baseline = np.random.default_rng(8).normal(size=1000)
    healthy = compare(baseline, baseline, POLICY)
    assert healthy.status == "healthy" and healthy.psi == 0
    assert compare(baseline, baseline + 2, POLICY).status == "drift"


def test_constant_and_missing():
    assert compare([1.0] * 100, [1.0] * 100, POLICY).status == "healthy"
    assert compare([1.0] * 100, [2.0] * 100, POLICY).status == "drift"
    assert compare([1.0] * 100, [float("nan")] * 100, POLICY).status == "invalid"
    assert compare([], [], POLICY).status == "invalid"


def test_fail_closed_restart_and_latch(tmp_path):
    path = tmp_path / "gate.db"
    gate = ActionCircuitBreaker(path, "radar_range")
    request = lambda revision: ActionRequest(
        action_type="ReviewTrack", object_id="track-7", expected_revision=revision
    )
    assert not gate.authorize(request(0))
    revision = gate.observe(compare([1.0] * 100, [1.0] * 100, POLICY))
    assert not gate.authorize(request(revision))
    gate.reset(revision)
    assert gate.authorize(request(revision + 1))
    gate.observe(compare([1.0] * 100, [4.0] * 100, POLICY))
    reopened = ActionCircuitBreaker(path, "radar_range")
    assert not reopened.authorize(request(revision + 2))
    with pytest.raises(RuntimeError):
        reopened.reset(revision + 2)


def test_stale_and_validation(tmp_path, monkeypatch):
    gate = ActionCircuitBreaker(tmp_path / "gate.db", "radar_range", 1)
    revision = gate.observe(compare([1.0] * 100, [1.0] * 100, POLICY))
    gate.reset(revision)
    monkeypatch.setattr("ontology_drift.action_circuit_breaker.time.time", lambda: 1e12)
    assert not gate.authorize(
        ActionRequest(action_type="test", object_id="a", expected_revision=revision + 1)
    )
    with pytest.raises(ValidationError):
        DriftPolicy(property_name="a", ks_limit=float("nan"))
    with pytest.raises(ValidationError):
        ActionRequest(
            action_type="a", object_id="b", expected_revision=0, override=True
        )


def test_concurrent_observations_preserve_latch(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "concurrent.db"
    gate = ActionCircuitBreaker(path, "radar_range")
    healthy = compare([1.0] * 100, [1.0] * 100, POLICY)
    drift = compare([1.0] * 100, [5.0] * 100, POLICY)
    revision = gate.observe(healthy)
    gate.reset(revision)
    with ThreadPoolExecutor(max_workers=4) as executor:
        revisions = list(executor.map(gate.observe, [healthy, drift, healthy, healthy]))
    assert len(set(revisions)) == 4
    assert not gate.authorize(
        ActionRequest(
            action_type="test", object_id="a", expected_revision=max(revisions)
        )
    )


def test_wrong_property_and_revision(tmp_path):
    gate = ActionCircuitBreaker(tmp_path / "gate.db", "radar_range")
    with pytest.raises(ValueError, match="property mismatch"):
        gate.observe(
            compare([1.0] * 100, [1.0] * 100, DriftPolicy(property_name="speed"))
        )
    revision = gate.observe(compare([1.0] * 100, [1.0] * 100, POLICY))
    with pytest.raises(RuntimeError):
        gate.reset(revision + 1)
