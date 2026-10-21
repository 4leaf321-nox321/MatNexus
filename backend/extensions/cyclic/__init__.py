"""반복(사이클) 시험의 공용 단계 — 반복 인장 · 반복 압축 · 반복 굽힘(2026-10-20).

    처리   cyclic.cycles              사이클 분리 — 점마다 사이클 번호 · 하중/제하 가지
           cyclic.unloading_modulus   사이클별 제하 탄성률(제하 가지 윗부분의 기울기)
           cyclic.residual_strain     사이클별 잔류 변형률(제하가 응력 0 을 지나는 곳)
           cyclic.hysteresis          사이클별 히스테리시스 에너지(고리 넓이) · 손실 비

**시험 종류를 따로 두지 않는다** — 반복 인장은 인장 시험이고 하중이 오르내릴 뿐이다. 앞 단계
(인장 · 압축 · 굽힘의 응력-변형률)가 만든 열을 찾아 쓰므로, 같은 단계가 세 시험에 다 선다.
하중 채널이 있는 시험이면 단계 목록에 뜬다(`requires_channels`). 부서가 「반복 인장」 같은
종류를 따로 만들어도 하중 채널이 있으면 그대로 쓴다.

사용자 보고(2026-10-20): 반복 시험 공용 단계(사이클 분리 · 사이클별 제하 탄성률 · 잔류 변형률 ·
히스테리시스 에너지)가 없었다. 계산은 `cycles.py`.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import cycles

#: 하중이 있는 시험이면 선다 — 인장 · 압축 · 굽힘, 그리고 부서가 만든 반복 시험 종류.
_FORCE = (("force",),)


def _common() -> tuple[ParamSpec, ...]:
    return (
        ParamSpec(
            name="min_amplitude",
            label="뒤집힘 문턱",
            type="float",
            default=cycles.MIN_AMPLITUDE,
            unit="1",
            help=(
                "응력이 전체 폭의 이 비율보다 크게 돌아가야(변형률도 함께 줄어야) 하중 ↔ "
                "제하가 바뀐 것으로 봅니다. 잡음이 사이클로 세어지면 키우세요."
            ),
        ),
        ParamSpec(
            name="strain",
            label="변형률 열",
            type="str",
            role="column",
            help="비우면 앞 단계가 만든 것 — 인장 공칭 · 압축 · 굽힘 차례로 찾습니다.",
        ),
        ParamSpec(
            name="stress",
            label="응력 열",
            type="str",
            role="column",
            help="비우면 변형률 열과 짝인 것.",
        ),
    )


def _three(key: str, label: str, unit: str) -> tuple[Produced, ...]:
    return (
        Produced(key=f"{key}_first", label=f"{label} (첫 사이클)", si_unit=unit),
        Produced(key=f"{key}_last", label=f"{label} (마지막 사이클)", si_unit=unit),
        Produced(key=f"{key}_mean", label=f"{label} (평균)", si_unit=unit),
    )


register(
    id="cyclic.cycles",
    kind="processing",
    label="사이클 분리",
    requires_channels=_FORCE,
    params=_common(),
    makes_columns=(
        Produced(key=cycles.CYCLE, label="사이클 번호", si_unit="1", help="사이클 밖은 0."),
        Produced(
            key=cycles.BRANCH, label="가지", si_unit="1", help="+1 하중, -1 제하, 0 사이클 밖."
        ),
    ),
    makes_values=(Produced(key="cycle_count", label="사이클 수", si_unit="1"),),
    order=60,
    version="1",
)(cycles.cycles)

register(
    id="cyclic.unloading_modulus",
    kind="processing",
    label="사이클별 제하 탄성률",
    requires_channels=_FORCE,
    params=(
        *_common(),
        ParamSpec(
            name="unload_fraction",
            label="잴 제하 구간",
            type="float",
            default=cycles.UNLOAD_FRACTION,
            unit="1",
            help="꼭짓점에서 내려온 응력 폭의 이 비율까지 — 제하 가지 윗부분의 직선 구간.",
        ),
    ),
    makes_values=(
        *_three("unloading_modulus", "제하 탄성률", "Pa"),
        Produced(
            key="unloading_modulus_ratio",
            label="제하 탄성률 비 (마지막/첫)",
            si_unit="1",
            help="1 보다 작으면 사이클마다 강성이 떨어졌다(손상).",
        ),
    ),
    order=61,
    version="1",
)(cycles.unloading_modulus)

register(
    id="cyclic.residual_strain",
    kind="processing",
    label="사이클별 잔류 변형률",
    requires_channels=_FORCE,
    params=_common(),
    makes_values=(
        *_three("residual_strain", "잔류 변형률", "1"),
        Produced(key="residual_strain_max", label="잔류 변형률 (최대)", si_unit="1"),
    ),
    order=62,
    version="1",
)(cycles.residual_strain)

register(
    id="cyclic.hysteresis",
    kind="processing",
    label="사이클별 히스테리시스 에너지",
    requires_channels=_FORCE,
    params=_common(),
    makes_values=(
        *_three("hysteresis_energy", "히스테리시스 에너지", "J/m3"),
        Produced(
            key="hysteresis_energy_total", label="히스테리시스 에너지 (합)", si_unit="J/m3"
        ),
        *_three("energy_loss_ratio", "손실 비 (고리/하중 에너지)", "1"),
    ),
    order=63,
    version="1",
)(cycles.hysteresis)
