"""배포에 실려 온 안내 → 공지 **초안**.

    python scripts/import_notices.py          # 빠진 것만 초안으로 넣는다
    python scripts/import_notices.py --check  # 넣을 것이 무엇인지만 본다

## 왜

새 기능은 코드와 함께 도착하는데, 그것을 알리는 글은 사람이 공지 화면에서 따로
써야 했다(2026-09-12). 폐쇄망 배포는 며칠 걸리는 왕복이라 "다음에 쓰지" 가 되고,
그러면 사용자는 물성 매핑이 생긴 것도 VOC 알림이 켜진 것도 모른다.

그래서 안내 글을 코드 옆(`seeds/notices/*.md`)에 두고, 배포가 이 스크립트를 돌려
**초안**으로 넣는다. 초안은 관리자만 본다 — 읽고, 고치고, 발행한다. 자동 발행하지
않는 이유: 배포한 사람이 글의 첫 독자여야 하고, 그 서버에 안 맞는 말이 있으면 거기서
걸러야 한다.

## 규칙

- 파일 이름이 키다(`2026-09-12-물성-매핑.md` → `2026-09-12-물성-매핑`). **같은 키는
  두 번 안 들어온다** — 운영에서 고친 글을 덮지 않는다. 고쳐서 다시 내려면 새 파일.
- 첫 줄 `# 제목`, 나머지가 본문. 공지 본문은 그대로 보이므로(마크다운 아님) 줄바꿈과
  「-」 목록만 쓴다.
- 실패해도 배포를 세우지 않는다(deploy.ps1) — 안내가 비는 것은 불편이지 장애가 아니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.notices.models import Notice  # noqa: E402

survive_cp949()

SEED_DIR = BACKEND_DIR / "seeds" / "notices"


def read_seed(path: Path) -> tuple[str, str]:
    """`(제목, 본문)`. 첫 줄이 `# 제목` 이어야 한다 — 아니면 파일 이름이 제목이다."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    first, _, rest = text.partition("\n")
    if first.startswith("# "):
        return first[2:].strip(), rest.strip()
    return path.stem, text


def plan(db: Session, seed_dir: Path = SEED_DIR) -> list[tuple[str, str, str]]:
    """넣을 것 — `(키, 제목, 본문)`. 이미 있는 키는 뺀다."""
    if not seed_dir.exists():
        return []
    have = set(db.scalars(select(Notice.seed_key).where(Notice.seed_key.is_not(None))))
    out: list[tuple[str, str, str]] = []
    for path in sorted(seed_dir.glob("*.md")):
        key = path.stem
        if key in have:
            continue
        title, body = read_seed(path)
        if not body:
            continue
        out.append((key, title, body))
    return out


def run(db: Session, seed_dir: Path = SEED_DIR) -> list[str]:
    """빠진 씨앗을 초안으로 넣는다. 넣은 키를 돌려준다."""
    made: list[str] = []
    for key, title, body in plan(db, seed_dir):
        db.add(
            Notice(title=title, body=body, is_published=False, is_popup=False, seed_key=key)
        )
        made.append(key)
    if made:
        db.commit()
    return made


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="넣지 않고 무엇을 넣을지만 본다")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.check:
            todo = plan(db)
            print(f"넣을 안내: {len(todo)}건")
            for key, title, _ in todo:
                print(f"  - {key}: {title}")
            return 0
        made = run(db)
        if made:
            print(f"공지 초안 {len(made)}건 — 관리자가 공지 화면에서 읽고 발행합니다:")
            for key in made:
                print(f"  - {key}")
        else:
            print("새로 넣을 안내가 없습니다.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
