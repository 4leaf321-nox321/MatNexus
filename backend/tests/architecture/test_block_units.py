"""블록이 드는 단위는 전부 단위계가 안다 — **확장 블록까지.**

실측(2026-09-05): 속도 의존(`1/s`)·선형탄성구간(`Hz`) 블록이 기본 계(mm·N·tonne)로
내려받기가 전부 422 였다 — 블록은 새 단위를 들고 왔는데 단위계 표(`systems.DECLARED`
와 두 계의 기호)는 몰랐다. `systems.py` 는 "시험이 블록 선언과 대조한다" 고 적어 뒀는데
그 시험이 없었다(2026-09-12). 여기가 그 시험이다.

확장(`backend/extensions/**`)이 등록한 블록도 함께 본다 — 새 물성은 확장 폴더 하나로
끝나야 하고, 그 블록이 새 단위를 들면 **중심 코드의 단위계 표를 함께 고쳐야 한다** —
그것을 여기서 알려 준다.
"""

from __future__ import annotations

from pathlib import Path

from matcore import cards, extensions
from matcore.export import systems

BACKEND = Path(__file__).resolve().parents[2]


def _all_units() -> dict[str, set[str]]:
    """블록 키 → 그 블록이 드는 SI 단위(값·행 열 모두)."""
    cards.load_builtin()
    extensions.load(BACKEND / "extensions")
    found: dict[str, set[str]] = {}
    for spec in cards.list_blocks():
        units = {one.si_unit for one in (*spec.produces, *spec.rows) if one.si_unit}
        if units:
            found[spec.key] = units
    return found


def test_블록이_드는_단위는_전부_선언돼_있다() -> None:
    missing = {
        key: sorted(units - set(systems.DECLARED))
        for key, units in _all_units().items()
        if units - set(systems.DECLARED)
    }
    assert not missing, (
        "블록이 단위계 표가 모르는 단위를 듭니다 — `matcore/export/systems.py` 의 DECLARED "
        f"와 두 계의 symbols 에 함께 적으세요: {missing}"
    )


def test_선언된_단위는_모든_내장_단위계가_기호를_안다() -> None:
    gaps = {
        system.key: [unit for unit in systems.DECLARED if unit not in system.symbols]
        for system in systems.SYSTEMS
    }
    gaps = {key: units for key, units in gaps.items() if units}
    assert not gaps, f"단위계가 기호를 모르는 선언 단위: {gaps}"


def test_확장_블록도_종류가_된다() -> None:
    """확장이 블록을 더하면 화면에서 카드 종류가 돼야 한다 — `kind_priority` 가 기본으로
    켜져 있고(`None` 이 아님), 내장 기본 블록(탄성·소성 표·모델 파라미터)만 종류가 아니다."""
    cards.load_builtin()
    extensions.load(BACKEND / "extensions")
    not_kinds = {spec.key for spec in cards.list_blocks() if spec.kind_priority is None}
    assert not_kinds == {"elastic", "table", "model_params"}, not_kinds
