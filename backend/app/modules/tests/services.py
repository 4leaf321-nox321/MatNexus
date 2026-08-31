"""시험 등록·파싱 로직.

업로드는 **파일만 받고 끝낸다.** 파싱은 워커가 한다. 큰 파일은 수 초가 걸리는데
그동안 요청이 물려 있으면 브라우저가 먼저 끊고, 그러면 사용자는 실패한 줄 아는데
서버는 계속 처리하고 있다. 그 어긋남을 없애려고 상태를 DB 에 둔다
(`uploaded → parsing → parsed | failed`).

**파싱 실패와 인프라 실패를 다르게 다룬다.** 형식이 안 맞는 파일은 몇 번을 다시
해도 안 맞으므로 재시도하지 않고 `failed` 로 기록해 사람이 보게 한다. 디스크·DB
오류는 던져서 워커가 재시도하게 한다. 이 둘을 섞으면 잘못된 파일 하나가 큐를 계속
돌거나, 일시적 장애가 영구 실패로 남는다.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.accounts.models import User
from app.modules.materials.models import Specimen
from app.modules.tests.models import (
    Curve,
    FormatProfile,
    TestChannel,
    TestConditionField,
    TestRun,
    TestSummary,
    TestType,
)
from app.modules.tests.schemas import RECORD_FIELDS
from app.modules.vocabulary import services as vocabulary_services
from app.shared import (
    audit,
    curvedata,
    filestore,
    parse_hooks,
    permissions,
    specimen_size,
)
from app.shared.errors import AppError, NotFound
from matcore import curves, parsers, readers, registry, units, viscoelastic
from matcore.parsers import ParsedTest, ParseError
from matcore.readers import profile as profiles

#: 기준정보를 거쳐 들어가는 칸(ADR 0010). 문자열을 그대로 박으면 'Zwick Z100' 과
#: 'zwick z100' 이 갈려 장비별 비교가 무의미해진다.
_RECORD_BOUND = {"instrument", "division"}

logger = logging.getLogger(__name__)

#: 정규화 곡선의 키. 지금은 하나지만 DMA 온도-주파수 스윕은 구간별로 여럿이 된다.
RAW_CURVE = "raw"


def _now() -> datetime:
    return datetime.now(UTC)


# --- 조회 범위 --------------------------------------------------------------


#: 시험 가시 범위는 `shared/permissions` 가 판정한다 — 처리·통계·적합도 같은
#: 것을 쓰기 때문이다. 여기서 다시 부르는 것은 기존 호출부(`services.get_run`)를
#: 그대로 두기 위한 재수출이고, 구현은 한 곳뿐이다.
visible_runs = permissions.visible_runs
get_run = permissions.get_run


def get_test_type(db: Session, key: str) -> TestType:
    # **지운 정의로는 못 올린다.** 소프트 삭제라 행은 남는데, 안 거르면 지운
    # 종류로 파일이 계속 들어온다 — 목록에는 없는 종류의 시험이 쌓인다.
    test_type = db.scalar(
        select(TestType).where(TestType.key == key, TestType.deleted_at.is_(None))
    )
    if test_type is None:
        raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {key}")
    if not test_type.is_active:
        raise AppError("MNX-TESTS-0003", f"중단된 시험 종류입니다: {key}", status=422)
    return test_type


def upload_limit(test_type: TestType) -> int:
    return test_type.max_upload_bytes or get_settings().max_upload_bytes


def next_run_seq(db: Session, specimen_id: uuid.UUID, test_type_id: uuid.UUID) -> int:
    """회차. 삭제한 회차의 번호는 재사용하지 않는다 — 옛 보고서에 적힌 이름이
    다른 시험을 가리키게 된다."""
    highest = db.scalar(
        select(func.max(TestRun.seq_no)).where(
            TestRun.specimen_id == specimen_id, TestRun.test_type_id == test_type_id
        )
    )
    return (highest or 0) + 1


def run_counts(db: Session, specimen_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not specimen_ids:
        return {}
    rows = db.execute(
        select(TestRun.specimen_id, func.count())
        .where(TestRun.specimen_id.in_(specimen_ids), TestRun.deleted_at.is_(None))
        .group_by(TestRun.specimen_id)
    )
    return {specimen_id: count for specimen_id, count in rows}


# --- 조건 값 ----------------------------------------------------------------


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


# --- 정의 편집 --------------------------------------------------------------


def definition_is_locked(db: Session, test_type_id: uuid.UUID) -> tuple[bool, int]:
    """이 종류로 등록된 시험이 있으면 채널의 key·단위·차원을 잠근다.

    **저장된 데이터의 해석이 바뀌기 때문이다.**

    - `key` 는 Parquet 컬럼 이름이자 `Curve.channels` 의 값이다. 바꾸면 이미 저장된
      곡선을 못 읽고, 오류가 아니라 조용히 "채널 없음" 이 된다.
    - `si_unit` 은 더 나쁘다. 저장된 숫자는 그대로인데 뜻이 바뀐다 — force 를
      N → kN 으로 바꾸면 3466.4 N 이 3466.4 kN 으로 읽힌다. **숫자가 그대로라
      화면 어디에도 티가 안 난다.** 조건 단위 6만 배 사고와 같은 부류다.

    라벨·정렬·필수여부는 잠그지 않는다 — 그것들은 해석을 바꾸지 않는다.

    소프트 삭제한 시험도 센다. 되살릴 수 있는 데이터의 해석을 바꾸면 안 된다.
    """
    count = (
        db.scalar(
            select(func.count())
            .select_from(TestRun)
            .where(TestRun.test_type_id == test_type_id)
        )
        or 0
    )
    return count > 0, count


def _count_children(db: Session, model: type[Any], test_type_id: uuid.UUID) -> int:
    """채널·조건이 몇 개였나. **개수가 줄었다는 것 자체가 신호다** — 채널이 사라지면
    그 채널을 읽던 곡선이 해석을 잃는다."""
    return (
        db.scalar(
            select(func.count()).select_from(model).where(model.test_type_id == test_type_id)
        )
        or 0
    )


def save_definition(
    db: Session,
    *,
    key: str,
    label: str,
    abbr: str,
    description: str | None,
    parser_key: str | None,
    is_active: bool,
    sort_order: int,
    max_upload_bytes: int | None,
    channels: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
    owner_workspace_id: uuid.UUID | None = None,
    actor: User | None = None,
) -> TestType:
    """정의 한 벌을 저장한다. 없으면 만들고, 있으면 갈아 끼운다.

    `owner_workspace_id` 는 **만들 때만** 쓴다. 소유를 옮기는 것(전역 승격)은
    성격이 다른 결정이라 이 경로로 조용히 일어나면 안 된다.

    `actor` 를 주면 **고칠 때만** 감사 기록을 남긴다. 만드는 것은 되돌릴 수 있고
    아직 아무것도 안 가리키지만, 고치는 것은 이미 저장된 곡선의 읽는 법을
    바꾼다 — 그 둘은 같은 무게가 아니다.
    """
    if not channels:
        raise AppError("MNX-TESTS-0015", "채널이 하나도 없습니다.", status=422)
    _ensure_unique_keys(channels, "채널")
    _ensure_unique_keys(conditions, "조건")
    _validate_units(channels, conditions)
    if parser_key:
        parsers.load_builtin()
        try:
            registry.get(parser_key)
        except KeyError:
            raise AppError(
                "MNX-TESTS-0016",
                f"등록되지 않은 파서입니다: {parser_key}. "
                f"파서는 코드로 등록합니다 — 정의만으로는 파일을 읽을 수 없습니다.",
                status=422,
            ) from None

    # **지운 것을 되쓰지 않는다.** 여기서 안 거르면 같은 key 로 새로 만들 때
    # 소프트 삭제된 행을 찾아 그 위에 덮어쓰고, `deleted_at` 이 그대로 남아
    # **201 을 받았는데 목록에 없는** 상태가 된다(2026-08-29 실측 — 같은 id 가
    # 두 번 돌아왔다). 되살리는 길은 휴지통이지 이 경로가 아니다.
    test_type = db.scalar(
        select(TestType).where(TestType.key == key, TestType.deleted_at.is_(None))
    )
    creating = test_type is None

    # **사전을 읽기 전에 flush 한다.** 세션이 `autoflush=False` 다
    # (`app/database.py`). 아직 안 나간 채널이 있으면 사전이 비어 보이고, 빈
    # 사전은 **아무것도 안 막는다** — 검사가 조용히 통과하는 것은 검사가 없는
    # 것보다 나쁘다. 실제로 이 함수를 처음 붙였을 때 그렇게 통과했다.
    #
    # 그리고 이 검사는 **아무것도 만들기 전에** 한다. 반쯤 만든 TestType 이
    # 세션에 얹힌 뒤 flush 하면 NOT NULL 에 걸린다.
    db.flush()
    _guard_channel_dictionary(db, test_type.id if test_type else None, channels)

    if test_type is None:
        test_type = TestType(key=key, owner_workspace_id=owner_workspace_id)
        db.add(test_type)
    else:
        _guard_locked_changes(db, test_type, channels, conditions)

    before = {
        "label": test_type.label,
        "abbr": test_type.abbr,
        "parser_key": test_type.parser_key,
        "is_active": test_type.is_active,
        "max_upload_bytes": test_type.max_upload_bytes,
        "channels": _count_children(db, TestChannel, test_type.id),
        "conditions": _count_children(db, TestConditionField, test_type.id),
    }
    test_type.label = label
    test_type.abbr = abbr
    test_type.description = description
    test_type.parser_key = parser_key
    test_type.is_active = is_active
    test_type.sort_order = sort_order
    test_type.max_upload_bytes = max_upload_bytes
    db.flush()

    _replace_children(db, test_type, channels, conditions)
    if actor is not None and not creating:
        changed = audit.diff(
            before,
            {
                "label": label,
                "abbr": abbr,
                "parser_key": parser_key,
                "is_active": is_active,
                "max_upload_bytes": max_upload_bytes,
                "channels": len(channels),
                "conditions": len(conditions),
            },
        )
        if changed:
            audit.record(
                db,
                action=audit.TEST_TYPE_CHANGED,
                actor=actor,
                target_table="test_types",
                target_id=test_type.id,
                target_label=f"{label} ({key})",
                workspace_id=test_type.owner_workspace_id,
                changes=changed,
            )
    db.commit()
    db.refresh(test_type)
    logger.info("시험 종류 %s: %s", "생성" if creating else "수정", key)
    return test_type


def _ensure_unique_keys(items: list[dict[str, Any]], label: str) -> None:
    keys = [str(item["key"]) for item in items]
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    if duplicated:
        raise AppError(
            "MNX-TESTS-0017", f"{label} 키가 겹칩니다: {', '.join(duplicated)}", status=422
        )


def _validate_units(channels: list[dict[str, Any]], conditions: list[dict[str, Any]]) -> None:
    """단위가 표에 있고 차원과 맞는지. 모르는 단위를 통과시키면 저장은 되는데
    변환할 때 터진다 — 그때는 이미 데이터가 들어온 뒤다."""
    for item in [*channels, *conditions]:
        symbol = item.get("si_unit")
        if not symbol:
            continue
        try:
            resolved = units.unit_of(str(symbol))
        except units.UnknownUnit as exc:
            raise AppError(
                "MNX-TESTS-0018",
                f"'{item['label']}' 의 단위를 알 수 없습니다: {exc.symbol}",
                status=422,
            ) from exc
        dimension = item.get("dimension")
        if dimension and not units.same_dimension(resolved.dimension, str(dimension)):
            raise AppError(
                "MNX-TESTS-0018",
                f"'{item['label']}' 은 {dimension} 인데 {symbol} 은 "
                f"{resolved.dimension} 입니다.",
                status=422,
            )

        # **저장 단위는 고를 수 있는 것이 아니다.** 값은 언제나 그 차원의 정본 SI 로
        # 저장된다(`to_si` 가 그렇게 만든다). 정의에 `MPa` 라고 적으면 저장된
        # 숫자는 Pa 인데 화면·계산은 MPa 로 읽어 **10⁶ 배** 틀린다. 숫자가 멀쩡해
        # 보여 티가 나지 않는 그 계열이다.
        expected = units.SI_UNITS.get(units.normalize_dimension(resolved.dimension))
        if expected and str(symbol) != expected:
            raise AppError(
                "MNX-TESTS-0018",
                f"'{item['label']}' 의 저장 단위는 {expected} 여야 합니다 "
                f"({symbol} 로 적었습니다). 저장은 언제나 정본 SI 이고, 사람이 보는 "
                f"단위는 화면이 따로 정합니다.",
                status=422,
            )


def _guard_channel_dictionary(
    db: Session, test_type_id: uuid.UUID | None, channels: list[dict[str, Any]]
) -> None:
    """이미 다른 종류가 쓰는 채널 키면 **차원·저장 단위가 같아야 한다.**

    시험 종류를 부서 관리자에게 열면서 생긴 유일한 진짜 위험이 이것이다. 채널
    키는 표시용 라벨이 아니라 **Parquet 의 컬럼 이름**이고, 곡선 비교·통계·
    내보내기가 전부 그 이름으로 열을 찾는다. A부서가 `stress` 를 Pa 로, B부서가
    같은 이름을 MPa 로 정의하면 두 부서 곡선을 겹쳐 그린 순간 **10⁶ 배 어긋난
    그림**이 나오는데, 축 이름이 같아서 아무도 이상하다고 느끼지 못한다.

    새 테이블(채널 사전)을 두지 않는 이유: 사전은 이미 있다 — **등록된 종류들의
    채널 전체**가 그것이다. 따로 두면 둘이 어긋나는 세 번째 문제가 생긴다.

    **새 키를 만드는 것은 막지 않는다.** 새 물성을 재는 것이 새 장비를 붙이는
    일이고, 그것을 막으면 문을 연 의미가 없다. 막는 것은 *같은 이름으로 다른
    것을 뜻하는* 경우뿐이다.
    """
    query = select(TestChannel.key, TestChannel.si_unit, TestChannel.dimension, TestType.label)
    query = query.join(TestType, TestType.id == TestChannel.test_type_id)
    if test_type_id is not None:
        query = query.where(TestChannel.test_type_id != test_type_id)

    known: dict[str, tuple[str, str, str]] = {}
    for key, si_unit, dimension, owner_label in db.execute(query):
        known.setdefault(key, (si_unit, dimension, owner_label))

    for item in channels:
        key = str(item["key"])
        existing = known.get(key)
        if existing is None:
            continue
        si_unit, dimension, owner_label = existing
        if str(item.get("si_unit")) == si_unit and str(item.get("dimension")) == dimension:
            continue
        raise AppError(
            "MNX-TESTS-0028",
            f"채널 '{key}' 는 이미 '{owner_label}' 에서 {dimension}({si_unit}) 로 "
            f"쓰고 있습니다. 여기서는 {item.get('dimension')}({item.get('si_unit')}) 입니다. "
            f"같은 이름은 같은 것을 뜻해야 합니다 — 곡선을 겹쳐 그릴 때 축이 어긋납니다. "
            f"다른 뜻이면 이름을 다르게 지으세요.",
            status=422,
        )


def _guard_locked_changes(
    db: Session,
    test_type: TestType,
    channels: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
) -> None:
    """데이터가 있으면 해석을 바꾸는 수정을 막는다."""
    locked, count = definition_is_locked(db, test_type.id)
    if not locked:
        return

    existing = {
        c.key: c
        for c in db.scalars(
            select(TestChannel).where(TestChannel.test_type_id == test_type.id)
        )
    }
    incoming = {str(item["key"]): item for item in channels}

    removed = sorted(set(existing) - set(incoming))
    if removed:
        raise AppError(
            "MNX-TESTS-0019",
            f"등록된 시험이 {count}건 있어 채널을 지울 수 없습니다: {', '.join(removed)}. "
            f"이미 저장된 곡선이 그 이름으로 열을 갖고 있습니다.",
            status=409,
        )

    for key, current in existing.items():
        item = incoming[key]
        if (
            str(item["si_unit"]) != current.si_unit
            or str(item["dimension"]) != current.dimension
        ):
            raise AppError(
                "MNX-TESTS-0019",
                f"등록된 시험이 {count}건 있어 '{current.label}' 의 단위·차원을 바꿀 수 "
                f"없습니다. 저장된 숫자는 그대로인데 뜻만 바뀌어, 화면 어디에도 티가 "
                f"나지 않는 오류가 됩니다.",
                status=409,
            )

    existing_fields = {
        f.key: f
        for f in db.scalars(
            select(TestConditionField).where(TestConditionField.test_type_id == test_type.id)
        )
    }
    incoming_fields = {str(item["key"]): item for item in conditions}
    for key, field in existing_fields.items():
        replacement = incoming_fields.get(key)
        if replacement is None:
            # 조건은 지워도 곡선이 안 깨진다. 값은 `TestRun.conditions` 에 남는다.
            continue
        if replacement.get("si_unit") != field.si_unit:
            raise AppError(
                "MNX-TESTS-0019",
                f"등록된 시험이 {count}건 있어 '{field.label}' 의 단위를 바꿀 수 없습니다. "
                f"이미 저장된 조건 값의 뜻이 달라집니다.",
                status=409,
            )


def _replace_children(
    db: Session,
    test_type: TestType,
    channels: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
) -> None:
    for channel in db.scalars(
        select(TestChannel).where(TestChannel.test_type_id == test_type.id)
    ):
        db.delete(channel)
    for field in db.scalars(
        select(TestConditionField).where(TestConditionField.test_type_id == test_type.id)
    ):
        db.delete(field)
    db.flush()

    for order, item in enumerate(channels):
        db.add(
            TestChannel(
                test_type_id=test_type.id,
                key=str(item["key"]),
                label=str(item["label"]),
                dimension=str(item["dimension"]),
                si_unit=str(item["si_unit"]),
                is_required=bool(item.get("is_required", True)),
                sort_order=int(item.get("sort_order", order * 10)),
            )
        )
    for order, item in enumerate(conditions):
        db.add(
            TestConditionField(
                test_type_id=test_type.id,
                key=str(item["key"]),
                label=str(item["label"]),
                value_type=str(item["value_type"]),
                dimension=item.get("dimension"),
                si_unit=item.get("si_unit"),
                choices=item.get("choices"),
                is_required=bool(item.get("is_required", False)),
                sort_order=int(item.get("sort_order", order * 10)),
            )
        )


def delete_definition(db: Session, key: str) -> None:
    """시험이 하나라도 있으면 지우지 않는다 — 지우면 그 시험들이 무엇이었는지
    말할 수 없게 된다. 쓰지 않으려면 `is_active` 를 끈다.

    ## 지우는 것이 아니라 **감추는 것**이다

    행은 남고 `deleted_at` 만 찍는다. 정의는 **이미 저장된 데이터의 뜻**이라
    (채널이 무엇을 재는 것이었나) 진짜로 지우면 그 답이 사라진다. 되살리는 길은
    휴지통에 있다.

    막는 검사를 그대로 둔 이유: 소프트여도 목록에서는 사라지고, 그 종류로 등록된
    시험이 있으면 화면에서 **이름 없는 시험**이 된다. 그럴 때 쓰라고 '중단' 이 있다.
    """
    test_type = db.scalar(
        select(TestType).where(TestType.key == key, TestType.deleted_at.is_(None))
    )
    if test_type is None:
        raise NotFound("MNX-TESTS-0002", f"시험 종류를 찾을 수 없습니다: {key}")
    _, count = definition_is_locked(db, test_type.id)
    if count:
        raise AppError(
            "MNX-TESTS-0020",
            f"이 종류로 등록된 시험이 {count}건 있어 지울 수 없습니다. "
            f"더 쓰지 않으려면 '중단' 으로 바꾸세요.",
            status=409,
        )
    # **자식은 그대로 둔다.** 되살릴 때 채널·조건이 함께 돌아와야 한다 —
    # 비우고 나면 껍데기만 남은 정의가 복원된다.
    test_type.deleted_at = datetime.now(UTC)
    db.commit()


# --- 파싱 -------------------------------------------------------------------


def parse_run(db: Session, run_id: uuid.UUID) -> str:
    """업로드한 원본을 읽어 곡선과 요약값을 만든다. 최종 상태를 돌려준다.

    워커가 부른다. 여기서 나가는 예외는 **인프라 오류뿐**이다 — 그것만 재시도할
    가치가 있다.
    """
    run = db.get(TestRun, run_id)
    if run is None or run.deleted_at is not None:
        # 업로드 직후 지운 경우다. 큐에 남은 작업이 실패로 쌓일 이유는 없다.
        logger.info("파싱 대상 시험이 사라졌습니다: %s", run_id)
        return "gone"

    test_type = db.get(TestType, run.test_type_id)
    if test_type is None:
        return _fail(db, run, "시험 종류가 삭제되었습니다.")
    if not run.source_path:
        return _fail(db, run, "원본 파일이 등록되지 않았습니다.")

    run.status = "parsing"
    db.commit()

    data = filestore.read_bytes(run.source_path)  # 인프라 오류는 그대로 올린다

    # **프로파일이 먼저다.** 장비가 늘 때마다 파서를 짜지 않으려고 만든 길이므로,
    # 맞는 프로파일이 있으면 그것을 쓴다. 없을 때만 코드 플러그인으로 내려간다.
    reader = _pick_reader(db, test_type, run, data)
    if reader is None:
        # **막다른 길을 가리키지 않는다.** 다른 종류가 읽을 수 있는 파일이면
        # 프로파일을 만들어도 영영 안 읽힌다 — 틀린 것은 시험 종류다.
        elsewhere = _who_could_read(db, run, data)
        return _fail(
            db,
            run,
            (
                f"'{test_type.label}' 을 읽을 방법이 없습니다. 다만 이 파일은 "
                f"{elsewhere} 이 읽는 형식으로 보입니다 — **시험 종류가 잘못 "
                f"지정된 것 같습니다.** 지우고 그 종류로 다시 올리세요."
            )
            if elsewhere
            else (
                f"'{test_type.label}' 을 읽을 방법이 없습니다. 형식 프로파일을 "
                f"만들거나 파서를 등록하세요."
            ),
        )
    how, source = reader

    try:
        parsed: ParsedTest = source(data)
    except ParseError as exc:
        return _fail(db, run, str(exc))
    except Exception as exc:  # 파서·프로파일 버그도 그 파일에서는 계속 난다
        logger.exception("읽는 중 예상치 못한 예외 (run=%s, %s)", run.id, how)
        return _fail(db, run, f"파일을 읽는 중 오류가 났습니다: {exc}")

    missing = _missing_required_channels(db, test_type, parsed)
    if missing:
        return _fail(
            db,
            run,
            f"필수 채널이 없습니다: {', '.join(missing)}. "
            f"장비 설정이나 시험 종류 정의를 확인하세요.",
        )

    conflicts = _channel_unit_conflicts(db, test_type, parsed)
    if conflicts:
        return _fail(
            db,
            run,
            f"단위가 정의와 맞지 않습니다 — {' / '.join(conflicts)}. "
            f"프로파일에서 그 열의 단위를 지정하거나 시험 종류 정의를 확인하세요.",
        )

    _store_curves(db, run, parsed, version=how)
    _store_summary(db, run, parsed)
    run.temperature_step_count = _temperature_steps(parsed)

    run.source_metadata = dict(parsed.metadata)
    _apply_dimensions(db, run, parsed)
    filled = _apply_record(db, run, parsed)
    filled += _apply_conditions(db, run, test_type, parsed)
    run.parser_version = how[:80]
    run.status = "parsed"
    run.parse_error = None
    # **다 읽은 뒤에 도메인이 할 일.** 파싱은 무엇을 하는지 모른다 — 점탄성이
    # 장비가 겹쳐 준 표를 마스터커브로 등록하는 것이 여기 걸린다(`parse_hooks`).
    # 훅에서 난 오류는 경고가 될 뿐 읽기를 실패시키지 않는다.
    db.flush()
    notes = [*parsed.warnings, *filled, *parse_hooks.fire_parsed(db, run)]
    if notes:
        # 경고는 실패가 아니지만 사라지면 안 된다. 상세 화면이 그대로 보여 준다.
        run.source_metadata = {
            **run.source_metadata,
            "_warnings": " / ".join(notes),
        }
    db.commit()
    logger.info(
        "파싱 완료 %s — 곡선 %d개 (%s, 경고 %d)",
        run.record_name,
        len(parsed.all_curves),
        how,
        len(parsed.warnings),
    )
    return "parsed"


def _apply_dimensions(db: Session, run: TestRun, parsed: ParsedTest) -> None:
    """파일이 들고 온 시편 치수를 **이 시험에** 담는다.

    ## 왜 시편이 아니라 여기인가

    실사용에서 나왔다 — *"시편 하나에 여러 시험으로 넣으니까, 그 시험은 다 같은
    두께, 폭을 가지게 되어 버린다"*. 치수는 **그 시험에서 잰 값**이다.

    전에는 사람이 「장비 치수 채우기」 를 눌러야 시편에 들어갔고, 그것도 **빈
    칸만** 채웠다. 그래서 두 번째 파일이 들고 온 값은 갈 자리가 아예 없었다.

    ## 여기는 물어보지 않는다

    시편에 쓸 때는 물어봐야 했다 — 사람이 재어 넣은 값을 파일이 조용히 바꾸는
    일이라서다. 여기는 **그 시험의 자기 값**이라 덮을 남의 값이 없다.

    시편 쪽 「채우기」 는 그대로 둔다. 시험이 없는 시편도 치수를 가져야 하고,
    사람이 규격 공칭을 적어 두는 자리도 거기다.
    """
    specimen = db.get(Specimen, run.specimen_id)
    found = curvedata.instrument_dimensions(
        parsed.metadata, specimen_size.dimension_fields(db, specimen)
    )
    if found:
        run.dimensions = found


def _apply_record(db: Session, run: TestRun, parsed: ParsedTest) -> list[str]:
    """파일이 말한 값을 시험 칸에 채운다. **빈 칸만.** 남긴 말을 돌려준다.

    ## 왜 빈 칸만인가

    사람이 올릴 때 적은 값을 파일이 조용히 바꾸면 어느 것이 맞는지 알 수 없다.
    그리고 **다시 읽기**가 있다 — 덮어쓰면, 사람이 고쳐 놓은 장비 이름이 다시
    읽을 때마다 파일 값으로 되돌아간다. 시편 치수를 채우는 자리와 같은 판단이다
    (`apply_instrument_dimensions` 의 `overwrite`).

    ## 곡선을 잃지 않는다

    기준정보 축이 `closed` 면 `resolve_or_create` 가 `AppError` 를 낸다. 그것을
    그냥 두면 `parse_run` 의 바깥 `except` 가 잡아 **파싱 실패**로 만든다 —
    파일은 멀쩡히 읽혔는데 곡선까지 통째로 잃는다. 채우기는 거들기이지 읽기가
    아니므로, 실패해도 **말만 남기고 넘어간다.**
    """
    if not parsed.record:
        return []

    said: list[str] = []
    plain: dict[str, str | None] = {}
    for field, raw in parsed.record.items():
        if field not in RECORD_FIELDS:
            continue
        if getattr(run, field, None):
            continue  # 사람이 이미 적었다. 건드리지 않는다.
        if field == "tested_at":
            try:
                run.tested_at = datetime.fromisoformat(raw)
            except ValueError:
                said.append(f"파일의 시험일 {raw!r} 를 못 읽어 비워 둡니다.")
            continue
        if field in _RECORD_BOUND:
            plain[field] = raw
            continue
        setattr(run, field, raw)

    if plain:
        try:
            vocabulary_services.apply_bindings(
                db,
                run,
                vocabulary_services.TEST_RUN_BINDINGS,
                plain,
                created_by_id=run.registered_by_id,
            )
        except AppError as error:
            # 기준정보가 닫혀 있다. **곡선은 지킨다.**
            said.append(
                f"파일이 말한 {'·'.join(RECORD_FIELDS[key] for key in plain)} 를 "
                f"기준정보에 넣지 못했습니다: {error.message}"
            )
    return said


def _apply_conditions(
    db: Session, run: TestRun, test_type: TestType, parsed: ParsedTest
) -> list[str]:
    """파일이 말한 **시험 조건**을 채운다. 빈 칸만. 남긴 말을 돌려준다.

    ## 폼과 같은 길을 탄다

    `normalize_conditions` 는 화면에서 올릴 때 쓰는 그 함수다. 여기서 다른 길을
    내면 검증이 둘로 갈리고, 그러면 **폼으로는 막히는 값이 파일로는 들어온다.**
    단위 차원 검사(길이 자리에 시간 단위)도 그 함수가 한다.

    ## 빈 칸만 채운다

    사람이 올릴 때 적은 조건을 파일이 조용히 바꾸면 어느 것이 맞는지 알 수 없다.
    그리고 다시 읽기가 있다 — 덮어쓰면 고쳐 놓은 값이 매번 되돌아간다.
    시험 칸(`_apply_record`)과 같은 판단이다.

    ## 곡선을 잃지 않는다

    파일의 조건 값이 정의와 안 맞으면(모르는 단위·목록에 없는 선택지)
    `normalize_conditions` 가 `AppError` 를 낸다. 그것을 그냥 두면 파싱 실패가
    되어 **파일은 멀쩡히 읽혔는데 곡선까지 통째로 잃는다.** 채우기는 거들기이지
    읽기가 아니므로, 실패해도 말만 남기고 넘어간다.
    """
    if not parsed.conditions:
        return []

    already = dict(run.conditions or {})
    fresh = {
        key: value
        for key, value in parsed.conditions.items()
        if already.get(key) in (None, "")
    }
    if not fresh:
        return []

    try:
        # **이미 있는 것과 함께 넘긴다.** 새 것만 넘기면 이미 적힌 조건이
        # 「안 보낸 것」이 되어 통째로 지워진다.
        values, units = normalize_conditions(
            db,
            test_type,
            {**already, **fresh},
            {**(run.input_units or {}), **parsed.condition_units},
        )
    except AppError as error:
        return [
            f"파일이 말한 시험 조건({', '.join(sorted(fresh))})을 "
            f"넣지 못했습니다: {error.message}"
        ]

    run.conditions = values
    run.input_units = units
    return []


def _who_could_read(db: Session, run: TestRun, data: bytes) -> str | None:
    """이 파일을 **다른 시험 종류**가 읽을 수 있나. 읽을 수 있으면 그 이름.

    ## 왜 필요한가

    「읽을 방법이 없습니다. 형식 프로파일을 만들거나 파서를 등록하세요」 는
    **막다른 길을 가리킬 때가 있다.** 실제로 인장 `.tra` 파일이 DMA 종류로
    올라온 일이 있었는데, 그 안내를 따라 프로파일을 만들어도 영영 안 읽힌다 —
    그 파일은 이미 읽을 줄 아는 파서가 있고, 틀린 것은 시험 종류였다.

    시스템은 그것을 알 수 있다. 알면서 안 말하면 사람은 없는 문제를 풀게 된다.
    """
    filename = run.source_filename or ""
    try:
        structure = readers.sniff(data)
    except readers.ReadError:
        structure = None

    if structure is not None:
        rows = db.scalars(
            select(FormatProfile, TestType)
            .join(TestType, TestType.id == FormatProfile.test_type_id)
            .where(
                FormatProfile.test_type_id != run.test_type_id,
                FormatProfile.is_active.is_(True),
                or_(
                    FormatProfile.owner_workspace_id.is_(None),
                    FormatProfile.owner_workspace_id == run.workspace_id,
                ),
            )
        )
        for profile in rows:
            if profiles.matches(profile.definition, filename=filename, structure=structure):
                kind = db.get(TestType, profile.test_type_id)
                return f"'{kind.label if kind else '?'}' (형식 {profile.key})"

    # 파서는 확장자로 본다 — 지문까지 재려면 전부 돌려 봐야 하고, 그 비용을
    # 오류 안내에 쓸 이유는 없다.
    suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""
    if suffix:
        parsers.load_builtin()
        for kind in db.scalars(
            select(TestType).where(
                TestType.id != run.test_type_id,
                TestType.parser_key.is_not(None),
                TestType.is_active.is_(True),
            )
        ):
            try:
                plugin = registry.get(kind.parser_key or "")
            except KeyError:
                continue
            declared = [str(one).lower() for one in plugin.meta.get("extensions", ())]
            if suffix in declared:
                return f"'{kind.label}' (파서 {kind.parser_key})"
    return None


def _pick_reader(
    db: Session, test_type: TestType, run: TestRun, data: bytes
) -> tuple[str, Any] | None:
    """이 파일을 무엇으로 읽을까. (표시용 이름, 읽는 함수).

    프로파일을 먼저 본다 — 그것이 배포 없이 장비를 늘리는 길이기 때문이다.
    맞는 것이 여럿이면 `priority` 가 높은 것이 이긴다. 실제로 생긴다: 같은 장비의
    형식이 조금 달라져 프로파일을 하나 더 만들면 지문이 겹친다.
    """
    filename = run.source_filename or ""

    # **사람이 고른 것이 있으면 그것만 쓴다.** 자동으로 되돌아가면 고른 뜻이
    # 없고, 「분명 그걸로 지정했는데」 를 설명할 길도 없다.
    if run.parse_profile_id is not None:
        chosen = db.get(FormatProfile, run.parse_profile_id)
        if chosen is None or not chosen.is_active:
            return None
        return (
            f"profile:{chosen.key}",
            lambda raw, rule=chosen.definition: profiles.apply(rule, raw),
        )

    candidates = list(
        db.scalars(
            select(FormatProfile)
            .where(
                FormatProfile.test_type_id == test_type.id,
                FormatProfile.is_active.is_(True),
                or_(
                    FormatProfile.owner_workspace_id.is_(None),
                    FormatProfile.owner_workspace_id == run.workspace_id,
                ),
            )
            # **내 부서 것이 전역보다 먼저다.** 같은 장비라도 부서마다 소프트웨어
            # 설정이 달라 열 이름이 조금씩 다른 일이 있다. 부서가 자기 것을
            # 만들어 뒀는데 전역이 이기면 그걸 만든 뜻이 없다.
            .order_by(
                FormatProfile.owner_workspace_id.is_(None),
                FormatProfile.priority.desc(),
                FormatProfile.key,
            )
        )
    )
    if candidates:
        try:
            structure = readers.sniff(data)
        except readers.ReadError:
            structure = None
        if structure is not None:
            for candidate in candidates:
                if profiles.matches(
                    candidate.definition, filename=filename, structure=structure
                ):
                    return (
                        f"profile:{candidate.key}",
                        # 기본 인자로 묶는다. 그냥 닫으면 루프의 마지막 값을
                        # 잡아, 맞지도 않는 프로파일로 읽는다.
                        lambda raw, rule=candidate.definition: profiles.apply(rule, raw),
                    )

    if test_type.parser_key:
        parsers.load_builtin()
        try:
            plugin = registry.get(test_type.parser_key)
        except KeyError:
            return None
        return f"{plugin.id}:{plugin.version}", plugin.fn

    return None


def _fail(db: Session, run: TestRun, reason: str) -> str:
    """읽지 못했다는 사실과 이유를 남긴다. 재시도하지 않는다.

    같은 바이트를 같은 파서로 다시 읽어도 결과는 같다. 재시도하면 큐만 돌고,
    실패 이유는 로그 깊숙이 묻힌다.
    """
    run.status = "failed"
    run.parse_error = reason
    db.commit()
    logger.warning("파싱 실패 %s: %s", run.record_name, reason)
    return "failed"


def _missing_required_channels(
    db: Session, test_type: TestType, parsed: ParsedTest
) -> list[str]:
    """정의에서 필수인 채널이 실제로 왔는지 본다.

    이 검사가 수준 2 설계의 값을 하는 지점이다. 정의가 데이터로 있으니, 장비
    설정이 바뀌어 채널이 빠졌을 때 **곡선이 조용히 반쪽이 되는 대신** 등록이
    실패하고 이유가 남는다.
    """
    required = db.scalars(
        select(TestChannel.key).where(
            TestChannel.test_type_id == test_type.id, TestChannel.is_required.is_(True)
        )
    ).all()
    present = {channel.key for curve in parsed.all_curves for channel in curve.channels}
    return [key for key in required if key not in present]


def _channel_unit_conflicts(db: Session, test_type: TestType, parsed: ParsedTest) -> list[str]:
    """읽어 온 채널의 단위가 정의가 선언한 차원과 맞는가.

    **저장 단계는 단위를 확인하지 않는다.** Parquet 에는 숫자만 들어가고, 읽을
    때는 정의의 `si_unit` 을 믿는다. 그래서 여기서 안 막으면 MPa 값이 Pa 인 척
    저장된다 — 10⁶ 배 틀리는데 **숫자는 멀쩡해 보이고 뜻만 바뀌므로** 화면 어디에도
    티가 나지 않는다.

    `matcore` 쪽에도 같은 성격의 방어가 있지만(매핑한 열의 단위를 모르면 거절),
    그쪽은 시험 종류를 모른다. 단위 칸이 비어 있어 무차원으로 읽힌 값이 응력
    채널에 들어가는 경우는 여기서만 잡힌다.
    """
    declared = {
        channel.key: channel
        for channel in db.scalars(
            select(TestChannel).where(TestChannel.test_type_id == test_type.id)
        )
    }
    conflicts: list[str] = []
    seen: set[str] = set()
    for curve in parsed.all_curves:
        for channel in curve.channels:
            spec = declared.get(channel.key)
            if spec is None or channel.key in seen:
                continue
            seen.add(channel.key)

            # **심볼이 아니라 차원으로 본다.** 정의의 저장 단위가 반드시 SI 정본은
            # 아니다 — 편집 화면은 그 차원의 아무 단위나 고를 수 있게 한다. 심볼로
            # 비교하면 `MPa` 로 선언한 멀쩡한 채널이 `Pa` 와 다르다며 걸린다.
            read = _dimension_of(channel.si_unit)
            wanted = _dimension_of(spec.si_unit)
            source = f" (파일 단위 {channel.source_unit})" if channel.source_unit else ""

            if read is None:
                conflicts.append(
                    f"{channel.label or channel.key}: 단위를 알 수 없습니다"
                    f"{source or ' (파일에 단위가 없습니다)'}"
                )
            elif wanted is not None and not units.same_dimension(read, wanted):
                conflicts.append(
                    f"{channel.label or channel.key}: {read}({channel.si_unit}) 로 "
                    f"읽혔는데 정의는 {wanted}({spec.si_unit}){source}"
                )
    return conflicts


def _dimension_of(symbol: str) -> str | None:
    try:
        return units.unit_of(symbol).dimension
    except units.UnknownUnit:
        return None


def _temperature_steps(parsed: ParsedTest) -> int | None:
    """읽은 곡선이 **온도 몇 단인가.** 온도 채널이 없으면 `None`.

    측정 곡선만 센다 — 장비가 계산해 준 표(마스터커브·이동인자)에도 온도 열이
    있는데, 그것은 잰 단이 아니라 겹친 결과다. 함께 세면 온도 한 단짜리 파일이
    여러 단으로 보인다.

    **곡선 하나가 한 단이다.** TA DMA850 은 `[step]` 마다 별개 측정이라 온도가
    구간마다 고정돼 있고, 그 안의 흔들림은 중앙값으로 뭉갠다. 한 곡선 안에서
    온도를 훑는 장비가 나오면 그때 다시 본다 — 지금 그것까지 가정하면 못 본
    파일에 맞춰 코드를 쓰는 것이다.

    `None` 과 0 을 구분한다. `None` 은 「온도를 안 쟀거나 못 읽었다」 이고,
    화면은 그것을 「겹칠 수 없다」 로 읽으면 안 된다.
    """
    found: list[float] = []
    for curve in parsed.all_curves:
        if curve.kind != "measured":
            continue
        for channel in curve.channels:
            if channel.key != "temperature":
                continue
            values = [float(one) for one in channel.values if one is not None and one == one]
            if values:
                found.append(statistics.median(values))
            break
    if not found:
        return None
    return viscoelastic.count_temperature_levels(found)


def _store_curves(db: Session, run: TestRun, parsed: ParsedTest, *, version: str) -> None:
    """곡선을 전부 Parquet 으로 쓰고 Curve 행을 만든다.

    **한 파일이 곡선을 여럿 낼 수 있다.** 실측: TA DMA850 주파수-온도 스윕은
    `[step]` 블록이 8개고 온도 구간마다 별개 측정이다. 하나로 이으면 서로 다른
    온도의 곡선이 한 줄로 붙어 버린다.

    다시 파싱하면 이전 것을 **전부** 지우고 새로 쓴다. 재파싱은 새 사실이 아니라
    같은 원본의 다시 읽기다 — 옛 곡선이 남으면 어느 것이 현재인지 화면이 판단해야
    하고, 프로파일을 고쳐 곡선 수가 줄면 없어진 것이 남는다.
    """
    directory = f"{filestore.run_dir(run.id, run.created_at)}/curves"
    for existing in db.scalars(select(Curve).where(Curve.test_run_id == run.id)):
        db.delete(existing)
    db.flush()

    for curve in parsed.all_curves:
        if not curve.channels:
            continue
        payload = curves.to_parquet(curve.channels)
        stored = filestore.write_bytes(
            payload, relative_dir=directory, filename=f"{curve.key}.parquet"
        )
        db.add(
            Curve(
                test_run_id=run.id,
                key=curve.key,
                label=curve.label or f"원본 정규화 ({version})",
                kind=curve.kind,
                storage_path=stored.relative_path,
                row_count=len(curve.channels[0].values),
                sha256=stored.sha256,
                byte_size=stored.size,
                channels=[channel.key for channel in curve.channels],
            )
        )


def _store_summary(db: Session, run: TestRun, parsed: ParsedTest) -> None:
    """장비가 계산한 값을 `source="instrument"` 로 넣는다.

    우리가 계산한 값(`source="matnexus"`)은 건드리지 않는다. 나란히 두는 것이
    목적이다 — 우리 계산이 장비 값과 크게 다르면 뭔가 잘못된 것이다.
    """
    for row in db.scalars(
        select(TestSummary).where(
            TestSummary.test_run_id == run.id, TestSummary.source == "instrument"
        )
    ):
        db.delete(row)
    db.flush()

    for value in parsed.summary:
        db.add(
            TestSummary(
                test_run_id=run.id,
                key=value.key,
                label=value.label,
                source="instrument",
                value_num=value.value,
                value_text=value.text,
                si_unit=value.si_unit,
            )
        )


# --- 저장소 정리 ------------------------------------------------------------


def _retention_days() -> int:
    return get_settings().filestore_retention_days


def storage_report(db: Session, *, retention_days: int | None = None) -> dict[str, Any]:
    """파일스토어에 무엇이 있고 무엇을 치워야 하는지. **읽기만 한다.**

    치울 것이 **세 종류**다. 하나만 다루면 나머지가 영원히 쌓인다.

    1. **오펀** — DB 에 행이 없는 폴더. 트랜잭션이 파일시스템까지 덮지 못해 생긴다.
       DB 를 훑는 방향으로는 못 찾는다(정의상 DB 에 없다). 파일시스템에서 시작한다.
    2. **미완성** — 쓰다 만 `.part`. 완성된 파일이 아니라 어떤 행도 안 가리키고,
       폴더 자체는 살아 있으므로 오펀 탐색에도 안 걸린다.
    3. **보존기간 지난 소프트 삭제** — 실제로 이것이 가장 크다. 소프트 삭제는 행을
       남기므로 그 파일은 **오펀 탐색으로 영원히 안 잡힌다.** 실측(2026-08-15):
       지운 시험 2건의 파일이 그대로 남아 있었고 치울 경로가 아예 없었다.
    """
    keep_days = retention_days if retention_days is not None else _retention_days()
    cutoff = _now() - timedelta(days=keep_days)

    orphans: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    live_count = 0
    live_bytes = 0

    for relative in filestore.existing_run_dirs():
        raw_id = relative.rsplit("/", 1)[-1]
        try:
            run_id = uuid.UUID(raw_id)
        except ValueError:
            # 우리가 만들지 않은 폴더다. 남의 파일을 지우지 않는다.
            logger.warning("시험 폴더 이름이 UUID 가 아닙니다: %s", relative)
            continue

        size = filestore.directory_size(relative)
        run = db.get(TestRun, run_id)
        if run is None:
            orphans.append({"path": relative, "bytes": size})
        elif run.deleted_at is not None and run.deleted_at < cutoff:
            expired.append(
                {
                    "path": relative,
                    "bytes": size,
                    "run_id": str(run.id),
                    "record_name": run.record_name,
                    "deleted_at": run.deleted_at,
                }
            )
        else:
            live_count += 1
            live_bytes += size

    incomplete = [
        {"path": path, "bytes": size, "age_hours": round(age / 3600, 1)}
        for path, size, age in filestore.incomplete_files()
    ]

    return {
        "root": str(filestore.root()),
        "total_bytes": filestore.total_size(),
        "retention_days": keep_days,
        "live_count": live_count,
        "live_bytes": live_bytes,
        "orphans": orphans,
        "incomplete": incomplete,
        "expired": expired,
        "reclaimable_bytes": sum(
            int(item["bytes"]) for item in [*orphans, *incomplete, *expired]
        ),
    }


def cleanup_storage(
    db: Session, *, dry_run: bool = True, retention_days: int | None = None
) -> dict[str, Any]:
    """`storage_report` 가 찾은 것을 실제로 지운다.

    기본이 `dry_run` 인 이유: 이 잡의 실수는 되돌릴 수 없다. 목록을 보고 납득한
    뒤에 지운다.

    보존기간이 지난 소프트 삭제 건은 **행을 남기고 파일만 지운다.** 이름과 계보는
    조회할 수 있어야 한다 — 옛 보고서에 적힌 이름이 무엇을 가리켰는지 답하지
    못하면 지운 것보다 나쁘다. 대신 곡선 행은 지운다(가리키는 파일이 없어졌다).
    """
    report = storage_report(db, retention_days=retention_days)
    removed: list[str] = []
    freed = 0

    if not dry_run:
        for item in [*report["orphans"], *report["expired"]]:
            if filestore.delete_dir(str(item["path"])):
                removed.append(str(item["path"]))
                freed += int(item["bytes"])

        for item in report["incomplete"]:
            if filestore.delete_file(str(item["path"])):
                removed.append(str(item["path"]))
                freed += int(item["bytes"])

        for item in report["expired"]:
            run = db.get(TestRun, uuid.UUID(str(item["run_id"])))
            if run is None:
                continue
            # 가리키던 파일이 사라졌으므로 포인터를 지운다. 행 자체는 남긴다.
            for curve in db.scalars(select(Curve).where(Curve.test_run_id == run.id)):
                db.delete(curve)
            run.source_path = None
            days = report["retention_days"]
            purged = f"※ 보존기간({days}일)이 지나 파일을 정리했습니다."
            run.note = f"{run.note}\n{purged}" if run.note else purged
        db.commit()

    logger.info(
        "저장소 정리: 오펀 %d · 미완성 %d · 보존만료 %d → 삭제 %d건 %.2fMB (dry_run=%s)",
        len(report["orphans"]),
        len(report["incomplete"]),
        len(report["expired"]),
        len(removed),
        freed / (1024 * 1024),
        dry_run,
    )
    return {**report, "dry_run": dry_run, "removed": removed, "freed_bytes": freed}


# --- 곡선 읽기 --------------------------------------------------------------


def channel_units(db: Session, test_type_id: uuid.UUID) -> dict[str, str]:
    """채널 키 → 저장 단위.

    처리는 **단위를 믿고 계산한다.** 변형률이 % 로 들어오면 100배 어긋나는데,
    그 사실은 곡선을 봐서는 알 수 없다. 그래서 곡선을 Frame 으로 읽을 때 정의에
    적힌 단위를 함께 실어 보낸다.
    """
    rows = db.execute(
        select(TestChannel.key, TestChannel.si_unit).where(
            TestChannel.test_type_id == test_type_id
        )
    )
    return {key: si_unit for key, si_unit in rows}


def curves_of(db: Session, run_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Curve]]:
    """시험별 곡선 전부. **`raw` 만 보면 안 된다.**

    한 파일이 곡선을 여럿 낸다(TA DMA850 주파수-온도 스윕은 `[step]` 8개). 그때
    키는 표 이름의 slug 이고 `raw` 는 아예 없다 — `raw` 만 찾던 목록·상세·차트는
    **저장된 곡선 6벌을 하나도 못 봤다.** 실측으로 걸렸다:

        상세: row_count=None, channels=[]
        차트: 404 "정규화된 곡선이 아직 없습니다"

    `raw` 를 맨 앞에 둔다. 표가 하나뿐인 파일(대부분)에서 예전과 같은 것이 기본이
    되도록.
    """
    if not run_ids:
        return {}
    found: dict[uuid.UUID, list[Curve]] = {}
    for curve in db.scalars(select(Curve).where(Curve.test_run_id.in_(run_ids))):
        found.setdefault(curve.test_run_id, []).append(curve)
    for items in found.values():
        # 측정을 먼저. **기본으로 그려지는 곡선이 마스터 곡선이면 안 된다** —
        # 사람은 그것이 원본인 줄 안다.
        items.sort(key=lambda item: (item.kind != "measured", item.key != RAW_CURVE, item.key))
    return found


def curve_points(
    db: Session, run: TestRun, *, x: str, y: str, max_points: int, curve_key: str | None = None
) -> dict[str, Any]:
    """차트가 쓸 점들. 필요한 두 열만 읽고 축약한다.

    전부 보내지 않는 이유는 크기다. 3만 점이면 JSON 이 수 MB 가 되고, 그 대부분은
    화면 픽셀 하나에 겹쳐 그려진다.
    """
    available = curves_of(db, [run.id]).get(run.id, [])
    if curve_key:
        curve = next((item for item in available if item.key == curve_key), None)
        if curve is None:
            raise NotFound(
                "MNX-TESTS-0009",
                f"그런 곡선이 없습니다: {curve_key} "
                f"(있는 것: {', '.join(item.key for item in available) or '없음'})",
            )
    else:
        curve = available[0] if available else None
    if curve is None:
        raise NotFound("MNX-TESTS-0009", "정규화된 곡선이 아직 없습니다.")

    channels = set(curve.channels)
    missing = [key for key in (x, y) if key not in channels]
    if missing:
        raise AppError(
            "MNX-TESTS-0010",
            f"이 시험에 없는 채널입니다: {', '.join(missing)} "
            f"(있는 것: {', '.join(sorted(channels))})",
            status=422,
        )

    data = filestore.read_bytes(curve.storage_path)
    columns = curves.read_columns(data, [x, y])
    points = curves.downsample(columns[x], columns[y], max_points=max_points)
    return {
        "x": x,
        "y": y,
        "row_count": curve.row_count,
        "returned": len(points),
        "points": points,
    }


def default_axes(db: Session, test_type_id: uuid.UUID) -> tuple[str, str]:
    """정의 순서상 첫 두 채널. 화면이 축을 고르기 전의 기본값이다."""
    keys = list(
        db.scalars(
            select(TestChannel.key)
            .where(TestChannel.test_type_id == test_type_id)
            .order_by(TestChannel.sort_order)
        )
    )
    if len(keys) < 2:
        raise AppError("MNX-TESTS-0011", "채널 정의가 두 개 미만입니다.", status=422)
    return keys[0], keys[1]


__all__ = [
    "RAW_CURVE",
    "cleanup_storage",
    "condition_fields",
    "curve_points",
    "default_axes",
    "get_run",
    "get_test_type",
    "next_run_seq",
    "normalize_conditions",
    "parse_run",
    "run_counts",
    "storage_report",
    "upload_limit",
    "visible_runs",
]
