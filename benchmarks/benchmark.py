import json
import platform
import statistics
import time
import numpy as np
from ontology_drift.drift_engine import compare
from ontology_drift.schemas import DriftPolicy

baseline = np.random.default_rng(8).normal(size=1000)
policy = DriftPolicy(property_name="range")
timings = []
for _ in range(101):
    started = time.perf_counter_ns()
    compare(baseline, baseline + 0.1, policy)
    timings.append((time.perf_counter_ns() - started) / 1000)
print(
    json.dumps(
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "samples_per_window": 1000,
            "median_us": statistics.median(timings[1:]),
            "p95_us": float(np.percentile(timings[1:], 95)),
        },
        indent=2,
    )
)
