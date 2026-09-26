"""Contract tests for the opt-in proof-anchor guard."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step, apply

EXTENSIONS = Path(__file__).resolve().parents[1]
RECIPE = EXTENSIONS / "tensile_extras" / "recipes" / "uniform_true_plastic_candidate_v1.json"
extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(
    x: list[float] | np.ndarray,
    stress: list[float] | np.ndarray,
    *,
    units: dict[str, str] | None = None,
) -> Frame:
    return Frame(
        {
            "strain_true_plastic": np.asarray(x),
            "stress_true": np.asarray(stress),
            "source_row": np.arange(len(x), dtype=np.float64),
        },
        units
        or {
            "strain_true_plastic": "1",
            "stress_true": "Pa",
            "source_row": "1",
        },
    )


def _run_guard(frame: Frame, **options: object) -> processing.PipelineResult:
    return apply([Step("tensile.proof_anchor_guard", options)], frame)


def test_registration_is_candidate_only_and_ordered_before_monotone() -> None:
    plugin = registry.get("tensile.proof_anchor_guard")

    assert plugin.version == "1"
    assert plugin.order == 91
    assert registry.get("tensile.true_plastic").order < plugin.order
    assert plugin.order < registry.get("curve.monotone").order
    assert plugin.order < registry.get("curve.resample").order
    assert plugin.meta["scope"] == "uniform_true_plastic_card"
    assert plugin.meta["candidate_only"] is True
    defaults = {param.name: param.default for param in plugin.params}
    assert defaults == {
        "proof_stress": None,
        "proof_strain": None,
        "x": "strain_true_plastic",
        "stress": "stress_true",
    }
    assert all(len(value.key) <= 50 for value in plugin.makes_values)


def test_exact_anchor_passes_and_returns_the_same_unchanged_frame() -> None:
    proof_stress = 200.0e6
    proof_strain = 0.002
    expected = proof_stress * (1.0 + proof_strain)
    frame = _frame([0.0, 0.01, 0.02], [expected, 205.0e6, 210.0e6])
    before = {key: values.copy() for key, values in frame.columns.items()}

    result = _run_guard(frame, proof_stress=proof_stress, proof_strain=proof_strain)

    stage = result.stages[-1]
    assert stage.frame is frame
    for key, values in before.items():
        np.testing.assert_array_equal(stage.frame.columns[key], values)
    values = {scalar.key: scalar.value for scalar in stage.scalars}
    assert values["proof_anchor_expected_stress"] == expected
    assert values["proof_anchor_observed_stress"] == expected
    assert values["proof_anchor_error_pa"] == 0.0
    assert values["proof_anchor_verified_code"] == 1.0
    assert stage.options["x"] == "strain_true_plastic"
    assert stage.options["stress"] == "stress_true"
    assert "proof anchor 검증 통과" in " ".join(stage.notes)

    replayed = _run_guard(frame, **stage.options)
    replayed_values = {scalar.key: scalar.value for scalar in replayed.stages[-1].scalars}
    assert replayed_values["proof_anchor_verified_code"] == 1.0


def test_pc_like_anchor_replacement_is_rejected_with_observed_expected_delta() -> None:
    proof_stress = 200.0e6
    proof_strain = 0.002
    expected = proof_stress * (1.0 + proof_strain)
    frame = _frame(
        [0.0, 0.01, 0.02],
        [expected + 0.494596e6, 205.0e6, 210.0e6],
    )

    with pytest.raises(ProcessingError, match=r"494596"):
        _run_guard(frame, proof_stress=proof_stress, proof_strain=proof_strain)


@pytest.mark.parametrize(
    ("frame", "options", "message"),
    [
        (_frame([0.001, 0.01], [200.4e6, 205.0e6]), {}, "첫 값은 0"),
        (
            _frame(
                [0.0, 0.01],
                [200.4e6, 205.0e6],
                units={"strain_true_plastic": "%", "stress_true": "Pa", "source_row": "1"},
            ),
            {},
            "단위는 '1'",
        ),
        (
            _frame(
                [0.0, 0.01],
                [200.4e6, 205.0e6],
                units={"strain_true_plastic": "1", "stress_true": "MPa", "source_row": "1"},
            ),
            {},
            "단위는 'Pa'",
        ),
        (_frame([0.0, 0.01], [200.4e6, 205.0e6]), {"x": "missing_x"}, "열이 없습니다"),
        (_frame([0.0, 0.01], [200.4e6, 205.0e6]), {"proof_stress": 0.0}, "양수"),
        (_frame([0.0, 0.01], [200.4e6, 205.0e6]), {"proof_strain": -0.001}, "0 이상"),
        (_frame([0.0, 0.01], [200.4e6, 205.0e6]), {"proof_stress": np.nan}, "유한한 숫자"),
    ],
)
def test_wrong_x_units_and_proof_values_are_rejected(
    frame: Frame, options: dict[str, object], message: str
) -> None:
    guard_options = {"proof_stress": 200.0e6, "proof_strain": 0.002, **options}
    with pytest.raises(ProcessingError, match=message):
        _run_guard(frame, **guard_options)


def test_proof_inserted_true_plastic_sequence_passes_first_and_holds_last() -> None:
    proof_stress = 100.0e6
    proof_strain = 0.005
    expected = proof_stress * (1.0 + proof_strain)
    replacement_delta = 0.494596e6
    raw_strain = np.asarray([0.0, 0.01, 0.02, 0.03])
    raw_stress = np.asarray(
        [
            0.0,
            (expected + replacement_delta) / 1.01,
            120.0e6,
            130.0e6,
        ]
    )
    source = Frame(
        {
            "strain_engineering": raw_strain,
            "stress_engineering": raw_stress,
        },
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )
    converted = apply(
        [
            Step(
                "tensile.true_plastic",
                {
                    "youngs_modulus": 8.0e9,
                    "proof_stress": proof_stress,
                    "proof_strain": proof_strain,
                    "negative_policy": "clip_zero",
                },
            )
        ],
        source,
    ).frame

    first = apply(
        [
            Step(
                "curve.sort_unique", {"x": "strain_true_plastic", "duplicate_policy": "first"}
            ),
            Step(
                "tensile.proof_anchor_guard",
                {"proof_stress": proof_stress, "proof_strain": proof_strain},
            ),
        ],
        converted,
    )
    assert first.stages[-1].scalars[-1].key == "proof_anchor_verified_code"
    np.testing.assert_allclose(first.frame.columns["stress_true"][0], expected)

    with pytest.raises(ProcessingError, match=r"494596"):
        apply(
            [
                Step(
                    "curve.sort_unique",
                    {"x": "strain_true_plastic", "duplicate_policy": "last"},
                ),
                Step(
                    "tensile.proof_anchor_guard",
                    {"proof_stress": proof_stress, "proof_strain": proof_strain},
                ),
            ],
            converted,
        )


def test_uniform_candidate_recipe_has_guarded_r36_stage_order_and_refs() -> None:
    payload = json.loads(RECIPE.read_text(encoding="utf-8"))
    assert payload["schema"] == "matnexus.tensile.uniform_true_plastic_candidate_v1/1"
    assert len(payload["recipes"]) == 1
    recipe = payload["recipes"][0]
    steps = recipe["steps"]
    ids = [step["plugin"] for step in steps]
    assert ids == [
        "tensile.engineering",
        "tensile.source_elastic_modulus_v2",
        "tensile.prepeak_prefix",
        "tensile.source_proof_stress",
        "curve.sort_unique",
        "tensile.strength",
        "tensile.necking_candidate",
        "tensile.plastic_domain",
        "tensile.true_plastic",
        "curve.sort_unique",
        "tensile.proof_anchor_guard",
        "curve.monotone",
        "curve.resample",
    ]
    for plugin_id in ids:
        registry.get(plugin_id)
    elastic_stage_ids = {
        "tensile.elastic_modulus",
        "tensile.source_elastic_modulus",
        "tensile.source_elastic_modulus_v2",
    }
    assert sum(plugin_id in elastic_stage_ids for plugin_id in ids) == 1

    assert steps[0]["options"] == {
        "gauge_length": "@specimen_gauge_length",
        "area": "@specimen_area",
    }
    assert steps[1]["options"] == {"policy": "auto_rows_v2"}
    assert steps[2]["options"] == {}
    assert steps[3]["options"] == {
        "policy": "first_positive_forward_v1",
        "youngs_modulus": "@youngs_modulus",
        "offset_strain": 0.002,
        "start_index": "@source_elastic_end_index",
        "search_start": "@elastic_window_end",
    }
    assert steps[4]["options"] == {
        "x": "strain_engineering",
        "duplicate_policy": "mean",
    }
    assert steps[7]["options"] == {
        "proof_strain": "@proof_strain",
        "proof_stress": "@proof_stress",
        "end_strain": "@necking_candidate_strain",
        "necking_limit": "@necking_candidate_strain",
    }
    true_options = steps[8]["options"]
    assert true_options["proof_stress"] == "@plastic_domain_proof_stress"
    assert true_options["proof_strain"] == "@plastic_domain_proof_strain"
    assert steps[9]["options"] == {
        "x": "strain_true_plastic",
        "duplicate_policy": "first",
    }
    guard_options = steps[10]["options"]
    assert guard_options["proof_stress"] == true_options["proof_stress"]
    assert guard_options["proof_strain"] == true_options["proof_strain"]
    assert steps[11]["options"] == {
        "column": "stress_true",
        "x": "strain_true_plastic",
        "method": "envelope",
        "strict": True,
        "step_ratio": 1e-6,
        "min_slope": 0.0,
    }
    assert steps[12]["options"] == {
        "x": "strain_true_plastic",
        "count": 300,
        "start": 0,
    }
    assert ids.index("tensile.proof_anchor_guard") < ids.index("curve.monotone")
    assert ids.index("curve.monotone") < ids.index("curve.resample")
    description = recipe["description"].lower()
    assert "uniform true-plastic candidate only" in description
    assert "not the polymer softening path" in description
    assert "no auto card approval" in description
    assert "order_evidence_code=1" in description
    assert "force_peak_match_code=1" in description
    assert "final-output adoption review" in description
    assert "remaining monotone lift" in description
