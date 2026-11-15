"""응력완화 + DMA 마스터커브 잇기 — 확장 `relaxation.dma_coupled`(2026-11-15, VOC 52 · ADR
0087).

답을 아는 합성 재료 — 일반화 Maxwell 14항(τ 1e-9~1e4 s, 자릿수마다, 로그 정규 스펙트럼 중심
1e-2 s), E₀ 3 GPa · E∞ 30 MPa, 기준 20 °C, WLF c1 8.86 · c2 101.6. DMA 는 -20~60 °C 를 10 K
간격으로 0.1~20 Hz 를 잰 것을 겹친 마스터커브, 응력완화는 40 °C 1~1e4 s.

    이으면           순간 탄성률이 참값(3 GPa) 근처 — 응력완화만이면 그 몇 분의 일
    겹친 구간        같은 재료면 비 ≈ 1, 25 % 넘게 다르면 막고 5 % 넘으면 말한다
    옮기기           이동을 맞춘 온도 범위 밖이면 외삽이라 막는다
    선형 구간        근거가 없으면 말하고, 유지 변형률이 한계를 넘으면 말한다
    전단(G′)         E = 2(1+ν)G 로 옮기면 인장으로 넣은 것과 같은 E₀ — ν 는 옵션 → 재료,
                     없으면 막는다(2026-11-15, 판 2)
"""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

from matcore import cards, extensions
from matcore.groups import GroupError, Member

extensions.load(Path(__file__).resolve().parents[2] / "extensions")
cards.load_builtin()

coupling = importlib.import_module(f"{extensions.PACKAGE}.relaxation.coupling")

TAUS = 10.0 ** np.arange(-9, 5)
_WEIGHTS = np.exp(-0.5 * ((np.log10(TAUS) + 2.0) / 2.0) ** 2)
E0, EINF = 3.0e9, 3.0e7
MODULI = (E0 - EINF) * _WEIGHTS / _WEIGHTS.sum()
REFERENCE_K = 293.15
C1, C2 = 8.86, 101.6


def _log_a(temperature_k: float) -> float:
    delta = temperature_k - REFERENCE_K
    return -C1 * delta / (C2 + delta)


def _relaxation(time: np.ndarray, temperature_k: float) -> np.ndarray:
    a_t = 10 ** _log_a(temperature_k)
    return EINF + np.sum(
        MODULI[:, None] * np.exp(-time[None, :] / (TAUS[:, None] * a_t)), axis=0
    )


def _master() -> Member:
    """잰 온도 · 주파수를 기준 온도로 옮겨 겹친 것 — 정확히 겹치는 합성이라 마스터커브
    그대로."""
    temperatures = REFERENCE_K + np.arange(-40.0, 41.0, 10.0)
    measured = np.geomspace(0.1, 20.0, 8)
    reduced = np.sort(np.concatenate([measured * 10 ** _log_a(t) for t in temperatures]))
    omega_tau = 2 * np.pi * reduced[None, :] * TAUS[:, None]
    storage = EINF + np.sum(MODULI[:, None] * omega_tau**2 / (1 + omega_tau**2), axis=0)
    loss = np.sum(MODULI[:, None] * omega_tau / (1 + omega_tau**2), axis=0)
    return Member(
        label="DMA_01",
        columns={"frequency_hz": reduced, "storage_pa": storage, "loss_pa": loss},
        values={"reference_temperature_k": REFERENCE_K},
        meta={
            "test_type": "dma_sweep",
            "shear": False,
            "shift": {
                "method": "wlf",
                "parameters": {"c1": C1, "c2": C2},
                "shifts": [{"temperature_k": t, "log10_a_t": _log_a(t)} for t in temperatures],
            },
        },
    )


def _relax(
    label: str = "SRX_01",
    temperature_k: float = REFERENCE_K + 20.0,
    scale: float = 1.0,
    **values: float,
) -> Member:
    time = np.geomspace(1.0, 1e4, 60)
    return Member(
        label=label,
        columns={"time": time, "relaxation_modulus": _relaxation(time, temperature_k) * scale},
        values={"temperature": temperature_k, **values},
        meta={"test_type": "stress_relaxation"},
    )


def test_이으면_순간_탄성률이_짧은_시간까지_맞는다() -> None:
    outcome = coupling.couple(
        [_relax(lve_strain_limit=0.01, held_strain_used=0.005), _master()]
    )
    values = outcome.values
    assert values["instantaneous_pa"] == pytest.approx(E0, rel=0.05)
    # 응력완화만이면 첫 측정(1 s) 근처에 묶여 몇 분의 일이었다.
    assert values["relaxation_only_instantaneous_pa"] < 0.5 * E0
    assert values["overlap_ratio"] == pytest.approx(1.0, abs=0.02)
    assert values["overlap_points"] >= coupling.MIN_OVERLAP_POINTS
    assert values["reference_temperature_k"] == pytest.approx(REFERENCE_K + 20.0)
    # 맞춘 Prony 가 응력완화 점과 DMA 가 덮는 짧은 시간 모두에서 참값을 따른다.
    terms = outcome.detail["terms"]
    probe = np.geomspace(values["time_min"], 1e4, 40)
    fitted = values["equilibrium_pa"] + sum(
        one["modulus_pa"] * np.exp(-probe / one["relaxation_time_s"]) for one in terms
    )
    truth = _relaxation(probe, REFERENCE_K + 20.0)
    assert float(np.max(np.abs(fitted / truth - 1))) < 0.1
    assert outcome.warnings[0].startswith("짧은 시간")
    assert not any("확인하세요" in one or "근거가 없습니다" in one for one in outcome.warnings)


@pytest.mark.parametrize(("scale", "blocked"), [(0.6, True), (0.9, False)])
def test_겹친_구간이_다르면_막거나_말한다(scale: float, blocked: bool) -> None:
    """25 % 를 넘으면 같은 것을 잰 두 곡선이 아니다(로트 · 온도 기록 · 비선형). 그 사이는 잇되
    말한다."""
    members = [_relax(scale=scale), _master()]
    if blocked:
        with pytest.raises(GroupError, match="잇지 않습니다"):
            coupling.couple(members)
        return
    outcome = coupling.couple(members)
    assert outcome.values["overlap_ratio"] == pytest.approx(scale, rel=0.03)
    assert any("확인하세요" in one for one in outcome.warnings)


def test_이동을_맞춘_온도_범위_밖이면_외삽이라_막는다() -> None:
    with pytest.raises(GroupError, match="외삽"):
        coupling.couple([_relax(temperature_k=REFERENCE_K + 70.0), _master()])


def test_한_온도씩만_잇는다() -> None:
    with pytest.raises(GroupError, match="섞여"):
        coupling.couple(
            [_relax("A", REFERENCE_K + 20.0), _relax("B", REFERENCE_K + 30.0), _master()]
        )


def test_겹치는_시간대가_없으면_막는다() -> None:
    """DMA 가 그 온도에서 덮는 시간이 응력완화의 첫 측정보다 짧으면 견줄 수 없다."""
    curve = _master()
    keep = curve.columns["frequency_hz"] > 1e3
    short = Member(
        label=curve.label,
        columns={key: value[keep] for key, value in curve.columns.items()},
        values=curve.values,
        meta=curve.meta,
    )
    with pytest.raises(GroupError, match="겹치는 시간대"):
        coupling.couple([_relax(), short])


def _shear_master(poisson: float, **values: float) -> Member:
    """같은 재료를 **전단으로 잰** 마스터커브 — G′ = E′ / 2(1+ν), G″ = E″ / 2(1+ν)."""
    curve = _master()
    factor = 2.0 * (1.0 + poisson)
    columns = {
        "frequency_hz": curve.columns["frequency_hz"],
        "storage_pa": curve.columns["storage_pa"] / factor,
        "loss_pa": curve.columns["loss_pa"] / factor,
    }
    return Member(
        curve.label, columns, {**curve.values, **values}, {**curve.meta, "shear": True}
    )


@pytest.mark.parametrize(
    ("option", "material", "source"),
    [(0.4, None, "option"), (None, 0.4, "material"), (0.4, 0.3, "option")],
)
def test_전단으로_넣어도_인장으로_넣은_것과_같은_E0(
    option: float | None, material: float | None, source: str
) -> None:
    """2026-11-15 — 전단(G′) 마스터커브를 E = 2(1+ν)G 로 옮겨 잇는다. ν 는 옵션 → 재료의 순."""
    tensile = coupling.couple([_relax(), _master()])
    given = {"poisson_ratio": material} if material is not None else {}
    outcome = coupling.couple([_relax(), _shear_master(0.4, **given)], poisson_ratio=option)
    values = outcome.values
    assert values["instantaneous_pa"] == pytest.approx(
        tensile.values["instantaneous_pa"], rel=1e-6
    )
    assert values["instantaneous_pa"] == pytest.approx(E0, rel=0.05)
    assert values["overlap_ratio"] == pytest.approx(tensile.values["overlap_ratio"], rel=1e-6)
    assert values["dma_poisson_ratio"] == pytest.approx(0.4)
    assert outcome.detail["dma_poisson_source"] == source
    assert "G′" in outcome.detail["dma_modulus_basis"]
    named = "묶음 옵션" if source == "option" else "재료에 적힌 값"
    converted = [one for one in outcome.warnings if "전단(G′)으로 잰 것" in one]
    assert len(converted) == 1 and f"ν = 0.4({named})" in converted[0]
    assert not any("0.5 에 가깝습니다" in one for one in outcome.warnings)
    # 인장으로 넣은 것은 ν 를 안 남긴다.
    assert "dma_poisson_ratio" not in tensile.values


def test_전단인데_푸아송비가_없으면_지어내지_않고_막는다() -> None:
    with pytest.raises(GroupError, match="푸아송비가 필요합니다"):
        coupling.couple([_relax(), _shear_master(0.4)])
    with pytest.raises(GroupError, match=r"-1 과 0\.5 사이"):
        coupling.couple([_relax(), _shear_master(0.4)], poisson_ratio=0.7)
    with pytest.raises(GroupError, match="숫자로 읽을 수 없습니다"):
        coupling.couple([_relax(), _shear_master(0.4)], poisson_ratio="약 0.4")


def test_고무에_가까운_푸아송비는_따로_말한다() -> None:
    outcome = coupling.couple([_relax(), _shear_master(0.49)], poisson_ratio="0.49")
    assert outcome.values["instantaneous_pa"] == pytest.approx(E0, rel=0.05)
    assert any("0.5 에 가깝습니다(고무)" in one for one in outcome.warnings)


def test_인장_마스터커브에_준_푸아송비는_안_썼다고_말한다() -> None:
    outcome = coupling.couple([_relax(), _master()], poisson_ratio=0.4)
    assert any("푸아송비 옵션(0.4)은 쓰지 않았습니다" in one for one in outcome.warnings)
    assert "dma_poisson_ratio" not in outcome.values


def test_마스터커브는_하나_응력완화는_하나_이상() -> None:
    with pytest.raises(GroupError, match="마스터커브가 2개"):
        coupling.couple([_relax(), _master(), _master()])
    with pytest.raises(GroupError, match="응력완화 시험이 없습니다"):
        coupling.couple([_master()])


def test_선형_구간_근거() -> None:
    nothing = coupling.couple([_relax(), _master()])
    assert any("선형 구간 근거가 없습니다" in one for one in nothing.warnings)
    over = coupling.couple([_relax(lve_strain_limit=0.01, held_strain_used=0.02), _master()])
    assert any("한계 0.01 를 넘습니다" in one for one in over.warnings)


def test_카드는_점탄성_블록에_이음_근거를_싣는다() -> None:
    outcome = coupling.couple([_relax(), _master()])
    blocks = coupling.card_blocks(outcome.values, outcome.detail, outcome.warnings)
    shown = blocks["viscoelastic"]["values"]
    assert shown["dma_join_time_s"] == pytest.approx(outcome.values["dma_join_time_s"])
    assert shown["overlap_ratio"] == pytest.approx(outcome.values["overlap_ratio"])
    assert blocks["elastic"]["values"]["youngs_modulus"] == pytest.approx(
        outcome.values["instantaneous_pa"]
    )
    assert shown["modulus_basis"].startswith("E′ (인장 · 굽힘 DMA)")
    assert "dma_poisson_ratio" not in shown
    declared = {one.key for one in cards.block("viscoelastic").produces}
    assert set(shown) <= declared  # 선언된 칸만 — 화면은 선언한 값만 그린다

    sheared = coupling.couple([_relax(), _shear_master(0.4)], poisson_ratio=0.4)
    blocks = coupling.card_blocks(sheared.values, sheared.detail, sheared.warnings)
    shown = blocks["viscoelastic"]["values"]
    assert shown["dma_poisson_ratio"] == pytest.approx(0.4)
    assert shown["modulus_basis"].startswith("G′ (전단 DMA) → E = 2(1+ν)G, ν = 0.4")
    assert set(shown) <= declared
    assert any("전단(G′)으로 잰 것" in one for one in blocks["viscoelastic"]["notes"])
