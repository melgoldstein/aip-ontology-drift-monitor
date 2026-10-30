from pathlib import Path
from tempfile import TemporaryDirectory
from ontology_drift.action_circuit_breaker import ActionCircuitBreaker
from ontology_drift.drift_engine import compare
from ontology_drift.schemas import ActionRequest, DriftPolicy

with TemporaryDirectory() as workspace:
    gate = ActionCircuitBreaker(Path(workspace) / "gate.db", "radar_range")
    policy = DriftPolicy(property_name="radar_range")
    healthy = compare(list(range(200)), list(range(200)), policy)
    revision = gate.observe(healthy)
    gate.reset(revision)
    request = ActionRequest(action_type="ReviewTrack", object_id="track-7", expected_revision=revision+1)
    assert gate.authorize(request)
    revision = gate.observe(compare(list(range(200)), list(range(1000,1200)), policy))
    assert not gate.authorize(request.model_copy(update={"expected_revision":revision}))
    print("healthy observation permits action; shifted observation blocks action")
