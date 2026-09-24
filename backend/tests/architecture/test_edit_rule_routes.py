"""자료를 고치는 길은 **전부 한 판정을 지난다** — ADR 0035 D4.

## 왜 이 시험이 있나

개편 전에는 같은 사람·같은 재료에서 판정이 다섯 갈래였다(볼 수 있으면 고친다 · 부서
멤버 · 부서 관리자 · 등록자 · 시스템 관리자). 모듈마다 제 판정을 적었기 때문이다. 그
결과 재료 필드는 고쳐지는데 문헌 연결은 막혔고, 자기가 만든 처리 결과를 자기가 못
지웠다 — 그리고 누구도 그 차이를 설명할 수 없었다.

규칙을 한 곳(`shared/permissions`)에 모았어도, 새 엔드포인트가 그것을 안 부르면 다시
갈라진다. 실제로 개편 중에 `shared/graph` 가 레시피 가시 규칙을 제 손으로 베껴 두고
있던 것이 드러났다. 그래서 여기서 막는다.

## 무엇을 보나

자료 모듈의 **쓰기 라우트**(POST·PUT·PATCH·DELETE)마다, 몸통이 판정 함수를 부르거나
`EXEMPT` 에 **사유와 함께** 적혀 있어야 한다. 새 쓰기 길을 만들면 이 시험이 멈춰 세우고,
사람은 「이것은 고치는 일인가」 를 한 번 묻게 된다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app" / "modules"

#: 자료를 고치는 모듈의 라우트 파일. 정의·장비·워크벤치·휴지통은 3단계에서 더했다 —
#: 장비 파일 정의(`formats.py`)는 2단계 동안 **이 목록에 없어서** 아무도 안 봤다.
FILES = {
    "materials": APP / "materials" / "routes.py",
    "tests": APP / "tests" / "routes.py",
    "formats": APP / "tests" / "formats.py",
    "processing": APP / "processing" / "routes.py",
    "fitting": APP / "fitting" / "routes.py",
    "grouping": APP / "grouping" / "routes.py",
    "viscoelastic": APP / "viscoelastic" / "routes.py",
    "catalog": APP / "catalog" / "routes.py",
    "ownership": APP / "ownership" / "routes.py",
    "equipment": APP / "equipment" / "routes.py",
    "workbench": APP / "workbench" / "routes.py",
    "trash": APP / "trash" / "routes.py",
}

#: 판정을 지났다는 표시. 앞의 넷이 판정 자체(`shared/permissions` · 시스템 관리자 문)이고,
#: 나머지는 그것을 부르는 모듈 안의 얇은 손잡이다(`test_손잡이도_판정을_부른다` 가 본다).
MARKERS = (
    "require_edit(",
    "require_hand_over(",
    "require_steward(",
    "Depends(require_system_admin)",
    "editor.allows(",
    "_require_publisher(",
    "_editable(",
    "_require_result_removal(",
    "require_contributor(",
    "_require_edit(",
    "_editable_run(",
    # 일괄 쓰기가 줄마다 묻는 판정 — `editor.allows` 에 「남의 자료를 고쳤다」 는 흔적을 더한
    # 것이다(2026-09-25). 시편·시험 일괄 수정, 시험 일괄 삭제, 처리 배치의 채택이 이것을 쓴다.
    "admits(",
)

#: 손잡이 → 그 안에 있어야 하는 판정.
HELPERS = {
    ("fitting", "_require_publisher"): "require_steward(",
    ("grouping", "_editable"): "require_edit(",
    ("processing", "_require_result_removal"): "require_edit(",
    ("equipment", "_require_edit"): "require_edit(",
    ("workbench", "_editable_run"): "require_edit(",
}

_만들기 = "만들기 — 누구나 한다. 만든 사람이 그 자료의 등록자다(ADR 0035)"
_읽기 = "쓰지 않는다 — 미리보기·계산·내보내기"
_정의 = _만들기 + " — 정의도 누구나 만든다(3단계). 등록 부서는 내 소속"

#: (모듈, 함수) → 판정이 없는 까닭.
EXEMPT: dict[tuple[str, str], str] = {
    ("materials", "preview_name"): _읽기,
    ("materials", "create_material"): _만들기,
    ("materials", "create_bulk"): _만들기 + " — 있는 재료 아래에 붙이는 것도 만들기다",
    ("materials", "create_sample"): _만들기,
    ("materials", "create_specimen"): _만들기,
    ("tests", "detect_test_type"): _읽기,
    ("tests", "create_test_type"): _정의,
    ("tests", "preview_summary_import"): _읽기,
    ("tests", "import_summaries"): _만들기 + " — 고른 시료 아래에 시편·시험을 붙인다",
    ("tests", "upload_test_run"): _만들기,
    ("processing", "preview"): _읽기,
    ("processing", "create_result"): _만들기 + " — 결과는 불변이다. 채택은 따로 막는다",
    ("processing", "create_recipe"): _정의,
    ("fitting", "preview"): _읽기,
    ("fitting", "create_card"): _만들기 + " — 카드는 초안으로 생긴다",
    ("fitting", "create_declared_card"): _만들기,
    ("fitting", "create_viscoelastic_card"): _만들기,
    ("fitting", "create_rate_card"): _만들기,
    ("fitting", "create_card_from_group"): _만들기,
    ("fitting", "create_lve_card"): _만들기,
    ("fitting", "derive_unit_system"): _읽기,
    ("fitting", "create_export_profile"): _정의,
    ("fitting", "scan_deck"): _읽기,
    ("fitting", "preview_deck"): _읽기,
    ("fitting", "export_bundle"): _읽기,
    ("fitting", "check_card_deck"): _읽기,
    ("fitting", "build_bom_deck"): _읽기,
    ("grouping", "create_group"): _만들기,
    ("viscoelastic", "create_master_curve"): _만들기 + " — 시험에서 나온 파생 자료다",
    ("viscoelastic", "import_master_curve"): _만들기 + " — 시험에서 나온 파생 자료다",
    ("viscoelastic", "create_prony_fit"): _만들기 + " — 파생 자료다. 대표 고르기는 막는다",
    ("catalog", "add_property_alias"): _만들기 + " — 별칭 하나. 지우기는 넣은 사람·관리자",
    ("catalog", "deck_match"): _읽기,
    ("catalog", "deck_build"): _읽기,
    ("catalog", "create_catalog_material"): _만들기 + " — 문헌 재료",
    ("catalog", "create_catalog_value"): _만들기 + " — 문헌 값",
    (
        "catalog",
        "delete_catalog_material",
    ): "문헌 — `contribute.require_contributor` 가 안에서 본다",
    (
        "catalog",
        "delete_catalog_value",
    ): "문헌 — `contribute.require_contributor` 가 안에서 본다",
    ("formats", "preview"): _읽기,
    ("formats", "try_profile"): _읽기,
    ("formats", "check_profile"): _읽기,
    ("formats", "create_profile"): _정의,
    ("equipment", "create_unit"): _만들기 + " — 장비도 누구나 올린다(3단계)",
    ("equipment", "bulk_create"): _만들기 + " — 붙여넣기 일괄 등록",
    ("workbench", "create_run"): _만들기 + " — 작업은 내 소속 부서의 것으로 선다",
    ("workbench", "bom_alias_lookup"): _읽기,
    (
        "workbench",
        "bom_alias_put",
    ): "BOM 매칭 기억 — 전사 공용 메모다. 마지막 판단이 이긴다(자료가 아니다)",
    (
        "trash",
        "restore",
    ): "되살리기 — `services._require_restore` 가 안에서 본다(아래 시험이 확인한다)",
}

WRITE = {"post", "put", "patch", "delete"}


def _writes(path: Path) -> dict[str, str]:
    """쓰기 라우트 → 그 함수의 소스."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and deco.func.attr in WRITE
            ):
                found[node.name] = ast.get_source_segment(source, node) or ""
    return found


def _functions(path: Path) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }


@pytest.mark.parametrize("module", sorted(FILES))
def test_쓰기_라우트는_판정을_지나거나_사유가_있다(module: str) -> None:
    missing = [
        name
        for name, body in _writes(FILES[module]).items()
        if not any(mark in body for mark in MARKERS) and (module, name) not in EXEMPT
    ]
    assert not missing, (
        f"{module}: 판정도 사유도 없는 쓰기 라우트 {missing}\n"
        "자료를 고치는 길이면 `permissions.require_edit` 를 부르고, 아니면 "
        "`EXEMPT` 에 왜 아닌지 적어라(ADR 0035)."
    )


def test_사유_목록이_늙지_않았다() -> None:
    """지운 라우트가 사유 목록에 남아 있으면 그 사유는 거짓말이다. 판정을 부르게 된
    라우트가 남아 있어도 그렇다 — 둘 중 하나만 참이다."""
    for (module, name), _reason in EXEMPT.items():
        writes = _writes(FILES[module])
        assert name in writes, f"EXEMPT 에 없는 라우트가 적혀 있다: {module}.{name}"
        assert not any(mark in writes[name] for mark in MARKERS), (
            f"{module}.{name} 은 이제 판정을 부른다 — EXEMPT 에서 지워라"
        )


def test_되살리기도_판정을_부른다() -> None:
    """휴지통의 되살리기는 판정이 서비스 안에 있다 — 거기서 빠지면 아무나 되살린다."""
    services = _functions(APP / "trash" / "services.py")
    assert "_require_restore(" in services.get("restore", ""), (
        "trash.services.restore 가 `_require_restore` 를 안 부른다"
    )
    assert "require_edit(" in services.get("_require_restore", ""), (
        "trash.services._require_restore 가 `permissions.require_edit` 를 안 부른다"
    )


@pytest.mark.parametrize(("module", "helper"), sorted(HELPERS))
def test_손잡이도_판정을_부른다(module: str, helper: str) -> None:
    body = _functions(FILES[module]).get(helper, "")
    assert HELPERS[(module, helper)] in body, (
        f"{module}.{helper} 가 `{HELPERS[(module, helper)]}` 를 안 부른다 — 손잡이가 "
        "제 판정을 적기 시작하면 규칙이 다시 둘이 된다."
    )
