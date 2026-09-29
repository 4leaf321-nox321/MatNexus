"""목록 찾기 상자의 공통 판정 — **재료·시험 목록이 전체 검색과 같은 말로 찾는다**(2026-09-29).

전체 검색(`entity_search`)은 세 모드(일치·포함·비슷)와 뜻 검색을 갖췄는데, 매일 쓰는 재료·
시험 목록의 찾기 상자는 「포함」 하나였다. 오타 하나(`SECC18O`)면 0건이고, 「아연도금 강판」
처럼 뜻으로 물으면 이름에 그 말이 없어 0건이었다(2026-09-29 지적: 「상단의 전체 검색처럼」).

여기 두는 것은 두 목록이 **함께 쓰는** 판정뿐이다 — 모드, 뜻이 가까운 id, 가까운 순서,
왜 걸렸나. 무엇을 어느 칸에서 찾는지는 목록마다 다르므로 각 라우트가 정한다.

## 「비슷」 은 셋을 합친다

    포함     낱말이 다 들어 있다              (목록이 이미 하던 것)
    글자     오타·표기 흔들림 — 트라이그램 `%`   `SECC18O` → `SECC180`
    뜻       의미 검색(`semantic`)             「아연도금 강판」 → SECC

**가까운 순으로 선다**(`closeness`). 흐린 검색은 순위가 전부다 — 등록순으로 두면 제대로 맞은
것이 3쪽에 가 있다. 그리고 **왜 걸렸는지를 줄마다 준다**(`why`) — 뜻으로만 걸린 줄에 이유가
없으면 엉뚱한 결과로 읽힌다(전체 검색 화면과 같은 판단).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, case, false, func
from sqlalchemy.orm import Session

from app.shared import entity_search, semantic
from app.shared.errors import AppError

MODES = entity_search.MODES
TRIGRAM_MIN = entity_search.TRIGRAM_MIN
RRF_K = entity_search.RRF_K

#: 뜻으로만 걸린 것을 몇 개까지 얹나. **목록은 쪽을 넘기며 보는 곳이다** — 뜻이 가까운 것을
#: 끝없이 얹으면 「비슷」 이 곧 「전부」 가 된다.
MEANING_LIMIT = 10

#: 이보다 먼 것은 안 얹는다. 실측(2026-09-29, bge-m3, 개발 DB 재료 135건): 뜻 없는 말
#: (「zzqx 무의미한 말」)에 가장 가까운 재료가 0.33, 뜻이 맞는 것은 0.44~0.59 였다.
#: **모델을 바꾸면 다시 잰다** — 코사인의 눈금은 모델마다 다르다.
MEANING_FLOOR = 0.40


def check_mode(mode: str, *, code: str) -> str:
    """모르는 모드는 거절한다 — 조용히 「포함」 으로 떨어뜨리면, 「비슷」 을 눌렀는데 결과가
    그대로인 이유를 아무도 모른다."""
    if mode not in MODES:
        raise AppError(
            code, f"'{mode}' 는 아는 방식이 아닙니다 — {' · '.join(MODES)}.", status=422
        )
    return mode


def words(q: str | None) -> list[str]:
    """낱말로 나눈다. 공백뿐이면 빈 목록 — 지운 것과 안 친 것을 같게 본다."""
    return q.split() if q else []


def escape_like(text: str) -> str:
    """`%`·`_` 를 글자로 — 「일치」 가 와일드카드로 새지 않게."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def exactly(column: Any, needle: str) -> ColumnElement[bool]:
    """대소문자만 무시한 정확 일치.

    `lower(x) = y` 가 아니라 와일드카드 없는 `ILIKE` 로 쓴다 — trgm GIN 색인이 그대로
    먹는다. `lower()` 에는 색인이 없어 5만 행을 훑는다.
    """
    result: ColumnElement[bool] = column.ilike(escape_like(needle), escape="\\")
    return result


def resembles(column: Any, needle: str) -> ColumnElement[bool]:
    """트라이그램 유사(`%`, 문턱 `pg_trgm.similarity_threshold` = 0.3).

    `similarity() >= 0.3` 으로 쓰지 않는다 — 함수 호출은 색인을 못 타고, `%` 는 같은 문턱으로
    GIN 을 탄다. 두 글자 이하는 트라이그램이 안 나와 늘 거짓이다 — 그때는 「포함」 이 받는다.
    """
    if len(needle) < TRIGRAM_MIN:
        return false()
    result: ColumnElement[bool] = column.op("%")(needle)
    return result


def meaning_ids(db: Session, needle: str, *, kind: str) -> list[uuid.UUID]:
    """뜻이 가까운 것의 id — **가까운 순.** 엔진이 없으면 빈 목록이다.

    검색은 이것 없이도 답해야 한다. 엔진이 죽었다고 목록이 오류를 띄우면 사람은 목록이
    고장 났다고 읽는다(`semantic.search` 와 같은 판단).

    권한은 여기서 안 건다 — 받은 id 는 부르는 쪽이 제 가시 범위 **안에서** 거른다
    (`visible_materials` 에 `IN` 으로 더한다). 조각 표에는 부서가 없다.
    """
    found: list[uuid.UUID] = []
    for match in semantic.search(db, needle, kinds=(kind,), limit=MEANING_LIMIT * 3):
        if match.score < MEANING_FLOOR:
            break  # 가까운 순이다 — 이 뒤는 더 멀다.
        try:
            one = uuid.UUID(match.entity_id)
        except ValueError:
            continue
        if one not in found:
            found.append(one)
        if len(found) >= MEANING_LIMIT:
            break
    return found


def closeness(
    columns: Sequence[Any],
    needle: str,
    *,
    words_hit: ColumnElement[bool] | None,
    id_column: Any,
    meaning: Sequence[uuid.UUID],
) -> ColumnElement[float]:
    """가까운 순의 점수. 글자 점수 중 가장 큰 것 + 뜻 순위의 가산(RRF).

        일치 1.0 · 앞 0.8 · 포함 0.6 · 낱말이 다 있음 0.6 · 트라이그램 유사도의 절반

    **글자가 뜻보다 위다.** 뜻으로만 걸린 것(가산 0.01~0.02)은 글자로 걸린 것 아래에 선다 —
    왜 떴는지 사람이 못 읽기 때문이다(`entity_search._fuse_meaning` 과 같은 판단). 양쪽에
    걸린 것은 가산만큼 위로 간다.
    """
    wanted = needle.lower()
    pattern = escape_like(wanted)
    parts: list[Any] = []
    for column in columns:
        text = func.coalesce(column, "")
        lowered = func.lower(text)
        parts.append(
            case(
                (lowered == wanted, 1.0),
                (lowered.like(f"{pattern}%", escape="\\"), 0.8),
                (lowered.like(f"%{pattern}%", escape="\\"), 0.6),
                else_=0.0,
            )
        )
        parts.append(func.similarity(text, needle) * 0.5)
    if words_hit is not None:
        # `SECC 1.0` 은 `SECC_MDOI_1.0` 에 통째로는 없지만 두 낱말을 다 가졌다 — 적어도
        # 「포함」 만큼은 가깝다.
        parts.append(case((words_hit, 0.6), else_=0.0))
    score: ColumnElement[float] = func.greatest(*parts)
    if meaning:
        bonus = case(
            {one: 1.0 / (RRF_K + rank) for rank, one in enumerate(meaning)},
            value=id_column,
            else_=0.0,
        )
        score = score + bonus
    return score


def why(
    *,
    words_hit: ColumnElement[bool] | None,
    text_similar: ColumnElement[bool],
    id_column: Any,
    meaning: Sequence[uuid.UUID],
) -> ColumnElement[str]:
    """왜 걸렸나 — `contains`(낱말이 다 있음) · `similar`(글자가 비슷) · `meaning`(뜻).

    값은 전체 검색의 `matched` 와 같은 말이다 — 화면이 같은 표(`MATCH_LABELS`)로 읽는다.
    """
    whens: list[Any] = []
    if words_hit is not None:
        whens.append((words_hit, "contains"))
    whens.append((text_similar, "similar"))
    if meaning:
        whens.append((id_column.in_(list(meaning)), "meaning"))
    result: ColumnElement[str] = case(*whens, else_=None)
    return result
