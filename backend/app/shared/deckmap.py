"""덱 지도 — 형식(렌더러) 목록과, 형식·블록·시험·문헌 사이의 **정적 관계**.

전반은 `fitting/renderers.py` 에 있던 것을 옮겨 왔다(2026-09-16): 온톨로지 지도
(`GET /api/ontology`)가 「형식마다 필요한 블록」 을 실어야 하는데, 모듈이 모듈을
직접 부르지 못하므로(AGENTS.md) 둘이 함께 쓰는 것은 shared 에 산다. `fitting` 은
`renderer_for` 만 남기고 여기를 부른다.

해석용 물성 정의를 행에서 읽어 렌더러로 만든다 — ADR 0023 2단계.

**`matcore` 는 DB 를 모른다.** 행을 읽는 것은 여기고, 넘기는 것은 dict 다
(인풋 프로파일과 같은 규칙, ADR 0006).

## 기동이 아니라 요청 때 합친다

ADR 초안은 「앱 기동 시점에 `add_renderer` 로 얹는다」 였다. 안 그렇게 했다:

- **고치면 바로 먹어야 한다.** 기동 때 한 번 얹으면 화면에서 정의를 고쳐도
  재기동 전까지 옛 덱이 나간다. 「배포 없이」 를 얻으려고 만든 것인데 재기동이
  남으면 절반만 얻는다.
- **워커마다 상태가 갈린다.** 여럿을 띄우면 얹은 시점이 달라, 같은 요청이 어느
  워커에 닿느냐에 따라 다른 덱이 나온다 — 그리고 그것은 재현되지 않는다.
- **레지스트리는 프로세스 전역이다.** 전에는 부서마다 보이는 정의가 달라 그 자체로
  전역에 얹을 수 없었다. 보기를 전원에게 연 뒤로(ADR 0035) 목록은 하나지만, 위 두
  이유로 여전히 요청 때 합친다.

부르는 자리가 둘뿐이라(`list_formats` · `export_card`) 값도 싸다.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.fitting.models import ExportProfile
from matcore import cards, export
from matcore.export import template

log = logging.getLogger(__name__)


def _rows(db: Session) -> list[ExportProfile]:
    """살아 있는 정의 전부 — **모든 부서의 것이 모두의 목록에 뜬다**(ADR 0035).

    전에는 내 부서 것과 전역만 보였고, 같은 key 면 부서 것이 전역을 덮었다(사업부마다
    덱 관례가 달라서). key 가 전사에서 하나가 되면서 덮을 것이 없어졌다 — 사업부의
    관례는 **다른 형식**으로 나란히 뜨고, 사람이 이름을 보고 고른다. 덮는 규칙은 고른
    사람에게 안 보였다: 같은 「abaqus」 를 눌러도 누구냐에 따라 다른 덱이 나왔다.
    """
    return list(
        db.scalars(
            select(ExportProfile)
            .where(ExportProfile.deleted_at.is_(None), ExportProfile.is_active.is_(True))
            .order_by(ExportProfile.key)
        )
    )


def all_renderers(db: Session) -> list[export.Renderer]:
    """코드 렌더러 + 정의 렌더러.

    **깨진 정의 하나가 목록을 죽이지 않는다.** 건너뛰고 로그를 남긴다 — 목록이
    안 뜨면 사람은 어느 정의가 문제인지 볼 길조차 없어지고, 고치러 들어갈 화면도
    그 목록 위에 있다.
    """
    found = list(export.list_renderers())
    taken = {item.key for item in found}
    for row in _rows(db):
        if row.key in taken:
            # **코드 렌더러가 이긴다.** 덮게 두면 코드 쪽 검증(키워드 확인·물리적
            # 타당성)을 정의 하나가 조용히 우회한다. 저장할 때도 막지만, 코드에
            # 새 렌더러가 붙어 뒤늦게 겹칠 수 있어 여기서도 본다.
            log.warning(
                "해석용 물성 정의 %s 를 건너뜁니다 — 같은 key 의 코드 렌더러가 있습니다",
                row.key,
            )
            continue
        try:
            found.append(
                # **행의 칸이 정본이다.** `key`·`label` 은 컬럼에도 정의에도 둘 수
                # 있는데, 두 벌로 두면 목록에 뜨는 이름과 덱에 적히는 이름이
                # 어긋난다 — 그리고 어느 쪽이 맞는지 화면에 안 나온다.
                template.renderer_from_definition(
                    {**row.definition, "key": row.key, "label": row.label}
                )
            )
        except export.ExportError:
            log.exception("해석용 물성 정의 %s 를 읽지 못했습니다", row.key)
    return found


def format_needs(renderers: list[export.Renderer]) -> dict[str, tuple[str, ...]]:
    """형식마다 **반드시** 있어야 하는 블록 — 온톨로지 지도에 실린다. 선택(`optional`)은 뺀다.

    `Renderer.needs` 는 렌더가 거절하는 근거였고 사람은 거절 메시지로만 알았다. 같은
    사실을 미리 읽을 수 있게 한다 — 「이 형식엔 무엇이 필요한가」 를 카드 없이도 답한다.
    """
    return {
        one.key: tuple(dict.fromkeys(need.block for need in one.needs if not need.optional))
        for one in renderers
        if one.key != "json"
    }


def block_sources() -> dict[str, dict[str, tuple[str, ...]]]:
    """블록마다 **어디서 오나** — 지도에 실리는 정적 관계.

    `from_tests` 는 그 블록을 내는 시험 종류 키(`BlockSpec.from_tests`), `fills` 는 그
    블록의 값을 채우는 문헌 물성 키(`Produced.property_key`). 둘 다 비면 사람이 적는
    블록이다(선언 물성).
    """
    cards.load_builtin()
    out: dict[str, dict[str, tuple[str, ...]]] = {}
    for spec in cards.list_blocks():
        fills = tuple(
            item.property_key for item in spec.produces if item.property_key is not None
        )
        out[spec.key] = {"from_tests": tuple(spec.from_tests), "fills": fills}
    return out
