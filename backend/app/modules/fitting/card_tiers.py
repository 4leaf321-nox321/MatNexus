"""카드 값의 등급 — **덱만 받은 사람이 「이 값 믿을 만한가」 를 파일 안에서 본다.**

값 검색(`shared/tiers`)이 문헌·사내를 같은 1~4 척도로 매기게 됐다(2026-09-16). 카드도
같은 척도로 자기 값마다 등급을 산출해 덱 각주에 적는다 — 「이 덱은 등급 1 값 3개 ·
등급 3 값 2개(밀도·푸아송비)」. 덱을 나중에 읽는 사람에게는 각주가 근거의 전부다.

## 사람이 매기지 않는다

카드가 자기 근거(`source.sample_count` · 값의 `_source` · 합성 표지)에서 산출한다. 저장하지
않고 덱을 낼 때마다 센다 — 저장하면 규칙이 바뀌었을 때 옛 카드가 옛 등급을 든 채 남는다.

    시험에서 온 값       표본 3 이상 1 · 1~2 는 2         (`tiers.measured_tier`)
    적어 둔 값           출처로 — 밀시트·데이터시트 1 · 규격 2 · 문헌 3 · 추정 4
    재료에 적힌 공칭값    3  (어디서 왔는지 모르는 옮겨 적음)
    사람이 직접 넣은 값   4  (근거 없음)
    합성 곡선·외삽 구간   4
"""

from __future__ import annotations

from collections import defaultdict

from app.modules.fitting.models import PropertyCard
from app.shared import tiers
from matcore import cards

#: 값의 `_source` 코드 → 등급. 시험에서 온 것은 표본 수로 따로 본다.
_SOURCE_TIERS: dict[str, int] = {
    "material": 3,
    "manual": 4,
}
_MEASURED_SOURCES = ("measured", "sample", "prony")

#: 시험에서 나오는 **내장** 블록 — 표본 수로 등급을 매긴다.
_MEASURED_BLOCKS = ("table", "hardening", "hyperelastic", "viscoelastic", "lve", "rate_table")


def _measured_block(key: str) -> bool:
    """이 항목란의 값이 시험에서 나오나.

    내장은 위 목록이 정하고, **화면에서 만든 항목란은 스스로 선언한다**
    (`meta["measured"]`, ADR 0033) — 그것 하나 때문에 코드의 목록에 이름을 더하러
    오게 하면 「배포 없이」 가 반만 참이 된다.
    """
    if key in _MEASURED_BLOCKS:
        return True
    try:
        return bool(cards.block(key).meta.get("measured"))
    except KeyError:
        # 레지스트리가 모르는 블록 — 끈 항목란이거나 사라진 확장이다. 옛 카드의
        # 값은 그대로 보이되 등급은 못 매긴다(`cards.unknown` 이 따로 말한다).
        return False


def _sample_count(card: PropertyCard) -> int:
    raw = (card.source or {}).get("sample_count", 0)
    return int(raw) if isinstance(raw, int | float) else 0


def value_tiers(card: PropertyCard) -> dict[str, int]:
    """`블록.값` 또는 `블록` → 등급. 카드에 없는 값은 없다."""
    cards.load_builtin()
    count = _sample_count(card)
    synthetic = any(
        str(line).startswith("합성") for line in (card.source or {}).get("notes", [])
    )
    out: dict[str, int] = {}
    for block_key, payload in (card.blocks or {}).items():
        values = cards.values_of(payload)
        for key, value in values.items():
            if key.endswith(("_source", "_reference")) or value is None:
                continue
            if not isinstance(value, int | float) or isinstance(value, bool):
                continue
            source = str(values.get(f"{key}_source", ""))
            if source.startswith("declared:"):
                out[f"{block_key}.{key}"] = tiers.declared_tier(
                    source.removeprefix("declared:")
                )
            elif source in _MEASURED_SOURCES:
                out[f"{block_key}.{key}"] = tiers.measured_tier(count)
            elif source in _SOURCE_TIERS:
                out[f"{block_key}.{key}"] = _SOURCE_TIERS[source]
            elif _measured_block(block_key) and count > 0:
                out[f"{block_key}.{key}"] = tiers.measured_tier(count)
        if _measured_block(block_key) and (payload or {}).get("rows"):
            if synthetic or values.get("source") == "합성":
                out[block_key] = tiers.computed_tier()
            elif values.get("source") == "외삽":
                # 측정 구간과 외삽 구간이 한 표에 있다 — 표 전체는 외삽이 든 채로 4 는 아니고,
                # 각주가 어디까지가 측정인지 따로 말한다. 표본 수로 매기되 표지는 남긴다.
                out[block_key] = tiers.measured_tier(count) if count else tiers.computed_tier()
            elif count:
                out[block_key] = tiers.measured_tier(count)
    return out


def _label(path: str) -> str:
    block_key, _, key = path.partition(".")
    try:
        spec = cards.block(block_key)
    except KeyError:
        return path
    if not key:
        return spec.label
    for item in (*spec.produces, *spec.rows):
        if item.key == key:
            return item.label
    return f"{spec.label} {key}"


def summary_lines(card: PropertyCard) -> list[str]:
    """덱 각주 줄. 등급마다 한 줄 — 「등급 3: 밀도 · 푸아송비」. 값이 없으면 빈 목록."""
    graded = value_tiers(card)
    if not graded:
        return []
    by_tier: dict[int, list[str]] = defaultdict(list)
    for path, tier in graded.items():
        by_tier[tier].append(_label(path))
    lines = ["값 등급(1 좋음 ~ 4 계산·추정 — 문헌과 같은 척도):"]
    for tier in sorted(by_tier):
        names = " · ".join(dict.fromkeys(by_tier[tier]))
        lines.append(f"  등급 {tier} — {tiers.TIER_LABELS[tier]}: {names}")
    return lines


def worst_tier(card: PropertyCard) -> int | None:
    """가장 낮은 등급 — 덱 묶음(BOM) 머리에 「등급 4 값이 든 재료 N」 을 적을 때."""
    graded = value_tiers(card)
    return max(graded.values()) if graded else None


__all__ = ["summary_lines", "value_tiers", "worst_tier"]
