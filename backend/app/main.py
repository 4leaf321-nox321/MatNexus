"""FastAPI 앱 — API와 SPA를 한 프로세스가 서빙한다.

65는 프로덕션 프론트 서빙이 없어(Dockerfile.web이 vite dev server) 출하 형태가
성립하지 않았다. 52는 backend가 frontend/dist를 직접 서빙해 배포 단위가 하나다.
후자를 따른다 — 배포 산출물이 하나면 롤백도 하나다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import version
from app.config import Settings, get_settings
from app.database import SessionLocal, engine, get_db
from app.logging_setup import setup_logging
from app.modules.accounts import routes as accounts_routes
from app.modules.audit import routes as audit_routes
from app.modules.auth import routes as auth_routes
from app.modules.catalog import routes as catalog_routes
from app.modules.equipment import routes as equipment_routes
from app.modules.fitting import routes as fitting_routes
from app.modules.formulas import routes as formulas_routes
from app.modules.formulas import services as formulas_services
from app.modules.grouping import routes as grouping_routes
from app.modules.guide import routes as guide_routes
from app.modules.materials import routes as materials_routes
from app.modules.metrology import routes as metrology_routes
from app.modules.notices import routes as notices_routes
from app.modules.notifications import routes as notifications_routes
from app.modules.ontology import routes as ontology_routes
from app.modules.pipelines import routes as pipelines_routes
from app.modules.processing import routes as processing_routes
from app.modules.search import routes as search_routes
from app.modules.server import routes as server_routes
from app.modules.statistics import routes as statistics_routes
from app.modules.tests import formats as tests_formats
from app.modules.tests import routes as tests_routes
from app.modules.trash import routes as trash_routes
from app.modules.units import routes as units_routes
from app.modules.viscoelastic import (  # noqa: F401  (파싱 훅을 등록시킨다)
    autoregister as _viscoelastic_autoregister,
)
from app.modules.viscoelastic import routes as viscoelastic_routes
from app.modules.voc import routes as voc_routes
from app.modules.vocabulary import routes as vocabulary_routes
from app.modules.workbench import routes as workbench_routes
from app.modules.workspaces import routes as workspaces_routes
from app.schema_version import warn_if_behind
from app.shared.access_log import AccessLogMiddleware
from app.shared.errors import NotFound, register_error_handlers
from app.shared.request_context import RequestIdMiddleware
from matcore import extensions
from matcore.export import dyna as _dyna  # noqa: F401  (LS-DYNA 렌더러를 등록시킨다)

logger = logging.getLogger(__name__)


API_PREFIX = "/api"


def _api_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health", tags=["system"])
    def health(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
        """살아 있나 — **DB 까지 찔러 본다.**

        실측(2026-09-10, 두 번): 사내망에서 DB 연결이 잠깐 끊긴 뒤 백엔드가 요청을
        받지 않는 채로 남았다. DB 는 멀쩡했고 재기동하면 바로 돌아왔다. 그동안 이
        주소는 DB 를 안 보고 「ok」 라고 답했으므로, 감시를 붙였어도 못 잡았을 것이다
        — 죽은 서버가 살아 있다고 대답하면 감시는 있으나 마나다.

        그래서 `SELECT 1` 을 한 번 날린다. 못 하면 **503** 과 이유를 낸다 — 서비스
        관리자(NSSM·스케줄러)가 그것을 보고 재기동한다. 연결이 매달리는 것은 엔진의
        `connect_timeout` 이 끊는다(`database.py`) — health 자체가 매달리면 감시도
        같이 매달린다.

        **버전을 함께 준다.** 원격에서 "지금 서버에 뭐가 깔렸나" 를 물을 수 있는
        유일한 자리다. 배포 뒤 확인도, 점검 스크립트도 여기를 본다.
        """
        body = {"status": "ok", "version": version.current(), "database": "ok"}
        try:
            db.execute(text("SELECT 1"))
        except Exception as failed:  # 무엇이 됐든 「못 찔렀다」 가 답이다
            logger.warning("health: DB 를 찌르지 못했다 — %s", failed)
            response.status_code = 503
            body["status"] = "degraded"
            body["database"] = f"unreachable: {type(failed).__name__}"
        return body

    # 모듈 라우터는 여기서만 모은다. 모듈이 서로를 import 하지 않게 하려면
    # 조립 지점이 하나여야 한다 (tests/architecture 가 검사).
    router.include_router(auth_routes.router)
    router.include_router(accounts_routes.router)
    router.include_router(workspaces_routes.router)
    router.include_router(notifications_routes.router)
    router.include_router(notices_routes.router)
    router.include_router(voc_routes.router)
    router.include_router(catalog_routes.router)
    router.include_router(metrology_routes.router)
    router.include_router(materials_routes.router)
    router.include_router(materials_routes.samples_router)
    router.include_router(materials_routes.specimens_router)
    router.include_router(tests_routes.router)
    router.include_router(tests_routes.runs_router)
    router.include_router(tests_routes.maintenance_router)
    router.include_router(tests_formats.router)
    router.include_router(processing_routes.router)
    router.include_router(viscoelastic_routes.router)
    router.include_router(workbench_routes.router)
    router.include_router(statistics_routes.router)
    router.include_router(equipment_routes.router)
    router.include_router(fitting_routes.router)
    router.include_router(formulas_routes.router)
    router.include_router(grouping_routes.router)
    router.include_router(units_routes.router)
    router.include_router(ontology_routes.router)
    router.include_router(search_routes.router)
    router.include_router(vocabulary_routes.router)
    router.include_router(audit_routes.router)
    router.include_router(trash_routes.router)
    router.include_router(pipelines_routes.router)
    router.include_router(guide_routes.router)
    router.include_router(server_routes.router)

    return router


def _mount_spa(app: FastAPI, settings: Settings) -> None:
    dist = settings.frontend_dist
    index = dist / "index.html"
    if not index.exists():
        logger.info("frontend dist 없음 (%s) — API만 서빙합니다.", dist)
        return

    # 해시가 붙은 자산은 오래 캐시해도 안전하다.
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # response_model=None — 이 경로는 스키마에 나오지 않으므로 응답 모델이 필요
    # 없다. 반환 애노테이션에 Union을 쓰면 FastAPI가 모델을 만들려다 기동에
    # 실패하므로, 여기는 앞으로도 단일 Response 타입으로 둔다.
    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def spa(full_path: str) -> FileResponse:
        # /api 아래는 위에서 이미 매칭됐어야 한다. 여기 닿았다면 없는 엔드포인트다.
        # index.html을 돌려주면 프론트가 200 HTML을 JSON으로 파싱하려다 실패해
        # 원인이 흐려지므로, 명시적으로 404를 준다. 응답 본문은 직접 만들지 않고
        # 오류 핸들러에 맡긴다 — 그래야 request_id와 로그가 함께 남는다.
        if full_path.startswith("api/"):
            raise NotFound(
                "MNX-COMMON-0404",
                "존재하지 않는 엔드포인트입니다.",
                details={"path": f"/{full_path}"},
            )
        # index.html은 캐시하지 않는다. 배포 후 사용자가 옛 index를 들고 있으면
        # 사라진 청크를 요청하게 된다.
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    logger.info("SPA 서빙: %s", dist)


def _guard_production_secrets(settings: Settings) -> None:
    """운영에서 기본 비밀키로 뜨는 것을 막는다.

    기본값이 그대로 배포되면 누구나 access 토큰을 위조할 수 있다. 경고 로그는
    아무도 읽지 않으므로 기동 자체를 거부한다 — install.ps1 이 난수를 넣어 준다.
    """
    if settings.app_env != "production":
        return
    if settings.jwt_secret == Settings.model_fields["jwt_secret"].default:
        raise RuntimeError(
            "JWT_SECRET 이 기본값입니다. .env 에 난수 값을 넣고 다시 시작하세요."
        )


def _sync_formulas() -> None:
    try:
        with SessionLocal() as db:
            keys = formulas_services.sync(db)
    except Exception as exc:  # 기동을 막지 않는다
        logger.warning("계산식을 레지스트리에 올리지 못했습니다 — %s", exc)
        return
    if keys:
        logger.info("계산식 %d개를 올렸습니다: %s", len(keys), ", ".join(keys))


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)
    _guard_production_secrets(settings)

    # **확장을 먼저 읽는다.** 라우트가 뜨기 전에 레지스트리가 차 있어야
    # `/fitting/blocks`·`/fitting/formats` 가 확장의 물성을 낸다.
    #
    # 하나가 터져도 서버는 뜬다 — 남의 확장 때문에 내 물성을 못 쓰면 안 되고,
    # 그 사실이 "서버가 안 켜진다" 로만 보이면 더 나쁘다.
    for failed in extensions.failures(extensions.load(settings.extensions_dir)):
        logger.error(
            "확장 '%s' 를 읽지 못했습니다 — 그 물성은 목록에 안 뜹니다.\n%s",
            failed.name,
            failed.error,
        )

    app = FastAPI(
        title="MatNexus API",
        version=version.current(),
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    # 순서가 중요하다. add_middleware 는 **나중에 더한 것이 바깥**이므로 아래
    # 두 줄은 RequestId(바깥) → AccessLog(안쪽) 이 된다. 접근 로그가 요청 id 를
    # 읽으려면 그 id 가 먼저 설정돼 있어야 한다.
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # 요청 처리 밖에서 DB 를 쓰는 곳(접근 로그)이 참조한다. 테스트는 이 값을
    # 자기 DB 로 바꿔 끼운다.
    app.state.session_factory = SessionLocal
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_error_handlers(app)
    app.include_router(_api_router())

    # 접근 로그는 RequestIdMiddleware가 남긴다 — 요청 id와 최종 상태 코드를
    # 동시에 아는 유일한 지점이라, 두 곳에서 찍으면 id가 '-' 인 줄이 섞인다.

    # SPA catch-all은 반드시 API 라우터 뒤에 등록한다.
    _mount_spa(app, settings)

    # **DB 가 코드보다 뒤처져 있으면 여기서 말한다.** 안 그러면 사람은 화면의
    # 500 으로 먼저 만나는데, 거기엔 원인이 안 적힌다. 운영은 배포가 알아서
    # `alembic upgrade head` 를 돌리므로 이건 개발 서버를 위한 안내다.
    warn_if_behind(engine)

    # **표에 적힌 계산식을 레지스트리에 올린다** (ADR 0030). 확장 다음이다 — 확장이
    # 같은 키를 내장으로 등록했다면 식이 그것을 덮지 못하게 `formula.` 접두어가
    # 가른다. DB 가 안 닿거나 표가 아직 없으면(마이그레이션 전) 경고만 남기고 뜬다 —
    # 식 없이 뜨는 서버가 안 뜨는 서버보다 낫다.
    _sync_formulas()

    logger.info("MatNexus 기동 (env=%s)", settings.app_env)
    return app


app = create_app()
