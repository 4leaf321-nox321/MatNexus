"""워커 없이 올린 파일을 읽는다 — **개발 편의 스크립트.**

개발 서버(`run.py`)만 띄우고 워커를 안 띄우면 올린 시험이 `uploaded` 에 머문다.
예시를 만들 때 그 자리에서 읽으려고 둔다. 운영에서는 워커가 이 일을 한다.

    python scripts/parse_uploaded.py            # uploaded 전부
    python scripts/parse_uploaded.py <run-id>…  # 준 것만
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

import app.all_models  # noqa: F401  (DB 를 만지는 스크립트는 전부 import 한다 — AGENTS.md)
from app.database import SessionLocal
from app.modules.tests import services
from app.modules.tests.models import TestRun


def main(argv: list[str]) -> int:
    with SessionLocal() as db:
        if argv:
            ids = [uuid.UUID(one) for one in argv]
        else:
            ids = list(db.scalars(select(TestRun.id).where(TestRun.status == "uploaded")))
        if not ids:
            print("읽을 것이 없습니다.")
            return 0
        for run_id in ids:
            status = services.parse_run(db, run_id)
            db.commit()
            print(f"{run_id}  {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
