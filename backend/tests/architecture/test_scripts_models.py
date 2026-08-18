"""배포용 스크립트 — **모델을 전부 등록시키는가.**

스크립트가 손대는 모델만 import 하면, 그 모델의 외래키가 가리키는 테이블이
메타데이터에 없어 SQLAlchemy 가 매핑을 못 푼다.

    NoReferencedTableError: Foreign key associated with column
    'test_types.owner_workspace_id' could not find table 'workspaces'

**앱에서는 안 드러난다.** `main` 이 모든 라우터를 부르면서 모델이 전부 실려
오기 때문이다. 그래서 이 결함은 배포 뒤 보정 스크립트를 돌리는 순간에만
나타나고, 그때는 이미 서버가 새 코드로 바뀐 뒤다 — 실제로 CI 스모크에서
처음 드러났다.

`app/all_models.py` 가 그 등록을 한곳에 모으는 파일이고(CLAUDE.md), 스크립트는
그것을 부르기만 하면 된다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

#: DB 를 만지지 않는 스크립트. 모델을 부를 이유가 없다.
NO_DATABASE = {"export_openapi.py"}


def database_scripts() -> list[Path]:
    return sorted(
        path
        for path in SCRIPTS.glob("*.py")
        if path.name not in NO_DATABASE and "SessionLocal" in path.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("script", database_scripts(), ids=lambda path: path.name)
def test_모델을_전부_등록시킨다(script: Path) -> None:
    source = script.read_text(encoding="utf-8")
    assert "app.all_models" in source, (
        f"{script.name} 이 `import app.all_models` 를 하지 않습니다. "
        f"손대는 모델만 import 하면 외래키가 가리키는 테이블을 못 찾아 "
        f"NoReferencedTableError 로 죽습니다 — 앱에서는 안 드러나고 "
        f"배포 뒤 이 스크립트를 돌릴 때만 터집니다."
    )
