"""사람이 적어 둔 값이 **카드의 빈 칸을 채운다** — 이름을 코드에 안 적고.

## 왜 생겼나

선언 물성이 카드로 가는 길이 **여섯뿐**이었다. 탄성계수·푸아송비·밀도·비열·
선팽창계수·열전도율 — 코드에 한글 이름이 박혀 있어서(`THERMAL_ITEMS`,
`_declared(material, "탄성계수")`) 그 여섯 말고는 갈 길이 없었다.

그래서 화면에서 항목란을 만들 수 있게 해 놓고도(ADR 0033) **그 칸을 선언 물성으로는
못 채웠다.** 계산식이나 확장의 묶음이 내는 값만 실렸다 — 「밀시트에 적힌 경도」 같은,
사람이 적는 것이 전부인 물성은 카드까지 못 갔다.

## 사슬은 이미 다 있었다

빠진 것은 가운데를 걷는 코드뿐이다:

    선언 물성 항목(기준정보)  ──property_links──▶  물성 키  ◀──property_key──  블록 슬롯
          「비열」                          thermal.specific_heat        thermal.specific_heat

양쪽 끝은 데이터다. 항목↔키는 화면에서 잇고(문헌 물성의 「사내 항목 연결」), 슬롯↔키는
블록 선언이 든다(화면에서 만든 항목란에도 그 칸이 있다). 여기서는 그 둘을 맞대 본다.

**안 이어 둔 항목은 조용히 안 실린다.** 짐작으로 이으면 비열 자리에 열전도율이 들어가고
숫자는 그럴듯하다 — 안 실리는 것이 맞는 결과다. 값이 카드에 없으면 그 연결 화면부터 본다.

`shared` 에 있는 이유: 재료·기준정보·문헌·카드를 한자리에서 맞대 보는 일이라 어느 한
모듈의 것이 아니다 — 모듈끼리는 `models` 말고 직접 안 부른다(`tests/architecture`).

## 규칙 둘

**① 빈 칸만 채운다.** 시험이 낸 값이 있으면 그대로 둔다 — 잰 값이 적은 값보다
앞선다(밀도가 「시료 실측 먼저」 인 것과 같은 자리).

**② 카드에 **있는** 블록만 본다.** 재료에 적어 둔 값이 있다고 없던 블록을 만들지
않는다. 이방성 카드를 만들었는데 열물성 블록이 따라 붙으면, 그 카드가 무엇의 카드인지
흐려진다.

값에는 `<키>_source = declared:<출처>` 가 함께 붙는다. 등급 판정이 그 낱말을 읽어
밀시트 1 · 규격 2 · 문헌 3 · 추정 4 로 매긴다 — 여기서 등급을 따로 계산하지 않는다.
자료 관리자가 승인한 값이면 `declared:<출처>+approved` 다(ADR 0049, 한 단계 오른다).

## 주파수 · 파장 표 (2026-10-02, ADR 0052)

블록의 표에 `frequency` · `wavelength` 열이 있으면 **그 축의 표**다(전기 · 광학 블록). 그 축을
타는 항목이 점을 여럿 들면 `values` 의 한 값에 더해 **표로도 편다** — Dk 를 1 MHz · 1 GHz ·
10 GHz 에서 적었는데 1 MHz 의 값 하나만 실리면, 고속 신호 해석이 보는 분산이 통째로 빠진다.
표가 이미 있는 블록은 건드리지 않는다(규칙 ①과 같다). 온도 축은 여기서 안 편다 — 열 · 탄성
표는 선언 카드의 조립기가 짓는다(`shared/declared_card`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.modules.materials.models import Material
from app.shared import coverage, declared_approval
from matcore import cards

#: 블록 표의 축 열 → 선언 물성 점의 조건 칸(`shared/declared_conditions`).
ROW_AXES = {"frequency": "frequency_hz", "wavelength": "wavelength_m"}


def _declared_by_key(db: Session, material: Material) -> dict[str, dict[str, Any]]:
    """물성 키 → 적어 둔 값 하나(값·출처·근거).

    점이 여럿이면(온도 의존) **첫 점**을 쓴다 — 저장이 온도 오름차순이라 가장 낮은
    온도의 값이고, 이것은 카드 `values` 의 규약과 같다(표가 있어도 `values` 는 첫
    줄을 든다). 표로 펴는 것은 블록마다 온도 열 이름이 달라 여기서 안 한다.
    """
    links = coverage.item_links(db)
    out: dict[str, dict[str, Any]] = {}
    for row in material.declared_properties or []:
        if not isinstance(row, dict):
            continue
        # **눈금으로 고른다** — 「경도」 는 HV · HB · HRC 가 다른 키다. HRC 로 적은 값이
        # 비커스 칸에 실리면 숫자는 그럴듯하고 아무도 모른다(`coverage.ItemLinks`).
        key = links.key_of(str(row.get("item") or ""), row.get("scale"))
        points = row.get("points") or []
        if not key or key in out or not points:
            continue
        first = points[0]
        # **저장 키는 `value_si` 다.** 받을 때는 `value` + 단위인데 저장은 SI 값
        # 하나로 접힌다(`materials/declared.py`) — 입력 모양으로 읽으면 조용히
        # 아무것도 안 채워진다(실측 2026-09-23).
        if not isinstance(first, dict) or not isinstance(first.get("value_si"), int | float):
            continue
        out[key] = {
            "value": float(first["value_si"]),
            "source": str(row.get("source") or "unknown"),
            # 카드 칸의 출처 표지 — 승인이면 `+approved`. 만들 때의 승인이 카드에 박힌다.
            "origin": declared_approval.origin(row),
            "reference": row.get("reference"),
            # **어느 주파수 · 파장의 값인지** 함께 간다. 유전율은 1 MHz 와 10 GHz 에서 다른데,
            # 칸에 숫자만 실리면 덱만 받은 사람이 그것을 모른다. 잰 온도도 — 저항률의
            # 온도 계수는 그 온도를 기준으로 읽힌다.
            "conditions": {
                key: float(first[key])
                for key in ("frequency_hz", "wavelength_m", "temperature_k")
                if isinstance(first.get(key), int | float)
            },
            # 주파수 · 파장 축의 점 전부 — 표로 펴는 재료(`fill`). 저장이 축 오름차순이고
            # 점이 둘 이상이면 축 값이 다 있고 서로 다르다(`materials/declared.py`).
            "series": {
                axis: [(float(point[axis]), float(point["value_si"])) for point in points]
                for axis in ROW_AXES.values()
                if len(points) > 1
                and all(
                    isinstance(point, dict)
                    and isinstance(point.get(axis), int | float)
                    and isinstance(point.get("value_si"), int | float)
                    for point in points
                )
            },
        }
    return out


@dataclass(frozen=True)
class Fillable:
    """적어 둔 값으로 **채울 수 있는** 항목란 하나와 그 칸들."""

    key: str
    label: str
    slots: tuple[tuple[str, str, str, float, str], ...]
    """`(칸 키, 칸 이름, SI 단위, 값, 출처)`. 값은 **SI** 다."""


def fillable(db: Session, material: Material | None) -> list[Fillable]:
    """이 재료의 적어 둔 값으로 채울 수 있는 항목란들. **만들지는 않는다.**

    `fill` 이 「있는 블록의 빈 칸」 을 채운다면 이쪽은 「어느 블록이면 채울 값이
    있나」 를 답한다 — 시험 없이 카드를 만드는 화면이 **누르기 전에** 무엇이 실릴지
    보여 주는 데 쓴다.

    **고르는 것은 사람이다.** 값이 있다고 다 실으면 이방성 카드에 열물성이 따라
    붙는 것과 같은 일이 생긴다(`fill` 의 규칙 ②와 같은 판단).
    """
    if material is None:
        return []
    stated = _declared_by_key(db, material)
    if not stated:
        return []

    cards.load_builtin()
    out: list[Fillable] = []
    for spec in sorted(cards.list_blocks(), key=lambda one: one.order):
        slots = tuple(
            (
                slot.key,
                slot.label,
                slot.si_unit,
                stated[slot.property_key]["value"],
                stated[slot.property_key]["source"],
            )
            for slot in spec.produces
            if slot.property_key and slot.property_key in stated
        )
        if slots:
            out.append(Fillable(key=spec.key, label=spec.label, slots=slots))
    return out


def fill(db: Session, material: Material | None, blocks: dict[str, Any]) -> list[str]:
    """카드의 빈 칸을 적어 둔 값으로 채운다. **채운 것의 이름을 돌려준다.**

    돌려주는 이름은 각주로 쓴다 — 덱을 받은 사람이 「이 값은 잰 것인가 적은 것인가」
    를 물을 때, 카드 안의 `_source` 와 각주가 같은 말을 해야 한다.
    """
    if material is None or not blocks:
        return []
    stated = _declared_by_key(db, material)
    if not stated:
        return []

    cards.load_builtin()
    filled: list[str] = []
    for block_key, payload in blocks.items():
        if not isinstance(payload, dict):
            continue
        try:
            spec = cards.block(block_key)
        except KeyError:
            # 레지스트리가 모르는 블록 — 끈 항목란이거나 사라진 확장이다.
            continue
        values = payload.setdefault("values", {})
        if not isinstance(values, dict):
            continue
        columns = {column.key for column in spec.rows}
        axis = next((column for column in ROW_AXES if column in columns), None)
        spread: dict[str, list[tuple[float, float]]] = {}
        for slot in spec.produces:
            if not slot.property_key or slot.property_key not in stated:
                continue
            if values.get(slot.key) is not None:
                # **잰 값이 이긴다.** 적은 값으로 덮으면 그 카드가 무엇에서 나왔는지
                # 가 뒤집히고, 그 사실은 어디에도 안 남는다.
                continue
            found = stated[slot.property_key]
            values[slot.key] = found["value"]
            values[f"{slot.key}_source"] = found["origin"]
            if found["reference"]:
                # **근거 문서를 카드 안에 복사한다.** 재료의 선언을 나중에 고쳐도
                # 이미 만든 카드가 무엇을 근거로 했는지는 그대로 남아야 한다.
                values[f"{slot.key}_reference"] = str(found["reference"])
            for condition_key, at in found["conditions"].items():
                values[f"{slot.key}_{condition_key}"] = at
            filled.append(f"{spec.label} {slot.label}")
            if axis is not None and slot.key in columns:
                series = found["series"].get(ROW_AXES[axis])
                if series:
                    spread[slot.key] = series
        if spread and not payload.get("rows"):
            payload["rows"] = _table(axis or "", spread)
    return filled


def _table(axis: str, spread: dict[str, list[tuple[float, float]]]) -> list[dict[str, float]]:
    """칸마다의 점을 **한 축의 표로** — 축 값을 합집합으로 모으고 없는 칸은 비운다.

    0 으로 채우면 손실 0 인 재료가 되고, 빼 버리면 그 주파수가 통째로 사라진다
    (`declared_card.declared_table` 과 같은 규칙). 한 점짜리 칸은 표에 안 넣는다 — 모든
    줄에 같은 값을 넣으면 「주파수와 상관없다」 를 우리가 정하는 셈이다.
    """
    by_axis: dict[float, dict[str, float]] = {}
    for column, series in spread.items():
        for at, value in series:
            by_axis.setdefault(at, {})[column] = value
    return [{axis: at, **by_axis[at]} for at in sorted(by_axis)]
