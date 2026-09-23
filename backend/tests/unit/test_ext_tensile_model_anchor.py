"""모델 시작점은 원곡선 Rp 와 다른, 모델 전용 결과로 남는다."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, processing, registry
from matcore.processing import Frame, ProcessingError, Step

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "s355_proof_point_excerpt.csv"
extensions.load(EXTENSIONS)
processing.load_builtin()


def s355() -> Frame:
    with FIXTURE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return Frame(
        {
            "strain_engineering": np.asarray(
                [float(row["strain_engineering"]) for row in rows]
            ),
            "stress_engineering": np.asarray(
                [float(row["stress_engineering_pa"]) for row in rows]
            ),
        },
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )


def scalar(result: processing.PipelineResult, key: str) -> float:
    return next(one.value for one in result.scalars if one.key == key)


class Test모델_시작점:
    def test_레지스트리에_Rp_속성_매핑_없이_분리되어_등록된다(self) -> None:
        plugin = registry.get("tensile.model_anchor")
        assert plugin.kind == "processing"
        assert plugin.label == "모델 소성 시작점(오프셋)"
        assert plugin.order == 85
        assert plugin.applies_to == ("tensile",)
        assert plugin.requires_channels == (("displacement",), ("force",))
        assert {one.key for one in plugin.makes_values} == {
            "model_proof_stress",
            "model_proof_strain",
            "model_proof_offset",
        }
        assert all(one.property_key is None for one in plugin.makes_values)
        assert next(one for one in plugin.params if one.name == "youngs_modulus").default == (
            "@youngs_modulus"
        )
        assert plugin.prepare_options is not None
        help_text = plugin.makes_values[0].help
        assert help_text is not None
        assert "재료의 Rp 가 아니라" in help_text

    def test_E_생략은_앞_단계_값을_잇고_입력_옵션은_복사한다(self) -> None:
        options = {"offset_strain": 0.0015}
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"method": "manual", "manual_modulus": 210e9},
                ),
                Step("tensile.model_anchor", options),
            ],
            s355(),
        )
        assert result.stages[-1].options["youngs_modulus"] == 210e9
        assert scalar(result, "youngs_modulus") == 210e9
        assert options == {"offset_strain": 0.0015}

    def test_명시한_E는_None_숫자_다른_참조를_그대로_보존한다(self) -> None:
        prepare = registry.get("tensile.model_anchor").prepare_options
        assert prepare is not None
        for explicit in (None, 205e9, "@custom_modulus"):
            options = {"youngs_modulus": explicit}
            prepared = prepare(options)
            assert prepared == options
            assert prepared is not options
            assert options == {"youngs_modulus": explicit}

    def test_None_E는_기본_E로_조용히_대체하지_않는다(self) -> None:
        with pytest.raises(ProcessingError, match=r"youngs_modulus.*값이 필요합니다"):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"method": "manual", "manual_modulus": 210e9},
                    ),
                    Step("tensile.model_anchor", {"youngs_modulus": None}),
                ],
                s355(),
            )

    def test_숫자로_지정한_E를_모델_교점에_쓴다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"method": "manual", "manual_modulus": 210e9},
                ),
                Step(
                    "tensile.model_anchor",
                    {"youngs_modulus": 205e9, "offset_strain": 0.0015},
                ),
            ],
            s355(),
        )
        assert result.stages[-1].options["youngs_modulus"] == 205e9
        assert scalar(result, "youngs_modulus") == 210e9
        assert scalar(result, "model_proof_stress") > 0

    def test_원곡선_Rp와_모델_시작점은_서로_다른_값으로_남는다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"method": "manual", "manual_modulus": 210e9},
                ),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
                Step("tensile.model_anchor", {"offset_strain": 0.0015}),
            ],
            s355(),
        )
        values = {one.key for one in result.scalars}
        assert {"proof_stress", "proof_strain", "proof_offset"} <= values
        assert {"model_proof_stress", "model_proof_strain", "model_proof_offset"} <= values
        assert scalar(result, "proof_stress") != pytest.approx(
            scalar(result, "model_proof_stress")
        )
        assert scalar(result, "youngs_modulus") == 210e9
        model_stage = result.stages[2]
        assert {one.key for one in model_stage.scalars}.isdisjoint(
            {"proof_stress", "proof_strain", "proof_offset", "youngs_modulus"}
        )
        assert any(
            "원곡선에서 계산한 Rp 를 대체하지 않습니다" in note for note in model_stage.notes
        )

    def test_재샘플과_자르기_뒤에도_명시한_쌍으로_소성곡선을_시작한다(self) -> None:
        frame = s355()
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"method": "manual", "manual_modulus": 210e9},
                ),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
                Step(
                    "tensile.model_anchor",
                    {"offset_strain": 0.0015, "youngs_modulus": "@youngs_modulus"},
                ),
                Step(
                    "curve.resample",
                    {"x": "strain_engineering", "count": 501},
                ),
                Step(
                    "curve.crop",
                    {"x": "strain_engineering", "start": 0.0018, "end": 0.0039941367693135535},
                ),
                Step(
                    "tensile.true_plastic",
                    {
                        "youngs_modulus": "@youngs_modulus",
                        "proof_stress": "@model_proof_stress",
                        "proof_strain": "@model_proof_strain",
                    },
                ),
            ],
            frame,
        )
        model_stress = scalar(result, "model_proof_stress")
        model_strain = scalar(result, "model_proof_strain")
        plastic_stage = result.stages[-1]
        assert plastic_stage.options["proof_stress"] == model_stress
        assert plastic_stage.options["proof_strain"] == model_strain
        assert result.frame.columns["strain_engineering"][0] == pytest.approx(model_strain)
        assert result.frame.columns["stress_engineering"][0] == pytest.approx(model_stress)
        assert result.frame.columns["strain_true_plastic"][0] == 0.0

    def test_교점이_없으면_외삽하지_않고_원본과_E를_보존한다(self) -> None:
        frame = s355()
        before = {key: values.copy() for key, values in frame.columns.items()}
        with pytest.raises(ProcessingError, match="외삽해서 값을 만들지 않습니다"):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"method": "manual", "manual_modulus": 210e9},
                    ),
                    Step(
                        "tensile.model_anchor",
                        {"search_end": 0.0025, "youngs_modulus": "@youngs_modulus"},
                    ),
                ],
                frame,
            )
        for key, values in before.items():
            np.testing.assert_array_equal(frame.columns[key], values)
        assert (
            scalar(
                processing.apply(
                    [
                        Step(
                            "tensile.elastic_modulus",
                            {"method": "manual", "manual_modulus": 210e9},
                        )
                    ],
                    frame,
                ),
                "youngs_modulus",
            )
            == 210e9
        )

    def test_사용자_열_이름을_계산에_그대로_쓴다(self) -> None:
        source = s355()
        frame = Frame(
            {
                "epsilon_source": source.columns["strain_engineering"].copy(),
                "sigma_source": source.columns["stress_engineering"].copy(),
            },
            {"epsilon_source": "1", "sigma_source": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "tensile.model_anchor",
                    {
                        "youngs_modulus": 210e9,
                        "strain": "epsilon_source",
                        "stress": "sigma_source",
                    },
                )
            ],
            frame,
        )
        assert result.frame is frame
        assert result.stages[0].options["strain"] == "epsilon_source"
        assert result.stages[0].options["stress"] == "sigma_source"
        assert scalar(result, "model_proof_stress") > 0
