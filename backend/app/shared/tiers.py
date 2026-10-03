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

## 문헌 카탈로그에서 받아 온 값은 그 값의 등급이다 (2026-10-03)

문헌이 3 인 까닭은 「어느 문헌인지 · 그 문헌의 등급을 모른다」 다. **카탈로그에서 받아 온 값은
안다** — 카탈로그가 값마다 등급을 든다. 그 근거를 버리고 3 으로 적었더니 논문에서 잰 1등급
값이 「옮겨 적음」 이 됐다(사용자 보고). 이제 받아 온 줄은 그 문헌 값의 등급을 잇는다
(`catalog_tier` — 서버가 그 값과 숫자를 대 보고 붙인 근거, `shared/declared_catalog`). 근거는
값에 묶여 있어 값을 고치면 풀리고 출처의 등급으로 돌아간다. 승인과 같은 규칙이다.

## 승인은 근거다 — 등급을 매기는 것이 아니다 (ADR 0049)

자료 관리자가 선언 값을 근거 문서와 대조해 **승인**하면 한 단계 오른다 — 문헌 3 → 2,
추정 4 → 3. 사람이 등급을 고르는 것이 아니라 「누가 언제 근거를 확인했다」 는 사실이
근거에 하나 더 붙고, 등급은 여전히 그 근거에서 산출한다. 값을 고치면 승인은 풀린다
(`shared/declared_approval`).

**2 위로는 못 간다.** 1 은 「그 제품 문서에 인쇄된 실측」 이다. 승인은 근거를 확인한
것이지 실측을 만들지 않는다 — 승인으로 1 이 되면 등급 1 이 「잰 값」 이라는 뜻을 잃는다.

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


#: 승인으로 오를 수 있는 가장 높은 등급. 1 은 실측의 자리다(위 「승인은 근거다」).
APPROVED_CEILING = 2

#: 카드 칸의 `<키>_source` 에서 **승인된** 선언 값을 가르는 꼬리 —
#: `declared:literature+approved`.
#: 카드는 만들 때의 근거를 든 스냅샷이라(ADR 0012), 승인 여부도 그때의 것을 칸이 든다.
APPROVED_MARK = "+approved"

#: 카드 칸의 `<키>_source` 에서 **문헌 카탈로그에서 받아 온** 선언 값의 그 문헌 등급 —
#: `declared:literature+catalog1`. 승인 꼬리는 그 뒤다(`…+catalog3+approved`). 카드는 받아 온
#: 근거도 만들 때의 것을 든다 — 출처만 남기면 카드에서 등급을 다시 셀 때 3 으로 돌아간다.
CATALOG_MARK = "+catalog"


def declared_tier(
    source: str | None, *, approved: bool = False, catalog_tier: int | None = None
) -> int:
    """사람이 적어 넣은 값. 모르는 출처는 **가장 낮게** — 좋게 봐 주면 등급이 뜻을 잃는다.

    `catalog_tier` 는 문헌 카탈로그에서 받아 온 값의 그 문헌 등급이다(위 「받아 온 값」) —
    있으면 출처 대신 그것이 근거다. `approved` 면 한 단계 오르되 `APPROVED_CEILING` 위로는
    안 간다.
    """
    if catalog_tier is not None and catalog_tier in TIER_LABELS:
        tier = catalog_tier
    else:
        tier = DECLARED_TIERS.get((source or "").strip().lower(), 4)
    if approved and tier > APPROVED_CEILING:
        return tier - 1
    return tier


def declared_origin(
    source: str | None, *, approved: bool, catalog_tier: int | None = None
) -> str:
    """카드 칸에 적는 출처 표지 — `declared:<출처>`, 받아 온 문헌 등급이면 `+catalog<N>`,
    승인이면 끝에 `+approved`."""
    mark = (
        f"{CATALOG_MARK}{catalog_tier}"
        if catalog_tier is not None and catalog_tier in TIER_LABELS
        else ""
    )
    return f"declared:{source or 'unknown'}{mark}{APPROVED_MARK if approved else ''}"


def split_declared(where: str) -> tuple[str, bool]:
    """`declared:` 뒤의 낱말 → (출처, 승인됐나). 꼬리가 없으면 승인 전이다.

    받아 온 문헌 등급(`+catalog<N>`)은 떼고 출처만 돌려준다 — 그 등급은 `catalog_tier_in` 이
    읽는다. 안 떼면 출처가 `literature+catalog1` 이 되어 모르는 출처(4)로 읽힌다.
    """
    approved = where.endswith(APPROVED_MARK)
    if approved:
        where = where.removesuffix(APPROVED_MARK)
    if catalog_tier_in(where) is not None:
        where = where[: where.rindex(CATALOG_MARK)]
    return where, approved


def catalog_tier_in(where: str) -> int | None:
    """출처 표지에 든 받아 온 문헌 등급 — 없으면 None. `declared:` 는 있어도 없어도 된다."""
    where = where.removesuffix(APPROVED_MARK)
    head, mark, tail = where.rpartition(CATALOG_MARK)
    if not mark or not head or not tail.isdigit() or int(tail) not in TIER_LABELS:
        return None
    return int(tail)


def computed_tier() -> int:
    """계산식·합성 곡선으로 만든 값."""
    return 4
