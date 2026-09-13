"""시험 조건 값 — 정의에 맞춰 검증하고 SI 로 바꾼다.

**여기 있는 이유:** 시험 등록(`tests`)이 쓰던 것인데 측정 의뢰(`commissions`)의
항목도 같은 조건 칸을 같은 규칙으로 받는다. 모듈끼리 직접 부르지 않으므로
(AGENTS.md) 공유해야 하는 판정은 shared 에 둔다 — 두 벌이 되면 「등록은 되는데
의뢰는 막힌다」 가 생긴다. 오류 코드는 옛 자리(`MNX-TESTS-*`)를 그대로 둔다 —
화면과 문서가 그 코드를 알고 있다.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests.models import TestConditionField, TestType
from app.shared.errors import AppError
from matcore import units


def condition_fields(db: Session, test_type_id: uuid.UUID) -> list[TestConditionField]:
    return list(
        db.scalars(
            select(TestConditionField)
            .where(TestConditionField.test_type_id == test_type_id)
            .order_by(TestConditionField.sort_order)
        )
    )


def normalize_conditions(
    db: Session,
    test_type: TestType,
    raw: dict[str, Any],
    given_units: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """조건 입력을 정의에 맞춰 검증하고 SI 로 바꾼다.

    정의에 없는 키는 **거절한다.** 조용히 버리면 오타로 넣은 조건이 사라진 줄
    모르고 저장되고, 받아 두면 정체 모를 키가 쌓인다. 둘 다 나쁘므로 알려 준다.

    `given_units` 는 **화면이 어떤 단위로 받았는지**다. 이것을 안 받던 때 실제
    사고가 났다: 정의의 `si_unit` 이 `m/s` 인데 화면은 사람이 쓰는 `mm/min` 으로
    라벨을 붙여 놓고 값은 그대로 보냈다. 서버가 `to_si(10, "m/s")` 를 해서 10 을
    10 m/s 로 저장했는데 사용자가 뜻한 것은 10 mm/min 이었다 — **6만 배**다.
    숫자가 그럴듯해 보여서 화면 어디에도 티가 나지 않는다.

    그래서 단위를 값과 함께 받고, **차원이 맞는지 확인한다.** 길이 자리에 시간
    단위가 오면 거절한다 — 계수만 맞춰 통과시키면 같은 종류의 사고가 다시 난다.

    돌려주는 둘째 값은 입력 단위다 — SI 로 바꿔 저장하되 무엇으로 입력했는지
    남긴다(ADR 0004).
    """
    supplied = given_units or {}
    fields = {field.key: field for field in condition_fields(db, test_type.id)}
    unknown = sorted(set(raw) - set(fields))
    if unknown:
        raise AppError(
            "MNX-TESTS-0004",
            f"{test_type.label} 에 없는 조건입니다: {', '.join(unknown)}",
            status=422,
        )

    values: dict[str, Any] = {}
    input_units: dict[str, str] = {}

    for key, field in fields.items():
        if key not in raw or raw[key] is None or raw[key] == "":
            if field.is_required:
                raise AppError(
                    "MNX-TESTS-0005", f"'{field.label}' 은 필수 조건입니다.", status=422
                )
            continue

        given = raw[key]
        if field.value_type == "number":
            number = _as_number(given, field.label)
            unit = supplied.get(key) or field.si_unit
            if unit:
                values[key] = _to_si_checked(number, unit, field)
                input_units[key] = unit
            else:
                values[key] = number
        elif field.value_type == "choice":
            allowed = field.choices or []
            if given not in allowed:
                raise AppError(
                    "MNX-TESTS-0007",
                    f"'{field.label}' 은 {', '.join(allowed)} 중 하나여야 합니다.",
                    status=422,
                )
            values[key] = given
        elif field.value_type == "boolean":
            values[key] = bool(given)
        elif field.value_type == "date":
            values[key] = str(given)
        else:
            values[key] = str(given)

    return values, input_units


def _to_si_checked(number: float, unit: str, field: TestConditionField) -> float:
    """단위를 SI 로 바꾸되 **차원이 맞는지 먼저 본다.**

    계수만 맞으면 통과시키는 변환은 위험하다. `mm` 자리에 `ms` 가 와도 둘 다
    0.001 이라 조용히 지나간다.
    """
    try:
        resolved = units.unit_of(unit)
    except units.UnknownUnit as exc:
        raise AppError(
            "MNX-TESTS-0006",
            f"'{field.label}' 의 단위를 알 수 없습니다: {exc.symbol}",
            status=422,
        ) from exc

    if field.dimension and not units.same_dimension(resolved.dimension, field.dimension):
        raise AppError(
            "MNX-TESTS-0014",
            f"'{field.label}' 은 {field.dimension} 인데 {unit} 은 "
            f"{resolved.dimension} 입니다.",
            status=422,
        )
    return units.to_si(number, unit)


def _as_number(given: Any, label: str) -> float:
    try:
        return float(given)
    except (TypeError, ValueError) as exc:
        raise AppError("MNX-TESTS-0008", f"'{label}' 은 숫자여야 합니다.", status=422) from exc
