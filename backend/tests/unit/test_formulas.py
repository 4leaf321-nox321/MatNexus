"""계산식 → 레지스트리 (ADR 0030 D1·D3·D4).

식으로 만든 적합식이 답을 되돌린다     Swift 를 식으로 적고 실제 fit 으로 계수 복원
식으로 만든 단계가 파이프라인에서 돈다  스칼라 단계(항복비) · 열 단계(진응력)
자리에 맞지 않으면 등록 전에 막는다     선언 안 한 이름 · 파라미터 없는 적합식 · 결과 없는 단계
판이 오르면 교체되고, 내장은 못 건드린다
"""

from __future__ import annotations

import numpy as np
import pytest

from matcore import fitting, formulas, processing, registry
from matcore.processing import Frame
from matcore.registry import Produced

SWIFT = formulas.FormulaSpec(
    key="my_swift",
    kind="family",
    label="내 Swift",
    expression="K * (e0 + x) ** n",
    variables=(formulas.Variable("x"),),
    parameters=(
        formulas.Parameter("K", "Pa", 500e6, 1e6, 5e9),
        formulas.Parameter("e0", "1", 0.005, 1e-6, 0.5),
        formulas.Parameter("n", "1", 0.2, 0.01, 1.0),
    ),
    applies_to=("Metal",),
)

RATIO = formulas.FormulaSpec(
    key="my_ratio",
    kind="scalar_step",
    label="내 항복비",
    expression="proof_stress / tensile_strength",
    variables=(
        formulas.Variable("proof_stress", "Pa"),
        formulas.Variable("tensile_strength", "Pa"),
    ),
    result=Produced(key="my_yield_ratio", label="내 항복비", si_unit="1"),
)

TRUE_STRESS = formulas.FormulaSpec(
    key="my_true_stress",
    kind="column_step",
    label="내 진응력",
    expression="stress_engineering * (1 + strain_engineering)",
    variables=(
        formulas.Variable("stress_engineering", "Pa"),
        formulas.Variable("strain_engineering", "1"),
    ),
    result=Produced(key="my_stress_true", label="내 진응력", si_unit="Pa"),
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    for key in formulas.installed():
        formulas.uninstall(key)


class Test적합식:
    def test_답을_아는_곡선에서_계수가_되돌아온다(self) -> None:
        fitting.load_builtin()
        key = formulas.install(SWIFT)
        assert key == "formula.my_swift"
        assert key in {one.key for one in fitting.families_for("Metal")}

        x = np.linspace(0.0, 0.2, 60)
        truth = (700e6, 0.01, 0.25)
        y = truth[0] * (truth[1] + x) ** truth[2]
        got = fitting.fit(key, x, y)
        found = {p.name: p.value for p in got.parameters}
        assert found["K"] == pytest.approx(truth[0], rel=1e-3)
        assert found["e0"] == pytest.approx(truth[1], rel=1e-2)
        assert found["n"] == pytest.approx(truth[2], rel=1e-3)
        assert got.r_squared > 0.9999

    def test_파라미터가_없거나_변수가_x_가_아니면_막는다(self) -> None:
        with pytest.raises(formulas.FormulaSpecError, match="파라미터"):
            formulas.validate(
                formulas.FormulaSpec(
                    key="k",
                    kind="family",
                    label="",
                    expression="x",
                    variables=(formulas.Variable("x"),),
                )
            )
        with pytest.raises(formulas.FormulaSpecError, match="`x` 하나"):
            formulas.validate(
                formulas.FormulaSpec(
                    key="k",
                    kind="family",
                    label="",
                    expression="A * strain",
                    variables=(formulas.Variable("strain"),),
                    parameters=(formulas.Parameter("A"),),
                )
            )


class Test단계:
    def test_스칼라_단계가_앞_값을_받아_낸다(self) -> None:
        key = formulas.install(RATIO)
        plugin = registry.get(key)
        assert plugin.kind == "processing"
        assert [p.default for p in plugin.params] == ["@proof_stress", "@tensile_strength"]
        assert plugin.meta["formula"] == RATIO.expression

        frame = Frame({"x": np.arange(3.0)}, {"x": "1"})
        out = processing.apply(
            [processing.Step(key, {"proof_stress": 300e6, "tensile_strength": 400e6})], frame
        )
        assert {s.key: s.value for s in out.stages[-1].scalars} == {"my_yield_ratio": 0.75}

        # 값이 없으면 실패하지 않고 이유를 남긴다.
        out = processing.apply(
            [processing.Step(key, {"proof_stress": None, "tensile_strength": 1})], frame
        )
        assert out.stages[-1].scalars == ()
        assert "내지 않았습니다" in " ".join(out.stages[-1].notes)

    def test_열_단계가_점마다_새_열을_만든다(self) -> None:
        key = formulas.install(TRUE_STRESS)
        plugin = registry.get(key)
        assert [c.key for c in plugin.makes_columns] == ["my_stress_true"]
        # 입력 열을 requires_channels 로 선언한다 — 편집기가 「무엇이 있어야 하나」 를 안다.
        assert plugin.requires_channels == (("stress_engineering",), ("strain_engineering",))

        frame = Frame(
            {
                "stress_engineering": np.array([100.0, 200.0]),
                "strain_engineering": np.array([0.1, 0.2]),
            },
            {"stress_engineering": "Pa", "strain_engineering": "1"},
        )
        out = processing.apply([processing.Step(key, {})], frame)
        assert out.stages[-1].frame.columns["my_stress_true"] == pytest.approx([110.0, 240.0])
        assert out.stages[-1].frame.units["my_stress_true"] == "Pa"

        # 열이 없으면 실패하지 않고 어느 열이 없는지 말한다.
        out = processing.apply(
            [processing.Step(key, {})], Frame({"force": np.ones(2)}, {"force": "N"})
        )
        assert "my_stress_true" not in out.stages[-1].frame.columns
        assert "stress_engineering" in " ".join(out.stages[-1].notes)

    def test_결과가_없거나_이름이_안_맞으면_막는다(self) -> None:
        with pytest.raises(formulas.FormulaSpecError, match="result"):
            formulas.validate(
                formulas.FormulaSpec(
                    key="k",
                    kind="scalar_step",
                    label="",
                    expression="a",
                    variables=(formulas.Variable("a"),),
                )
            )
        with pytest.raises(formulas.FormulaSpecError, match="선언에 없습니다"):
            formulas.validate(
                formulas.FormulaSpec(
                    key="k",
                    kind="scalar_step",
                    label="",
                    expression="a / b",
                    variables=(formulas.Variable("a"),),
                    result=Produced(key="r", label="r", si_unit="1"),
                )
            )


class Test교체와_보호:
    def test_같은_키를_다시_넣으면_새_판으로_바뀐다(self) -> None:
        key = formulas.install(RATIO)
        assert registry.get(key).version == "1"
        changed = formulas.FormulaSpec(
            **{
                **RATIO.__dict__,
                "expression": "2 * proof_stress / tensile_strength",
                "version": "2",
            }
        )
        assert formulas.install(changed) == key
        assert registry.get(key).version == "2"
        out = processing.apply(
            [processing.Step(key, {"proof_stress": 300e6, "tensile_strength": 400e6})],
            Frame({"x": np.arange(2.0)}, {"x": "1"}),
        )
        assert out.stages[-1].scalars[0].value == pytest.approx(1.5)

    def test_내장은_이_길로_못_뺀다(self) -> None:
        processing.load_builtin()
        with pytest.raises(formulas.FormulaSpecError):
            formulas.uninstall("tensile.engineering")
        assert registry.get("tensile.engineering")

    def test_키_규칙(self) -> None:
        with pytest.raises(formulas.FormulaSpecError, match="snake_case"):
            formulas.validate(formulas.FormulaSpec(**{**RATIO.__dict__, "key": "My Ratio"}))
