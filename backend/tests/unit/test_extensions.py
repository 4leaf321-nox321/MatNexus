"""확장 폴더 — **폴더에 넣으면 읽는다.**

여기서 지키는 것은 셋이다.

    폴더에 넣으면 등록된다        중심 코드에 이름을 안 적는다
    하나가 터져도 나머지는 산다   남의 확장 때문에 내 물성을 못 쓰면 안 된다
    실패를 삼키지 않는다          "서버가 안 켜진다" 로만 보이면 더 나쁘다
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from matcore import cards, export, extensions

GOOD = """
from matcore import cards
from matcore.registry import Produced

cards.register_block(
    cards.BlockSpec(
        key="pretend_creep",
        label="지어낸 크리프",
        help="확장 시험용이다. 실제 물성이 아니다.",
        produces=(Produced(key="a", label="계수 A", si_unit="1/s"),),
    )
)
"""

BROKEN = "raise RuntimeError('일부러 터뜨린다')\n"

WITH_SOLVER = """
from matcore import export

@export.register_renderer(
    key="pretend_deck",
    label="지어낸 솔버",
    extension="txt",
    describe="확장 시험용.",
    keywords=("*PRETEND",),
    needs=(export.Need("pretend_creep", values=("a",)),),
)
def render(deck):
    return export.Rendered(text="*PRETEND\\n")
"""


def write(root: Path, name: str, body: str) -> None:
    folder = root / name
    folder.mkdir()
    (folder / "__init__.py").write_text(body, encoding="utf-8")


@pytest.fixture
def sandbox() -> Any:
    """레지스트리와 sys.modules 를 건드리는 시험용. 끝나면 원래대로."""
    blocks = cards.list_blocks()
    renderers = export.list_renderers()
    loaded = set(sys.modules)
    yield
    cards.clear()
    for spec in blocks:
        cards.register_block(spec)
    export.clear_renderers()
    for item in renderers:
        export.add_renderer(item)
    for name in set(sys.modules) - loaded:
        if name.startswith(extensions.PACKAGE):
            del sys.modules[name]


class Test읽기:
    def test_폴더에_넣으면_등록된다(self, tmp_path: Path, sandbox: Any) -> None:
        """**중심 코드에 이름을 안 적는다.** 그것이 이 장치의 전부다."""
        write(tmp_path, "pretend_creep", GOOD)
        report = extensions.load(tmp_path)

        assert [item.name for item in report] == ["pretend_creep"]
        assert all(item.ok for item in report)
        assert "pretend_creep" in {spec.key for spec in cards.list_blocks()}

    def test_솔버도_같이_붙는다(self, tmp_path: Path, sandbox: Any) -> None:
        """물성과 그것을 먹는 솔버가 **한 폴더에서** 온다."""
        write(tmp_path, "a_creep", GOOD)
        write(tmp_path, "b_solver", WITH_SOLVER)
        extensions.load(tmp_path)

        assert "pretend_deck" in {item.key for item in export.list_renderers()}
        deck = export.Deck(
            name="M", solver_id=1, blocks={"pretend_creep": {"values": {"a": 1.0}}}
        )
        assert "pretend_deck" in export.available_formats(deck)

    def test_폴더가_없어도_된다(self, tmp_path: Path) -> None:
        """확장이 없는 설치가 정상이다."""
        assert extensions.load(tmp_path / "없는폴더") == ()

    def test_밑줄과_점으로_시작하는_것은_건너뛴다(self, tmp_path: Path, sandbox: Any) -> None:
        """`__pycache__` 나 `.git` 을 확장으로 읽으면 안 된다."""
        write(tmp_path, "__pycache__", GOOD)
        write(tmp_path, ".hidden", GOOD)
        assert extensions.load(tmp_path) == ()


class Test실패:
    def test_하나가_터져도_나머지는_산다(self, tmp_path: Path, sandbox: Any) -> None:
        """**남의 확장 때문에 내 물성을 못 쓰면 안 된다.**"""
        write(tmp_path, "a_broken", BROKEN)
        write(tmp_path, "b_good", GOOD)
        report = extensions.load(tmp_path)

        assert [(item.name, item.ok) for item in report] == [
            ("a_broken", False),
            ("b_good", True),
        ]
        assert "pretend_creep" in {spec.key for spec in cards.list_blocks()}

    def test_실패를_삼키지_않는다(self, tmp_path: Path, sandbox: Any) -> None:
        """그 사실이 로그 없이 사라지면 **"왜 이 물성이 안 뜨지" 로만 보인다.**"""
        write(tmp_path, "broken", BROKEN)
        (failed,) = extensions.failures(extensions.load(tmp_path))
        assert failed.name == "broken"
        assert failed.error and "일부러 터뜨린다" in failed.error

    def test_이름이_겹치면_실패로_기록된다(self, tmp_path: Path, sandbox: Any) -> None:
        """같은 key 가 둘이면 **어느 쪽이 도는지 알 수 없다.**"""
        write(tmp_path, "a_first", GOOD)
        write(tmp_path, "b_again", GOOD)
        report = extensions.load(tmp_path)

        assert [item.ok for item in report] == [True, False]
        assert report[1].error and "중복" in report[1].error

    def test_init_이_없으면_말해_준다(self, tmp_path: Path, sandbox: Any) -> None:
        (tmp_path / "빈폴더").mkdir()
        (failed,) = extensions.load(tmp_path)
        assert failed.error == "__init__.py 가 없습니다."
