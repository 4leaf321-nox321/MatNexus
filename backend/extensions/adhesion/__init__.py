"""박리 · 이탈력 — 테이프 박리 · 배터리 PTT · SIM 트레이 삽입/인출(2026-10-20).

    처리   adhesion.peel      하중-변위 → 최대 하중 · 안정 구간 평균 박리력 ·
                              박리 강도(N/m) · 파단 에너지(J) ·
                              접착 에너지(J/m², 박리 각도를 알 때)
    묶음   adhesion.summary   시편 여럿의 평균 · 변동계수
                              → 응집 영역 카드 · 참고 물성(박리 강도)
    블록   cohesive_zone      파괴 에너지 G_c · 최대 견인력 T_max(`card.py`)

사용자 보고: 이탈력(배터리 PTT · 테이프 · SIM 트레이 삽입 · 인출) 처리 단계가 없었다.
시험 종류 `adhesion`(박리 · 이탈력)은 중심이 든다. 계산은 `peel.py`.
"""

from __future__ import annotations

from matcore.registry import ParamSpec, Produced, register

from . import card as _card  # noqa: F401  (블록 등록)
from . import peel

register(
    id="adhesion.peel",
    kind="processing",
    label="박리 · 이탈력",
    # **키로만 거른다** — 하중 · 변위는 인장도 같아서, 채널로 거르면 인장 목록에 뜬다
    # (`tests/architecture/test_applies_to.py` 의 `SAME_SHAPE_AS_TENSILE`).
    applies_to=("adhesion",),
    params=(
        ParamSpec(
            name="width",
            label="시편 폭",
            type="float",
            unit="m",
            dimension="length",
            default="@?specimen_width",
            help=(
                "박리 강도(N/m)의 분모 — 비우면 박리 강도를 안 냅니다"
                "(이탈 · 삽입은 폭이 없다)."
            ),
        ),
        ParamSpec(
            name="peel_angle",
            label="박리 각도",
            type="float",
            unit="rad",
            dimension="angle",
            default="@?condition_peel_angle",
            help="90° · 180° 등 — 접착 에너지 = 박리 강도 · (1 - cos θ). 비우면 안 냅니다.",
        ),
        ParamSpec(
            name="window_start",
            label="안정 구간 시작",
            type="float",
            default=peel.WINDOW_START,
            unit="1",
            help="변위 폭의 비율. 처음 당겨 세우는 구간을 뺍니다.",
        ),
        ParamSpec(
            name="window_end",
            label="안정 구간 끝",
            type="float",
            default=peel.WINDOW_END,
            unit="1",
            help="변위 폭의 비율. 끝에서 떨어지는 구간을 뺍니다.",
        ),
        ParamSpec(
            name="force", label="하중 열", type="str", role="column", default=peel.FORCE
        ),
        ParamSpec(
            name="displacement",
            label="변위 열",
            type="str",
            role="column",
            default=peel.DISPLACEMENT,
        ),
    ),
    makes_values=(
        Produced(
            key="max_force", label="최대 하중", si_unit="N", help="이탈 · 삽입력의 보고값."
        ),
        Produced(key="max_force_displacement", label="최대 하중의 변위", si_unit="m"),
        Produced(key="plateau_force", label="안정 구간 평균 하중", si_unit="N"),
        Produced(key="plateau_force_cv", label="안정 구간 변동계수", si_unit="1"),
        Produced(
            key="peel_strength",
            label="박리 강도",
            si_unit="N/m",
            property_key="interface.peel_strength",
        ),
        Produced(key="fracture_energy", label="파단 에너지(곡선 아래 넓이)", si_unit="J"),
        Produced(key="adhesion_energy", label="접착 에너지", si_unit="J/m2"),
    ),
    order=10,
    version="1",
)(peel.peel)

register(
    id="adhesion.summary",
    kind="grouping",
    label="박리 · 이탈력 묶음 (평균 → 응집 영역)",
    applies_to=("adhesion",),
    makes_values=(
        *(
            Produced(key=key, label=label, si_unit=unit)
            for key, label, unit in (
                ("max_force", "최대 하중 (평균)", "N"),
                ("plateau_force", "안정 구간 평균 하중 (평균)", "N"),
                ("peel_strength", "박리 강도 (평균)", "N/m"),
                ("fracture_energy", "파단 에너지 (평균)", "J"),
                ("adhesion_energy", "접착 에너지 (평균)", "J/m2"),
            )
        ),
        Produced(key="sample_count", label="시편 수", si_unit="1"),
    ),
    # 채택된 결과의 값 — 없으면 사람이 표로 적은 요약값에서(외부 자료 · 보고서만 있는 시험).
    members={"from": "measured_or_stated", "values": [], "optional": list(peel.SUMMARY_KEYS)},
    card=peel.card_blocks,
    order=20,
    version="1",
)(peel.summary)
