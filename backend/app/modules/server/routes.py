"""서버 현황 — **읽기만 한다.**

여기서 서버를 재시작하거나 설정을 바꾸지 않는다. 화면에서 만질 수 있으면 그것은
「현황」 이 아니라 운영 도구이고, 웹으로 그 권한을 여는 것은 별개의 결정이다.
참고한 ReportArchive 는 워커 수를 화면에서 고치는데, 거기는 systemd 가 있고
재시작을 사람이 따로 한다 — 여기는 그 전제가 없다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs import kinds
from app.jobs.queue import enqueue
from app.modules.accounts.models import User
from app.modules.server import services
from app.modules.server.schemas import (
    ExportOut,
    ExportQueuedOut,
    ExportRequest,
    FailedJobOut,
    QueueOut,
    ServerInfoOut,
)
from app.shared import audit
from app.shared.auth import require_system_admin

router = APIRouter(prefix="/server", tags=["server"])


@router.get("/info", response_model=ServerInfoOut)
def server_info(
    user: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> ServerInfoOut:
    """호스트·CPU·메모리·디스크·DB 를 한 번에.

    **시스템 관리자만.** 호스트 이름과 경로가 담겨 있어 사내라도 모두에게 보일
    것은 아니다.
    """
    return ServerInfoOut.model_validate(services.info(db))


@router.get("/queue", response_model=QueueOut)
def queue(
    user: User = Depends(require_system_admin), db: Session = Depends(get_db)
) -> QueueOut:
    """큐 현황과 실패 목록. 도는 것은 문제없다 — 보이지 않는 것이 문제였다(2026-09-05)."""
    return QueueOut.model_validate(services.queue_status(db))


@router.post("/queue/{job_id}/retry", response_model=FailedJobOut)
def retry(
    job_id: uuid.UUID,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> FailedJobOut:
    """실패한 작업을 처음부터 다시. 워커가 다음 틱에 집어 간다."""
    job = services.retry_job(db, job_id)
    return FailedJobOut(
        id=job.id,
        kind=job.kind,
        kind_label=services.KIND_LABELS.get(job.kind, job.kind),
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        last_error=job.last_error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get("/exports", response_model=list[ExportOut])
def list_exports(user: User = Depends(require_system_admin)) -> list[ExportOut]:
    """만들어 둔 내보내기들. 최근 것부터.

    **무엇이 들었는지 함께 준다**(부서·곡선·문헌·줄 수). 폴더 이름만 보이면
    「이게 곡선 포함이었나」 를 열어 봐야 알고, 그때는 이미 건넨 뒤다.
    """
    return [ExportOut.model_validate(one) for one in services.exports()]


@router.post("/exports", response_model=ExportQueuedOut, status_code=202)
def create_export(
    payload: ExportRequest,
    user: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> ExportQueuedOut:
    """물성 데이터를 CSV 묶음으로 뽑는다. **큐에 넣고 바로 돌려준다.**

    곡선까지 뽑으면 수 분에 수백 MB 다 — 요청을 붙잡으면 브라우저가 먼저 끊고,
    그러면 사람은 실패한 줄 아는데 서버는 계속 만든다.

    ## 되돌릴 수 없는 일이라 감사에 남긴다

    나간 파일은 회수가 안 되고, 그 파일 안에서는 **부서 가시성도 뜻이 없다.**
    누가 언제 무엇을 뽑았는지는 반년 뒤에 실제로 물어질 수 있다.
    """
    folder = services.export_folder_name(workspace=payload.workspace, note=payload.note)
    enqueue(
        db,
        kind=kinds.DATA_EXPORT_DATASET,
        payload={
            "folder": folder,
            "workspace": payload.workspace,
            "curves": payload.curves,
            "catalog": payload.catalog,
        },
        # **재시도를 안 한다.** 반쯤 만들다 실패한 폴더 위에 다시 쓰면 무엇이 온전한지
        # 알 수 없다 — 실패는 화면에 남기고 사람이 다시 누른다.
        max_attempts=1,
    )
    audit.record(
        db,
        action=audit.DATA_EXPORTED,
        actor=user,
        target_table="exports",
        target_id=None,
        target_label=folder,
        changes={
            "workspace": payload.workspace or "전 부서",
            "curves": payload.curves,
            "catalog": payload.catalog,
        },
        reason=payload.note,
    )
    db.commit()
    return ExportQueuedOut(
        status="queued",
        folder=folder,
        path=str(services.export_root() / folder),
        message=(
            "내보내기를 큐에 넣었습니다. 다 되면 이 목록에 줄 수와 크기가 뜹니다 — "
            "파일은 서버 폴더에서 가져갑니다."
        ),
    )
