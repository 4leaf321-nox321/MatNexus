"""핸드북 씨앗을 DB 에 넣는다.

    python scripts/import_guides.py                 # seeds/guide 전부, 있으면 건너뜀
    python scripts/import_guides.py --replace       # 있어도 덮는다(판이 하나 더 쌓인다)
    python scripts/import_guides.py --only dma-prony

씨앗은 `frontend/scripts/guide_seed.mjs` 가 원본 HTML 에서 만든다. 여기는 그것을
문서·절·그림으로 넣을 뿐이다 — 변환은 편집기와 같은 코드가 해야 하므로 Node 쪽에 있다.

## 다시 돌려도 된다

문서 키로 있는지 본다. 있으면 건너뛴다(`--replace` 면 절마다 새 승인 판을 얹는다 —
사람이 고친 것을 지우지 않고 **리비전으로 남긴다**). 그림은 내용 해시로 같은 것을
두 번 안 올린다.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.modules.guide import services  # noqa: E402
from app.modules.guide.models import (  # noqa: E402
    GuideAsset,
    GuideDocument,
    GuideRevision,
    GuideSection,
)

SEEDS = BACKEND_DIR / "seeds" / "guide"


def _rewrite_images(node: Any, urls: dict[str, str]) -> None:
    """`asset:<이름>` 자리표시를 진짜 주소로."""
    if isinstance(node, dict):
        attrs = node.get("attrs")
        if node.get("type") == "image" and isinstance(attrs, dict):
            src = str(attrs.get("src", ""))
            if src.startswith("asset:"):
                attrs["src"] = urls.get(src[len("asset:") :], src)
        for child in node.get("content", []) or []:
            _rewrite_images(child, urls)
    elif isinstance(node, list):
        for child in node:
            _rewrite_images(child, urls)


def _upload_assets(db: Session, document_id: Any, seed: dict[str, Any]) -> dict[str, str]:
    urls: dict[str, str] = {}
    for asset in seed.get("assets", []):
        path = SEEDS / "assets" / asset["name"]
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        existing = db.scalar(select(GuideAsset).where(GuideAsset.sha256 == digest))
        if existing is None:
            existing = services.save_asset(
                db,
                user=None,
                document_id=document_id,
                filename=asset["name"],
                content_type="image/svg+xml",
                stream=io.BytesIO(data),
            )
        urls[asset["name"]] = services.asset_url(existing.id)
    return urls


def load(db: Session, seed: dict[str, Any], *, replace: bool) -> str:
    document = db.scalar(select(GuideDocument).where(GuideDocument.key == seed["key"]))
    if document is not None and not replace:
        return "있음, 건너뜀"
    if document is None:
        document = services.create_document(
            db,
            None,
            key=seed["key"],
            title=seed["title"],
            kind=seed["kind"],
            topic=seed.get("topic"),
            summary=seed.get("summary") or None,
            position=0,
            source_filename=seed.get("source_filename"),
        )
        made = True
    else:
        document.deleted_at = None
        made = False

    urls = _upload_assets(db, document.id, seed)
    count = 0
    for item in seed["sections"]:
        body = item["body"]
        _rewrite_images(body, urls)
        section = db.scalar(
            select(GuideSection).where(
                GuideSection.document_id == document.id, GuideSection.key == item["key"]
            )
        )
        if section is None:
            services.create_section(
                db,
                document,
                user=None,
                key=item["key"],
                title=item["title"],
                position=int(item.get("position", 0)),
                body=body,
            )
        else:
            # 덮되 지우지 않는다 — 앞 판은 리비전에 남아 있다.
            section.deleted_at = None
            section.title = item["title"]
            section.position = int(item.get("position", 0))
            section.body = body
            section.body_text = services.plain_text(body)
            section.revision_no += 1
            db.add(
                GuideRevision(
                    section_id=section.id,
                    status="approved",
                    body=body,
                    body_text=section.body_text,
                    note="씨앗에서 다시 가져옴",
                    reviewed_at=datetime.now(UTC),
                )
            )
        count += 1
    db.commit()
    return f"{'만듦' if made else '덮음'} — 절 {count} · 그림 {len(urls)}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--only", help="이 키의 문서만")
    args = parser.parse_args()

    files = sorted(SEEDS.glob("*.json"))
    if args.only:
        files = [f for f in files if f.stem == args.only]
    if not files:
        print("씨앗이 없습니다:", SEEDS)
        return
    with SessionLocal() as db:
        for file in files:
            seed = json.loads(file.read_text(encoding="utf-8"))
            print(f"{seed['key']:<40} {load(db, seed, replace=args.replace)}")


if __name__ == "__main__":
    main()
