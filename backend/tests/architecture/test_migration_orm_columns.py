"""옛 마이그레이션이 **지금의 ORM 모델**로 값을 만드는 자리 — 뒤에 더한 칸은 거기서 미리
만든다.

## 왜 (2026-10-16)

`b3cecec7f07c` · `c7a4e0b93f16` · `6e746a0bfd2b` 는 `app.modules.vocabulary.definitions` 의
`ensure_*` 를 불러 값을 만든다. 그 함수는 **지금의** `Vocabulary` · `VocabularyTerm` 으로
조회하므로, 모델에 뒤에 더한 칸을 그 시점 DB 에 없는 채로 SELECT 한다. `processing_defaults`
(f3c8a1d6e2b9)를 더한 v1.292.0 이 그랬다 — 새 설치(CI 스모크)가 `b3cecec7f07c` 에서
「column vocabulary_terms.processing_defaults does not exist」 로 통째로 되돌아갔다.

**이 PC 의 검증 넷으로는 안 보였다.** 시험 DB 는 `create_all` 로 만들고(`tests/conftest.py`),
개발 · 운영 DB 는 그 지점을 이미 지나 새 마이그레이션만 돈다. 마이그레이션 사슬을 처음부터 도는
것은 CI 스모크뿐이라, 이 시험이 DB 없이 그 자리를 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2]

#: 지금의 ORM 모델로 값을 만드는 마이그레이션. 새로 생기면 여기 — 건드리는 표도 `TABLES` 에.
ORM_USERS = {"b3cecec7f07c", "c7a4e0b93f16", "6e746a0bfd2b"}
#: 그 마이그레이션들이 조회하는 표.
TABLES = ("vocabularies", "vocabulary_terms")
#: 그중 가장 이른 것 — 뒤에 더한 칸은 여기서 `ADD COLUMN IF NOT EXISTS` 로 미리 만든다.
EARLIEST = "b3cecec7f07c"

_ADD = re.compile(rf'add_column\(\s*"({"|".join(TABLES)})"\s*,\s*sa\.Column\(\s*"(\w+)"', re.S)
_ALTER = re.compile(
    rf"ALTER TABLE ({'|'.join(TABLES)})\s+ADD COLUMN (?:IF NOT EXISTS )?(\w+)", re.I
)


def _text(path: str) -> str:
    """이어 붙인 문자열 조각(`"ALTER TABLE x " "ADD COLUMN …"`)을 한 줄로."""
    return re.sub(r'"\s*\n\s*"', "", Path(path).read_text(encoding="utf-8"))


def _order() -> list[tuple[str, str]]:
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    return [(one.revision, str(one.path)) for one in reversed(list(script.walk_revisions()))]


def test_옛_ORM_마이그레이션_뒤에_더한_칸은_거기서_미리_만든다() -> None:
    order = _order()
    revisions = [revision for revision, _ in order]
    start = revisions.index(EARLIEST)
    early = _text(order[start][1])
    missing = [
        f"{revision}: {table}.{column}"
        for revision, path in order[start + 1 :]
        for table, column in (*_ADD.findall(_text(path)), *_ALTER.findall(_text(path)))
        if not re.search(
            rf"ALTER TABLE {table}\s+ADD COLUMN IF NOT EXISTS {column}\b", early, re.I
        )
    ]
    assert not missing, (
        f"{EARLIEST} 가 지금의 ORM 모델로 값을 만들어서, 뒤에 더한 칸이 그 시점 DB 에 "
        f"없으면 새 설치가 거기서 멈춥니다. {EARLIEST} 의 upgrade 에 "
        "`ALTER TABLE … ADD COLUMN IF NOT EXISTS …` 를 더하고, 새 마이그레이션도 같은 "
        "꼴로 쓰세요(AGENTS.md 「데이터」): " + ", ".join(missing)
    )


def test_ORM_을_쓰는_마이그레이션은_목록에_있다() -> None:
    """`app.modules` 를 부르는 마이그레이션이 늘면 위 검사가 그 자리를 모른다. 순수 함수
    (`app.shared.text` 의 글자 정리)만 부르는 것은 괜찮다 — 칸을 조회하지 않는다."""
    unknown = [
        revision
        for revision, path in _order()
        if re.search(r"from app\.modules\.", _text(path)) and revision not in ORM_USERS
    ]
    assert not unknown, (
        f"지금의 ORM 모델을 부르는 마이그레이션이 새로 있습니다: {unknown}. "
        "ORM_USERS 에 올리고, 그것이 조회하는 표를 TABLES 에 더하세요 — "
        "뒤에 더한 칸이 새 설치에서 그 자리를 멈춰 세웁니다."
    )
