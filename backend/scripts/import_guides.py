"""핸드북 씨앗을 DB 에 넣는다.

    python scripts/import_guides.py             # 빠진 것만 채운다 (배포에 넣어도 된다)
    python scripts/import_guides.py --check     # 씨앗과 운영 본문의 차이만 본다
    python scripts/import_guides.py --replace   # 덮는다 — --check 를 보고 의식적으로만
    python scripts/import_guides.py --only dma-prony
    python scripts/import_guides.py --titles-only  # 제목만 (본문·리비전 안 건드림)

씨앗은 `frontend/scripts/guide_seed.mjs` 가 원본 HTML 에서 만든다. 여기는 그것을
문서·절·그림으로 넣을 뿐이다 — 변환은 편집기와 같은 코드가 해야 하므로 Node 쪽에 있다.

## 정본은 저장소이고, 운영 편집은 되돌려 흡수한다

가이드는 **저장소에서 갱신되어 배포로 올라간다.** 그런데 운영에서도 사람이 고치고
검토자가 승인한다 — 두 곳에서 바뀌는 것이다. 그래서 세 모드가 각각 다른 일을 한다.

    기본       빠진 절만 더한다.      **아무것도 안 덮는다** → 배포에 넣어도 된다
    --check    다른 절을 짚는다.      덮기 전에 무엇이 부딪히는지 본다
    --replace  씨앗대로 덮는다.       사람이 보고 결정할 때만

운영 편집을 저장소로 되돌리는 길은 `export_guides.py` 다. 그것이 없으면 운영 편집은
언젠가 반드시 사라지고, 그러면 사람들이 운영에서 편집하기를 그만둔다.

## 왜 기본이 「문서 건너뛰기」 가 아닌가

전에는 문서 key 가 있으면 **통째로** 건너뛰었다. 그러면 저장소에 절을 새로 써도
운영에 영영 안 갔다 — 실측(2026-08-31): 운영 가이드가 통째로 비어 있었고, 그 뒤로
새 문서만 들어가고 새 절은 안 들어가는 상태였을 것이다. 지금은 **절 단위로** 본다.

## 다시 돌려도 된다

세 모드 다 그렇다. 그림은 내용 해시로 같은 것을 두 번 안 올린다.
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


def sync_titles(db: Session, seed: dict[str, Any]) -> str:
    """제목만 씨앗대로. 본문·리비전은 안 건드린다 — 제목은 가변 메타다."""
    document = db.scalar(select(GuideDocument).where(GuideDocument.key == seed["key"]))
    if document is None:
        return "없음, 건너뜀"
    document.title = seed["title"]
    changed = 0
    for item in seed["sections"]:
        section = db.scalar(
            select(GuideSection).where(
                GuideSection.document_id == document.id, GuideSection.key == item["key"]
            )
        )
        if section is not None and section.title != item["title"]:
            section.title = item["title"]
            changed += 1
    db.commit()
    return f"제목 {changed}건 갱신"


def check(db: Session, seed: dict[str, Any]) -> str:
    """**넣지 않고 견주기만 한다.** 덮기 전에 무엇이 부딪히는지 보는 자리.

    본문을 통째로 견준다(편집기 문서 JSON). 글자만 뽑아 견주면 표의 셀 병합이나
    그림이 바뀐 것을 못 본다 — 그것도 사람이 고친 것이다.
    """
    document = db.scalar(select(GuideDocument).where(GuideDocument.key == seed["key"]))
    if document is None:
        return f"운영에 없음 — 절 {len(seed['sections'])} 개가 새로 들어간다"

    seeded = {item["key"]: item for item in seed["sections"]}
    rows = {
        row.key: row
        for row in db.scalars(
            select(GuideSection).where(
                GuideSection.document_id == document.id, GuideSection.deleted_at.is_(None)
            )
        )
    }
    fresh = [key for key in seeded if key not in rows]
    only_there = [key for key in rows if key not in seeded]
    # **그림 주소는 빼고 견준다.** 씨앗은 `asset:이름` 자리표시를 들고 DB 는 진짜
    # 주소를 든다 — 그대로 견주면 안 고친 절이 전부 「다름」 으로 뜬다.
    differs = [
        key
        for key in seeded
        if key in rows
        and _without_images(rows[key].body) != _without_images(seeded[key]["body"])
    ]

    parts = []
    if fresh:
        parts.append(
            f"새 절 {len(fresh)}({', '.join(fresh[:3])}{'…' if len(fresh) > 3 else ''})"
        )
    if differs:
        shown = ", ".join(differs[:3]) + ("…" if len(differs) > 3 else "")
        parts.append(f"**다름 {len(differs)}**({shown})")
    if only_there:
        parts.append(f"운영에만 {len(only_there)}")
    return " · ".join(parts) if parts else "같음"


def _without_images(body: Any) -> Any:
    """그림 주소를 지운 사본. 견주기 전용."""
    if isinstance(body, dict):
        cleaned = {
            key: _without_images(value) for key, value in body.items() if key != "attrs"
        }
        attrs = body.get("attrs")
        if isinstance(attrs, dict):
            cleaned["attrs"] = {k: v for k, v in attrs.items() if k != "src"}
        elif attrs is not None:
            cleaned["attrs"] = attrs
        return cleaned
    if isinstance(body, list):
        return [_without_images(one) for one in body]
    return body


def load(db: Session, seed: dict[str, Any], *, replace: bool) -> str:
    """씨앗을 넣는다.

    **기본은 빠진 절만 더한다 — 아무것도 안 덮는다.** 그래서 배포에 넣어도 되고,
    저장소에 절을 새로 써도 다음 배포에 저절로 간다. 있는 절의 본문은 `--replace`
    로만 바뀐다.
    """
    document = db.scalar(select(GuideDocument).where(GuideDocument.key == seed["key"]))
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
    added = 0
    kept = 0
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
            added += 1
        elif not replace:
            # **안 덮는다.** 운영에서 고쳐 승인한 본문이 여기 있을 수 있고, 그것을
            # 말없이 되돌리면 다음부터 아무도 운영에서 편집하지 않는다.
            kept += 1
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
    if made:
        return f"만듦 — 절 {count} · 그림 {len(urls)}"
    if replace:
        return f"덮음 — 절 {count} · 그림 {len(urls)}"
    return f"채움 — 새 절 {added} · 그대로 둔 절 {kept}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="넣지 않고 씨앗과 운영 본문의 차이만 본다"
    )
    parser.add_argument("--only", help="이 키의 문서만")
    parser.add_argument("--titles-only", action="store_true")
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
            if args.check:
                print(f"{seed['key']:<40} {check(db, seed)}")
            elif args.titles_only:
                print(f"{seed['key']:<40} {sync_titles(db, seed)}")
            else:
                print(f"{seed['key']:<40} {load(db, seed, replace=args.replace)}")


if __name__ == "__main__":
    main()
