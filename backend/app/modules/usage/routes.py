"""사용 현황 — 관리자 화면(「관리 → 사용 현황」)과 MCP 서버의 도구 호출 보고."""

from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.accounts.models import User
from app.modules.usage import services
from app.modules.usage.schemas import McpCallIn, UsageSummaryOut
from app.shared import usage_meter
from app.shared.auth import current_user, require_system_admin

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary", response_model=UsageSummaryOut)
def usage_summary(
    days: int = Query(default=30, ge=1, le=366, description="오늘까지 며칠"),
    _admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> UsageSummaryOut:
    """기간의 사용 현황 한 장 — **시스템 관리자만.** 사람마다의 사용량이 실린다."""
    return services.summary(db, days=days)


#: 사람별 CSV 의 머리줄. 요약 화면 「사람별」 표와 같은 칸이다.
PEOPLE_HEADER = (
    "이름",
    "이메일",
    "대표 부서",
    "쓴 날",
    "마지막",
    "화면 요청",
    "쓰기",
    "MCP 도구 호출",
    "상세 조회",
)


@router.get("/people.csv", include_in_schema=False)
def usage_people_csv(
    days: int = Query(default=30, ge=1, le=366, description="오늘까지 며칠"),
    _admin: User = Depends(require_system_admin),
    db: Session = Depends(get_db),
) -> Response:
    """사람별 활동 **전부**를 CSV 로(2026-10-04) — 화면은 앞 30명만 보인다. 시스템 관리자만.

    BOM 을 붙인다(Excel 이 한글을 깬다) · 스키마에 안 싣는다(파일을 내려받는 자리다) —
    부서 정보 CSV 와 같은 규약이다.
    """
    period, people = services.people_rows(db, days=days)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(PEOPLE_HEADER)
    writer.writerows(
        (
            one.name,
            one.email or "",
            one.workspace or services.NO_WORKSPACE,
            one.active_days,
            one.last_day.isoformat(),
            one.web_requests,
            one.writes,
            one.mcp_calls,
            one.views,
        )
        for one in people
    )
    span = period.start.isoformat() + "_" + period.end.isoformat()
    # 파일 이름은 둘로 — ASCII 는 옛 브라우저용, UTF-8 은 한글 이름용(부서 정보 CSV 와 같다).
    disposition = (
        'attachment; filename="usage-people-' + span + '.csv"; '
        "filename*=UTF-8''" + quote("사용현황-사람별-" + span + ".csv")
    )
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


@router.post("/mcp-calls", status_code=204)
def report_mcp_call(
    payload: McpCallIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """MCP 서버가 도구 하나를 마칠 때 알린다 — **그 토큰의 주인 몫으로** 센다.

    요청 수로는 도구 수를 못 센다(도구 하나가 여러 요청을 내고, 백엔드를 안 부르는 도구도
    있다).
    이 보고 자체는 요청 집계에서 뺀다(`usage_meter.SKIP_ROUTES`) — 두 번 세지 않게.
    """
    usage_meter.record_tool(
        db,
        user_id=user.id,
        tool=payload.tool,
        ok=payload.ok,
        elapsed_ms=payload.elapsed_ms,
    )
    db.commit()
    return Response(status_code=204)
