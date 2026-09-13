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


def _jc_member(label: str, temperature_k: float, m: float, melt_k: float) -> groups.Member:
    """답을 아는 Johnson-Cook 온도 항 — σ = σ₀(ε)·(1 - T*^m)."""
    strain = np.linspace(0.0, 0.1, 21)
    base = 400e6 + 500e6 * strain
    t_star = max(0.0, (temperature_k - 293.15) / (melt_k - 293.15))
    return groups.Member(
        label=label,
        columns={"strain_true_plastic": strain, "stress_true": base * (1.0 - t_star**m)},
        values={"temperature": temperature_k},
    )


class Test묶음:
    def test_레지스트리가_묶음으로_알고_구성원_규칙과_카드_규칙을_들고_있다(self) -> None:
        plugin = registry.get("tensile.temperature_family")
        assert plugin.kind == "grouping"
        assert plugin.meta["members"]["from"] == "adopted_result"
        assert "temperature" in plugin.meta["members"]["conditions"]
        assert callable(plugin.meta["card"])
        assert plugin.id in {one.id for one in groups.groupings(applies_to="tensile")}

    def test_온도_묶음별_표와_연화_기울기가_되돌아온다(self) -> None:
        """답을 아는 곡선 — 1 K 마다 1 MPa 내려가게 만든 세 온도. 기울기가 그대로 나온다.
        가까운 온도(±5 K)는 한 묶음이고 묶음 온도는 평균이다."""
        members = [
            _member("T293", 293.15, 1e6),
            _member("T295", 295.15, 1e6),  # 293 과 한 묶음 → 294.15
            _member("T323", 323.15, 1e6),
            _member("T353", 353.15, 1e6),
        ]
        out = groups.run_group("tensile.temperature_family", members, {"levels": "0.02, 0.05"})
        assert out.values["temperature_count"] == 3
        assert out.values["reference_temperature"] == pytest.approx(294.15)
        assert out.values["softening_slope"] == pytest.approx(-1e6, rel=1e-6)
        assert out.values["softening_r_squared"] == pytest.approx(1.0)
        assert out.used == ["T293", "T295", "T323", "T353"]
        bins = out.detail["temperatures"]
        assert [one["temperature"] for one in bins] == pytest.approx([294.15, 323.15, 353.15])
        assert bins[0]["members"] == ["T293", "T295"]
        # 기준 온도 자신의 응력비는 1, 더운 쪽은 1 보다 작다.
        assert bins[0]["ratio_mean"] == pytest.approx(1.0)
        assert bins[2]["ratio_mean"] < bins[1]["ratio_mean"] < 1.0
        # 묶음마다 곡선이 있다 — 카드가 온도별 표로 싣는 것이 이것이다.
        assert len(bins[1]["curve"]["stress_true"]) == len(
            bins[1]["curve"]["strain_true_plastic"]
        )

    def test_Johnson_Cook_m_이_되돌아온다(self) -> None:
        melt = 1800.0
        members = [
            _jc_member("T293", 293.15, 1.1, melt),
            _jc_member("T473", 473.15, 1.1, melt),
            _jc_member("T673", 673.15, 1.1, melt),
            _jc_member("T873", 873.15, 1.1, melt),
        ]
        out = groups.run_group(
            "tensile.temperature_family",
            members,
            {"model": "johnson_cook", "melt_temperature": melt, "levels": "0.01, 0.05"},
        )
        assert out.values["jc_m"] == pytest.approx(1.1, rel=1e-6)
        assert out.values["model_r_squared"] == pytest.approx(1.0)
        assert out.detail["melt_temperature"] == melt

    def test_녹는점이_기준보다_낮으면_식을_안_맞추고_말한다(self) -> None:
        out = groups.run_group(
            "tensile.temperature_family",
            [_member("T293", 293.15, 1e6), _member("T353", 353.15, 1e6)],
            {"model": "johnson_cook", "melt_temperature": 0},
        )
        assert "jc_m" not in out.values
        assert any("녹는점" in one for one in out.warnings)

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
            {"levels": "0.02"},
        )
        # 묶음은 셋 다 서고, 짧은 곡선의 온도는 그 변형률의 응력비만 빠진다.
        assert out.values["temperature_count"] == 3
        assert out.detail["temperatures"][1]["ratios"] == [None]
        assert any("323.1 K" in one and "안 가서" in one for one in out.warnings)

    def test_온도가_없거나_묶음이_하나면_막는다(self) -> None:
        bare = groups.Member(label="X", columns=_member("X", 293.15, 1e6).columns, values={})
        with pytest.raises(groups.GroupError, match="시험 온도가 없습니다"):
            groups.run_group(
                "tensile.temperature_family", [bare, _member("Y", 323.15, 1e6)], {}
            )
        with pytest.raises(groups.GroupError, match="하나뿐"):
            groups.run_group(
                "tensile.temperature_family",
                [_member("A", 293.15, 1e6), _member("B", 294.15, 1e6)],
                {},
            )

    def test_카드_블록은_기준_온도_표와_온도별_표를_낸다(self) -> None:
        members = [
            _member("T293", 293.15, 1e6),
            _member("T323", 323.15, 1e6),
            _member("T353", 353.15, 1e6),
        ]
        out = groups.run_group("tensile.temperature_family", members, {})
        plugin = registry.get("tensile.temperature_family")
        blocks = plugin.meta["card"](out.values, out.detail, out.warnings)
        assert set(blocks) == {"table", "temperature_table"}
        assert blocks["table"]["values"]["source"] == "temperature_family"
        rows = blocks["temperature_table"]["rows"]
        assert sorted({round(row["temperature"], 2) for row in rows}) == [
            293.15,
            323.15,
            353.15,
        ]
        assert blocks["temperature_table"]["values"]["temperature_count"] == 3
        assert blocks["temperature_table"]["values"]["reference_temperature"] == pytest.approx(
            293.15
        )
        # 기준 온도 표는 온도별 표의 첫 온도와 같다.
        first = [r for r in rows if r["temperature"] == pytest.approx(293.15)]
        assert len(first) == len(blocks["table"]["rows"])


class Test덱:
    def test_Abaqus_온도_의존_덱은_온도별_PLASTIC_행을_낸다(self) -> None:
        from matcore import export

        members = [
            _member("T293", 293.15, 1e6),
            _member("T323", 323.15, 1e6),
            _member("T353", 353.15, 1e6),
        ]
        out = groups.run_group("tensile.temperature_family", members, {})
        blocks = registry.get("tensile.temperature_family").meta["card"](
            out.values, out.detail, out.warnings
        )
        blocks["elastic"] = {
            "values": {"youngs_modulus": 200e9, "poisson_ratio": 0.3, "density": 7850.0}
        }
        deck = export.Deck(name="SECC_MD", solver_id=1, blocks=blocks)
        rendered = export.render("abaqus_temperature", deck)
        text = rendered.text
        assert "*PLASTIC, HARDENING=ISOTROPIC" in text
        assert "3 temperatures" in text
        # 데이터 줄 셋째 열이 온도다 — 온도 셋이 다 들어 있다.
        thirds = {
            round(float(line.split(",")[2]), 2)
            for line in text.splitlines()
            if line.count(",") == 2 and not line.startswith("*")
        }
        assert thirds == {293.15, 323.15, 353.15}
        # 온도가 하나뿐이면 이 덱은 낼 수 없다 — 「가능」 으로 보이지 않는다.
        one_only = {
            **blocks,
            "temperature_table": {
                **blocks["temperature_table"],
                "values": {**blocks["temperature_table"]["values"], "temperature_count": 1},
            },
        }
        assert export.missing_for(
            export.Deck(name="x", solver_id=1, blocks=one_only), "abaqus_temperature"
        )
