"""Focused checks for the opt-in fixed-window source-E v2 policy.

The two material cases below are compact values copied from the frozen R22
review artifacts.  AT4 is the five-row Sandia 304L window (source rows
146--150); M04CPMMA is the five-row auto window from the retained application
preview.  A synthetic peak row is appended only to let the small fixture
reproduce the original 10--40% peak-band selection.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step, apply

EXTENSIONS = Path(__file__).resolve().parents[1]
extensions.load(EXTENSIONS)
processing.load_builtin()

from matnexus_ext.tensile_extras import source_elastic  # noqa: E402


def _frame(strain: list[float], stress: list[float]) -> Frame:
    values = {
        "strain_engineering": np.asarray(strain, dtype=np.float64),
        "stress_engineering": np.asarray(stress, dtype=np.float64),
        "source_row": np.arange(len(strain), dtype=np.float64),
    }
    return Frame(
        values,
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "source_row": "1",
        },
    )


def _scalars(result: object) -> dict[str, float]:
    # Keep this helper independent of PipelineResult's merged scalar behavior;
    # the stage is what stores the source-E policy evidence.
    stage = result.stages[-1]  # type: ignore[attr-defined]
    return {item.key: item.value for item in stage.scalars}


def _run(frame: Frame, policy: str = source_elastic.AUTO_POLICY_V2):
    return apply(
        [Step("tensile.source_elastic_modulus_v2", {"policy": policy})],
        frame,
    )


def _snapshot(frame: Frame) -> tuple[dict[str, str], dict[str, bytes]]:
    return dict(frame.units), {key: value.tobytes() for key, value in frame.columns.items()}


def _at4_frame() -> Frame:
    window_strain = [
        0.00019636167464134543,
        0.00026036186793065456,
        0.0003419922641170819,
        0.00041344405974260003,
        0.0005391454701692773,
    ]
    window_stress = [
        0.06296769470677166e9,
        0.08234586894425197e9,
        0.10247659794488188e9,
        0.14461945452913388e9,
        0.19654547633385827e9,
    ]
    # Keep the compact test's current-input indices equal to the R22 source
    # rows 146--150, with a later peak defining the original stress band.
    prefix = np.linspace(0.0, window_strain[0] - 1e-7, 146).tolist()
    strain = prefix + window_strain + [0.001]
    stress = [0.0] * len(prefix) + window_stress + [0.5e9]
    return _frame(strain, stress)


def _m04_frame() -> Frame:
    strain = [5.479e-06, 0.0004745, 0.0009627, 0.001455, 0.001927, 0.003]
    stress = [
        4571197.8990087025,
        6146928.319487728,
        7750303.133308491,
        9262846.369006403,
        10733923.014691709,
        30e6,
    ]
    return _frame(strain, stress)


def test_v2_holds_sandia_at4_when_fixed_window_loo_fails() -> None:
    frame = _at4_frame()
    before = _snapshot(frame)

    result = _run(frame)
    values = _scalars(result)
    stage = result.stages[-1]

    assert "youngs_modulus" not in values
    assert "elastic_intercept" not in values
    assert values["elastic_slope_reference"] == pytest.approx(396.0718675699107e9)
    assert values["elastic_point_count"] == 5.0
    assert values["elastic_support_member_count"] == 5.0
    assert values["elastic_r_squared"] == pytest.approx(0.9823646268946213)
    assert values["elastic_loo_min_r_squared"] == pytest.approx(0.9591522122673674)
    assert values["elastic_loo_failed_row"] == 150.0
    assert stage.options["policy"] == source_elastic.AUTO_POLICY_V2
    assert "다시 고르지" in " ".join(stage.notes)
    assert "지지점이 5개라 최소 6개" in " ".join(stage.notes)
    assert "0.959152" in " ".join(stage.notes)
    assert "원행 150" in " ".join(stage.notes)
    assert _snapshot(frame) == before

    with pytest.raises(ProcessingError, match="내지 않았습니다"):
        apply(
            [
                Step("tensile.source_elastic_modulus_v2", {}),
                Step(
                    "tensile.source_proof_stress",
                    {"youngs_modulus": "@youngs_modulus", "offset_strain": 0.002},
                ),
            ],
            frame,
        )

    replay = _run(frame, stage.options["policy"])
    assert _scalars(replay) == values
    assert replay.stages[-1].notes == stage.notes


def test_legacy_registry_choices_stay_unchanged_and_v2_has_dedicated_route() -> None:
    legacy = registry.get("tensile.source_elastic_modulus")
    legacy_params = {item.name: item for item in legacy.params}
    assert legacy_params["policy"].choices == ("auto_rows_v1", "manual_rows")

    v2 = registry.get("tensile.source_elastic_modulus_v2")
    v2_params = {item.name: item for item in v2.params}
    assert v2_params["policy"].default == "auto_rows_v2"
    assert v2_params["policy"].choices == ("auto_rows_v2",)
    assert "start_index" not in v2_params

    with pytest.raises(ProcessingError, match="auto_rows_v1, manual_rows"):
        apply(
            [Step("tensile.source_elastic_modulus", {"policy": "auto_rows_v2"})],
            _m04_frame(),
        )


def test_v2_holds_actual_m04cpmmma_window_for_support_margin() -> None:
    frame = _m04_frame()
    result = _run(frame)
    values = _scalars(result)
    notes = " ".join(result.stages[-1].notes)

    assert "youngs_modulus" not in values
    assert "elastic_intercept" not in values
    assert values["elastic_slope_reference"] == pytest.approx(3.2010398265438557e9)
    assert values["elastic_point_count"] == 5.0
    assert values["elastic_support_member_count"] == 5.0
    assert values["elastic_r_squared"] == pytest.approx(0.9996320771231093)
    assert values["elastic_loo_min_r_squared"] == pytest.approx(0.9995775947969974)
    assert "지지점이 5개라 최소 6개" in notes
    assert "LOO" in notes
    assert result.stages[-1].options["policy"] == source_elastic.AUTO_POLICY_V2


def test_v1_default_and_manual_replay_are_unchanged() -> None:
    frame = _m04_frame()
    default = apply([Step("tensile.source_elastic_modulus", {})], frame)
    explicit_v1 = apply(
        [Step("tensile.source_elastic_modulus", {"policy": source_elastic.AUTO_POLICY_V1})],
        frame,
    )
    assert _scalars(default) == _scalars(explicit_v1)
    assert default.stages[-1].notes == explicit_v1.stages[-1].notes
    assert default.stages[-1].options == explicit_v1.stages[-1].options

    manual = apply(
        [
            Step(
                "tensile.source_elastic_modulus",
                {
                    "policy": source_elastic.MANUAL_POLICY,
                    "start_index": 0,
                    "end_index": 4,
                },
            )
        ],
        frame,
    )
    manual_values = _scalars(manual)
    assert manual_values["youngs_modulus"] == pytest.approx(3.2010398265438557e9)
    assert manual.stages[-1].options["policy"] == source_elastic.MANUAL_POLICY


def test_v2_pure_linear_six_support_rows_passes_and_nonstrict_window_is_fixed() -> None:
    strict = _frame(
        [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007],
        [0.2e9, 0.3e9, 0.4e9, 0.5e9, 0.6e9, 0.7e9, 2.0e9],
    )
    strict_values = _scalars(_run(strict))
    assert strict_values["youngs_modulus"] == pytest.approx(100e9)
    assert strict_values["elastic_support_member_count"] == 6.0
    assert strict_values["elastic_loo_min_r_squared"] == pytest.approx(1.0)

    nonstrict = _frame(
        [0.001, 0.002, 0.003, 0.0029, 0.004, 0.005, 0.006],
        [0.2e9, 0.3e9, 0.4e9, 0.39e9, 0.5e9, 0.6e9, 1.5e9],
    )
    values = _scalars(_run(nonstrict))
    assert values["youngs_modulus"] == pytest.approx(100e9)
    assert values["elastic_support_member_count"] == 6.0
    assert values["source_elastic_nonincreasing_step_count"] == 1.0
    assert values["elastic_loo_min_r_squared"] > 0.99
