import argparse
import json
from pathlib import Path
from collections.abc import Sequence
import numpy as np
from scipy.stats import ks_2samp
from .schemas import DriftPolicy, DriftReport


def compare(
    reference: Sequence[float], observed: Sequence[float], policy: DriftPolicy
) -> DriftReport:
    baseline = np.asarray(reference, dtype=float)
    current = np.asarray(observed, dtype=float)
    if baseline.ndim != 1 or current.ndim != 1:
        raise ValueError("one-dimensional property windows required")
    finite_reference = baseline[np.isfinite(baseline)]
    finite_current = current[np.isfinite(current)]
    invalid = any(
        len(clean) < policy.minimum_samples
        or 1 - len(clean) / max(1, len(raw)) > policy.maximum_missing_fraction
        for clean, raw in ((finite_reference, baseline), (finite_current, current))
    )
    common = dict(
        property_name=policy.property_name,
        reference_count=len(finite_reference),
        observed_count=len(finite_current),
    )
    if invalid:
        return DriftReport(
            **common,
            status="invalid",
            reason="insufficient finite samples or missing fraction exceeded",
        )
    inner_edges = np.unique(
        np.quantile(finite_reference, np.linspace(0, 1, policy.bins + 1)[1:-1])
    )
    # Constant references need two boundaries to detect shifts in either direction.
    if np.ptp(finite_reference) == 0:
        anchor = finite_reference[0]
        inner_edges = np.array(
            [np.nextafter(anchor, -np.inf), np.nextafter(anchor, np.inf)]
        )
    edges = np.r_[-np.inf, inner_edges, np.inf]
    expected = np.histogram(finite_reference, edges)[0].astype(float) + 0.5
    actual = np.histogram(finite_current, edges)[0].astype(float) + 0.5
    expected /= expected.sum()
    actual /= actual.sum()
    psi = float(np.sum((actual - expected) * np.log(actual / expected)))
    ks = float(ks_2samp(finite_reference, finite_current, method="asymp").statistic)
    breached = psi >= policy.psi_limit or ks >= policy.ks_limit
    return DriftReport(
        **common,
        psi=psi,
        ks_statistic=ks,
        status="drift" if breached else "healthy",
        reason="threshold exceeded" if breached else "within policy",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare numeric Ontology property windows"
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("observed", type=Path)
    parser.add_argument("--property", default="sensor_value")
    arguments = parser.parse_args()
    report = compare(
        json.loads(arguments.reference.read_text()),
        json.loads(arguments.observed.read_text()),
        DriftPolicy(property_name=arguments.property),
    )
    print(report.model_dump_json(indent=2))
    raise SystemExit(0 if report.status == "healthy" else 1)


if __name__ == "__main__":
    main()
