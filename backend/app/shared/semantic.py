"""의미 검색 — **낱말이 안 겹쳐도 뜻이 가까우면 찾는다.**

전체 검색 3단계다. 1·2단계는 글자를 본다(일치·포함·오타). 여기는 뜻을 본다:

    「얇은 판 잡아당길 때 규격」  →  핸드북의 「박판 인장 시편은 ASTM E8/E8M…」

## 산문에만 건다

`SECC180_MDOI_1.0` 에 임베딩을 걸면 **뜻 없는 유사도**가 나온다 — 이름은 트라이그램이
훨씬 정확하다. 대상은 사람이 문장으로 쓴 것뿐이다:

    핸드북 절(guide_sections.body_text)   실측 198절 1.9MB — 사실상 여기가 전부다
    문헌 재료 설명                        76건
    공지 · VOC                            사람이 쓴 글

## 표는 마이그레이션이 아니라 여기가 만든다

**pgvector 는 선택 부품이다.** 마이그레이션에 `CREATE EXTENSION vector` 를 넣으면
확장을 아직 안 넣은 서버에서 **배포가 통째로 실패한다** — 검색의 곁가지 때문에
릴리스가 못 나가는 것은 균형이 안 맞는다.

그래서 `ensure_schema()` 가 **있으면 만들고 없으면 조용히 넘어간다.** 배포는 이것을
매번 부르므로, 나중에 pgvector 를 설치하면 그다음 배포에서 저절로 생긴다.

`Base.metadata` 에 안 올리는 이유도 같다 — 올리면 autogenerate 가 확장 없는 기계에서
**이 표를 지우는 마이그레이션**을 만든다(AGENTS.md 의 all_models 함정과 같은 뿌리).
대신 `migrations/env.py` 가 이 표를 자동 생성 대상에서 뺀다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.shared import embeddings

logger = logging.getLogger(__name__)

TABLE = "search_chunks"

#: 한 조각의 길이. 문단 하나쯤이다 — 너무 길면 한 벡터에 여러 주제가 섞여 무엇에도
#: 안 가깝고, 너무 짧으면 문맥이 끊겨 뜻이 안 담긴다.
CHUNK_CHARS = 500

#: 조각 사이를 겹친다. 경계에서 잘린 문장이 어느 쪽에도 온전히 안 남는 것을 막는다.
CHUNK_OVERLAP = 80

#: 한 번의 검색에서 볼 조각 수.
SEARCH_LIMIT = 40


@dataclass(frozen=True)
class Chunk:
    """색인할 조각 하나."""

    kind: str
    entity_id: str
    seq: int
    title: str
    body: str


@dataclass(frozen=True)
class Match:
    """찾은 조각 하나."""

    kind: str
    entity_id: str
    title: str
    snippet: str
    score: float
    """0~1. 코사인 거리를 뒤집은 것이다."""


def extension_ready(db: Session) -> bool:
    """pgvector 가 이 DB 에 켜져 있나."""
    found = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
    return bool(found)


def table_ready(db: Session) -> bool:
    return db.execute(text(f"SELECT to_regclass('{TABLE}')")).scalar() is not None


def available(db: Session) -> bool:
    """의미 검색을 쓸 수 있나 — **셋이 다 있어야 한다.**

    엔진(임베딩) · 확장(pgvector) · 표. 하나라도 없으면 「비슷」 은 트라이그램만으로
    계속 돈다.
    """
    return embeddings.enabled() and table_ready(db)


def ensure_schema(db: Session) -> bool:
    """표와 색인을 만든다. **확장이 없으면 아무것도 안 하고 False 를 준다.**

    멱등이다. 배포가 매번 불러도 되고, 나중에 pgvector 를 설치하면 그다음 배포에서
    생긴다.
    """
    if not extension_ready(db):
        available_here = db.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
        if not available_here:
            logger.info("pgvector 가 없습니다 — 의미 검색 표를 만들지 않습니다.")
            return False
        # 파일은 있는데 안 켜져 있으면 켠다 — 이 자리가 그 한 번을 대신한다.
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector 를 켰습니다.")

    dim = get_settings().embedding_dim
    db.execute(
        text(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id uuid PRIMARY KEY,
            kind varchar(40) NOT NULL,
            entity_id varchar(80) NOT NULL,
            seq integer NOT NULL,
            title varchar(300) NOT NULL DEFAULT '',
            body text NOT NULL,
            embedding vector({dim}) NOT NULL,
            model varchar(80) NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (kind, entity_id, seq)
        )
        """)
    )
    db.execute(
        text(f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_entity ON {TABLE} (kind, entity_id)")
    )
    # HNSW — 조각이 늘어도 검색 시간이 거의 안 는다(실측: 5,000개 x 1024차원에 1.4ms).
    db.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_embedding ON {TABLE} "
            f"USING hnsw (embedding vector_cosine_ops)"
        )
    )
    return True


def split(body: str) -> list[str]:
    """긴 글을 조각으로. **문단 경계를 먼저 본다** — 문장 가운데를 자르면 뜻이 상한다."""
    clean = " ".join((body or "").split())
    if not clean:
        return []
    if len(clean) <= CHUNK_CHARS:
        return [clean]

    made: list[str] = []
    at = 0
    while at < len(clean):
        end = min(at + CHUNK_CHARS, len(clean))
        if end < len(clean):
            # 가까운 문장 끝에서 자른다. 못 찾으면 그냥 자른다 — 한 조각이 조금
            # 어색한 것이 무한히 커지는 것보다 낫다.
            window = clean.rfind(". ", at + CHUNK_CHARS // 2, end)
            if window == -1:
                window = clean.rfind(" ", at + CHUNK_CHARS // 2, end)
            if window != -1:
                end = window + 1
        made.append(clean[at:end].strip())
        if end >= len(clean):
            break
        at = max(end - CHUNK_OVERLAP, at + 1)
    return [one for one in made if one]


def collect(db: Session) -> list[Chunk]:
    """색인할 산문을 모은다. **이름 열은 여기 없다** — 그건 트라이그램의 일이다."""
    made: list[Chunk] = []

    rows = db.execute(
        text("""
        SELECT s.id::text, s.title, s.body_text, d.title
        FROM guide_sections s
        JOIN guide_documents d ON d.id = s.document_id
        WHERE s.deleted_at IS NULL AND d.deleted_at IS NULL
          AND s.body_text IS NOT NULL AND length(s.body_text) > 40
        """)
    ).all()
    for section_id, section_title, body, document_title in rows:
        # 문서 제목을 조각마다 붙인다 — 「인장」 이 문서 제목에만 있고 절 본문에는
        # 없는 경우가 흔하고, 그때 그 조각은 문맥을 잃는다.
        label = f"{document_title} · {section_title}"
        for seq, piece in enumerate(split(body)):
            made.append(
                Chunk(
                    kind="guide_section",
                    entity_id=section_id,
                    seq=seq,
                    title=label,
                    body=piece,
                )
            )

    rows = db.execute(
        text("""
        SELECT id::text, name, description FROM catalog_materials
        WHERE description IS NOT NULL AND length(description) > 40
        """)
    ).all()
    for material_id, name, description in rows:
        for seq, piece in enumerate(split(description)):
            made.append(
                Chunk(
                    kind="catalog_material",
                    entity_id=material_id,
                    seq=seq,
                    title=name or "",
                    body=piece,
                )
            )

    return made


def _to_literal(vector: list[float]) -> str:
    """pgvector 는 `'[1,2,3]'` 모양의 문자열을 받는다."""
    return "[" + ",".join(f"{one:.7g}" for one in vector) + "]"


def reindex(db: Session, *, batch: int | None = None) -> dict[str, int]:
    """산문을 전부 다시 색인한다. **모델이 바뀌면 이것을 다시 돌린다.**

    조각 단위로 갈아 끼운다 — 중간에 실패해도 이미 넣은 것은 남고, 다시 돌리면
    이어서 채운다.
    """
    if not embeddings.enabled():
        return {"chunks": 0, "skipped": 1}
    if not ensure_schema(db):
        return {"chunks": 0, "skipped": 1}

    model = get_settings().embedding_model if embeddings.backend() == "ollama" else "mock"
    chunks = collect(db)
    size = batch or get_settings().embedding_batch

    seen: set[tuple[str, str, int]] = set()
    written = 0
    for at in range(0, len(chunks), size):
        window = chunks[at : at + size]
        vectors = embeddings.embed([f"{one.title}\n{one.body}" for one in window])
        for one, vector in zip(window, vectors, strict=True):
            db.execute(
                text(f"""
                INSERT INTO {TABLE} (id, kind, entity_id, seq, title, body, embedding, model)
                VALUES (:id, :kind, :entity_id, :seq, :title, :body,
                        CAST(:embedding AS vector), :model)
                ON CONFLICT (kind, entity_id, seq) DO UPDATE
                SET title = EXCLUDED.title, body = EXCLUDED.body,
                    embedding = EXCLUDED.embedding, model = EXCLUDED.model,
                    updated_at = now()
                """),
                {
                    "id": str(uuid.uuid4()),
                    "kind": one.kind,
                    "entity_id": one.entity_id,
                    "seq": one.seq,
                    "title": one.title[:300],
                    "body": one.body,
                    "embedding": _to_literal(vector),
                    "model": model,
                },
            )
            seen.add((one.kind, one.entity_id, one.seq))
            written += 1
        db.commit()

    # **사라진 것을 지운다.** 절을 지웠는데 조각이 남으면 검색 결과에서 「없는 문서」 로
    # 나오고, 눌러도 아무 데도 안 간다.
    removed = 0
    rows = db.execute(text(f"SELECT kind, entity_id, seq FROM {TABLE}")).all()
    stale = [one for one in rows if (one[0], one[1], one[2]) not in seen]
    for kind, entity_id, seq in stale:
        db.execute(
            text(f"DELETE FROM {TABLE} WHERE kind = :k AND entity_id = :e AND seq = :s"),
            {"k": kind, "e": entity_id, "s": seq},
        )
        removed += 1
    db.commit()
    return {"chunks": written, "removed": removed}


def search(db: Session, query: str, *, limit: int = SEARCH_LIMIT) -> list[Match]:
    """뜻이 가까운 조각들. **못 쓰면 빈 목록이다** — 예외를 던지지 않는다.

    검색은 이 기능 없이도 답해야 한다. 엔진이 죽었다고 검색 화면이 오류를 띄우면,
    사람은 검색이 고장 났다고 읽는다.
    """
    if not query.strip() or not available(db):
        return []
    try:
        vector = embeddings.embed_one(query)
    except embeddings.EmbeddingError as failed:
        logger.warning("의미 검색을 건너뜁니다: %s", failed)
        return []

    rows = db.execute(
        text(f"""
        SELECT kind, entity_id, title, body, 1 - (embedding <=> CAST(:q AS vector)) AS score
        FROM {TABLE}
        ORDER BY embedding <=> CAST(:q AS vector)
        LIMIT :limit
        """),
        {"q": _to_literal(vector), "limit": limit},
    ).all()

    # 같은 절의 조각이 여럿 걸린다 — **가장 가까운 조각 하나만** 남긴다. 안 그러면
    # 결과 열 줄이 같은 문서의 다른 문단으로 채워진다.
    best: dict[tuple[str, str], Match] = {}
    for kind, entity_id, title, body, score in rows:
        key = (kind, entity_id)
        if key in best:
            continue
        best[key] = Match(
            kind=kind,
            entity_id=entity_id,
            title=title or "",
            snippet=(body or "")[:200],
            score=float(score),
        )
    return list(best.values())


def stats(db: Session) -> dict[str, Any]:
    """무엇이 얼마나 색인돼 있나. 화면이 「의미 검색 꺼짐」 을 말할 근거."""
    if not table_ready(db):
        return {"ready": False, "chunks": 0, "kinds": {}}
    rows = db.execute(text(f"SELECT kind, count(*) FROM {TABLE} GROUP BY kind")).all()
    return {
        "ready": available(db),
        "chunks": sum(int(one[1]) for one in rows),
        "kinds": {one[0]: int(one[1]) for one in rows},
    }
