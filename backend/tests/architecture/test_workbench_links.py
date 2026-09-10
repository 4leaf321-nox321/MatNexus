"""워크벤치가 가리키는 화면이 **실재하는가.**

## 왜 (2026-09-11 점검)

워크플로 정의는 데이터다(ADR 0024) — 단계마다 「그 화면으로」 링크(`where`)와
「여기서 담습니다」 링크(`COLLECT_AT`)를 문자열로 든다. 그 문자열은 라우터와
아무 관계가 없어서, **경로를 바꾸면 조용히 어긋난다.** 누른 사람은 빈 화면을
보고, 워크벤치는 계속 그리로 보낸다.

여섯 워크플로 전부를 지금 손으로 맞춰 보니 다 맞았다. 손으로 맞춰 본 것은 이번
한 번뿐이고, 다음 사람은 안 맞춰 본다 — 그래서 여기 둔다.

`?collect=` 같은 물음표 뒤는 떼고 본다. 그것은 화면이 읽는 값이지 경로가 아니다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / "frontend" / "src" / "modules" / "workbench" / "workflows.ts"
ROUTER = ROOT / "frontend" / "src" / "routes" / "router.tsx"


def routes() -> set[str]:
    """라우터가 아는 경로. 앞의 `/` 를 붙여 워크플로가 적는 모양으로 맞춘다."""
    found = re.findall(r"path: '([^']+)'", ROUTER.read_text(encoding="utf-8"))
    return {one if one.startswith("/") else f"/{one}" for one in found}


def targets() -> list[str]:
    """`where:` 와 `COLLECT_AT` 이 가리키는 곳 — 물음표 뒤는 뗀다."""
    text = WORKFLOWS.read_text(encoding="utf-8")
    where = re.findall(r"where: '([^']+)'", text)
    block = re.search(r"COLLECT_AT: Record<ItemKind, string> = \{(.*?)\}", text, re.DOTALL)
    collect = re.findall(r": '([^']+)'", block.group(1)) if block else []
    assert collect, "COLLECT_AT 을 못 찾았다 — 이름이 바뀌었나"
    return [one.split("?")[0] for one in (*where, *collect)]


def test_워크플로가_가리키는_화면이_있다() -> None:
    known = routes()
    assert known, "라우터에서 경로를 하나도 못 찾았다 — 대조가 무의미하다"
    missing = sorted({one for one in targets() if one not in known})
    assert not missing, (
        "워크벤치가 없는 화면으로 보냅니다 — 누르면 빈 화면입니다:\n  "
        + "\n  ".join(missing)
    )


def test_담으러_보내는_길에_표시가_붙어_있다() -> None:
    """**그 표시가 담기 창을 띄운다.**

    평소에는 체크를 해도 창이 안 뜬다(담을 생각 없이 고르는 일이 더 흔하다).
    워크벤치에서 담으러 온 사람만 고르는 순간 창을 본다 — 그 판단의 근거가
    이 `?collect=` 다. 빠뜨리면 「담기」 단추를 또 찾아야 한다.
    """
    text = WORKFLOWS.read_text(encoding="utf-8")
    block = re.search(r"COLLECT_AT: Record<ItemKind, string> = \{(.*?)\}", text, re.DOTALL)
    assert block
    for kind, path in re.findall(r"(\w+): '([^']+)'", block.group(1)):
        assert f"collect={kind}" in path, f"{kind} 로 담으러 가는 길에 표시가 없다: {path}"
