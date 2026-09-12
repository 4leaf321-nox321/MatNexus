"""확장 폴더에서 **처리 단계와 묶음**이 붙는가 — 남은 창구 둘을 실제로 써 본다.

`ghosh_hardening`(적합식)·`johnson_cook_static`(블록)이 앞의 둘이었다. 여기서는
`tensile_extras` 가 `registry.register(kind="processing" | "grouping")` 으로 붙고,
파이프라인과 묶음 커널이 그것을 내장과 똑같이 돌리는지 본다. 운영과 같은 길
(`extensions.load`)로 읽는다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from matcore import extensions, groups, processing, registry
from matcore.processing import Frame

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
extensions.load(EXTENSIONS)
processing.load_builtin()


class Test처리_단계:
    def test_레지스트리에_내장과_나란히_선다(self) -> None:
        plugin = registry.get("tensile.yield_ratio")
        assert plugin.kind == "processing"
        assert [one.key for one in plugin.makes_values] == ["yield_ratio"]
        assert "tensile" in plugin.applies_to

    def test_앞_단계의_값을_참조로_받아_항복비를_낸다(self) -> None:
        """`@proof_stress`·`@tensile_strength` 가 앞 단계 스칼라로 바뀌어 들어온다."""
        frame = Frame({"x": np.arange(3.0)}, {"x": "1"})
        result = processing.apply(
            [
                # 앞 단계를 흉내 낸다 — 항복강도·인장강도를 내는 단계가 앞에 있어야 한다.
                processing.Step(
                    "tensile.yield_ratio", {"proof_stress": 300e6, "tensile_strength": 400e6}
                ),
            ],
            frame,
        )
        stage = result.stages[-1]
        assert stage.plugin == "tensile.yield_ratio"
        assert {one.key: one.value for one in stage.scalars} == {
            "yield_ratio": pytest.approx(0.75)
        }
        assert stage.scalars[0].si_unit == "1"

    def test_값이_없으면_실패하지_않고_이유를_남긴다(self) -> None:
        frame = Frame({"x": np.arange(3.0)}, {"x": "1"})
        result = processing.apply(
            [
                processing.Step(
                    "tensile.yield_ratio", {"proof_stress": None, "tensile_strength": 400e6}
                )
            ],
            frame,
        )
        stage = result.stages[-1]
        assert stage.scalars == ()
        assert "내지 않았습니다" in " ".join(stage.notes)


def _member(label: str, temperature_k: float, drop_per_k: float) -> groups.Member:
    strain = np.linspace(0.0, 0.1, 21)
    stress = 400e6 - drop_per_k * (temperature_k - 293.15) + 500e6 * strain
    return groups.Member(
        label=label,
        columns={"strain_true_plastic": strain, "stress_true": stress},
        values={"temperature": temperature_k},
    )


class Test묶음:
    def test_레지스트리가_묶음으로_알고_구성원_규칙을_들고_있다(self) -> None:
        plugin = registry.get("tensile.temperature_family")
        assert plugin.kind == "grouping"
        assert plugin.meta["members"]["from"] == "adopted_result"
        assert "temperature" in plugin.meta["members"]["conditions"]
        assert plugin.id in {one.id for one in groups.groupings(applies_to="tensile")}

    def test_온도_연화_기울기가_되돌아온다(self) -> None:
        """답을 아는 곡선 — 1 K 마다 1 MPa 내려가게 만든 세 온도. 기울기가 그대로 나온다."""
        members = [
            _member("T293", 293.15, 1e6),
            _member("T323", 323.15, 1e6),
            _member("T353", 353.15, 1e6),
        ]
        out = groups.run_group("tensile.temperature_family", members, {"level": 0.02})
        assert out.values["temperature_count"] == 3
        assert out.values["softening_slope"] == pytest.approx(-1e6, rel=1e-6)
        assert out.values["softening_r_squared"] == pytest.approx(1.0)
        assert out.used == ["T293", "T323", "T353"]
        assert [one["temperature_k"] for one in out.detail["temperatures"]] == [
            293.15,
            323.15,
            353.15,
        ]

    def test_변형률까지_못_간_곡선은_빼고_말한다(self) -> None:
        short = _member("짧은", 323.15, 1e6)
        short = groups.Member(
            label=short.label,
            columns={key: value[:3] for key, value in short.columns.items()},  # 0.01 까지만
            values=short.values,
        )
        out = groups.run_group(
            "tensile.temperature_family",
            [_member("T293", 293.15, 1e6), short, _member("T353", 353.15, 1e6)],
            {"level": 0.02},
        )
        assert out.values["temperature_count"] == 2
        assert any("짧은" in one for one in out.warnings)

    def test_온도가_없으면_막는다(self) -> None:
        bare = groups.Member(label="X", columns=_member("X", 293.15, 1e6).columns, values={})
        with pytest.raises(groups.GroupError, match="온도 조건"):
            groups.run_group(
                "tensile.temperature_family", [bare, _member("Y", 323.15, 1e6)], {}
            )
