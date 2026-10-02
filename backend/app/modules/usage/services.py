"""사용 현황 집계 — **실제로 얼마나 잘 쓰고 있나**(2026-10-02).

한 화면에 답할 물음들:

    누가 쓰나        기간 안에 쓴 사람 · 하루 평균 · 화면 / MCP(AI) / 둘 다
    얼마나 쓰나      요청(조회 · 쓰기) · 날마다 · 기능마다 · 실패
    AI 로 쓰나       MCP 도구 호출 · 도구별 · 사람별 · 실패 · 걸린 시간 · 토큰
    무엇을 보나      많이 본 재료 · 문헌 재료 · 시험 · 카드 · 가이드
    들어오나         가입 · 승인 대기 · 로그인
    남기나           기간 안에 만든 재료 · 시료 · 시편 · 시험 · 카드 · 의뢰

요청 · 조회 · 도구 수는 계량기가 쌓기 시작한 날(`measured_since`)부터다. 가입 · 로그인 ·
만든 것 · AI 경유 기록은 원래 표에서 세므로 그 전 기간도 나온다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.audit.models import AccessLog, AuditEntry
from app.modules.auth.models import PersonalAccessToken
from app.modules.catalog.models import CatalogMaterial
from app.modules.commissions.models import Commission
from app.modules.fitting.models import PropertyCard
from app.modules.guide.models import GuideDocument
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.models import TestRun
from app.modules.usage.models import McpToolDaily, UsageDaily, UsageViewDaily
from app.modules.usage.schemas import (
    ActiveDayOut,
    ActivityOut,
    AreaOut,
    ContentOut,
    DayCountOut,
    McpOut,
    McpUserOut,
    PeriodOut,
    RequestDayOut,
    RequestsOut,
    SignupOut,
    TokensOut,
    ToolOut,
    UsagePersonOut,
    UsageSummaryOut,
    UsersOut,
    ViewedOut,
    ViewsOut,
)
from app.modules.workspaces.models import Workspace
from app.shared import usage_meter

#: 라우트의 첫 조각 → 사람이 읽는 기능 이름. 없는 조각은 그대로 보인다(감추지 않는다).
AREA_LABELS: dict[str, str] = {
    "materials": "재료",
    "samples": "시료",
    "specimens": "시편",
    "test-runs": "시험",
    "test-types": "시험 종류",
    "formats": "장비 파일 정의",
    "processing": "처리",
    "groups": "묶음 분석",
    "statistics": "물성 분석",
    "viscoelastic": "점탄성",
    "fitting": "카드 · 덱",
    "catalog": "문헌 물성",
    "search": "검색",
    "guide": "가이드",
    "graph": "지식 그래프",
    "ontology": "온톨로지",
    "vocabularies": "기준정보",
    "units": "단위",
    "formulas": "계산식",
    "commissions": "측정 의뢰",
    "workbench": "워크벤치",
    "equipment": "장비",
    "metrology": "측정 범위",
    "pipelines": "장비 연동",
    "notices": "공지",
    "notifications": "알림",
    "voc": "VOC",
    "audit": "변경 이력",
    "ownership": "권한",
    "trash": "휴지통",
    "accounts": "계정",
    "auth": "로그인 · 토큰",
    "workspaces": "부서",
    "server": "서버",
    "maintenance": "유지보수",
    "usage": "사용 현황",
}

TOP = 10
PEOPLE = 30


def area_of(route: str) -> str:
    """`/materials/{material_id}` → `materials`."""
    parts = [one for one in route.split("/") if one]
    return parts[0] if parts else route


def _local_start(day: date) -> datetime:
    """그 날 0시(서버 현지). `created_at` 은 시각대가 붙은 값이라 현지 0시로 견준다."""
    return datetime.combine(day, time.min).astimezone()


def _local_day(at: datetime) -> date:
    return at.astimezone().date()


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _names(
    db: Session, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None, str | None]]:
    """사용자 id → (이름, 이메일, 대표 부서). 지운 계정도 이름은 남는다(행은 남아 있다)."""
    wanted = set(ids)
    if not wanted:
        return {}
    rows = db.execute(
        select(User.id, User.display_name, User.email, Workspace.name)
        .outerjoin(Workspace, Workspace.id == User.home_workspace_id)
        .where(User.id.in_(wanted))
    ).all()
    return {row[0]: (row[1] or row[2], row[2], row[3]) for row in rows}


def summary(db: Session, *, days: int) -> UsageSummaryOut:
    end = usage_meter.today()
    start = end - timedelta(days=days - 1)
    since = _local_start(start)
    calendar = _days(start, end)

    measured = db.scalar(select(func.min(UsageDaily.day)))
    measured_tools = db.scalar(select(func.min(McpToolDaily.day)))
    measured_since = min((one for one in (measured, measured_tools) if one), default=None)

    requests_rows = db.execute(
        select(
            UsageDaily.day,
            UsageDaily.user_id,
            UsageDaily.client,
            UsageDaily.method,
            UsageDaily.route,
            UsageDaily.requests,
            UsageDaily.errors,
        ).where(UsageDaily.day >= start, UsageDaily.day <= end)
    ).all()
    tool_rows = db.execute(
        select(
            McpToolDaily.day,
            McpToolDaily.user_id,
            McpToolDaily.tool,
            McpToolDaily.calls,
            McpToolDaily.failures,
            McpToolDaily.elapsed_ms,
        ).where(McpToolDaily.day >= start, McpToolDaily.day <= end)
    ).all()
    view_rows = db.execute(
        select(
            UsageViewDaily.day,
            UsageViewDaily.kind,
            UsageViewDaily.entity_id,
            UsageViewDaily.user_id,
            UsageViewDaily.client,
            UsageViewDaily.views,
        ).where(UsageViewDaily.day >= start, UsageViewDaily.day <= end)
    ).all()

    activity = _activity(db, calendar, requests_rows, tool_rows, since)
    return UsageSummaryOut(
        period=PeriodOut(start=start, end=end, days=days),
        measured_since=measured_since,
        users=_users(db, calendar, since),
        activity=activity,
        requests=_requests(calendar, requests_rows, tool_rows),
        mcp=_mcp(db, tool_rows, since),
        views=_views(db, view_rows),
        content=_content(db, since),
        people=_people(db, requests_rows, tool_rows, view_rows),
    )


def _users(db: Session, calendar: list[date], since: datetime) -> UsersOut:
    live = User.deleted_at.is_(None)
    active = db.scalar(
        select(func.count()).select_from(User).where(live, User.status == "active")
    )
    pending = db.scalar(
        select(func.count()).select_from(User).where(live, User.status == "pending")
    )
    joined = db.execute(
        select(User.display_name, User.email, User.status, User.created_at, Workspace.name)
        .outerjoin(
            Workspace,
            Workspace.id == func.coalesce(User.home_workspace_id, User.requested_workspace_id),
        )
        .where(live, User.created_at >= since)
        .order_by(User.created_at.desc())
    ).all()
    per_day: dict[date, int] = defaultdict(int)
    for row in joined:
        per_day[_local_day(row.created_at)] += 1
    return UsersOut(
        active_accounts=active or 0,
        pending=pending or 0,
        signups=len(joined),
        signups_by_day=[DayCountOut(day=one, count=per_day.get(one, 0)) for one in calendar],
        recent_signups=[
            SignupOut(
                name=row.display_name or row.email,
                email=row.email,
                workspace=row.name,
                status=row.status,
                created_at=row.created_at,
            )
            for row in joined[:15]
        ],
    )


def _activity(
    db: Session,
    calendar: list[date],
    requests_rows: Sequence[Any],
    tool_rows: Sequence[Any],
    since: datetime,
) -> ActivityOut:
    web: dict[date, set[uuid.UUID]] = defaultdict(set)
    mcp: dict[date, set[uuid.UUID]] = defaultdict(set)
    for row in requests_rows:
        (mcp if row.client == "mcp" else web)[row.day].add(row.user_id)
    for row in tool_rows:
        mcp[row.day].add(row.user_id)
    web_all = set().union(*web.values()) if web else set()
    mcp_all = set().union(*mcp.values()) if mcp else set()
    by_day = [
        ActiveDayOut(
            day=one,
            web=len(web.get(one, set())),
            mcp=len(mcp.get(one, set())),
            any=len(web.get(one, set()) | mcp.get(one, set())),
        )
        for one in calendar
    ]
    logins = db.execute(
        select(AccessLog.user_id).where(
            AccessLog.action == "LOGIN",
            AccessLog.status_code == 200,
            AccessLog.created_at >= since,
        )
    ).all()
    return ActivityOut(
        any_users=len(web_all | mcp_all),
        web_users=len(web_all),
        mcp_users=len(mcp_all),
        both_users=len(web_all & mcp_all),
        average_daily=round(sum(one.any for one in by_day) / max(len(by_day), 1), 2),
        by_day=by_day,
        logins=len(logins),
        login_users=len({row.user_id for row in logins if row.user_id}),
    )


def _requests(
    calendar: list[date], requests_rows: Sequence[Any], tool_rows: Sequence[Any]
) -> RequestsOut:
    by_client: dict[str, int] = defaultdict(int)
    web_day: dict[date, int] = defaultdict(int)
    mcp_day: dict[date, int] = defaultdict(int)
    tools_day: dict[date, int] = defaultdict(int)
    areas: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    reads = writes = errors = 0
    for row in requests_rows:
        by_client[row.client] += row.requests
        (mcp_day if row.client == "mcp" else web_day)[row.day] += row.requests
        write = row.method in usage_meter.WRITE_METHODS
        if write:
            writes += row.requests
        else:
            reads += row.requests
        errors += row.errors
        area = areas[area_of(row.route)]
        area["writes" if write else "reads"] += row.requests
        area["errors"] += row.errors
        if row.client == "mcp":
            area["mcp"] += row.requests
    for row in tool_rows:
        tools_day[row.day] += row.calls
    ordered = sorted(areas.items(), key=lambda pair: -(pair[1]["reads"] + pair[1]["writes"]))
    return RequestsOut(
        total=reads + writes,
        reads=reads,
        writes=writes,
        errors=errors,
        by_client=dict(by_client),
        by_day=[
            RequestDayOut(
                day=one,
                web=web_day.get(one, 0),
                mcp=mcp_day.get(one, 0),
                mcp_tools=tools_day.get(one, 0),
            )
            for one in calendar
        ],
        by_area=[
            AreaOut(
                area=key,
                label=AREA_LABELS.get(key, key),
                reads=counts["reads"],
                writes=counts["writes"],
                mcp=counts["mcp"],
                errors=counts["errors"],
            )
            for key, counts in ordered
        ],
    )


def _mcp(db: Session, tool_rows: Sequence[Any], since: datetime) -> McpOut:
    tools: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "failures": 0, "ms": 0, "users": set()}
    )
    people: dict[uuid.UUID, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "tools": set(), "last": date.min}
    )
    calls = failures = elapsed = 0
    for row in tool_rows:
        calls += row.calls
        failures += row.failures
        elapsed += row.elapsed_ms
        one = tools[row.tool]
        one["calls"] += row.calls
        one["failures"] += row.failures
        one["ms"] += row.elapsed_ms
        one["users"].add(row.user_id)
        person = people[row.user_id]
        person["calls"] += row.calls
        person["tools"].add(row.tool)
        person["last"] = max(person["last"], row.day)
    names = _names(db, people)
    now = datetime.now().astimezone()
    usable = (
        PersonalAccessToken.revoked_at.is_(None),
        (PersonalAccessToken.expires_at.is_(None)) | (PersonalAccessToken.expires_at > now),
    )
    active_tokens = db.scalar(
        select(func.count()).select_from(PersonalAccessToken).where(*usable)
    )
    token_users = db.scalar(
        select(func.count(func.distinct(PersonalAccessToken.user_id))).where(*usable)
    )
    used = db.scalar(
        select(func.count())
        .select_from(PersonalAccessToken)
        .where(PersonalAccessToken.last_used_at >= since)
    )
    recorded = db.scalar(
        select(func.count())
        .select_from(AuditEntry)
        .where(AuditEntry.client == "mcp", AuditEntry.created_at >= since)
    )
    return McpOut(
        calls=calls,
        failures=failures,
        users=len(people),
        average_ms=round(elapsed / calls, 1) if calls else 0.0,
        tools_used=len(tools),
        writes_recorded=recorded or 0,
        by_tool=[
            ToolOut(
                tool=name,
                calls=one["calls"],
                failures=one["failures"],
                users=len(one["users"]),
                average_ms=round(one["ms"] / one["calls"], 1) if one["calls"] else 0.0,
            )
            for name, one in sorted(tools.items(), key=lambda pair: -pair[1]["calls"])
        ],
        by_user=[
            McpUserOut(
                name=names.get(user_id, ("지운 계정", None, None))[0],
                calls=one["calls"],
                tools=len(one["tools"]),
                last_day=one["last"],
            )
            for user_id, one in sorted(people.items(), key=lambda pair: -pair[1]["calls"])
        ][:PEOPLE],
        tokens=TokensOut(
            active=active_tokens or 0, users=token_users or 0, used_in_period=used or 0
        ),
    )


def _views(db: Session, view_rows: Sequence[Any]) -> ViewsOut:
    counted: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {"views": 0, "mcp": 0, "users": set()})
    )
    total = 0
    for row in view_rows:
        total += row.views
        one = counted[row.kind][row.entity_id]
        one["views"] += row.views
        one["users"].add(row.user_id)
        if row.client == "mcp":
            one["mcp"] += row.views

    def top(kind: str) -> list[tuple[str, dict[str, Any]]]:
        return sorted(counted[kind].items(), key=lambda pair: -pair[1]["views"])[:TOP]

    def labelled(kind: str, labels: dict[str, str]) -> list[ViewedOut]:
        return [
            ViewedOut(
                id=entity,
                label=labels.get(entity, "(지웠거나 없는 항목)"),
                views=one["views"],
                viewers=len(one["users"]),
                mcp_views=one["mcp"],
            )
            for entity, one in top(kind)
        ]

    def uuids(kind: str) -> list[uuid.UUID]:
        out = []
        for entity, _ in top(kind):
            try:
                out.append(uuid.UUID(entity))
            except ValueError:
                continue
        return out

    materials = {
        str(row[0]): f"{row[1]} · {row[2]}"
        for row in db.execute(
            select(Material.id, Material.code, Material.record_name).where(
                Material.id.in_(uuids("material"))
            )
        ).all()
    }
    catalog = {
        str(row[0]): row[1]
        for row in db.execute(
            select(CatalogMaterial.id, CatalogMaterial.name).where(
                CatalogMaterial.id.in_(uuids("catalog_material"))
            )
        ).all()
    }
    runs = {
        str(row[0]): f"{row[1]} · {row[2]}"
        for row in db.execute(
            select(TestRun.id, TestRun.code, TestRun.record_name).where(
                TestRun.id.in_(uuids("test_run"))
            )
        ).all()
    }
    cards = {
        str(row[0]): row[1]
        for row in db.execute(
            select(PropertyCard.id, PropertyCard.label).where(
                PropertyCard.id.in_(uuids("card"))
            )
        ).all()
    }
    guides = {
        row[0]: row[1]
        for row in db.execute(
            select(GuideDocument.key, GuideDocument.title).where(
                GuideDocument.key.in_([entity for entity, _ in top("guide")])
            )
        ).all()
    }
    return ViewsOut(
        total=total,
        materials=labelled("material", materials),
        catalog_materials=labelled("catalog_material", catalog),
        test_runs=labelled("test_run", runs),
        cards=labelled("card", cards),
        guides=labelled("guide", guides),
    )


def _content(db: Session, since: datetime) -> list[ContentOut]:
    def created(column: Any) -> int:
        return db.scalar(select(func.count()).where(column >= since)) or 0

    return [
        ContentOut(key="materials", label="재료", created=created(Material.created_at)),
        ContentOut(key="samples", label="시료", created=created(Sample.created_at)),
        ContentOut(key="specimens", label="시편", created=created(Specimen.created_at)),
        ContentOut(key="test_runs", label="시험", created=created(TestRun.created_at)),
        ContentOut(key="cards", label="물성 카드", created=created(PropertyCard.created_at)),
        ContentOut(
            key="cards_published",
            label="확정한 카드",
            created=created(PropertyCard.published_at),
        ),
        ContentOut(
            key="commissions", label="측정 의뢰", created=created(Commission.created_at)
        ),
    ]


def _people(
    db: Session,
    requests_rows: Sequence[Any],
    tool_rows: Sequence[Any],
    view_rows: Sequence[Any],
) -> list[UsagePersonOut]:
    people: dict[uuid.UUID, dict[str, Any]] = defaultdict(
        lambda: {"days": set(), "web": 0, "writes": 0, "mcp": 0, "views": 0}
    )
    for row in requests_rows:
        one = people[row.user_id]
        one["days"].add(row.day)
        if row.client != "mcp":
            one["web"] += row.requests
        if row.method in usage_meter.WRITE_METHODS:
            one["writes"] += row.requests
    for row in tool_rows:
        one = people[row.user_id]
        one["days"].add(row.day)
        one["mcp"] += row.calls
    for row in view_rows:
        people[row.user_id]["views"] += row.views
    ranked = sorted(
        (pair for pair in people.items() if pair[1]["days"]),
        key=lambda pair: (-len(pair[1]["days"]), -(pair[1]["web"] + pair[1]["mcp"])),
    )[:PEOPLE]
    names = _names(db, (user_id for user_id, _ in ranked))
    return [
        UsagePersonOut(
            user_id=user_id,
            name=names.get(user_id, ("지운 계정", None, None))[0],
            email=names.get(user_id, ("", None, None))[1],
            workspace=names.get(user_id, ("", None, None))[2],
            last_day=max(one["days"]),
            active_days=len(one["days"]),
            web_requests=one["web"],
            writes=one["writes"],
            mcp_calls=one["mcp"],
            views=one["views"],
        )
        for user_id, one in ranked
    ]
