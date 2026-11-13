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

    def test_수명을_응력에_회귀한다_ASTM_E739(self) -> None:
        """흩어짐은 수명 쪽에 있다. 응력마다 수명을 ±0.3 자릿수로 대칭으로 흩어 두면 log N 을
        log S 에 맞춘 직선은 참값을 그대로 되찾는다. 반대로(log S 를 log N 에) 맞추면 기울기가
        완만해져 긴 수명의 강도가 높게 나온다 — 2026-10-04 점검에서 찾은 결함."""
        members = []
        for index, stress in enumerate((400e6, 350e6, 300e6, 250e6)):
            for sign in (1.0, -1.0):
                cycles = (stress / A) ** (1.0 / B) * 10.0 ** (0.3 * sign)
                members.append(
                    groups.Member(
                        label=f"S{index}{'+' if sign > 0 else '-'}",
                        columns={},
                        values={"stress_amplitude": stress, "cycles_to_failure": cycles},
                    )
                )
        out = groups.run_group("fatigue.sn_curve", members, {})
        assert out.values["basquin_b"] == pytest.approx(B, rel=1e-9)
        assert out.values["basquin_a"] == pytest.approx(A, rel=1e-9)
        assert out.values["strength_at_1e7"] == pytest.approx(A * 1e7**B, rel=1e-9)
        # 흩어짐은 **수명의** 자릿수 — 잔차 ±0.3 여덟 개, 자유도 6.
        assert out.values["log_scatter"] == pytest.approx((8 * 0.09 / 6) ** 0.5, rel=1e-9)

    def test_응력이_하나뿐이면_막는다(self) -> None:
        same = [
            groups.Member(
                label=f"S{i}",
                columns={},
                values={"stress_amplitude": 400e6, "cycles_to_failure": 1e4 * 10**i},
            )
            for i in range(4)
        ]
        with pytest.raises(groups.GroupError, match="응력 진폭이 모두 같습니다"):
            groups.run_group("fatigue.sn_curve", same, {})

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


# ── 2구간 S-N (VOC 61, 2026-11-14) ───────────────────────────────────────────────────
# 답을 아는 꺾인 곡선: A1 = 1000 MPa · b1 = -0.1 · 꺾임 수명 1e5 · b2 = -0.05. 꺾임 응력은
# A1·1e5^-0.1 ≈ 316 MPa 다.

A1, B1, KNEE, B2 = 1000e6, -0.1, 1e5, -0.05
KNEE_STRESS = A1 * KNEE**B1


def _bent_cycles(stress: float, knee: float = KNEE) -> float:
    knee_stress = A1 * knee**B1
    if stress >= knee_stress:
        return float((stress / A1) ** (1.0 / B1))
    return float(knee * (stress / knee_stress) ** (1.0 / B2))


def _bent(
    label: str,
    stress: float,
    *,
    knee: float = KNEE,
    scatter: float = 0.0,
    runout: bool = False,
) -> groups.Member:
    values = {
        "stress_amplitude": stress,
        "cycles_to_failure": _bent_cycles(stress, knee) * 10.0**scatter,
        "stress_ratio": -1.0,
    }
    if runout:
        values["cycles_to_failure"] = 1e8
        values["runout"] = 1.0
    return groups.Member(label=label, columns={}, values=values)


BENT = (600e6, 520e6, 450e6, 400e6, 350e6, 300e6, 280e6, 260e6, 240e6)


class Test2구간:
    def test_등록은_한_직선_옆에_따로_서고_카드를_낸다(self) -> None:
        plugin = registry.get("fatigue.sn_bilinear")
        assert plugin.kind == "grouping"
        assert plugin.meta["members"]["from"] == "summary"
        assert callable(plugin.meta["card"])
        ids = {one.id for one in groups.groupings(applies_to="fatigue")}
        assert {"fatigue.sn_curve", "fatigue.sn_bilinear"} <= ids

    def test_꺾인_곡선이_되돌아오고_런아웃은_빠지되_세어진다(self) -> None:
        members = [_bent(f"F{i}", s) for i, s in enumerate(BENT)]
        members.append(_bent("RO", 200e6, runout=True))
        out = groups.run_group("fatigue.sn_bilinear", members, {})
        values = out.values
        assert values["sn_a1"] == pytest.approx(A1, rel=1e-5)
        assert values["sn_b1"] == pytest.approx(B1, rel=1e-5)
        assert values["sn_b2"] == pytest.approx(B2, rel=1e-5)
        assert values["knee_cycles"] == pytest.approx(KNEE, rel=1e-4)
        assert values["knee_stress"] == pytest.approx(KNEE_STRESS, rel=1e-5)
        # 이어짐 — 꺾임 응력은 첫 구간 식이 꺾임 수명에서 내는 값이다.
        assert values["sn_a1"] * values["knee_cycles"] ** values["sn_b1"] == pytest.approx(
            values["knee_stress"], rel=1e-9
        )
        assert values["bilinear_supported"] == 1.0
        assert values["bilinear_p_value"] < 1e-6 and values["bilinear_delta_bic"] < 0
        assert values["point_count"] == 9 and values["runout_count"] == 1
        assert (values["segment1_points"], values["segment2_points"]) == (5, 4)
        assert values["strength_at_1e7"] == pytest.approx(
            KNEE_STRESS * (1e7 / KNEE) ** B2, rel=1e-4
        )
        assert out.used == [f"F{i}" for i in range(9)], "런아웃은 쓴 시편에 없다"
        assert any("꺾임 아래 응력에 런아웃 1건" in one for one in out.warnings)
        assert not any("근거 약함" in one for one in out.warnings)

    def test_직선인_시험군은_근거_약함을_달고_막지_않는다(self) -> None:
        """2구간은 늘 조금은 낫다 — 흩어짐에 맞춘 가짜 꺾임을 한 직선과 견줘 짚는다."""
        members = [
            groups.Member(
                label=f"L{i}",
                columns={},
                values={
                    "stress_amplitude": s,
                    "cycles_to_failure": (s / A1) ** (1.0 / B1) * 10.0 ** (0.2 * (-1) ** i),
                },
            )
            for i, s in enumerate(BENT)
        ]
        out = groups.run_group("fatigue.sn_bilinear", members, {})
        assert out.values["bilinear_supported"] == 0.0
        assert out.values["bilinear_p_value"] > 0.05
        assert any("2구간 근거 약함 — 한 직선(Basquin) 권장" in one for one in out.warnings)

    @pytest.mark.parametrize(
        ("knee", "stresses"),
        [
            # 꺾임이 높은 응력 쪽(짧은 수명) 끝 — 응력 범위의 위 30 % 안.
            (3e3, (700e6, 640e6, 580e6, 520e6, 470e6, 430e6, 380e6, 330e6, 280e6, 240e6)),
            # 꺾임이 낮은 응력 쪽(긴 수명) 끝 — 꺾임(≈225 MPa) 아래 파단점이 셋(구간 최소).
            (
                3e6,
                (700e6, 600e6, 500e6, 420e6, 350e6, 300e6, 260e6, 230e6, 220e6, 210e6, 200e6),
            ),
        ],
    )
    def test_꺾임이_범위_어느_끝에_있어도_전_범위에서_찾는다(
        self, knee: float, stresses: tuple[float, ...]
    ) -> None:
        """로컬 검증은 첫 값 둘레 ±0.25 자릿수였다 — 여기는 범위 전체를 훑는다. 양 끝 둘 다
        되찾아야 한쪽만 훑는 탐색이 잡힌다(사보타주: 앞 30 % 만 훑으면 한쪽은 통과했다)."""
        members = [_bent(f"K{i}", s, knee=knee) for i, s in enumerate(stresses)]
        out = groups.run_group("fatigue.sn_bilinear", members, {})
        assert out.values["knee_cycles"] == pytest.approx(knee, rel=1e-4)
        assert out.values["sn_b1"] == pytest.approx(B1, rel=1e-5)
        assert out.values["sn_b2"] == pytest.approx(B2, rel=1e-5)

    def test_같은_점이면_늘_같은_답이다(self) -> None:
        members = [_bent(f"F{i}", s, scatter=0.1 * ((-1) ** i)) for i, s in enumerate(BENT)]
        first = groups.run_group("fatigue.sn_bilinear", members, {}).values
        assert groups.run_group("fatigue.sn_bilinear", members, {}).values == first
        # 순서만 바꾸면 합의 차례만 달라진다 — 같은 꺾임 · 같은 계수(기계 정밀도 안).
        shuffled = groups.run_group("fatigue.sn_bilinear", list(reversed(members)), {}).values
        assert shuffled == pytest.approx(first, rel=1e-12)

    def test_구간마다_파단점이_모자라면_막는다(self) -> None:
        few = [_bent(f"F{i}", s) for i, s in enumerate(BENT[:5])]
        with pytest.raises(groups.GroupError, match="6건 이상"):
            groups.run_group("fatigue.sn_bilinear", few, {})
        with pytest.raises(groups.GroupError, match="10건 이상"):
            groups.run_group(
                "fatigue.sn_bilinear",
                [_bent(f"F{i}", s) for i, s in enumerate(BENT)],
                {"min_segment_points": 5},
            )

    def test_카드_블록은_2구간_블록이고_한_직선_블록이_아니다(self) -> None:
        """같은 블록이면 한 직선만 읽는 덱이 둘째 기울기를 버리고 조용히 한 직선을 낸다."""
        members = [_bent(f"F{i}", s) for i, s in enumerate(BENT)]
        members.append(_bent("RO", 200e6, runout=True))
        out = groups.run_group("fatigue.sn_bilinear", members, {})
        blocks = registry.get("fatigue.sn_bilinear").meta["card"](
            out.values, out.detail, out.warnings
        )
        assert set(blocks) == {"sn_bilinear"}
        block = blocks["sn_bilinear"]
        assert block["values"]["model"] == "bilinear"
        assert "basquin_a" not in block["values"]
        assert block["values"]["sn_b2"] == pytest.approx(B2, rel=1e-5)
        assert len(block["rows"]) == 10 and sum(row["runout"] for row in block["rows"]) == 1
