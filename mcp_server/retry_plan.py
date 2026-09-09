"""재시도할 때 **무엇을 넓힐 것인가** — 딸린 것 없는 순수 함수.

`server.py` 에 두면 시험이 못 부른다(그쪽은 `mcp` SDK 를 import 하고, 그 SDK 는
백엔드 venv 에 없다). 조용히 틀릴 수 있는 판단이라 시험이 닿는 자리에 둔다.

## 넓히는 것과 못 넓히는 것

    넓힌다   구간·창 — 「어디를 볼까」. 사람이 화면에서 하는 것과 같다
    못 넓힌다 최소 점 수·R² 문턱 — 「얼마나 믿을까」. **코드 상수라 옵션에 없다**

이 구분이 자동 재시도를 허용할 수 있는 이유다. AI 가 아무리 다시 돌려도 방어선
자체는 안 내려간다 — 실측(2026-08-29)으로 세운 그 선이 API 밖에 있기 때문이다.
"""

from __future__ import annotations

from typing import Any

#: 넓힐 수 있는 옵션 이름. **여기 없는 것은 안 건드린다** — 모르는 옵션을 곱하면
#: 무슨 뜻인지 모르는 값을 바꾸게 된다.
WIDENABLE = ("maximum_strain", "maximum_displacement", "end", "window")

#: 몇 배씩 넓혀 볼까. 두 번이면 충분하다 — 더 늘리면 「될 때까지」 가 되고, 그것은
#: 사람이 곡선을 보고 할 판단이지 기계가 반복할 일이 아니다.
FACTORS = (2.0, 4.0)


def widen(steps: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """구간·창을 넓힌 후보들. 넓힐 것이 없으면 **빈 목록**이다.

    빈 목록은 「재시도해도 달라질 게 없다」 는 뜻이다 — 그때 다시 돌리면 같은
    실패를 두 번 겪고 사람에게는 「여러 번 시도했다」 는 인상만 남는다.
    """
    made: list[list[dict[str, Any]]] = []
    for factor in FACTORS:
        widened: list[dict[str, Any]] = []
        changed = False
        for step in steps:
            options = dict(step.get("options") or {})
            for key in WIDENABLE:
                raw = options.get(key)
                # bool 은 int 의 하위형이다 — 켬/끔 옵션을 2배 하면 안 된다.
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    options[key] = raw * factor
                    changed = True
            widened.append({**step, "options": options})
        if changed:
            made.append(widened)
    return made
