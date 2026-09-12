"""코드의 씨앗을 DB 에 맞춘다 — **배포마다 돈다.**

    python scripts/refresh_builtins.py

## 왜

기본 축·물성 항목·시험 종류·형식 프로파일은 코드에 씨앗이 있고, `ensure_*` 가 없는
것만 만든다 — 있으면 통째로 건너뛴다. 관리자가 고친 라벨·열 이름을 배포가 되돌리면
안 되기 때문이고 그것은 옳다. 그런데 **코드가 뒤에 더한 것**(새 채널, 프로파일 규칙,
차원 선택지, 항목 속성)까지 얼어붙었고, 그것을 다시 심는 길은 누군가 마이그레이션을
쓰는 것뿐이었다. 실측(2026-09-12): `ta_dma850` 의 마스터커브 자동 등록 규칙이 08-31
에 코드에 들어갔는데 그 전에 설치된 DB 는 못 받았다 — 오류 없이 기능이 없었다.

여기서는 두 가지를 한다. **없는 것은 만들고**(`ensure_*`), **있는 것에는 코드가 정하는
부분만 채운다**(`refresh_*`) — 빠진 키·칸·채널·속성·선택지. 관리자가 고친 값은 어느
쪽도 건드리지 않는다. 몇 번 돌려도 같다.

`deploy.ps1` 이 `alembic upgrade` 뒤에 부른다. 실패해도 배포는 세우지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.tests.definitions import (  # noqa: E402
    ensure_builtin_test_types,
    refresh_builtin_test_types,
)
from app.modules.tests.legacy_profiles import (  # noqa: E402
    ensure_builtin_format_profiles,
    refresh_builtin_format_profiles,
)
from app.modules.vocabulary.definitions import (  # noqa: E402
    ensure_builtin_axis_fields,
    ensure_builtin_property_items,
    ensure_builtin_specimen_categories,
    ensure_builtin_vocabularies,
    refresh_builtin_axis_fields,
    refresh_builtin_property_items,
)

survive_cp949()


def run(db) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    """순서가 있다 — 축이 있어야 칸·항목이 붙고, 시험 종류가 있어야 프로파일이 붙는다."""
    return {
        "축 만듦": ensure_builtin_vocabularies(db),
        "축 칸 만듦": ensure_builtin_axis_fields(db),
        "축 칸 맞춤": refresh_builtin_axis_fields(db),
        "시편 분류 만듦": ensure_builtin_specimen_categories(db),
        "물성 항목 만듦": ensure_builtin_property_items(db),
        "물성 항목 맞춤": refresh_builtin_property_items(db),
        "시험 종류 만듦": ensure_builtin_test_types(db),
        "시험 종류 맞춤": refresh_builtin_test_types(db),
        "형식 프로파일 만듦": ensure_builtin_format_profiles(db),
        "형식 프로파일 맞춤": refresh_builtin_format_profiles(db),
    }


def main() -> int:
    with SessionLocal() as db:
        report = run(db)
        db.commit()
    touched = {label: keys for label, keys in report.items() if keys}
    if not touched:
        print("코드의 씨앗과 DB 가 같습니다 — 할 일이 없습니다.")
        return 0
    for label, keys in touched.items():
        print(f"{label}: {', '.join(keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
