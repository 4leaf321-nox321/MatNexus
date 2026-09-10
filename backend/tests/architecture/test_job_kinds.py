"""선언한 작업 종류에 **처리할 사람이 있는가.**

## 왜 (실측 2026-09-11)

작업 표에 `failed` 로 굳은 것이 둘 있었다. 사유는 둘 다 같다 —
`KeyError: 등록되지 않은 작업 종류: …`. 세 번 시도하고 죽었고, 그 뒤로 아무도
안 돌렸다.

    pipelines.parse_inbox   2026-08-28
    tests.cleanup_storage   2026-08-15

`kinds.py` 는 오타를 막으려고 이름을 한곳에 모아 둔다. 그런데 **이름이 있고
핸들러가 없는 경우**는 그 표로도 안 막힌다 — 넣는 쪽은 상수를 쓰니 오타가 없고,
없는 것은 받는 쪽이다. 그 어긋남은 큐에 들어간 뒤에야, 그것도 **워커 로그에서만**
드러난다.

`enqueue` 가 넣을 때 검사하게 하지 않은 이유: API 프로세스는 핸들러를 안 싣는다
(`load_all` 은 워커와 시험이 부른다). 거기서 검사하면 **API 가 워커 코드를 지고
가야** 하고, 그것은 둘을 나눠 둔 뜻과 어긋난다. 그래서 여기서 정적으로 맞댄다.

두 방향을 다 본다. 이름만 있고 핸들러가 없으면 그 작업은 영영 실패하고,
핸들러만 있고 이름이 없으면 그것을 넣는 코드가 문자열을 손으로 적고 있다는 뜻
이다(`kinds.py` 를 둔 이유가 그것을 막는 것이다).
"""

from __future__ import annotations

from app.jobs import handlers, kinds


def declared_kinds() -> dict[str, str]:
    """`kinds.py` 가 선언한 이름 — {상수 이름: 값}."""
    return {
        name: value
        for name, value in vars(kinds).items()
        if name.isupper() and isinstance(value, str)
    }


def test_선언한_이름에는_핸들러가_있다() -> None:
    """**없으면 그 작업은 큐에 들어가 세 번 실패하고 굳는다.**"""
    handlers.load_all()
    known = set(handlers.known_kinds())
    orphan = {name: value for name, value in declared_kinds().items() if value not in known}
    assert not orphan, (
        "이 종류를 처리할 핸들러가 없습니다 — 넣으면 실패만 쌓입니다:\n  "
        + "\n  ".join(f"{name} = {value!r}" for name, value in sorted(orphan.items()))
    )


def test_핸들러의_종류는_이름표에_있다() -> None:
    """**문자열을 손으로 적은 자리를 찾는다.** 그것이 오타의 자리다."""
    handlers.load_all()
    values = set(declared_kinds().values())
    stray = sorted(set(handlers.known_kinds()) - values)
    assert not stray, (
        "`app/jobs/kinds.py` 에 없는 종류를 핸들러가 들고 있습니다 — "
        f"넣는 쪽이 문자열을 손으로 적고 있을 수 있습니다: {stray}"
    )
