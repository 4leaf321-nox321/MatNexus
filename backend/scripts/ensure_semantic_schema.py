"""의미 검색 표를 보장한다 — 배포가 매번 돌리는 보정 스크립트.

**마이그레이션이 아닌 이유**: `search_chunks` 는 `vector` 열을 갖고, 그것은
pgvector 확장이 있어야 만들 수 있다. 마이그레이션에 넣으면 확장을 아직 안 넣은
서버에서 **`alembic upgrade` 가 통째로 실패한다** — 검색의 곁가지 때문에 릴리스가
못 나가는 것은 균형이 안 맞는다.

여기서는 **있으면 만들고 없으면 조용히 넘어간다.** 나중에
`scripts/deploy/install_pgvector.ps1` 로 확장을 넣으면, 그다음 배포에서 표가
저절로 생긴다.

멱등하다. 여러 번 돌려도 된다.

사용:
    python scripts/ensure_semantic_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from scripts._console import survive_cp949  # noqa: E402

survive_cp949()

# **모델을 전부 등록시킨다.** 앱에서는 안 드러나고 이 스크립트를 돌릴 때만 터진다.
import app.all_models  # noqa: F401,E402
from app.database import SessionLocal  # noqa: E402
from app.shared import embeddings, semantic  # noqa: E402


def main() -> int:
    with SessionLocal() as db:
        if not semantic.ensure_schema(db):
            print("pgvector 가 없습니다 — 의미 검색 표를 만들지 않았습니다.")
            print("  넣으려면: scripts\\deploy\\install_pgvector.ps1")
            return 0
        db.commit()

        counted = semantic.stats(db)
        state = embeddings.health()
        print(f"표 준비됨 — 조각 {counted['chunks']}개 {counted['kinds'] or ''}")
        print(f"임베딩 백엔드: {state['backend']} (준비됨={state['ready']})")
        if not state["ready"]:
            print(f"  {state.get('note', '')}")
            print("  켜려면 .env 에 EMBEDDING_BACKEND=ollama 를 적고 워커를 다시 띄웁니다.")
        elif counted["chunks"] == 0:
            print("  아직 색인이 비었습니다 — 워커의 `search.reindex` 작업이 채웁니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
