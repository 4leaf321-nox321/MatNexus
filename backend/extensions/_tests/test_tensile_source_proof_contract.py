"""Storage-contract checks for original-row tensile proof diagnostics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, Step, apply

EXTENSIONS = Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()


def test_source_proof_keys_fit_summary_storage_on_observed_m11_curve() -> None:
    # Consecutive measured points from the retained M11BPMMA app preview around
    # its successful 0.2% proof crossing; E and expected result are from that run.
    strain = np.asarray([0.01757, 0.01781, 0.01810, 0.01836], dtype=np.float64)
    stress = np.asarray(
        [40_372_264.0630252, 40_802_380.1934787, 41_232_496.3239323, 41_662_612.4543858],
        dtype=np.float64,
    )
    frame = Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )

    result = apply(
        [
            Step(
                "tensile.source_proof_stress",
                {
                    "youngs_modulus": 2_573_091_893.509718,
                    "offset_strain": 0.002,
                    "start_index": 0,
                    "end_index": 3,
                    "search_start": float(strain[0]),
                    "search_end": float(strain[-1]),
                },
            )
        ],
        frame,
    )

    stage = result.stages[-1]
    emitted_keys = {item.key for item in stage.scalars}
    plugin = registry.get("tensile.source_proof_stress")
    declared_keys = {item.key for item in plugin.makes_values}
    renamed_key = "source_proof_forward_coincident_segment_count"
    values = {item.key: item.value for item in stage.scalars}

    assert plugin.version == "2"
    assert all(len(key) <= 50 for key in emitted_keys)
    assert all(len(key) <= 50 for key in declared_keys)
    assert renamed_key in emitted_keys
    assert renamed_key in declared_keys
    assert values[renamed_key] == 0.0
    assert values["proof_stress"] == pytest.approx(40_968_119.6327597)
    assert values["proof_strain"] == pytest.approx(0.0179217475816143)
