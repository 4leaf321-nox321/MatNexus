"""The effective card domain follows model support without rewriting measurements."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Scalar, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
EXTENSION_ROOT = EXTENSIONS / "tensile_extras"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "stable_band_model_v1_cases.npz"
SOURCE_EXAMPLES = EXTENSION_ROOT / "recipes" / "source_measurement_model_v2_examples.json"
EXAMPLES = EXTENSION_ROOT / "recipes" / "effective_card_domain_v1_examples.json"

UNIFORM = "uniform_measured_v1"
AUTO = "effective_engineering_model_auto_v1"
MANUAL = "manual_observed_end_v1"
ASSUMPTION = "effective_engineering_to_true_uniform_v1"
METHODS = (
    "lower_envelope",
    "isotonic",
    "median_plateau",
    "linear",
    "least_squares",
    "robust_linear",
)

extensions.load(EXTENSIONS)
processing.load_builtin()
effect_module = import_module("matnexus_ext.tensile_extras.model_effect")
band_module = import_module("matnexus_ext.tensile_extras.band_model")


def _frame(
    strain: Any | None = None,
    stress: Any | None = None,
    *,
    extra: dict[str, Any] | None = None,
) -> Frame:
    x = np.asarray(
        np.arange(8, dtype=np.float64) * 0.01 if strain is None else strain,
        dtype=np.float64,
    )
    y = np.asarray(
        np.arange(8, dtype=np.float64) * 100e6 if stress is None else stress,
        dtype=np.float64,
    )
    columns: dict[str, np.ndarray] = {
        "strain_engineering": x.copy(),
        "stress_engineering": y.copy(),
        "displacement": x.copy(),
        "force": y.copy(),
        "source_row": np.arange(x.size, dtype=np.int64),
        "marker": np.arange(x.size, dtype=np.float64) * 2.0,
    }
    if extra:
        columns.update({key: np.asarray(value) for key, value in extra.items()})
    units = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "displacement": "m",
        "force": "N",
        "source_row": "1",
        "marker": "1",
    }
    units.update({key: "1" for key in (extra or {})})
    return Frame(columns, units)


def _stable_frame(case_index: int) -> Frame:
    prefix = f"c{case_index:03d}_"
    with np.load(FIXTURE, allow_pickle=False) as archive:
        columns = {
            "strain_engineering": archive[f"{prefix}x"].copy(),
            "stress_engineering": archive[f"{prefix}y"].copy(),
            "time": archive[f"{prefix}time"].copy(),
            "source_row": archive[f"{prefix}row"].copy(),
            "displacement": archive[f"{prefix}displacement_m"].copy(),
            "force": archive[f"{prefix}force_N"].copy(),
            "prepared_row": archive[f"{prefix}prepared_row"].copy(),
        }
        for key in archive.files:
            if key.startswith(prefix + "source_") and key not in columns:
                columns[key.removeprefix(prefix)] = archive[key].copy()
    units = {
        "strain_engineering": "1",
        "stress_engineering": "Pa",
        "time": "s",
        "source_row": "1",
        "displacement": "m",
        "force": "N",
        "prepared_row": "1",
    }
    units.update({key: "1" for key in columns if key not in units})
    return Frame(columns, units)


def _given(
    frame: Frame,
    *,
    proof_index: int = 1,
    necking_strain: float | None = None,
    necking_index: int = 4,
) -> list[Scalar]:
    strain = frame.columns["strain_engineering"]
    stress = frame.columns["stress_engineering"]
    neck = float(strain[necking_index]) if necking_strain is None else necking_strain
    return [
        Scalar(
            "model_proof_strain",
            "모델 proof 변형률",
            float(strain[proof_index]),
            "1",
            "strain",
        ),
        Scalar("model_proof_stress", "모델 proof 응력", float(stress[proof_index]), "Pa"),
        Scalar("necking_candidate_strain", "네킹 후보 변형률", neck, "1", "strain"),
    ]


def _effect_scalars(frame: Frame, index: int) -> list[Scalar]:
    strain = frame.columns["strain_engineering"]
    return [
        Scalar("model_card_effect_end_index", "모델 영향 끝 행", float(index), "1"),
        Scalar(
            "model_card_effect_end_strain",
            "모델 영향 끝 변형률",
            0.0 if index < 0 else float(strain[index]),
            "1",
            "strain",
        ),
        Scalar("model_card_input_points", "모델 입력 관측점 수", float(len(strain)), "1"),
    ]


def _run(
    frame: Frame,
    options: dict[str, Any] | None = None,
    *,
    given: list[Scalar] | None = None,
) -> processing.PipelineResult:
    return processing.apply(
        [Step("tensile.effective_card_domain", options or {})], frame, given=given or []
    )


def _values(stage: processing.Stage) -> dict[str, float]:
    return {scalar.key: scalar.value for scalar in stage.scalars}


def _auto_metadata(frame: Frame, index: int) -> dict[str, Any]:
    strain = frame.columns["strain_engineering"]
    return {
        "effect_end_index": index,
        "effect_end_strain": 0.0 if index < 0 else float(strain[index]),
        "model_input_points": len(strain),
    }


class TestRegistration:
    def test_registers_modes_references_and_preserved_plastic_domain_outputs(self) -> None:
        plugin = registry.get("tensile.effective_card_domain")

        assert plugin.kind == "processing"
        assert plugin.order == 87
        assert plugin.version == "1"
        assert plugin.applies_to == ("tensile",)
        assert plugin.requires_channels == (("displacement",), ("force",))
        assert registry.get("tensile.model_anchor").order < plugin.order
        assert registry.get("tensile.true_plastic").order > plugin.order
        params = {param.name: param for param in plugin.params}
        assert params["policy"].default == UNIFORM
        assert params["policy"].choices == (UNIFORM, AUTO, MANUAL)
        assert params["coordinate_assumption"].choices == (ASSUMPTION,)
        assert "시뮬레이션 근사" in (params["coordinate_assumption"].help or "")
        assert params["end_index"].when == {"policy": (MANUAL,)}
        assert params["effect_end_index"].when == {"policy": (AUTO, MANUAL)}

        assert plugin.prepare_options is not None
        uniform = plugin.prepare_options({})
        assert uniform == {
            "policy": UNIFORM,
            "coordinate_assumption": ASSUMPTION,
            "proof_strain": "@model_proof_strain",
            "proof_stress": "@model_proof_stress",
            "source_necking_strain": "@necking_candidate_strain",
            "strain": "strain_engineering",
            "stress": "stress_engineering",
        }
        automatic = plugin.prepare_options({"policy": AUTO})
        assert automatic["effect_end_index"] == "@model_card_effect_end_index"
        assert automatic["effect_end_strain"] == "@model_card_effect_end_strain"
        assert automatic["model_input_points"] == "@model_card_input_points"
        assert all(name not in uniform for name in _auto_metadata(_frame(), 2))

        values = {one.key for one in plugin.makes_values}
        assert {
            "plastic_domain_input_points",
            "plastic_domain_support_points",
            "plastic_domain_output_points",
            "plastic_domain_inserted_points",
            "plastic_domain_proof_inserted",
            "plastic_domain_end_inserted",
            "plastic_domain_proof_strain",
            "plastic_domain_proof_stress",
            "plastic_domain_end_strain",
            "plastic_domain_necking_limit",
            "card_domain_source_necking_strain",
            "card_domain_end_index",
            "card_domain_end_strain",
            "card_domain_end_stress",
            "card_domain_effect_end_index",
            "card_domain_effect_end_strain",
            "card_domain_effect_info_known",
            "card_domain_beyond_source_neck",
            "card_domain_effect_truncated",
            "card_domain_effect_truncation_deliberate",
            "card_domain_model_input_points",
            "card_domain_last_input_strain",
        } <= values

    def test_both_model_steps_register_all_common_effect_references(self) -> None:
        expected = {
            "model_card_input_points",
            "model_card_changed_points",
            "model_card_last_changed_index",
            "model_card_effect_end_index",
            "model_card_effect_end_strain",
            "model_card_support_kind",
        }
        for name, version in (("tensile.band_model", "3"), ("tensile.model_curve", "2")):
            plugin = registry.get(name)
            assert plugin.version == version
            assert expected <= {one.key for one in plugin.makes_values}

    def test_new_examples_preserve_every_non_domain_v2_stage(self) -> None:
        source = json.loads(SOURCE_EXAMPLES.read_text(encoding="utf-8"))
        examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))

        assert source["schema"] == "matnexus.tensile.source_measurement_model_v2_examples/1"
        assert examples["schema"] == "matnexus.tensile.effective_card_domain_v1_examples/1"
        assert len(source["recipes"]) == len(examples["recipes"]) == 7
        assert len({recipe["key"] for recipe in examples["recipes"]}) == 7
        for old, new in zip(source["recipes"], examples["recipes"], strict=True):
            assert new["key"].startswith("r19_effective_card_domain_v1_")
            assert new["label"].startswith("R19 ")
            assert new["test_type_key"] == old["test_type_key"]
            assert len(new["steps"]) == len(old["steps"])
            for old_step, new_step in zip(old["steps"], new["steps"], strict=True):
                if old_step["plugin"] == "tensile.plastic_domain":
                    assert new_step == {
                        "plugin": "tensile.effective_card_domain",
                        "options": {
                            "policy": AUTO,
                            "coordinate_assumption": ASSUMPTION,
                        },
                    }
                else:
                    assert new_step == old_step


class TestDomain:
    @pytest.mark.parametrize("necking_strain", [0.04, 0.045])
    def test_default_is_exact_old_source_necking_domain_and_keeps_its_scalars(
        self, necking_strain: float
    ) -> None:
        frame = _frame()
        original = {key: values.copy() for key, values in frame.columns.items()}
        given = _given(frame, necking_strain=necking_strain)

        old = processing.apply([Step("tensile.plastic_domain", {})], frame, given=given)
        new = _run(frame, given=given)

        assert new.frame.length() == old.frame.length()
        for key in old.frame.columns:
            np.testing.assert_array_equal(new.frame.columns[key], old.frame.columns[key])
        old_values = _values(old.stages[-1])
        new_values = _values(new.stages[-1])
        for key, value in old_values.items():
            assert new_values[key] == value
        assert new_values["card_domain_end_index"] == (4.0 if necking_strain == 0.04 else -1.0)
        assert new_values["card_domain_end_strain"] == necking_strain
        assert new_values["card_domain_effect_info_known"] == 0.0
        assert new_values["card_domain_effect_end_index"] == -1.0
        assert new_values["card_domain_effect_end_strain"] == 0.0
        assert new_values["card_domain_beyond_source_neck"] == 0.0
        assert "source_necking_strain" in new.stages[-1].options
        assert "end_strain" not in new.stages[-1].options
        assert "necking_limit" not in new.stages[-1].options
        for key, values in original.items():
            np.testing.assert_array_equal(frame.columns[key], values)

    def test_auto_extends_through_validated_effect_end_and_replays_resolved_inputs(
        self,
    ) -> None:
        frame = _frame()
        given = [*_given(frame), *_effect_scalars(frame, 6)]

        result = _run(frame, {"policy": AUTO}, given=given)
        stage = result.stages[-1]
        values = _values(stage)

        assert stage.frame.columns["strain_engineering"][-1] == 0.06
        assert stage.frame.columns["stress_engineering"][-1] == 600e6
        assert values["card_domain_source_necking_strain"] == 0.04
        assert values["card_domain_end_index"] == 6.0
        assert values["card_domain_end_strain"] == 0.06
        assert values["card_domain_effect_end_index"] == 6.0
        assert values["card_domain_effect_info_known"] == 1.0
        assert values["card_domain_beyond_source_neck"] == 1.0
        assert values["card_domain_effect_truncated"] == 0.0
        assert "측정된 국부 응력" in " ".join(stage.notes)
        assert stage.options == {
            "policy": AUTO,
            "coordinate_assumption": ASSUMPTION,
            "proof_strain": 0.01,
            "proof_stress": 100e6,
            "source_necking_strain": 0.04,
            "effect_end_index": 6,
            "effect_end_strain": 0.06,
            "model_input_points": 8,
            "strain": "strain_engineering",
            "stress": "stress_engineering",
        }
        assert "end_strain" not in stage.options
        assert "necking_limit" not in stage.options

        replay = _run(frame, stage.options)
        for key in stage.frame.columns:
            np.testing.assert_array_equal(replay.frame.columns[key], stage.frame.columns[key])
        assert _values(replay.stages[-1]) == values

    @pytest.mark.parametrize(
        ("end_index", "expected_truncated", "expected_deliberate"),
        [(7, 0.0, 0.0), (4, 1.0, 1.0)],
    )
    def test_manual_inclusive_endpoint_reports_full_or_deliberately_truncated_effect(
        self, end_index: int, expected_truncated: float, expected_deliberate: float
    ) -> None:
        frame = _frame()
        result = _run(
            frame,
            {"policy": MANUAL, "end_index": end_index, **_auto_metadata(frame, 6)},
            given=_given(frame),
        )
        values = _values(result.stages[-1])

        assert values["card_domain_end_index"] == float(end_index)
        assert values["card_domain_end_strain"] == float(
            frame.columns["strain_engineering"][end_index]
        )
        assert values["card_domain_effect_truncated"] == expected_truncated
        assert values["card_domain_effect_truncation_deliberate"] == expected_deliberate
        assert result.stages[-1].options["end_index"] == end_index
        assert (
            result.frame.columns["strain_engineering"][-1]
            == frame.columns["strain_engineering"][end_index]
        )

    def test_model_noop_uses_sentinel_and_effect_auto_keeps_source_cap(self) -> None:
        frame = _frame(
            [0.0, 0.01, 0.02, 0.03],
            [1.0, 2.0, 2.0, 5.0],
        )
        given = [
            Scalar("model_proof_strain", "모델 proof 변형률", 0.0, "1", "strain"),
            Scalar("model_proof_stress", "모델 proof 응력", 1.0, "Pa"),
            Scalar("necking_candidate_strain", "네킹 후보 변형률", 0.02, "1", "strain"),
        ]
        result = processing.apply(
            [
                Step("tensile.model_curve", {}),
                Step("tensile.effective_card_domain", {"policy": AUTO}),
            ],
            frame,
            given=given,
        )
        model_values = _values(result.stages[0])
        card_values = _values(result.stages[1])

        assert model_values["model_card_changed_points"] == 0.0
        assert model_values["model_card_effect_end_index"] == -1.0
        assert model_values["model_card_effect_end_strain"] == 0.0
        assert model_values["model_card_support_kind"] == 0.0
        assert card_values["card_domain_effect_end_index"] == -1.0
        assert card_values["card_domain_end_strain"] == 0.02
        assert result.frame.columns["strain_engineering"][-1] == 0.02

    def test_closure_ends_after_last_change_before_input_end_and_last_row_edit_is_capped(
        self,
    ) -> None:
        before_end = _frame(
            [0.0, 0.01, 0.02, 0.03, 0.04, 0.05],
            [1.0, 4.0, 3.0, 2.0, 5.0, 6.0],
        )
        first = processing.apply([Step("tensile.model_curve", {})], before_end)
        values = _values(first.stages[-1])
        assert values["model_card_last_changed_index"] == 3.0
        assert values["model_card_effect_end_index"] == 4.0
        assert values["model_card_effect_end_strain"] == 0.04
        assert (
            values["model_card_effect_end_index"]
            < len(before_end.columns["strain_engineering"]) - 1
        )

        last_row = _frame([0.0, 0.01, 0.02, 0.03], [1.0, 4.0, 3.0, 2.0])
        second = processing.apply([Step("tensile.model_curve", {})], last_row)
        last_values = _values(second.stages[-1])
        assert last_values["model_card_last_changed_index"] == 3.0
        assert last_values["model_card_effect_end_index"] == 3.0
        assert last_values["model_card_effect_end_strain"] == 0.03

    def test_declared_selected_support_is_kept_even_when_nothing_changed(self) -> None:
        strain = np.arange(6, dtype=np.float64) * 0.01
        stress = np.arange(6, dtype=np.float64) * 100.0
        values = effect_module.effect_scalars(
            strain, stress, stress.copy(), supports=(), selected_end=4
        )
        got = {one.key: one.value for one in values}

        assert got["model_card_changed_points"] == 0.0
        assert got["model_card_last_changed_index"] == -1.0
        assert got["model_card_effect_end_index"] == 4.0
        assert got["model_card_effect_end_strain"] == strain[4]
        assert got["model_card_support_kind"] == 2.0

    def test_later_disjoint_event_right_support_controls_effect_end(self) -> None:
        frame = _stable_frame(4)
        source = frame.columns["stress_engineering"].copy()
        strain = frame.columns["strain_engineering"]
        computation = band_module.compute_band_model(
            strain,
            source,
            frame.columns["time"],
            method="least_squares",
            policy="band_and_events_auto_v1",
        )
        result = processing.apply(
            [
                Step(
                    "tensile.band_model",
                    {"policy": "band_and_events_auto_v1", "method": "least_squares"},
                )
            ],
            frame,
        )
        values = _values(result.stages[-1])
        changed = computation.values != source
        changed_rows = np.flatnonzero(changed)
        closure = min(int(changed_rows[-1]) + 1, len(source) - 1) if changed_rows.size else -1
        declared_ends = [
            record.right_anchor
            for record in computation.records
            if record.proposal is not None
            and record.left_anchor is not None
            and np.any(
                computation.values[record.left_anchor : record.right_anchor + 1]
                != source[record.left_anchor : record.right_anchor + 1]
            )
        ]
        selected_end = (
            computation.model_end_row
            if computation.model_end_row is not None
            else computation.selection.band_end_row
        )
        expected_end = max(
            [closure, *declared_ends, *([selected_end] if selected_end is not None else [])]
        )

        assert len(declared_ends) > 1
        assert selected_end is not None
        assert expected_end > selected_end
        assert values["model_card_effect_end_index"] == float(expected_end)
        assert values["model_card_effect_end_strain"] == strain[expected_end]
        assert values["model_card_support_kind"] == 2.0

    @pytest.mark.parametrize("method", (*METHODS, "upper_envelope_auto_v1"))
    def test_all_successful_model_methods_feed_the_same_domain_contract(
        self, method: str
    ) -> None:
        frame = _stable_frame(0)
        strain = frame.columns["strain_engineering"]
        stress = frame.columns["stress_engineering"]
        given = _given(frame, proof_index=20, necking_strain=float(strain[500]))
        if method == "upper_envelope_auto_v1":
            model = Step("tensile.model_curve", {})
        else:
            model = Step(
                "tensile.band_model",
                {"policy": "band_and_events_auto_v2", "method": method},
            )

        result = processing.apply(
            [model, Step("tensile.effective_card_domain", {"policy": AUTO})],
            frame,
            given=given,
        )
        model_values = _values(result.stages[0])
        card_values = _values(result.stages[1])
        effect_end = int(model_values["model_card_effect_end_index"])

        assert isinstance(result.stages[1].frame, Frame)
        assert card_values["card_domain_effect_info_known"] == 1.0
        assert card_values["card_domain_end_index"] == float(effect_end)
        assert result.stages[1].frame.columns["strain_engineering"][-1] == strain[effect_end]
        assert card_values["card_domain_beyond_source_neck"] == 1.0
        assert card_values["card_domain_effect_truncated"] == 0.0
        if method != "upper_envelope_auto_v1":
            model_start = int(model_values["band_model_band_start_index"])
            model_end = int(model_values["band_model_band_end_index"])
            # This fixture's band begins after proof; the wrapper does not enforce this.
            assert 20 < model_start <= model_end <= effect_end
        modeled = result.stages[0].frame.columns["stress_engineering"]
        changed_after_proof = np.flatnonzero(
            (modeled != stress) & (np.arange(len(stress)) > 20)
        )
        assert not changed_after_proof.size or int(changed_after_proof[-1]) <= effect_end

    def test_terminal_crop_prevents_removed_tail_from_returning(self) -> None:
        frame = _frame(
            np.arange(8, dtype=np.float64) * 0.01,
            [0.0, 100e6, 200e6, 300e6, 400e6, 350e6, 600e6, 700e6],
        )
        retained = processing.apply(
            [Step("tensile.terminal_domain", {"policy": "manual_end_v1", "end_index": 5})],
            frame,
        ).frame
        given = [
            Scalar("model_proof_strain", "모델 proof 변형률", 0.01, "1", "strain"),
            Scalar("model_proof_stress", "모델 proof 응력", 100e6, "Pa"),
            Scalar("necking_candidate_strain", "네킹 후보 변형률", 0.03, "1", "strain"),
        ]
        result = processing.apply(
            [
                Step("tensile.model_curve", {}),
                Step("tensile.effective_card_domain", {"policy": AUTO}),
            ],
            retained,
            given=given,
        )

        values = _values(result.stages[-1])
        assert retained.columns["strain_engineering"][-1] == 0.05
        assert result.frame.columns["strain_engineering"][-1] == 0.05
        assert values["card_domain_last_input_strain"] == 0.05
        assert (
            values["card_domain_end_index"] <= len(retained.columns["strain_engineering"]) - 1
        )
        assert 0.06 not in result.frame.columns["strain_engineering"]


class TestValidation:
    @pytest.mark.parametrize(
        ("options", "message"),
        [
            ({"policy": AUTO, "effect_end_index": 6}, "세 항목을 함께"),
            ({"policy": UNIFORM, "effect_end_index": 6}, "세 항목을 함께"),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": 6.5,
                    "effect_end_strain": 0.06,
                    "model_input_points": 8,
                },
                "정수",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": 6,
                    "effect_end_strain": 0.06,
                    "model_input_points": 7,
                },
                "행 수와 다릅니다",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": 6,
                    "effect_end_strain": 0.060000000000000005,
                    "model_input_points": 8,
                },
                "일치하지 않습니다",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": 8,
                    "effect_end_strain": 0.07,
                    "model_input_points": 8,
                },
                "범위 밖",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": -1,
                    "effect_end_strain": 0.01,
                    "model_input_points": 8,
                },
                "strain 0",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": 6,
                    "effect_end_strain": 0.06,
                    "model_input_points": 8,
                    "end_index": 7,
                },
                "에서만",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": True,
                    "effect_end_strain": 0.06,
                    "model_input_points": 8,
                },
                "유한한 실수",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": 6,
                    "effect_end_strain": 0.06,
                    "model_input_points": 8,
                    "coordinate_assumption": "measured_local_true_stress_v1",
                },
                "coordinate_assumption",
            ),
            (
                {
                    "policy": AUTO,
                    "effect_end_index": 6,
                    "effect_end_strain": 0.06,
                    "model_input_points": 8,
                    "end_strain": 0.06,
                },
                "지원하지 않는",
            ),
        ],
    )
    def test_rejects_partial_or_inconsistent_effect_metadata_and_unknown_options(
        self, options: dict[str, Any], message: str
    ) -> None:
        frame = _frame()
        with pytest.raises(ProcessingError, match=message):
            _run(frame, options, given=_given(frame))

    def test_rejects_boolean_numeric_values_and_inapplicable_or_missing_manual_index(
        self,
    ) -> None:
        frame = _frame()
        effect = _auto_metadata(frame, 6)
        with pytest.raises(ProcessingError, match=r"proof_strain.*유한한 실수"):
            _run(
                frame,
                {"proof_strain": True, "policy": AUTO, **effect},
                given=_given(frame),
            )
        with pytest.raises(ProcessingError, match="end_index 가 필요"):
            _run(frame, {"policy": MANUAL, **effect}, given=_given(frame))
        with pytest.raises(ProcessingError, match="정수"):
            _run(
                frame,
                {"policy": MANUAL, "end_index": 4.5, **effect},
                given=_given(frame),
            )
        with pytest.raises(ProcessingError, match="범위 밖"):
            _run(
                frame,
                {"policy": MANUAL, "end_index": 8, **effect},
                given=_given(frame),
            )
        with pytest.raises(ProcessingError, match="proof 변형률 뒤"):
            _run(
                frame,
                {"policy": MANUAL, "end_index": 1, **effect},
                given=_given(frame),
            )

    def test_source_neck_must_remain_inside_the_current_model_frame(self) -> None:
        frame = _frame()
        with pytest.raises(ProcessingError, match="자동으로 자르지 않습니다"):
            _run(
                frame,
                {"source_necking_strain": 0.08},
                given=_given(frame),
            )

    def test_delegated_proof_match_and_minimum_support_guards_remain_active(self) -> None:
        frame = _frame()
        with pytest.raises(ProcessingError, match="일치하지 않습니다"):
            _run(
                frame,
                {"proof_stress": 101e6},
                given=_given(frame),
            )
        with pytest.raises(ProcessingError, match="최소 2개"):
            _run(
                frame,
                {
                    "proof_strain": 0.02,
                    "proof_stress": 200e6,
                    "source_necking_strain": 0.03,
                },
                given=_given(frame),
            )
