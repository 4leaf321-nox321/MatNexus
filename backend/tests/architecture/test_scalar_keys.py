"""값의 이름이 요약값 표의 칸에 들어가는가 — `matcore.processing.SCALAR_KEY_MAX`.

실측(이슈 #2, 2026-09-27): 확장이 낸 51자 진단 키가 미리보기 · 저장을 다 지나 **채택에서
500** 이었다. 결과는 불변이라 그 결과는 영영 채택이 안 된다. 처리 커널이 값을 낸 자리에서
막지만(런타임), 선언에 적힌 이름은 여기서 미리 본다 — 확장을 붙인 사람이 CI 에서 안다.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import String

from app.modules.tests.models import TestSummary
from matcore import extensions, processing, registry

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"


def test_상수가_요약값_칸의_폭과_같다() -> None:
    """`matcore` 는 DB 를 모르므로 숫자를 따로 든다 — 둘이 어긋나면 막는 의미가 없다."""
    column = TestSummary.__table__.c.key.type
    assert isinstance(column, String)
    assert column.length == processing.SCALAR_KEY_MAX


def test_선언된_값_이름이_칸_안이다() -> None:
    """`{param}` 틀은 기본값으로 채워 잰다 — 실제 옵션이 더 길면 런타임 검사가 잡는다."""
    processing.load_builtin()
    extensions.load(EXTENSIONS)
    too_long: list[str] = []
    for plugin in (*registry.list_plugins("processing"), *registry.list_plugins("grouping")):
        defaults = {
            spec.name: spec.default for spec in plugin.params if spec.default is not None
        }
        for item in plugin.makes_values:
            key = item.key
            for name, value in defaults.items():
                key = key.replace("{" + name + "}", str(value))
            if len(key) > processing.SCALAR_KEY_MAX:
                too_long.append(f"{plugin.id}: {key} ({len(key)}자)")
    assert too_long == [], too_long
