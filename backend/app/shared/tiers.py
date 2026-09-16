"""품질 등급 — **사내 값에도 문헌과 같은 1~4 척도를 준다.**

찾기 결과에는 문헌값·사내 선언값·시험으로 잰 값이 한 목록에 선다. 문헌만 등급이
있었다(`catalog.QUALITY_TIERS`, 원본 독트린) — 문헌 3등급 값과 사내 3표본 평균이
같은 줄로 섰다(2026-09-16, [계획] 온톨로지 고도화 §2-C).

## 사람이 매기지 않는다

값이 **자기 근거에서 산출한다.** 매기게 두면 근거와 등급이 두 벌이 되고, 두 벌은
갈린다 — 표본을 하나 더 채택했는데 등급은 그대로인 채로.

    1  그 제품 문서에 인쇄된 실측     ← 사내: 시험 · 채택 · 표본 3 이상 / 밀시트·데이터시트
    2  핸드북·규격·공인 DB           ← 사내: 시험 · 채택 · 표본 1~2 / 규격
    3  계열 대표값·2차 인용           ← 사내: 문헌에서 옮겨 적음(어느 문헌인지 등급을 모른다)
    4  계산·추정·가정                 ← 사내: 추정 · 계산식 · 합성 곡선

문헌 쪽 뜻은 `catalog.models.QUALITY_TIERS` 가 정본이고 여기는 사내 쪽을 그 척도에
맞춰 적는다 — 두 표가 갈리면 `tests/architecture` 가 잡는다.
"""

from __future__ import annotations

#: 한 척도의 이름 — 문헌 정의(`QUALITY_TIERS`)와 같은 번호, 사내까지 아우르는 말.
TIER_LABELS: dict[int, str] = {
    1: "실측 (제품 문서 · 표본 3 이상)",
    2: "규격·공인 DB · 표본 1~2",
    3: "대표값 · 2차 인용 · 옮겨 적음",
    4: "계산·추정·가정",
}

#: 선언 물성의 출처(`materials.declared.SOURCES`) → 등급.
DECLARED_TIERS: dict[str, int] = {
    "millsheet": 1,  # 그 로트의 성적서 — 인쇄된 실측
    "datasheet": 1,  # 그 제품의 문서
    "standard": 2,  # 규격의 값
    "literature": 3,  # 어느 문헌인지·그 문헌의 등급을 모른다 — 보수적으로
    "estimate": 4,
}

#: 시험으로 잰 값이 1등급이 되는 표본 수. 반복시편 통계(ADR 0008)와 같은 문턱.
MEASURED_TIER1_COUNT = 3


def measured_tier(sample_count: int) -> int:
    """채택된 처리 결과에서 온 값. 표본이 셋이면 흩어짐을 말할 수 있다(ADR 0008)."""
    return 1 if sample_count >= MEASURED_TIER1_COUNT else 2


def declared_tier(source: str | None) -> int:
    """사람이 적어 넣은 값. 모르는 출처는 **가장 낮게** — 좋게 봐 주면 등급이 뜻을 잃는다."""
    return DECLARED_TIERS.get((source or "").strip().lower(), 4)


def computed_tier() -> int:
    """계산식·합성 곡선으로 만든 값."""
    return 4
