"""카탈로그 ↔ MatNexus 라벨 매핑 — **잇는 지점은 여기 한 곳이다** (ADR 0027).

카탈로그는 자기 라벨(MT 물성 정의 271종·category 7종)로 닫힌 세계다. 우리
체계와 이어 보여 줄 때만 이 표를 거친다 — 화면·통계가 각자 이름을 짜맞추면
같은 물성이 화면마다 다르게 이어진다.

## 우리 쪽 「자리」 가 셋이다

같은 물성이라도 MatNexus 에서 사는 곳이 다르다:

    declared   기준정보 property_item 항목 — 선언 물성 추가로 입력
    column     재료의 기본 칸 (Material.density_si · poisson_ratio) —
               선언 물성 항목으로 또 받으면 같은 값을 두 곳에 받게 된다
    measured   처리 결과 스칼라 키 — 시험이 주는 값

매핑을 추가할 때 이 구분을 지킬 것 — 「밀도」 를 property_item 에 넣고 싶어지면
그 전에 재료 기본 칸과의 관계부터 정해야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    label: str
    """우리 쪽 표시 이름 — 기준정보 property_item 값 또는 컬럼의 한글 라벨."""
    place: str
    """declared · column · measured — 위 모듈 주석 참고."""


#: MT 물성 키 → 우리 자리. **MT key 는 안정 id 다**(`domain.name` 꼴) — 이름이
#: 개명돼도 매핑은 안 깨진다. 우리 쪽 이름 개명(열전도도→열전도율 등)이 확정되면
#: 이 표의 label 만 따라 바꾼다.
PROPERTY_ITEM_MAP: dict[str, Target] = {
    "mechanical.youngs_modulus": Target("탄성계수", "declared"),
    "mechanical.shear_modulus": Target("전단탄성계수", "declared"),
    "mechanical.yield_strength": Target("항복강도", "declared"),
    "mechanical.tensile_strength": Target("인장강도", "declared"),
    "mechanical.elongation_at_break": Target("연신율", "declared"),
    "thermal.specific_heat": Target("비열", "declared"),
    # 이름 정비 예정(사용자 결정 2026-09-05): 열전도도→열전도율,
    # 열팽창계수→선팽창계수(CTE). 개명은 기준정보 개명 기계(별칭 흡수)로 별도
    # 진행하고, 확정되면 여기 label 을 따라 바꾼다.
    "thermal.conductivity": Target("열전도도", "declared"),
    "thermal.expansion_linear": Target("열팽창계수", "declared"),
    # 재료의 기본 칸 — 선언 물성 항목이 아니다.
    "physical.density": Target("밀도", "column"),
    "mechanical.poisson_ratio": Target("포아송비", "column"),
}

#: 자리 → 검증 근거. column 은 Material 의 실제 컬럼 이름.
COLUMN_TARGETS: dict[str, str] = {
    "밀도": "density_si",
    "포아송비": "poisson_ratio",
}

#: MT category → 우리 family 축 표기. MT 는 영어 소문자, 우리 축은 대문자
#: 표기(Metal·Polymer)를 쓴다. 아직 우리 축에 없는 값(Ceramic 등)은 카탈로그
#: 재료를 사내 재료와 연결하는 단계에서 family 용어로 만들어진다.
CATEGORY_MAP: dict[str, str] = {
    "metal": "Metal",
    "polymer": "Polymer",
    "ceramic": "Ceramic",
    "composite": "Composite",
    "rubber": "Rubber",
    "foam": "Foam",
    "molecular": "Molecular",
}
