"""기동 전 포트 확인 — **띄웠다고 생각한 서버와 답하는 서버가 달라지면 안 된다.**

실측에서 나왔다(2026-08-28). 같은 PC 에 운영 설치본이 함께 있었고 둘 다 8010 을
썼다. 개발 백엔드를 내린 순간 프론트의 프록시가 **운영 v1.115.0 에 그대로 붙었고**,
화면은 「존재하지 않는 엔드포인트」 만 말했다. 서버가 죽은 것도 코드가 틀린 것도
아니어서 볼 곳이 어디에도 없었다.

**이 가드가 조용히 죽으면 그 상태가 그대로 돌아온다.** 그래서 시험을 붙인다 —
「빈 포트에서 안 막는다」 보다 **「물린 포트를 놓치지 않는다」** 가 무는 자리다.
"""

from __future__ import annotations

import importlib.util
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: 스크립트는 패키지가 아니라 파일이다. 경로로 불러온다 — 그래야 시험이 실제로
#: 돌아가는 그 파일을 본다.
_spec = importlib.util.spec_from_file_location("run_entry", BACKEND_DIR / "run.py")
assert _spec is not None and _spec.loader is not None
run_entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_entry)


@pytest.fixture
def held_port() -> Iterator[int]:
    """아무도 안 쓰는 포트를 하나 잡아 **물고 있는** 상태로 준다."""
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    # **백로그를 넉넉히, 그리고 계속 받는다.** 한 번만 받으면 두 번째 두드림이
    # 백로그에 쌓인 채 거절되고, 그러면 **가드가 멀쩡한데 시험이 빨갛다.**
    # 실제로 그렇게 한 번 틀렸다.
    server.listen(16)

    def serve() -> None:
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return  # 픽스처가 닫았다
            connection.close()

    threading.Thread(target=serve, daemon=True).start()
    try:
        yield int(server.getsockname()[1])
    finally:
        server.close()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Test포트가_물려_있으면_말한다:
    def test_물린_포트를_잡아낸다(self, held_port: int) -> None:
        """**이걸 놓치면 두 서버가 겹친다.** 우리가 못 붙는데도 uvicorn 이 조용히
        뜨면, 「띄웠다」 고 생각한 사람과 실제로 답하는 프로세스가 달라진다."""
        assert run_entry._who("0.0.0.0", held_port) is not None

    def test_빈_포트는_안_막는다(self) -> None:
        """막는 것만큼 **안 막는 것**도 중요하다 — 늘 막으면 아무도 못 띄운다."""
        assert run_entry._who("0.0.0.0", _free_port()) is None

    def test_0_0_0_0_은_127로_두드린다(self, held_port: int) -> None:
        """`0.0.0.0` 으로는 연결할 수 없다. 그대로 두드리면 늘 「비었다」 가 나와서
        **가드가 있으나 마나** 가 된다."""
        assert run_entry._who("0.0.0.0", held_port) is not None
        assert run_entry._who("127.0.0.1", held_port) is not None

    def test_이름을_못_알아내도_막는다(self, held_port: int) -> None:
        """`/api/health` 가 없는 무언가가 물고 있을 수도 있다. 알아내기는
        거들기이지 판단이 아니다 — 이름을 몰라도 막는 것은 같다."""
        said = run_entry._who("0.0.0.0", held_port)
        assert said == "무언가"
