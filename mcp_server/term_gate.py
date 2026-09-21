"""AI 는 **새 낱말을 세우지 않는다** — 그 판정만 떼어 둔 순수 함수(ADR 0032).

## 왜 막나

`SECC` 를 `secc`·`SECC강판` 으로 적으면 재료가 셋으로 갈리고, 그 뒤의 검색·통계·
카드가 따라 갈린다. 되돌리려면 사람이 병합해야 한다. 그리고 **그럴듯한 이름을
지어내는 것은 AI 가 가장 잘하는 일**이다 — 「DP980 이면 Family 는 Steel 이겠지」 가
맞는 날이 대부분이라, 틀린 날에도 아무도 못 본다.

그래서 목록에 없는 값이면 만들지 않고 **비슷한 값을 후보로 준다.** 관리자 토큰이어도
같다: 권한의 문제가 아니라 규약이다. 정말 새 등급이면 사람이 화면에서 세운다.

## 서버가 아니라 여기서 한 번 더 보는 이유

판정은 백엔드가 한다(403). 여기서 미리 보는 것은 **아무것도 안 만든 채로 멈추기
위해서**다 — 재료를 만들다 Grade 에서 막히면 그 앞의 Family·Category 는 이미
생겨 있을 수 있고, 그것은 아무도 쓰지 않는 용어로 남는다.

`server.py` 가 IO(축 목록·값 검색)를 맡고, 여기는 받은 것으로 판단만 한다 —
`retry_plan` 과 같은 자리다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

#: 어느 칸이 어느 기준정보 축에 붙는가.
#:
#: **백엔드의 바인딩 표와 같아야 한다**(`app/modules/vocabulary/services.py` 의
#: `MATERIAL_BINDINGS` · `SAMPLE_BINDINGS` · `SPECIMEN_BINDINGS`). 여기가 짧으면
#: 못 본 축은 서버가 판정한다 — 이 표가 하는 일은 **거절당할 것을 미리 말해 주는
#: 것**이지 권한 판정이 아니다.
FIELDS: dict[str, str] = {
    "family": "family",
    "category": "category",
    "grade": "grade",
    "manufacturer": "manufacturer",
    # 유통사와 주 벤더는 **한 축**을 쓴다 — 같은 회사가 로트에 따라 둘 중 어느
    # 쪽도 된다.
    "distributor": "vendor",
    "primary_vendor": "vendor",
    "sales_type": "sales_type",
    "standard": "specimen_standard",
}

#: 통제되는 정책. `open` 은 누구나 즉석에서 더하는 축이라 막을 것이 없다.
GATED = ("managed", "closed")


def to_check(
    values: Mapping[str, str | None], policy: Mapping[str, str]
) -> list[tuple[str, str, str]]:
    """검사할 (칸, 축, 값). **값이 있고 그 축이 통제되는 것만.**

    정책을 모르는 축(`policy` 에 없음)은 안 본다 — 축 목록을 못 받아 왔을 때
    전부를 막으면, 읽기 한 번 실패한 것이 쓰기 전체를 세운다.
    """
    out: list[tuple[str, str, str]] = []
    for field, raw in values.items():
        text = (raw or "").strip()
        axis = FIELDS.get(field)
        if not text or axis is None:
            continue
        if policy.get(axis) not in GATED:
            continue
        out.append((field, axis, text))
    return out


def is_new(value: str, items: Sequence[Mapping[str, Any]]) -> bool:
    """검색 결과에 **같은 표기**가 없으면 새 낱말이다.

    대소문자와 앞뒤 공백은 무시한다 — `secc` 와 `SECC` 가 갈리는 것이 애초에
    이 문의 목적이다. 별칭에 걸려 정본 표기가 다르게 온 경우는 **새것으로 본다**:
    그때 후보로 정본(`포스코`)이 함께 오므로, 그 표기로 다시 부르면 된다.
    """
    needle = value.strip().lower()
    return not any(str(one.get("value", "")).strip().lower() == needle for one in items)


def candidates(items: Sequence[Mapping[str, Any]], limit: int = 5) -> list[str]:
    """보여 줄 비슷한 값들. 갈림은 대개 오타에서 난다."""
    return [str(one.get("value")) for one in items][:limit]


def refusal(blocked: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """거절하되 **다음에 할 일**을 준다 — 서버의 거절문과 같은 결이다.

    「권한이 없습니다」 로 끝내면 AI 는 그 말을 사람에게 옮기고 끝난다. 후보가
    있으면 대개 그 자리에서 해결된다.
    """
    return {
        "error": "기준정보에 없는 값이 있어 **아무것도 만들지 않았습니다** — "
        "새 용어는 사람이 세웁니다(부서 관리자, ADR 0032).",
        "blocked": list(blocked),
        "hint": "후보(`candidates`) 중에 같은 것이 있으면 그 표기로 다시 부르세요. "
        "정말 새 값이면 사람에게 전하세요 — 화면의 「기준정보」 에서 부서 관리자가 "
        "세웁니다. 비슷하다고 아무거나 고르지 마세요: 다른 등급을 고르면 그 뒤의 "
        "통계·카드가 조용히 섞입니다.",
    }
