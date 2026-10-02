"""선언 물성 승인 — **자료 관리자가 근거 문서와 대조해 확인한 값**(ADR 0049).

선언 물성은 사람이 적은 값이라 출처로만 등급이 정해졌다 — 문헌 3 · 추정 4. 그런데
「어느 핸드북 몇 판의 몇 쪽」 을 자료 관리자가 직접 펴 보고 맞다고 한 값과, 누가 옮겨
적었는지 모르는 값이 같은 3 이었다. 승인이 그 차이를 근거에 남긴다(등급 규칙은
`shared/tiers` 의 「승인은 근거다」).

## 승인은 값에 묶인다

승인은 **그때의 값**을 확인한 것이다. 그래서 줄에 승인한 사람 · 때와 함께 **그 값의 지문**
(`digest`)을 남기고, 읽을 때마다 지문이 지금 값과 같은지 본다. 값 · 단위 · 조건 · 척도 ·
출처 · 근거 문서 중 하나라도 바뀌면 지문이 갈려 승인은 없는 것이 된다 — 승인된 값을 누가
고쳐도 「승인됨」 이 그대로 붙어 있는 일이 없다.

**비고와 표시 단위는 지문에 안 든다.** 비고를 다듬거나 MPa 를 GPa 로 바꿔 보이는 것은 값을
바꾸는 일이 아니다. 숫자는 유효숫자 9자리로 견준다 — 화면은 값을 12자리, 온도 · 조건을
10자리로 되돌려 보내므로, 고치지 않고 다시 저장한 것만으로 승인이 풀리지 않는다.

## 승인은 고치는 길로 들어오지 않는다

선언 물성 수정은 통째 교체다(PATCH). 지문은 누구나 셈할 수 있어서, 받은 줄의 `approval` 을
받아 주면 아무나 승인을 적어 넣는다. 그래서 세 겹으로 버린다 — 입력 스키마가 모르는 칸이라
버리고, `materials.declared.check` 가 줄을 새로 지으며 버리고, `carry` 가 마지막으로 뗀다. 그런
뒤 `carry` 가 **저장돼 있던** 승인 중 지문이 그대로인 것만 옮긴다. 승인은 승인 길
(`/declared/approve`, 자료 관리자만)로만 생긴다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.shared import declared_conditions, tiers
from app.shared.text import compare_key

#: 줄에서 승인이 드는 칸.
KEY = "approval"

#: 지문에서 숫자를 견주는 유효숫자. 위 「승인은 값에 묶인다」.
DIGITS = 9

#: 점 밖에서 지문에 드는 칸 — 값의 뜻을 정하는 것들. 비고(`note`) · 표시 단위
#: (`input_unit`)는 뺀다.
_EVIDENCE = ("si_unit", "scale", "source", "reference")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(f"{float(value):.{DIGITS}g}")


def digest(row: dict[str, Any]) -> str:
    """이 줄의 값 지문. 승인이 무엇을 확인했는지를 이것이 정한다."""
    body = {
        "item": compare_key(str(row.get("item") or "")),
        "points": [
            [
                _number(point.get("value_si")),
                *(_number(point.get(key)) for key in declared_conditions.POINT_KEYS),
            ]
            for point in row.get("points") or []
            if isinstance(point, dict)
        ],
        **{key: row.get(key) for key in _EVIDENCE},
    }
    text = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def of(row: dict[str, Any]) -> dict[str, Any] | None:
    """**지금 값에 유효한** 승인. 값이 바뀌어 지문이 갈렸으면 없다."""
    found = row.get(KEY)
    if not isinstance(found, dict) or found.get("digest") != digest(row):
        return None
    return found


def tier(row: dict[str, Any]) -> int:
    """이 줄의 등급 — 출처와 승인에서."""
    return tiers.declared_tier(row.get("source"), approved=of(row) is not None)


def origin(row: dict[str, Any]) -> str:
    """카드 칸에 적는 출처 표지(`declared:literature+approved`)."""
    return tiers.declared_origin(row.get("source"), approved=of(row) is not None)


def stamp(row: dict[str, Any], *, user_id: str, name: str, note: str | None) -> dict[str, Any]:
    """승인을 붙인 새 줄."""
    return {
        **row,
        KEY: {
            "by_id": user_id,
            "by": name,
            "at": datetime.now(UTC).isoformat(),
            "note": note,
            "digest": digest(row),
        },
    }


def strip(row: dict[str, Any]) -> dict[str, Any]:
    """승인을 뗀 새 줄."""
    return {key: value for key, value in row.items() if key != KEY}


def find(rows: list[dict[str, Any]], item: str) -> int | None:
    """이름으로 줄을 찾는다 — 저장과 같은 비교키(`check` 가 중복을 이것으로 막는다)."""
    wanted = compare_key(item)
    for index, row in enumerate(rows):
        if isinstance(row, dict) and compare_key(str(row.get("item") or "")) == wanted:
            return index
    return None


def carry(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """수정 전 줄의 승인을 **값이 그대로인 줄에만** 옮긴다.

    돌려주는 둘째는 **승인이 풀린 항목 이름** — 승인된 값을 고쳤거나 지운 것. 감사에 남긴다:
    승인된 값이 어느 수정으로 승인을 잃었는지가 나중에 「이 값 왜 등급이 내려갔나」 의 답이다.
    """
    approved = {
        compare_key(str(row.get("item") or "")): row
        for row in before
        if isinstance(row, dict) and of(row) is not None
    }
    out: list[dict[str, Any]] = []
    kept: set[str] = set()
    for given in after:
        # **받은 줄의 승인은 버린다.** 지금은 입력 스키마와 `check` 도 버리지만, 그 둘에 기대면
        # 한쪽이 칸을 받아 주기 시작하는 날 아무나 승인을 적어 넣는다 — 여기가 마지막 문이다.
        row = strip(given)
        key = compare_key(str(row.get("item") or ""))
        previous = approved.get(key)
        if previous is not None and previous[KEY]["digest"] == digest(row):
            out.append({**row, KEY: previous[KEY]})
            kept.add(key)
        else:
            out.append(row)
    lapsed = [str(row.get("item")) for key, row in approved.items() if key not in kept]
    return out, lapsed


__all__ = [
    "KEY",
    "carry",
    "digest",
    "find",
    "of",
    "origin",
    "stamp",
    "strip",
    "tier",
]
