"""Endpoint-preserving engineering domain for paired-proof plastic conversion."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Scalar, Step

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = ROOT / "extensions"
PC2_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "oxford_pc_fig5_50mm_min_test2.csv"
)
EXAMPLES = (
    EXTENSIONS / "tensile_extras" / "recipes" / "adaptive_plastic_domain_v1_examples.json"
)
extensions.load(EXTENSIONS)
processing.load_builtin()


def _frame(
    strain: list[float] | np.ndarray,
    stress: list[float] | np.ndarray,
    *,
    extra: dict[str, list[float] | np.ndarray] | None = None,
    units: dict[str, str] | None = None,
) -> Frame:
    columns: dict[str, np.ndarray] = {
        "strain_engineering": np.asarray(strain),
        "stress_engineering": np.asarray(stress),
    }
    if extra:
        columns.update({key: np.asarray(values) for key, values in extra.items()})
    unit_map = {"strain_engineering": "1", "stress_engineering": "Pa"}
    if extra:
        unit_map.update({key: "1" for key in extra})
    if units:
        unit_map.update(units)
    return Frame(columns, unit_map)


def _given(proof_strain: float, proof_stress: float, necking_strain: float) -> list[Scalar]:
    return [
        Scalar("model_proof_strain", "모델 소성 시작 변형률", proof_strain, "1", "strain"),
        Scalar("model_proof_stress", "모델 소성 시작 응력", proof_stress, "Pa"),
        Scalar("necking_candidate_strain", "네킹 후보 변형률", necking_strain, "1", "strain"),
    ]


def _run(
    frame: Frame,
    *,
    options: dict[str, object] | None = None,
    given: list[Scalar] | None = None,
) -> processing.PipelineResult:
    return processing.apply(
        [Step("tensile.plastic_domain", options or {})], frame, given=given or []
    )


def _values(stage: processing.Stage) -> dict[str, float]:
    return {one.key: one.value for one in stage.scalars}


def _pc2_raw_frame() -> Frame:
    with PC2_FIXTURE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    displacement_mm = np.asarray([float(row["displacement_mm"]) for row in rows])
    return Frame(
        {
            "displacement": displacement_mm * 1e-3,
            "force": np.asarray([float(row["force_N"]) for row in rows]),
            "time": np.asarray([float(row["time_s"]) for row in rows]),
            "source_excel_row": np.asarray([int(row["source_excel_row"]) for row in rows]),
        },
        {"displacement": "m", "force": "N", "time": "s", "source_excel_row": "1"},
    )


class Test등록:
    def test_확장로더_등록과_기본참조를_확인한다(self) -> None:
        plugin = registry.get("tensile.plastic_domain")

        assert plugin.kind == "processing"
        assert plugin.order == 87
        assert plugin.version == "1"
        assert plugin.applies_to == ("tensile",)
        assert registry.get("tensile.model_anchor").order < plugin.order
        assert plugin.order < registry.get("tensile.true_plastic").order
        assert plugin.prepare_options is not None
        param_defaults = {param.name: param.default for param in plugin.params}
        assert param_defaults["proof_strain"] == "@model_proof_strain"
        assert param_defaults["proof_stress"] == "@model_proof_stress"
        assert param_defaults["end_strain"] == "@necking_candidate_strain"
        assert param_defaults["necking_limit"] == "@necking_candidate_strain"
        assert plugin.prepare_options({}) == {
            "proof_strain": "@model_proof_strain",
            "proof_stress": "@model_proof_stress",
            "end_strain": "@necking_candidate_strain",
            "necking_limit": "@necking_candidate_strain",
            "strain": "strain_engineering",
            "stress": "stress_engineering",
        }

    def test_기존R14를_덮지않고_일곱_새레시피의_실행순서를_보존한다(self) -> None:
        payload = json.loads(EXAMPLES.read_text(encoding="utf-8"))

        assert payload["schema"] == "matnexus.tensile.adaptive_plastic_domain_examples/1"
        recipes = payload["recipes"]
        assert len(recipes) == 7
        assert len({one["key"] for one in recipes}) == 7
        for recipe in recipes:
            assert set(recipe) == {"key", "label", "description", "test_type_key", "steps"}
            assert recipe["test_type_key"] == "tensile"
            steps = recipe["steps"]
            ids = [one["plugin"] for one in steps]
            assert ids[:6] == [
                "tensile.engineering",
                "tensile.terminal_domain",
                "tensile.strength",
                "tensile.elastic_modulus",
                "tensile.proof_stress",
                "tensile.necking_candidate",
            ]
            assert steps[4]["options"]["search_start"] == "@elastic_window_end"
            anchor = ids.index("tensile.model_anchor")
            domain = ids.index("tensile.plastic_domain")
            true_plastic = ids.index("tensile.true_plastic")
            assert domain == anchor + 1
            assert true_plastic == domain + 1
            assert steps[domain]["options"] == {}
            assert steps[true_plastic]["options"]["proof_stress"] == (
                "@plastic_domain_proof_stress"
            )
            assert steps[true_plastic]["options"]["proof_strain"] == (
                "@plastic_domain_proof_strain"
            )
            assert steps[true_plastic + 1]["plugin"] == "curve.sort_unique"
            assert steps[true_plastic + 1]["options"]["duplicate_policy"] == "first"
            assert ids[true_plastic + 1 : true_plastic + 3] == [
                "curve.sort_unique",
                "curve.monotone",
            ]
            assert ids[-1] == "curve.resample"
            assert steps[-1]["options"]["count"] == 300
            assert not any(
                step["plugin"] == "curve.resample"
                and step["options"].get("x") == "strain_engineering"
                for step in steps
            )
            assert not any(
                step["plugin"] == "curve.crop"
                and step["options"].get("x") == "strain_engineering"
                for step in steps
            )


class Test경계점:
    def test_PC2_실측곡선에서_두_경계를_보간하고_trueplastic에_짝을_전달한다(self) -> None:
        source = _pc2_raw_frame()
        source_before = {key: values.copy() for key, values in source.columns.items()}
        engineering = processing.apply(
            [Step("tensile.engineering", {"gauge_length": 0.08, "area": 40e-6})], source
        )
        frame = engineering.frame
        before = {key: values.copy() for key, values in frame.columns.items()}
        strain = frame.columns["strain_engineering"]
        stress = frame.columns["stress_engineering"]
        proof_strain = float((strain[100] + strain[101]) / 2.0)
        proof_stress = float((stress[100] + stress[101]) / 2.0)
        necking_strain = float(strain[500] + (strain[501] - strain[500]) * 0.25)
        given = [
            *_given(proof_strain, proof_stress, necking_strain),
            Scalar("youngs_modulus", "탄성계수", 200e9, "Pa"),
        ]

        result = processing.apply(
            [
                Step("tensile.plastic_domain", {}),
                Step(
                    "tensile.true_plastic",
                    {
                        "youngs_modulus": "@youngs_modulus",
                        "proof_stress": "@plastic_domain_proof_stress",
                        "proof_strain": "@plastic_domain_proof_strain",
                    },
                ),
            ],
            frame,
            given=given,
        )

        domain = result.stages[0]
        values = _values(domain)
        assert values["plastic_domain_proof_inserted"] == 1.0
        assert values["plastic_domain_end_inserted"] == 1.0
        assert values["plastic_domain_support_points"] >= 2.0
        assert domain.frame.columns["strain_engineering"][0] == proof_strain
        assert domain.frame.columns["strain_engineering"][-1] == necking_strain
        assert domain.frame.columns["stress_engineering"][0] == proof_stress
        assert domain.frame.columns["source_excel_row"][0] == pytest.approx(103.5)
        assert "파생값" in " ".join(domain.notes)
        assert domain.frame.units == frame.units
        assert result.frame.columns["strain_engineering"][0] == proof_strain
        assert result.frame.columns["stress_engineering"][0] == proof_stress
        assert result.frame.columns["strain_true_plastic"][0] == 0.0
        assert result.frame.columns["stress_true"][0] == pytest.approx(
            proof_stress * (1.0 + proof_strain)
        )
        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)
        for key, original in source_before.items():
            np.testing.assert_array_equal(source.columns[key], original)

    def test_정확한_경계는_기존행을_쓰고_앞쪽_음의응력은_유지하지_않는다(self) -> None:
        frame = _frame(
            [0.0, 0.01, 0.02, 0.03, 0.04],
            [-1e6, 100e6, 200e6, 300e6, 400e6],
            extra={"source_row": np.arange(10, 15, dtype=np.int64)},
        )
        before = {key: values.copy() for key, values in frame.columns.items()}

        result = _run(
            frame,
            given=_given(0.01, 100e6, 0.04),
        )

        assert result.frame.columns["strain_engineering"].tolist() == [0.01, 0.02, 0.03, 0.04]
        assert result.frame.columns["stress_engineering"].tolist() == [
            100e6,
            200e6,
            300e6,
            400e6,
        ]
        assert result.frame.columns["source_row"].dtype == np.dtype(np.int64)
        assert _values(result.stages[-1])["plastic_domain_inserted_points"] == 0.0
        for key, original in before.items():
            np.testing.assert_array_equal(frame.columns[key], original)

    def test_보간모드_효과옵션으로_재생된다(self) -> None:
        frame = _frame(
            [0.0, 0.01, 0.02, 0.03, 0.04, 0.05],
            [0.0, 100e6, 200e6, 300e6, 400e6, 500e6],
            extra={
                "source_row": np.arange(1, 7, dtype=np.int64),
                "marker": np.asarray([0.0, 10.0, 20.0, 30.0, 40.0, 50.0]),
            },
        )
        given = _given(0.015, 150e6, 0.05)
        result = _run(frame, given=given)
        effective = result.stages[-1].options
        replay = _run(frame, options=effective, given=given)

        assert effective == {
            "proof_strain": 0.015,
            "proof_stress": 150e6,
            "end_strain": 0.05,
            "necking_limit": 0.05,
            "strain": "strain_engineering",
            "stress": "stress_engineering",
        }
        np.testing.assert_array_equal(
            result.frame.columns["strain_engineering"], [0.015, 0.02, 0.03, 0.04, 0.05]
        )
        np.testing.assert_allclose(
            result.frame.columns["source_row"], [2.5, 3.0, 4.0, 5.0, 6.0]
        )
        np.testing.assert_allclose(result.frame.columns["marker"], [15, 20, 30, 40, 50])
        assert _values(result.stages[-1])["plastic_domain_inserted_points"] == 1.0
        for key in result.frame.columns:
            np.testing.assert_array_equal(result.frame.columns[key], replay.frame.columns[key])

    def test_수동경계쌍을_trueplastic에_그대로_전달한다(self) -> None:
        frame = _frame(
            [0.0, 0.01, 0.02, 0.03, 0.04],
            [0.0, 100e6, 200e6, 300e6, 400e6],
        )
        given = _given(0.015, 150e6, 0.04)

        result = processing.apply(
            [
                Step(
                    "tensile.plastic_domain",
                    {
                        "proof_strain": 0.015,
                        "proof_stress": 150e6,
                        "end_strain": 0.03,
                        "necking_limit": 0.04,
                    },
                ),
                Step(
                    "tensile.true_plastic",
                    {
                        "youngs_modulus": 50e9,
                        "proof_stress": "@plastic_domain_proof_stress",
                        "proof_strain": "@plastic_domain_proof_strain",
                    },
                ),
            ],
            frame,
            given=given,
        )

        assert result.stages[0].options["proof_strain"] == 0.015
        assert result.stages[0].options["proof_stress"] == 150e6
        assert result.stages[1].options["proof_strain"] == 0.015
        assert result.stages[1].options["proof_stress"] == 150e6
        assert result.frame.columns["strain_true_plastic"][0] == 0.0
        assert result.frame.columns["stress_true"][0] == pytest.approx(152.25e6)

    def test_PC1실측구간에서_첫_중복행이_검증된_anchor를_보존한다(self) -> None:
        # First four rows of the actual R15 PC Test1 upper-envelope
        # tensile.plastic_domain output (Oxford PC Figure 5, 50 mm/min).
        # Source key: oxford_pc_fig5_50mm_min_test1. Values came from the
        # frozen product run's stage-array archive, not a synthetic curve.
        proof_strain = 0.041647629196065725
        proof_stress = 60530816.37760683
        frame = _frame(
            [proof_strain, 0.04221375, 0.043255, 0.0443025],
            [proof_stress, 60972499.99999999, 61765000.0, 62535000.0],
        )
        given = [
            Scalar("youngs_modulus", "탄성계수", 1526719695.6032207, "Pa"),
            Scalar("plastic_domain_proof_stress", "모델 proof 응력", proof_stress, "Pa"),
            Scalar(
                "plastic_domain_proof_strain",
                "모델 proof 변형률",
                proof_strain,
                "1",
                "strain",
            ),
        ]

        def run(policy: str) -> processing.PipelineResult:
            return processing.apply(
                [
                    Step(
                        "tensile.true_plastic",
                        {
                            "youngs_modulus": "@youngs_modulus",
                            "proof_stress": "@plastic_domain_proof_stress",
                            "proof_strain": "@plastic_domain_proof_strain",
                            "negative_policy": "clip_zero",
                        },
                    ),
                    Step(
                        "curve.sort_unique",
                        {"x": "strain_true_plastic", "duplicate_policy": policy},
                    ),
                    Step(
                        "curve.monotone",
                        {"x": "strain_true_plastic", "column": "stress_true"},
                    ),
                    Step(
                        "curve.resample",
                        {"x": "strain_true_plastic", "count": 300, "start": 0},
                    ),
                ],
                frame,
                given=given,
            )

        last = run("last")
        first = run("first")
        anchor_true_stress = proof_stress * (1.0 + proof_strain)
        clipped_next_true_stress = 60972499.99999999 * (1.0 + 0.04221375)

        assert last.stages[0].frame.columns["strain_true_plastic"][:2].tolist() == [0.0, 0.0]
        assert last.stages[0].frame.columns["stress_true"][0] == pytest.approx(
            anchor_true_stress, rel=1e-12
        )
        assert last.stages[1].frame.columns["stress_true"][0] == pytest.approx(
            clipped_next_true_stress, rel=1e-12
        )
        assert first.stages[1].frame.columns["stress_true"][0] == pytest.approx(
            anchor_true_stress, rel=1e-12
        )
        assert last.frame.columns["stress_true"][0] == pytest.approx(
            clipped_next_true_stress, rel=1e-12
        )
        assert first.frame.columns["stress_true"][0] == pytest.approx(
            anchor_true_stress, rel=1e-12
        )


class Test검증:
    def test_현재입력지원점이_둘보다적으면_경계를추가하기전에_실패한다(self) -> None:
        frame = _frame([0.0, 0.01, 0.02, 0.03], [0.0, 100e6, 200e6, 300e6])

        with pytest.raises(ProcessingError, match="최소 2개"):
            _run(frame, given=_given(0.02, 200e6, 0.03))

    def test_짝지은proof응력과_보간값이_다르면_거부한다(self) -> None:
        frame = _frame([0.0, 0.01, 0.02, 0.03], [0.0, 100e6, 200e6, 300e6])

        with pytest.raises(ProcessingError, match="일치하지 않습니다"):
            _run(frame, given=_given(0.015, 151e6, 0.03))

    @pytest.mark.parametrize(
        ("proof_strain", "end_strain", "necking_limit", "message"),
        [
            (-0.01, 0.03, 0.04, "외삽하지 않았습니다"),
            (0.01, 0.06, 0.06, "외삽하지 않았습니다"),
            (0.01, 0.04, 0.03, "necking_limit"),
        ],
    )
    def test_관측범위와_네킹상한을_넘지_않는다(
        self, proof_strain: float, end_strain: float, necking_limit: float, message: str
    ) -> None:
        frame = _frame([0.0, 0.01, 0.02, 0.03, 0.04], [0.0, 100e6, 200e6, 300e6, 400e6])
        proof_stress = max(
            float(
                np.interp(
                    proof_strain,
                    frame.columns["strain_engineering"],
                    frame.columns["stress_engineering"],
                )
            ),
            1.0,
        )

        with pytest.raises(ProcessingError, match=message):
            _run(
                frame,
                options={"end_strain": end_strain, "necking_limit": necking_limit},
                given=_given(proof_strain, proof_stress, necking_limit),
            )

    def test_네킹후보보다_짧은_수동끝은_받는다(self) -> None:
        frame = _frame([0.0, 0.01, 0.02, 0.03, 0.04], [0.0, 100e6, 200e6, 300e6, 400e6])

        result = _run(
            frame,
            options={"end_strain": 0.03, "necking_limit": 0.04},
            given=_given(0.01, 100e6, 0.04),
        )

        assert result.frame.columns["strain_engineering"][-1] == 0.03

    def test_선택된_영역내_음의응력은_거부한다(self) -> None:
        frame = _frame([0.0, 0.01, 0.02, 0.03], [0.0, 100e6, -1e6, 300e6])

        with pytest.raises(ProcessingError, match="음의 공칭응력"):
            _run(frame, given=_given(0.01, 100e6, 0.03))

    def test_선택된_영역의_minus1이하_변형률은_거부한다(self) -> None:
        frame = _frame([-1.2, -1.0, -0.8, -0.6], [100e6, 200e6, 300e6, 400e6])

        with pytest.raises(ProcessingError, match="-1 이하"):
            _run(frame, given=_given(-1.1, 150e6, -0.6))

    @pytest.mark.parametrize(
        ("strain", "stress", "units", "message"),
        [
            ([0.0, 0.02, 0.01, 0.03], [0.0, 100e6, 200e6, 300e6], {}, "엄격히 증가"),
            ([0.0, 0.01, np.nan, 0.03], [0.0, 100e6, 200e6, 300e6], {}, "유한하지 않은"),
            (
                [0.0, 0.01, 0.02, 0.03],
                [0.0, 100e6, 200e6, 300e6],
                {"stress_engineering": "MPa"},
                "단위는 'Pa'",
            ),
        ],
    )
    def test_비단조_비유한_또는_잘못된단위는_거부한다(
        self,
        strain: list[float],
        stress: list[float],
        units: dict[str, str],
        message: str,
    ) -> None:
        frame = _frame(strain, stress, units=units)

        with pytest.raises(ProcessingError, match=message):
            _run(frame, given=_given(0.01, 100e6, 0.03))
