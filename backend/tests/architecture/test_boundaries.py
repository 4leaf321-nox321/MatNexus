"""경계 검사 — 사람이 지키는 규약은 AI 개발에서 반드시 뚫린다.

개발계획 §8.2. 여기서 막는 것:
  1. matcore가 DB·웹을 모른다               ← 이 설계의 전제 전부
  2. 모듈끼리 직접 import 하지 않는다        ← 65의 계층 경계 위반 재발 방지
  3. 백엔드·프론트 모듈명이 같다             ← R1
  4. workbench는 조립만 한다                 ← R5
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
APP = BACKEND / "app"
MATCORE = BACKEND / "matcore"

# --- 1. matcore 격리 -------------------------------------------------------

FORBIDDEN_IN_MATCORE = ("sqlalchemy", "fastapi", "starlette", "app", "alembic", "psycopg")


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


@pytest.mark.parametrize("path", _py_files(MATCORE), ids=lambda p: p.name)
def test_matcore_does_not_know_db_or_web(path: Path) -> None:
    """matcore는 순수 계산이다. 여기가 뚫리면 65의 슬라이스 복제로 되돌아간다."""
    leaked = _imported_roots(path) & set(FORBIDDEN_IN_MATCORE)
    assert not leaked, f"{path.relative_to(BACKEND)} 가 {sorted(leaked)} 를 import 한다"


# --- 2. 모듈 간 직접 의존 금지 ---------------------------------------------


def _backend_modules() -> list[str]:
    root = APP / "modules"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))


@pytest.mark.parametrize("module", _backend_modules())
def test_modules_do_not_import_each_other(module: str) -> None:
    """모듈 사이의 로직 공유는 shared를 거친다.

    예외는 `models` 하나다. DB 스키마는 본질적으로 서로를 참조한다 — refresh
    토큰은 사용자를 가리키고 멤버십은 부서와 사용자를 가리킨다. FK를 못 걸게
    막으면 모델이 한 파일로 뭉치거나 shared 로 밀려나 소유가 흐려진다.

    반대로 `services`·`routes` 를 직접 부르는 것은 막는다. 얽히면 경계가
    사라지는 쪽은 스키마가 아니라 로직이다.
    """
    others = set(_backend_modules()) - {module}
    for path in _py_files(APP / "modules" / module):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                if parts[:2] != ["app", "modules"] or len(parts) < 4:
                    continue
                other, member = parts[2], parts[3]
                if other in others and member != "models":
                    raise AssertionError(
                        f"{path.relative_to(BACKEND)} 가 다른 모듈의 "
                        f"'{other}.{member}' 를 직접 import 한다 "
                        f"(models 만 허용 — 로직은 shared 를 거칠 것)"
                    )


# --- 3·4. 프론트 대응과 workbench 규칙 --------------------------------------

FRONTEND_MODULES = REPO / "frontend" / "src" / "modules"

#: R2 — 백엔드가 없어도 되는 프론트 모듈. 늘릴 때는 ADR에 근거를 남긴다.
#: `workbench` 가 여기 있었다. **v1.173.0 에 서버 짝이 생겨 예외가 없어졌다** —
#: 바구니(담아 둔 것)와 진행이 서버에 살아야 「어제 하던 것을 오늘 다른 사람이」 가
#: 된다(ADR 0025). 예외 목록이 줄어드는 쪽이 맞는 방향이다.
FRONTEND_ONLY = {"profile"}

#: R3 — 아직 프론트 짝이 없는 백엔드 모듈과 그 사유.
#: 화면이 생기면 같은 이름의 프론트 모듈을 만들고 여기서 지운다. 사유를 함께
#: 적는 이유는, 목록이 길어질 때 "언제 사라질 항목인가"가 보여야 하기 때문이다.
BACKEND_ONLY = {
    # `audit` 이 여기 있었다. **v1.51.0 에 화면이 생겨 예외가 없어졌다** — 감사
    # 기록이 쌓이는데 볼 자리가 API 뿐이었고, 그건 이 저장소가 반복해서 데인
    # 패턴("만들어 두고 안 쓰는 것")이다. 예외 목록이 줄어드는 쪽이 맞는 방향이다.
    "search": "화면 없는 하부 기능",
    # 묶음은 **제 화면을 안 갖는다.** 여러 시험을 묶는 일은 재료 상세의
    # 물성 탭에서 하고, 결과도 거기서 카드로 이어진다 — 따로 화면을 두면
    # 「어디서 묶나」 가 둘이 된다.
    "grouping": "화면은 재료 상세의 물성 탭이 쓴다",
}


def _frontend_modules() -> list[str]:
    if not FRONTEND_MODULES.exists():
        return []
    return sorted(p.name for p in FRONTEND_MODULES.iterdir() if p.is_dir())


@pytest.mark.skipif(not FRONTEND_MODULES.exists(), reason="프론트 모듈 아직 없음")
def test_module_names_match() -> None:
    """R1 — 이름 하나로 코드와 화면을 동시에 찾을 수 있어야 한다.

    비교표가 65의 최대 탐색 비용으로 꼽은 항목이다: '백엔드 16 모듈과 프론트
    파일명 사이에 연결 규칙이 없어 양쪽 다 훑어야 함'.
    """
    backend = set(_backend_modules()) - set(BACKEND_ONLY)
    frontend = set(_frontend_modules()) - FRONTEND_ONLY
    assert backend == frontend, (
        f"모듈 이름 불일치 — 백엔드에만: {sorted(backend - frontend)}, "
        f"프론트에만: {sorted(frontend - backend)}. "
        f"예외로 두려면 FRONTEND_ONLY/BACKEND_ONLY 에 넣고 ADR을 남길 것"
    )


#: 워크벤치가 부를 수 있는 주소. **자기 자원만이다.**
WORKBENCH_OWN_PATHS = ("/workbench/",)


@pytest.mark.skipif(
    not (FRONTEND_MODULES / "workbench").exists(), reason="workbench 아직 없음"
)
def test_workbench_only_assembles() -> None:
    """R5 — **남의 도메인 로직을 여기서 다시 쓰지 않는다.**

    65는 워크벤치마다 약 1,200줄을 다시 썼다. 조립 셸에 로직이 쌓이면 같은 길이다.

    ## 규칙을 좁혔다 (2026-09-01)

    전에는 `shared/api` 를 부르기만 해도 걸렸다. 그때 워크벤치는 **자기 자원이
    없었다** — 담아 두는 자리가 브라우저에 있었기 때문이다.

    바구니가 서버로 오면서(ADR 0025) 워크벤치에도 제 자원이 생겼다(`/workbench/…`).
    자기 것을 부르는 것은 「남의 도메인을 다시 쓰는 것」 이 아니다. 그래서 **주소로**
    가른다 — 자기 것은 되고, 남의 도메인 주소를 직접 부르면 걸린다.

    `fetch(` 는 그대로 막는다. 토큰 갱신·오류 규약을 안 타는 요청이 생기면 그 화면만
    조용히 401 을 받는다(`shared/api/client` 의 머리말이 그 사고를 적어 두었다).
    """
    offenders = []
    for path in (FRONTEND_MODULES / "workbench").rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        if "fetch(" in text:
            offenders.append(f"{path.relative_to(REPO)}: fetch() 직접 호출")
            continue
        for line in text.splitlines():
            if "api." not in line or "/" not in line:
                continue
            # `api.get<T>('/무엇')` 처럼 주소가 든 줄만 본다.
            for quoted in re.findall(r"[`'\"](/[a-z0-9/_{}$-]+)", line):
                if not quoted.startswith(WORKBENCH_OWN_PATHS):
                    offenders.append(f"{path.relative_to(REPO)}: {quoted}")
    assert not offenders, (
        f"워크벤치가 남의 도메인 API 를 직접 부릅니다: {offenders}. "
        f"그 일은 도메인 모듈의 화면·API 에서 가져오세요 — 여기는 조립만 합니다."
    )
