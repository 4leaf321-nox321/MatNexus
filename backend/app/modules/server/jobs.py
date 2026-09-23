"""서버 작업 핸들러 — 데이터 내보내기.

요청 안에서 만들지 않는다. 곡선까지 뽑으면 수 분에 수백 MB 라 브라우저가 먼저
끊고, 그러면 사람은 실패한 줄 아는데 서버는 계속 만든다 — 업로드 파싱을 워커로
옮긴 것과 같은 이유다.

**만드는 코드는 여기 없다.** `app/shared/dataset_export.py` 를 부른다 — 명령줄
스크립트도 같은 함수를 부르므로 둘이 갈라지지 않는다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import kinds
from app.jobs.handlers import handler
from app.modules.server import services
from app.shared import dataset_export

logger = logging.getLogger(__name__)


@handler(kinds.DATA_EXPORT_DATASET)
def export_dataset(db: Session, payload: dict[str, Any]) -> None:
    """내보내기 한 번. **실패하면 던진다** — 워커가 재시도하고 서버 화면에 뜬다.

    결과 폴더는 요청할 때 정해진다(`folder`). 여기서 시각으로 다시 지으면 큐에서
    기다린 시간만큼 이름이 밀려, 사람이 화면에서 본 이름과 폴더 이름이 달라진다.
    """
    folder = services.export_root() / str(payload["folder"])
    workspace = payload.get("workspace")
    report = dataset_export.export(
        folder,
        # **워커가 든 세션을 그대로 넘긴다.** 여기서 새로 열면 그 작업이 어느 DB 를
        # 보는지가 설정에만 달리고, 시험은 제 DB 가 아닌 것을 뽑는다.
        db=db,
        workspace=str(workspace) if workspace else None,
        with_curves=bool(payload.get("curves", True)),
        with_catalog=bool(payload.get("catalog", True)),
    )
    rows = sum(int(one) for one in report["counts"].values())
    logger.info(
        "데이터 내보내기 완료: %s (표 %d장 · %s줄%s)",
        folder,
        len(report["counts"]),
        f"{rows:,}",
        (
            f" · 못 읽은 곡선 {len(report['missing_curve_files'])}건"
            if report["missing_curve_files"]
            else ""
        ),
    )
