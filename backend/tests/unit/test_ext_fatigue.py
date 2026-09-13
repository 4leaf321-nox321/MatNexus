"""피로 확장 — **점 하나짜리 시험들을 Basquin 으로 잇고, 런아웃은 뺀다.**

답을 아는 점: S = A·N^b, A = 1000 MPa, b = -0.1. 런아웃 하나를 섞어 두면 빼고
맞춰야 A·b 가 그대로 돌아온다 — 넣으면 곡선이 위로 휜다.
"""

from __future__ import annotations

import pytest

from matcore import groups, registry

A, B = 1000e6, -0.1


def _point(
    label: str, stress: float, *, runout: bool = False, ratio: float = -1.0
) -> groups.Member:
    cycles = (stress / A) ** (1.0 / B)
    values = {"stress_amplitude": stress, "cycles_to_failure": cycles, "stress_ratio": ratio}
    if runout:
        # 런아웃은 그 응력에서 식이 말하는 수명보다 **오래** 버틴 것 — 멈춘 수명을 적는다.
        values["cycles_to_failure"] = 1e7
        values["runout"] = 1.0
    return groups.Member(label=label, columns={}, values=values)


STRESSES = (600e6, 500e6, 420e6, 350e6, 300e6, 260e6)


class Test등록:
    def test_요약값_구성원을_선언하고_카드를_낼_수_있다(self) -> None:
        plugin = registry.get("fatigue.sn_curve")
        assert plugin.kind == "grouping"
        assert plugin.meta["members"]["from"] == "summary"
        assert "cycles_to_failure" in plugin.meta["members"]["values"]
        assert callable(plugin.meta["card"])
        assert plugin.id in {one.id for one in groups.groupings(applies_to="fatigue")}


class Test적합:
    def test_Basquin_이_되돌아오고_런아웃은_빠진다(self) -> None:
        members = [_point(f"F{i}", s) for i, s in enumerate(STRESSES)]
        members.append(_point("RO", 240e6, runout=True))
        out = groups.run_group("fatigue.sn_curve", members, {})
        assert out.values["basquin_a"] == pytest.approx(A, rel=1e-6)
        assert out.values["basquin_b"] == pytest.approx(B, rel=1e-6)
        assert out.values["sn_r_squared"] == pytest.approx(1.0)
        assert out.values["point_count"] == 6
        assert out.values["runout_count"] == 1
        assert out.values["strength_at_1e6"] == pytest.approx(A * 1e6**B, rel=1e-6)
        assert out.used == [f"F{i}" for i in range(6)], "런아웃은 쓴 시편에 없다"
        assert any("런아웃 1건" in one for one in out.warnings)
        # 점은 전부 남고, 런아웃은 표시가 붙는다 — 카드 표가 그것을 싣는다.
        points = out.detail["points"]
        assert len(points) == 7
        assert next(p for p in points if p["runout"])["used"] is False

    def test_런아웃을_넣으면_곡선이_달라진다(self) -> None:
        """뺀 것과 넣은 것이 같으면 옵션이 아무것도 안 하는 것이다."""
        members = [_point(f"F{i}", s) for i, s in enumerate(STRESSES)]
        members.append(_point("RO", 240e6, runout=True))
        with_ro = groups.run_group("fatigue.sn_curve", members, {"exclude_runouts": False})
        assert with_ro.values["point_count"] == 7
        assert with_ro.values["basquin_b"] != pytest.approx(B, rel=1e-3)

    def test_응력비가_섞이면_말한다(self) -> None:
        members = [
            _point(f"F{i}", s, ratio=-1.0 if i % 2 else 0.1) for i, s in enumerate(STRESSES)
        ]
        out = groups.run_group("fatigue.sn_curve", members, {})
        assert any("응력비 R" in one for one in out.warnings)

    def test_점이_모자라거나_수명이_몰려_있으면_막는다(self) -> None:
        with pytest.raises(groups.GroupError, match="3건 이상"):
            groups.run_group("fatigue.sn_curve", [_point("A", 600e6), _point("B", 500e6)], {})
        same = [
            groups.Member(
                label=f"S{i}",
                columns={},
                values={"stress_amplitude": 400e6, "cycles_to_failure": 1e5 * (1 + i / 10)},
            )
            for i in range(4)
        ]
        with pytest.raises(groups.GroupError, match="몰려"):
            groups.run_group("fatigue.sn_curve", same, {})

    def test_카드_블록은_점과_계수를_낸다(self) -> None:
        members = [_point(f"F{i}", s) for i, s in enumerate(STRESSES)]
        members.append(_point("RO", 240e6, runout=True))
        out = groups.run_group("fatigue.sn_curve", members, {})
        blocks = registry.get("fatigue.sn_curve").meta["card"](
            out.values, out.detail, out.warnings
        )
        assert set(blocks) == {"sn_curve"}
        rows = blocks["sn_curve"]["rows"]
        assert len(rows) == 7
        assert sum(row["runout"] for row in rows) == 1
        assert blocks["sn_curve"]["values"]["basquin_a"] == pytest.approx(A, rel=1e-6)
        assert blocks["sn_curve"]["values"]["strength_at_1e7"] == pytest.approx(
            A * 1e7**B, rel=1e-6
        )
