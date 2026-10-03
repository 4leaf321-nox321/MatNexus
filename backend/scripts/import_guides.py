"""핸드북 씨앗을 DB 에 넣는다.

    python scripts/import_guides.py             # 빠진 절 + 사람이 안 고친 절 (배포)
    python scripts/import_guides.py --check     # 씨앗과 운영 본문의 차이만 본다
    python scripts/import_guides.py --replace   # 고친 절까지 덮는다 — --check 보고 의식적으로
    python scripts/import_guides.py --only dma-prony
    python scripts/import_guides.py --titles-only  # 제목만 (본문·리비전 안 건드림)

씨앗은 `frontend/scripts/guide_seed.mjs` 가 원본 HTML 에서 만든다. 여기는 그것을
문서·절·그림으로 넣을 뿐이다 — 변환은 편집기와 같은 코드가 해야 하므로 Node 쪽에 있다.

## 정본은 저장소이고, 운영 편집은 되돌려 흡수한다

가이드는 **저장소에서 갱신되어 배포로 올라간다.** 그런데 운영에서도 사람이 고치고
검토자가 승인한다 — 두 곳에서 바뀌는 것이다. 그래서 세 모드가 각각 다른 일을 한다.

    기본       빠진 절을 더하고, 사람이 안 고친 절은 씨앗대로 바꾼다.
               **사람이 고친 절은 안 덮는다** → 배포에 넣어도 된다
    --check    다른 절을 짚는다.      덮기 전에 무엇이 부딪히는지 본다
    --replace  씨앗대로 덮는다.       사람이 보고 결정할 때만

## 「사람이 안 고친 절」 은 리비전이 안다

절의 본문은 리비전으로만 바뀐다. 씨앗이 넣은 리비전은 쓴 사람이 비어 있고(`author_id`
없음), 화면에서 낸 리비전은 반드시 쓴 사람이 있다. 그래서 **마지막으로 승인된 리비전이
씨앗의 것이고 본문이 그 리비전과 같으면** 그 절은 씨앗이 주인이다 — 새 씨앗으로 바꿔도
잃는 것이 없다. 하나라도 어긋나면(사람이 고쳐 승인했다 · 대기 중인 초안이 있다 · 삭제됐다 ·
리비전 없이 본문이 바뀌었다) 안 덮고 이름을 적는다.

전에는 기본이 **있는 절은 무엇이든 안 덮었다.** 그러면 저장소에서 원문을 고쳐도 운영
가이드는 처음 들어간 판에 머문다 — 실측(2026-09-30): 앱이 해석 프로그램 여섯을 내보내는데
운영 가이드 「지금 이 앱이 다루는 물성」 은 두 개 시절 판이었고, 사람이 고친 절은 하나도
없었다. 대기 초안이 있는 절을 안 덮는 이유: 그 초안은 옛 본문 위에 쓴 것이라, 승인되는
순간 씨앗 갱신을 말없이 되돌린다 — 검토자가 초안을 처리한 뒤 다음 배포가 가져간다.

운영 편집을 저장소로 되돌리는 길은 `export_guides.py` 다. 그것이 없으면 운영 편집은
언젠가 반드시 사라지고, 그러면 사람들이 운영에서 편집하기를 그만둔다.

## 지운 것은 되살리지 않는다 (2026-10-04)

기본 모드가 문서를 찾으면 무조건 `deleted_at = None` 을 했다 — 검토자가 휴지통으로 보낸
문서가 **배포마다** 되살아났다. 지운 사람은 다음 배포 뒤 그 문서가 다시 선 것을 보고, 지워도
소용없다고 배운다. 이제 기본 모드는 지운 문서·절을 건너뛰고 이름만 적는다
(`import_export_profiles.py` 가 지운 정의판을 대하는 것과 같다). 되살리는 것은 사람이
의식적으로 부르는 `--replace` 뿐이다.

## 왜 기본이 「문서 건너뛰기」 가 아닌가

전에는 문서 key 가 있으면 **통째로** 건너뛰었다. 그러면 저장소에 절을 새로 써도
운영에 영영 안 갔다 — 실측(2026-08-31): 운영 가이드가 통째로 비어 있었고, 그 뒤로
새 문서만 들어가고 새 절은 안 들어가는 상태였을 것이다. 지금은 **절 단위로** 본다.

## 다시 돌려도 된다

세 모드 다 그렇다. 그림은 내용 해시로 같은 것을 두 번 안 올린다.
"""

from __future__ import annotations

import argparse
import copy
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
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.guide import services  # noqa: E402
from app.modules.guide.models import (  # noqa: E402
    GuideAsset,
    GuideDocument,
    GuideRevision,
    GuideSection,
)

survive_cp949()

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
    return _asset_urls(db, seed, document_id=document_id, upload=True)


def _asset_urls(
    db: Session, seed: dict[str, Any], *, document_id: Any = None, upload: bool = False
) -> dict[str, str]:
    """그림 이름 → 이 서버의 주소. 같은 내용(해시)이면 있는 것을 쓴다.

    `upload=False` 는 **보기만** 한다(`--check`) — 아직 없는 그림은 주소가 없어서
    자리표시가 남고, 그 절은 「다름」 이 된다. 적재하면 새로 올라갈 그림이니 맞는 답이다.
    """
    urls: dict[str, str] = {}
    for asset in seed.get("assets", []):
        path = SEEDS / "assets" / asset["name"]
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        existing = db.scalar(select(GuideAsset).where(GuideAsset.sha256 == digest).limit(1))
        if existing is None and not upload:
            continue
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
    if document.deleted_at is not None:
        return "운영에서 지운 문서 — 기본 적재는 안 되살린다(--replace 로만)"

    seeded = {item["key"]: item for item in seed["sections"]}
    rows = {
        row.key: row
        for row in db.scalars(
            select(GuideSection).where(
                GuideSection.document_id == document.id, GuideSection.deleted_at.is_(None)
            )
        )
    }
    # 지운 절은 `rows` 에 없지만 **새로 들어가지도 않는다** — 적재가 건너뛴다(보기와 넣기가
    # 같은 답을 내게).
    removed = set(
        db.scalars(
            select(GuideSection.key).where(
                GuideSection.document_id == document.id, GuideSection.deleted_at.is_not(None)
            )
        )
    ) - set(rows)
    fresh = [key for key in seeded if key not in rows and key not in removed]
    gone = [key for key in seeded if key in removed]
    only_there = [key for key in rows if key not in seeded]
    # **그림은 적재가 쓸 주소로 바꿔 견준다.** 씨앗은 `asset:이름` 자리표시를 든다.
    # 전에는 그림 주소를 빼고 견줬는데, 그러면 그림 파일이 바뀐 절이 「같음」 으로
    # 보이고 적재는 그 절을 바꿨다 — 보기와 넣기가 다른 답을 냈다. 실측(2026-09-30):
    # SVG 를 고친 뒤(54fd70b) 개발 DB 의 그림만 다른 절 59 개가 옛 그림을 가리키고
    # 있었는데 `--check` 는 전부 「같음」 이었다.
    urls = _asset_urls(db, seed)
    differs = [
        key
        for key in seeded
        if key in rows and rows[key].body != _resolved(seeded[key]["body"], urls)
    ]
    # 다른 절을 둘로 가른다 — 배포가 알아서 가져갈 것과 사람이 정해야 할 것.
    guarded = [key for key in differs if not seed_owned(db, rows[key])]
    follows = len(differs) - len(guarded)

    parts = []
    if fresh:
        parts.append(
            f"새 절 {len(fresh)}({', '.join(fresh[:3])}{'…' if len(fresh) > 3 else ''})"
        )
    if follows:
        parts.append(f"씨앗대로 바뀔 절 {follows}")
    if guarded:
        shown = ", ".join(guarded[:3]) + ("…" if len(guarded) > 3 else "")
        parts.append(f"**다름 · 사람이 고친 절 {len(guarded)}**({shown})")
    if only_there:
        parts.append(f"운영에만 {len(only_there)}")
    if gone:
        parts.append(f"지운 절 {len(gone)} — 안 되살림(--replace 로만)")
    return " · ".join(parts) if parts else "같음"


def seed_owned(db: Session, section: GuideSection) -> bool:
    """이 절을 씨앗이 바꿔도 되는가 — **사람이 손댄 흔적이 하나도 없을 때만.**

    마지막 승인 리비전이 씨앗의 것(`author_id` 없음)이고 본문이 그것과 같아야 한다.
    대기 초안이 있으면 아니다: 옛 본문 위에 쓴 초안이 승인되면 씨앗 갱신이 말없이
    되돌려진다.
    """
    if section.deleted_at is not None:
        return False
    pending = db.scalar(
        select(GuideRevision.id)
        .where(GuideRevision.section_id == section.id, GuideRevision.status == "pending")
        .limit(1)
    )
    if pending is not None:
        return False
    last = db.scalar(
        select(GuideRevision)
        .where(GuideRevision.section_id == section.id, GuideRevision.status == "approved")
        .order_by(
            GuideRevision.reviewed_at.desc().nulls_last(), GuideRevision.created_at.desc()
        )
        .limit(1)
    )
    return last is not None and last.author_id is None and last.body == section.body


def _resolved(body: Any, urls: dict[str, str]) -> Any:
    """자리표시를 주소로 바꾼 사본. 견주기 전용 — 씨앗 본문은 안 건드린다."""
    copied = copy.deepcopy(body)
    _rewrite_images(copied, urls)
    return copied


def load(db: Session, seed: dict[str, Any], *, replace: bool) -> str:
    """씨앗을 넣는다.

    **기본은 빠진 절을 더하고, 사람이 안 고친 절만 씨앗대로 바꾼다**(`seed_owned`).
    그래서 배포에 넣어도 되고, 저장소에서 절을 새로 쓰거나 고쳐도 다음 배포에 저절로
    간다. 사람이 고친 절의 본문은 `--replace` 로만 바뀐다.
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
    elif document.deleted_at is not None and not replace:
        # **지운 문서는 되살리지 않는다**(2026-10-04, 위 「지운 것은 되살리지 않는다」). 전에는
        # 여기서 무조건 `deleted_at = None` 이라 검토자가 지운 문서가 배포마다 돌아왔다.
        return "운영에서 지운 문서 — 안 되살림(되살리려면 휴지통에서, 또는 --replace)"
    else:
        document.deleted_at = None  # --replace 만 여기 온다 — 사람이 의식적으로 되살린다
        made = False

    urls = _upload_assets(db, document.id, seed)
    count = 0
    added = 0
    kept = 0
    renewed = 0
    guarded: list[str] = []
    removed: list[str] = []
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
        elif not replace and section.deleted_at is not None:
            # 사람이 지운 절도 그대로 둔다. 전에도 되살리지는 않았지만 「같은 절」 이나
            # 「사람이 고쳐 둔 절」 로 세어서, --check 로 보라는 안내가 엉뚱한 데를 가리켰다.
            removed.append(item["key"])
        elif not replace and section.body == body:
            kept += 1
        elif not replace and seed_owned(db, section):
            # 씨앗이 넣은 판 그대로다 — 새 씨앗으로 바꿔도 잃는 것이 없다.
            _renew(db, section, body, note="씨앗에서 갱신")
            renewed += 1
        elif not replace:
            # **안 덮는다.** 운영에서 고쳐 승인한 본문이 여기 있을 수 있고, 그것을
            # 말없이 되돌리면 다음부터 아무도 운영에서 편집하지 않는다.
            guarded.append(item["key"])
        else:
            # 덮되 지우지 않는다 — 앞 판은 리비전에 남아 있다.
            section.deleted_at = None
            section.title = item["title"]
            section.position = int(item.get("position", 0))
            _renew(db, section, body, note="씨앗에서 다시 가져옴")
        count += 1
    db.commit()
    if made:
        return f"만듦 — 절 {count} · 그림 {len(urls)}"
    if replace:
        return f"덮음 — 절 {count} · 그림 {len(urls)}"
    said = f"채움 — 새 절 {added} · 씨앗대로 갱신 {renewed} · 같은 절 {kept}"
    if guarded:
        shown = ", ".join(guarded[:3]) + ("…" if len(guarded) > 3 else "")
        said += f" · 사람이 고쳐 둔 절 {len(guarded)}({shown}) — 안 덮음, --check 로 보고 결정"
    if removed:
        shown = ", ".join(removed[:3]) + ("…" if len(removed) > 3 else "")
        said += f" · 지운 절 {len(removed)}({shown}) — 안 되살림"
    return said


def _renew(db: Session, section: GuideSection, body: dict[str, Any], *, note: str) -> None:
    """본문을 씨앗으로 바꾸고 리비전을 남긴다. 쓴 사람은 비운다 — 씨앗의 판이라는 표시다."""
    section.body = body
    section.body_text = services.plain_text(body)
    section.revision_no += 1
    db.add(
        GuideRevision(
            section_id=section.id,
            status="approved",
            body=body,
            body_text=section.body_text,
            note=note,
            reviewed_at=datetime.now(UTC),
        )
    )


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
