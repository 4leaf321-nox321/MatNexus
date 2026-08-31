"""DB 의 핸드북을 씨앗 JSON 으로 되돌린다 — **운영에서 고친 것을 저장소로.**

    python scripts/export_guides.py                  # 전부, seeds/guide 에 덮어쓴다
    python scripts/export_guides.py --only dma-prony
    python scripts/export_guides.py --out ../tmp     # 다른 곳에 내고 눈으로 견준다

## 왜 필요한가

가이드는 **저장소에서 갱신되어 배포로 올라가는데**, 운영에서도 사람이 고치고
검토자가 승인한다. 되돌리는 길이 없으면 운영 편집은 다음 `--replace` 에 덮이고,
그 일을 한 번 겪은 사람은 **다시는 운영에서 편집하지 않는다.** 그러면 현장 지식이
핸드북에 안 쌓인다.

이 스크립트가 운영 본문을 씨앗으로 뽑아 준다. 커밋하면 저장소가 다시 정본이 되고
차이가 0 이 된다.

    개발 → 운영   배포마다 import_guides.py (빠진 것만, 안 덮음)
    운영 → 개발   가끔 export_guides.py 로 뽑아 커밋
    덮어쓰기      import_guides.py --replace 를 --check 보고 의식적으로만

## 그림은 자리표시로 되돌린다

본문의 그림은 `/api/guide/assets/<id>` 를 든다. 그 주소는 **그 서버의 것**이라
씨앗에 실으면 다른 서버에서 깨진다. 적재 스크립트가 `asset:<파일이름>` 을 주소로
바꿨으므로, 여기서는 반대로 돌린다 — 파일도 `seeds/guide/assets/` 에 함께 쓴다.

## 안 싣는 것

`id` · 만든 사람 · 시각 · 리비전 이력은 **그 서버의 사정**이다. 씨앗은 「무엇이
적혀 있나」 이지 「누가 언제 적었나」 가 아니다 — 뒤엣것은 그 서버의 감사 기록에
남는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.modules.guide.models import (  # noqa: E402
    GuideAsset,
    GuideDocument,
    GuideSection,
)
from app.shared import filestore  # noqa: E402

SEEDS = BACKEND_DIR / "seeds" / "guide"


def _asset_names(body: Any, names: dict[str, str], out: list[str]) -> None:
    """본문의 그림 주소를 `asset:<이름>` 으로 되돌리고, 쓴 이름을 모은다."""
    if isinstance(body, dict):
        attrs = body.get("attrs")
        if body.get("type") == "image" and isinstance(attrs, dict):
            src = str(attrs.get("src", ""))
            name = names.get(src)
            if name is not None:
                attrs["src"] = f"asset:{name}"
                if name not in out:
                    out.append(name)
        for child in body.get("content", []) or []:
            _asset_names(child, names, out)
    elif isinstance(body, list):
        for child in body:
            _asset_names(child, names, out)


def _alt_of(body: Any, name: str) -> str:
    """그 그림의 대체 글. 씨앗이 그것도 들고 있다."""
    if isinstance(body, dict):
        attrs = body.get("attrs")
        if (
            body.get("type") == "image"
            and isinstance(attrs, dict)
            and str(attrs.get("src", "")) == f"asset:{name}"
        ):
            return str(attrs.get("alt") or name)
        for child in body.get("content", []) or []:
            found = _alt_of(child, name)
            if found:
                return found
    elif isinstance(body, list):
        for child in body:
            found = _alt_of(child, name)
            if found:
                return found
    return ""


def dump(db: Any, document: GuideDocument, out_dir: Path) -> str:
    sections = list(
        db.scalars(
            select(GuideSection)
            .where(
                GuideSection.document_id == document.id,
                GuideSection.deleted_at.is_(None),
            )
            .order_by(GuideSection.position, GuideSection.key)
        )
    )
    assets = list(db.scalars(select(GuideAsset).where(GuideAsset.document_id == document.id)))
    # 주소 → 파일이름. 적재가 만든 것과 같은 짝이다.
    names = {f"/api/guide/assets/{one.id}": one.filename for one in assets}
    by_name = {one.filename: one for one in assets}

    used: list[str] = []
    payload_sections = []
    for section in sections:
        body = json.loads(json.dumps(section.body or {"type": "doc", "content": []}))
        _asset_names(body, names, used)
        payload_sections.append(
            {
                "key": section.key,
                "title": section.title,
                "position": section.position,
                "body": body,
            }
        )

    asset_dir = out_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    payload_assets = []
    for name in used:
        row = by_name.get(name)
        if row is None:
            continue
        alt = ""
        for item in payload_sections:
            alt = _alt_of(item["body"], name)
            if alt:
                break
        payload_assets.append({"name": name, "alt": alt or name})
        # **파일도 함께 쓴다.** 씨앗 JSON 만 커밋하면 다른 서버에서 그림이 안 뜬다.
        (asset_dir / name).write_bytes(filestore.read_bytes(row.path))
        written += 1

    payload = {
        "key": document.key,
        "kind": document.kind,
        "topic": document.topic,
        "title": document.title,
        "summary": document.summary or "",
        "source_filename": document.source_filename,
        "sections": payload_sections,
        "assets": payload_assets,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{document.key}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return f"절 {len(payload_sections)} · 그림 {written}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--only", help="이 키의 문서만")
    parser.add_argument("--out", help="쓸 곳. 기본은 backend/seeds/guide")
    args = parser.parse_args()

    out_dir = Path(args.out).resolve() if args.out else SEEDS
    with SessionLocal() as db:
        query = select(GuideDocument).where(GuideDocument.deleted_at.is_(None))
        if args.only:
            query = query.where(GuideDocument.key == args.only)
        documents = list(db.scalars(query.order_by(GuideDocument.kind, GuideDocument.key)))
        if not documents:
            print("문서가 없습니다.")
            return
        for document in documents:
            print(f"{document.key:<40} {dump(db, document, out_dir)}")
    print(f"\n쓴 곳: {out_dir}")


if __name__ == "__main__":
    main()
