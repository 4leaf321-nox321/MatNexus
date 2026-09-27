"""Contract tests for the opt-in numerical-to-card-review boundary."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Scalar, Step, StepResult, apply

EXTENSIONS = Path(__file__).resolve().parents[1]
RECIPES = EXTENSIONS / "tensile_extras" / "recipes"
extensions.load(EXTENSIONS)
processing.load_builtin()

PLUGIN_ID = "tensile.card_review_evidence_v1"
OPTION_KEYS = (
    "model_card_changed_points",
    "card_domain_beyond_source_neck",
    "card_domain_effect_info_known",
    "card_domain_effect_truncated",
    "monotone_points",
    "monotone_max_lift",
)
OUTPUT_KEYS = (
    "card_review_required_code",
    "card_review_model_edit_code",
    "card_review_scope_code",
    "card_review_monotone_adjust_code",
    "card_review_observed_risk_code",
)


def _frame() -> Frame:
    return Frame(
        {
            "strain_true_plastic": np.array([0.0, 0.1, 0.2]),
            "stress_true": np.array([1.0, 2.0, 3.0]),
        },
        {"strain_true_plastic": "1", "stress_true": "Pa"},
    )


def _options(**overrides: float) -> dict[str, float]:
    options: dict[str, float] = {
        "model_card_changed_points": 0.0,
        "card_domain_beyond_source_neck": 0.0,
        "card_domain_effect_info_known": 1.0,
        "card_domain_effect_truncated": 0.0,
        "monotone_points": 0.0,
        "monotone_max_lift": 0.0,
    }
    options.update(overrides)
    return options


def _direct(options: dict[str, float]) -> StepResult:
    return registry.get(PLUGIN_ID).fn(_frame(), options)


def _values(scalars: tuple[Scalar, ...]) -> dict[str, float]:
    return {item.key: item.value for item in scalars}


def test_registration_declares_order_refs_and_unit_one_outputs() -> None:
    plugin = registry.get(PLUGIN_ID)

    assert plugin.kind == "processing"
    assert plugin.order == 94
    assert plugin.version == "1"
    assert registry.get("curve.monotone").order < plugin.order
    assert plugin.order < registry.get("curve.resample").order
    assert plugin.meta["candidate_only"] is True
    assert plugin.meta["scope"] == "uniform_true_plastic_card"

    params = {param.name: param for param in plugin.params}
    assert tuple(params) == OPTION_KEYS
    assert all(params[name].required for name in OPTION_KEYS)
    assert all(params[name].default == f"@{name}" for name in OPTION_KEYS)

    values = {item.key: item for item in plugin.makes_values}
    assert tuple(values) == OUTPUT_KEYS
    assert all(item.si_unit == "1" for item in values.values())
    help_text = " ".join(item.help or "" for item in values.values()).lower()
    assert "card/material/solver approval" in help_text
    assert "absolute change" in help_text
    assert "positive lift" in help_text
    assert "model stress changed but effect scope metadata absent" in help_text


def test_prepare_options_wires_all_upstream_scalars_and_rejects_unknown() -> None:
    plugin = registry.get(PLUGIN_ID)
    assert plugin.prepare_options is not None
    assert plugin.prepare_options({}) == {name: f"@{name}" for name in OPTION_KEYS}

    with pytest.raises(ProcessingError, match="알 수 없는 옵션"):
        plugin.prepare_options({"unexpected": 0.0})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("model_card_changed_points", 0.0),
        ("card_domain_effect_info_known", "@card_domain_beyond_source_neck"),
    ],
)
def test_prepare_options_rejects_literal_or_wrong_upstream_reference(
    name: str, value: object
) -> None:
    plugin = registry.get(PLUGIN_ID)
    assert plugin.prepare_options is not None
    with pytest.raises(ProcessingError, match="upstream 참조"):
        plugin.prepare_options({name: value})


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {},
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 0.0,
                "card_review_scope_code": 0.0,
                "card_review_monotone_adjust_code": 0.0,
                "card_review_observed_risk_code": 0.0,
            },
        ),
        (
            {"model_card_changed_points": 2.0},
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 1.0,
                "card_review_scope_code": 0.0,
                "card_review_monotone_adjust_code": 0.0,
                "card_review_observed_risk_code": 1.0,
            },
        ),
        (
            {"card_domain_beyond_source_neck": 1.0},
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 0.0,
                "card_review_scope_code": 1.0,
                "card_review_monotone_adjust_code": 0.0,
                "card_review_observed_risk_code": 1.0,
            },
        ),
        (
            {"card_domain_effect_info_known": 0.0},
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 0.0,
                "card_review_scope_code": 0.0,
                "card_review_monotone_adjust_code": 0.0,
                "card_review_observed_risk_code": 0.0,
            },
        ),
        (
            {"model_card_changed_points": 1.0, "card_domain_effect_info_known": 0.0},
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 1.0,
                "card_review_scope_code": 1.0,
                "card_review_monotone_adjust_code": 0.0,
                "card_review_observed_risk_code": 1.0,
            },
        ),
        (
            {"card_domain_effect_truncated": 1.0},
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 0.0,
                "card_review_scope_code": 1.0,
                "card_review_monotone_adjust_code": 0.0,
                "card_review_observed_risk_code": 1.0,
            },
        ),
        (
            {"monotone_points": 3.0, "monotone_max_lift": 1.0},
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 0.0,
                "card_review_scope_code": 0.0,
                "card_review_monotone_adjust_code": 1.0,
                "card_review_observed_risk_code": 1.0,
            },
        ),
        (
            {
                "model_card_changed_points": 1.0,
                "card_domain_beyond_source_neck": 1.0,
                "card_domain_effect_info_known": 0.0,
                "card_domain_effect_truncated": 1.0,
                "monotone_points": 1.0,
                "monotone_max_lift": 2.0,
            },
            {
                "card_review_required_code": 1.0,
                "card_review_model_edit_code": 1.0,
                "card_review_scope_code": 1.0,
                "card_review_monotone_adjust_code": 1.0,
                "card_review_observed_risk_code": 1.0,
            },
        ),
    ],
)
def test_cause_flags_are_explicit_or_zero(
    overrides: dict[str, float], expected: dict[str, float]
) -> None:
    result = _direct(_options(**overrides))
    assert _values(result.scalars) == expected


def test_stage_returns_exact_same_frame_and_keeps_notes_boundary_explicit() -> None:
    frame = _frame()
    before = {key: value.copy() for key, value in frame.columns.items()}

    result = registry.get(PLUGIN_ID).fn(
        frame, _options(monotone_points=2.0, monotone_max_lift=1.0)
    )

    stage = result
    assert stage.frame is frame
    for key, value in before.items():
        np.testing.assert_array_equal(stage.frame.columns[key], value)
    notes = " ".join(stage.notes).lower()
    assert "model stress changed but effect scope metadata absent" in notes
    assert "0 is not card/material/solver approval" in notes
    assert "absolute change diagnostic, not positive lift" in notes


def test_refs_resolve_from_given_scalars() -> None:
    given = tuple(
        Scalar(name, name, value, "1")
        for name, value in (
            ("model_card_changed_points", 1.0),
            ("card_domain_beyond_source_neck", 0.0),
            ("card_domain_effect_info_known", 1.0),
            ("card_domain_effect_truncated", 0.0),
            ("monotone_points", 1.0),
            ("monotone_max_lift", 2.0),
        )
    )
    result = apply([Step(PLUGIN_ID, {})], _frame(), given=given)
    assert _values(result.stages[-1].scalars)["card_review_observed_risk_code"] == 1.0
    assert result.stages[-1].options == {
        name: value
        for name, value in (
            ("model_card_changed_points", 1.0),
            ("card_domain_beyond_source_neck", 0.0),
            ("card_domain_effect_info_known", 1.0),
            ("card_domain_effect_truncated", 0.0),
            ("monotone_points", 1.0),
            ("monotone_max_lift", 2.0),
        )
    }


@pytest.mark.parametrize("missing", OPTION_KEYS)
def test_missing_upstream_value_fails_closed(missing: str) -> None:
    options = _options()
    options.pop(missing)
    with pytest.raises(ProcessingError):
        _direct(options)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("model_card_changed_points", -1.0),
        ("model_card_changed_points", 1.5),
        ("card_domain_beyond_source_neck", 0.5),
        ("card_domain_effect_info_known", 2.0),
        ("card_domain_effect_truncated", np.nan),
        ("monotone_points", -1.0),
        ("monotone_points", 1.5),
        ("monotone_max_lift", -1.0),
        ("monotone_max_lift", np.inf),
    ],
)
def test_invalid_upstream_value_fails_closed(name: str, value: float) -> None:
    options = _options()
    options[name] = value
    with pytest.raises(ProcessingError):
        _direct(options)


@pytest.mark.parametrize(
    ("points", "max_lift"),
    [(0.0, 1.0), (1.0, 0.0), (0.0, 1e-12)],
)
def test_monotone_count_and_absolute_change_must_agree(points: float, max_lift: float) -> None:
    options = _options(monotone_points=points, monotone_max_lift=max_lift)
    with pytest.raises(ProcessingError, match="일관되지 않습니다"):
        _direct(options)


def test_tiny_nonzero_monotone_adjustment_is_accepted() -> None:
    result = _direct(
        _options(
            model_card_changed_points=1.0,
            monotone_points=1.0,
            monotone_max_lift=1e-16,
        )
    )
    values = _values(result.scalars)
    assert values["card_review_model_edit_code"] == 1.0
    assert values["card_review_monotone_adjust_code"] == 1.0
    assert values["card_review_observed_risk_code"] == 1.0


@pytest.mark.parametrize("profile", ["uniform", "tail"])
def test_v4_recipes_insert_only_the_boundary_step_after_monotone(profile: str) -> None:
    v3 = json.loads(
        (RECIPES / f"source_order_{profile}_v3_examples.json").read_text(encoding="utf-8")
    )
    v4 = json.loads(
        (RECIPES / f"source_order_{profile}_v4_examples.json").read_text(encoding="utf-8")
    )

    assert v4["schema"] == f"matnexus.tensile.source_order_{profile}_v4_examples/1"
    assert len(v4["recipes"]) == len(v3["recipes"]) == 7
    assert "card-review" in v4["description"].lower()
    assert "not material-card approved" in v4["description"].lower()
    assert "solver approval" in v4["description"].lower()
    assert "not defaults" in v4["description"].lower()

    for old, new in zip(v3["recipes"], v4["recipes"], strict=True):
        assert new["key"] == old["key"].replace("_v3_", "_v4_")
        assert new["test_type_key"] == old["test_type_key"]
        old_monotone = next(
            index
            for index, step in enumerate(old["steps"])
            if step["plugin"] == "curve.monotone"
        )
        new_monotone = next(
            index
            for index, step in enumerate(new["steps"])
            if step["plugin"] == "curve.monotone"
        )
        assert new_monotone == old_monotone
        assert new["steps"][: new_monotone + 1] == old["steps"][: old_monotone + 1]
        assert new["steps"][new_monotone + 1] == {
            "plugin": PLUGIN_ID,
            "options": {},
        }
        assert new["steps"][new_monotone + 2 :] == old["steps"][old_monotone + 1 :]
        for step in new["steps"]:
            registry.get(step["plugin"])
