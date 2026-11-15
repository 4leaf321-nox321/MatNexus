"""처리 결과가 낡았나 — 결과가 쓴 시편 치수와 지금 치수를 견준다(`shared/result_staleness`).

결과는 불변이라, 치수를 고친 뒤에도 옛 치수로 낸 응력 · 탄성률이 채택 · 통계 · 카드로 간다.
이 판정 하나를 통계 노트 · 카드 근거 · 채택 확인 · 운영 점검 보고서가 함께 쓴다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from app.shared import result_staleness
from app.shared.result_staleness import Current


def _result(used_area: Any, *, given: str = "@specimen_area") -> Any:
    return SimpleNamespace(
        steps_snapshot=[{"plugin": "tensile.engineering", "options": {"area": given}}],
        stages=[{"plugin": "tensile.engineering", "options": {"area": used_area}}],
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


NOW = Current({"specimen_area": (15e-6, "시편 초기 단면적", "m2")})


def test_쓴_치수가_지금과_다르면_바뀐_것을_댄다() -> None:
    [change] = result_staleness.dimension_changes(_result(12.5e-6), NOW)
    assert change.key == "specimen_area"
    assert change.used == 12.5e-6 and change.now == 15e-6
    assert change.text() == "시편 초기 단면적 12.5 mm2 → 15 mm2(+20.00 %)"


def test_같으면_반올림만큼은_낡지_않았다() -> None:
    assert result_staleness.dimension_changes(_result(15e-6 * (1 + 1e-9)), NOW) == []


def test_참조가_아니거나_시편_치수가_아니면_안_본다() -> None:
    # 직접 넣은 숫자 — 시편 치수를 고쳐도 그 결과의 입력은 그대로다.
    assert result_staleness.dimension_changes(_result(12.5e-6, given="12.5e-6"), NOW) == []
    # 앞 단계의 값(`@youngs_modulus`)은 치수가 아니다.
    assert (
        result_staleness.dimension_changes(_result(12.5e-6, given="@youngs_modulus"), NOW)
        == []
    )
    # 지금 그 치수가 없으면 견주지 않는다(처리 자체가 「그 값이 없습니다」 로 멈출 자리).
    assert result_staleness.dimension_changes(_result(12.5e-6), Current({})) == []


def test_있으면_쓰는_참조도_본다() -> None:
    assert result_staleness.dimension_changes(_result(12.5e-6, given="@?specimen_area"), NOW)


def test_원본을_바꾼_뒤에_만든_결과가_아니면_낡았다() -> None:
    result = _result(15e-6)
    run = SimpleNamespace(source_replaced_at=result.created_at + timedelta(hours=1))
    assert result_staleness.replaced(result, run)  # type: ignore[arg-type]
    run.source_replaced_at = result.created_at - timedelta(hours=1)
    assert not result_staleness.replaced(result, run)  # type: ignore[arg-type]
    run.source_replaced_at = None
    assert not result_staleness.replaced(result, run)  # type: ignore[arg-type]
