"""기본 형식의 정의판을 DB 에 넣는다 — **꺼진 채로, 아무도 손대지 않은 것만 새 씨앗대로.**

    python scripts/import_export_profiles.py            # 배포가 도는 모드
    python scripts/import_export_profiles.py --check    # 넣지 않고 무엇이 바뀔지만 본다

씨앗은 `seeds/export-profiles/기본-형식-정의.json` 이다 — 기본 형식(코드판) 50개를 정의로
다시 적은 것이고, 코드판과 글자까지 같다는 시험이 묶는다(`tests/unit/test_export_twins.py`).
파일 모양은 화면의 「불러오기」 가 읽는 것과 같다.

## 왜 배포가 넣나 (ADR 0047)

정의판은 **코드판이 틀렸을 때 대신 켜는 비상용**이다 — 시스템 관리자가 코드판을 「사용
중단」 하고, 정의판을 켜서 화면에서 고친 덱을 낸다(ADR 0037 · 0038). 그런데 정의판을 DB 에
넣는 길이 개발 서버의 손작업뿐이었다. 운영에는 없었고, 그러면 사용 중단은 형식을 메뉴에서
빼기만 하고 대신 쓸 것이 없다. 실측(2026-09-30): Abaqus 점탄성 코드판에 `MODULI` 가 빠진
것을 찾았을 때 운영에서 쓸 수 있는 대안이 없었다.

## 누가 무엇을 덮나

    없다                            꺼진 채 만든다(등록자 없음 — 관리자만 고친다)
    씨앗과 같다                      그대로. 지문이 없으면 적어 둔다(손으로 들여온 같은 판)
    씨앗이 마지막에 쓴 그대로 · 꺼짐  새 씨앗으로 바꾼다 — 코드판을 고친 것이 따라온다
    그 밖(고쳤다 · 켰다 · 옛 판)      **안 덮는다** — 이름을 적는다

켠 것을 안 덮는 이유: 누군가 그것으로 덱을 내고 있다. 사용 중단한 코드판 대신 켜 둔 판이
배포 한 번에 바뀌면 받는 사람은 이유를 모른다. 손으로 들여온 옛 판(지문 없음)을 안 덮는
이유: 사람이 들여와 고쳤는지 씨앗의 옛 판인지 가를 수 없다 — 「불러오기」 창에서 그 줄의
「덮어쓰기」 를 켜면 된다. 지운 정의판은 되살리지 않는다(사람이 지운 것이다).

**꺼진 채로만 넣는다.** 켜면 카드의 내보내기 메뉴에 코드판과 같은 형식이 하나씩 더 선다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.fitting.models import ExportProfile  # noqa: E402
from matcore import export  # noqa: E402
from matcore.export import template  # noqa: E402

survive_cp949()

SEED = BACKEND_DIR / "seeds" / "export-profiles" / "기본-형식-정의.json"


def digest(label: str, description: str | None, definition: dict[str, Any]) -> str:
    """이름 · 설명 · 정의의 지문. 켜짐은 안 넣는다 — 켜고 끄기는 따로 본다."""
    body = json.dumps(
        {"label": label, "description": description, "definition": definition},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _of_row(row: ExportProfile) -> str:
    return digest(row.label, row.description, row.definition)


def _of_seed(item: dict[str, Any]) -> str:
    return digest(item["label"], item.get("description"), item["definition"])


def plan(db: Session, profiles: list[dict[str, Any]]) -> dict[str, list[str]]:
    """무엇을 할지 — **아무것도 안 쓴다.** `--check` 와 적재가 같은 판정을 쓴다."""
    decided: dict[str, list[str]] = {
        "new": [],
        "same": [],
        "adopt": [],
        "renew": [],
        "guarded": [],
        "deleted": [],
        "broken": [],
    }
    for item in profiles:
        key = item["key"]
        try:
            # **깨진 씨앗은 안 넣는다.** 넣으면 목록이 그 줄을 건너뛰며 로그만 남긴다
            # (`deckmap.all_renderers`) — 켜려는 순간에야 안다.
            template.renderer_from_definition(
                {**item["definition"], "key": key, "label": item["label"]}
            )
        except export.ExportError:
            decided["broken"].append(key)
            continue
        live = db.scalar(
            select(ExportProfile).where(
                ExportProfile.key == key, ExportProfile.deleted_at.is_(None)
            )
        )
        if live is None:
            gone = db.scalar(select(ExportProfile.id).where(ExportProfile.key == key).limit(1))
            decided["deleted" if gone is not None else "new"].append(key)
            continue
        now, wanted = _of_row(live), _of_seed(item)
        if now == wanted:
            decided["same" if live.seed_digest == wanted else "adopt"].append(key)
        elif live.seed_digest is not None and now == live.seed_digest and not live.is_active:
            decided["renew"].append(key)
        else:
            decided["guarded"].append(key)
    return decided


def load(db: Session, seed: dict[str, Any]) -> dict[str, list[str]]:
    """씨앗을 넣는다. 판정은 `plan` 과 같다 — 보기와 넣기가 다른 답을 내지 않게."""
    profiles = seed["profiles"]
    decided = plan(db, profiles)
    by_key = {item["key"]: item for item in profiles}
    for key in decided["new"]:
        item = by_key[key]
        db.add(
            ExportProfile(
                key=key,
                label=item["label"],
                description=item.get("description"),
                definition=item["definition"],
                # **꺼진 채로만.** 씨앗 파일이 켜짐을 말해도 따르지 않는다.
                is_active=False,
                seed_digest=_of_seed(item),
            )
        )
    for key in decided["adopt"] + decided["renew"]:
        item = by_key[key]
        row = db.scalar(
            select(ExportProfile).where(
                ExportProfile.key == key, ExportProfile.deleted_at.is_(None)
            )
        )
        assert row is not None
        row.label = item["label"]
        row.description = item.get("description")
        row.definition = item["definition"]
        row.seed_digest = _of_seed(item)
    db.commit()
    return decided


def summary(decided: dict[str, list[str]], *, dry: bool) -> str:
    verb = "넣을" if dry else "넣은"
    parts = [
        f"새로 {verb} 것 {len(decided['new'])}",
        f"씨앗대로 {'바뀔' if dry else '바꾼'} 것 {len(decided['renew'])}",
        f"같음 {len(decided['same']) + len(decided['adopt'])}",
    ]
    lines = ["정의판(기본 형식) — " + " · ".join(parts)]
    if decided["guarded"]:
        lines.append(
            f"  안 덮음 {len(decided['guarded'])} — 고쳤거나 켰거나 손으로 들여온 옛 판: "
            + ", ".join(decided["guarded"])
        )
    if decided["deleted"]:
        lines.append(f"  지운 것 — 안 되살림: {', '.join(decided['deleted'])}")
    if decided["broken"]:
        lines.append(f"  !! 씨앗이 정의로 안 읽힘 — 안 넣음: {', '.join(decided['broken'])}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="넣지 않고 무엇이 바뀔지만 본다")
    args = parser.parse_args()
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        if args.check:
            print(summary(plan(db, seed["profiles"]), dry=True))
        else:
            print(summary(load(db, seed), dry=False))


if __name__ == "__main__":
    main()
