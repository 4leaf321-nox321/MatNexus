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
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.modules.accounts.models import User
from app.modules.materials.models import Sample, Specimen
from app.modules.tests.models import (
    Curve,
    TestChannel,
    TestConditionField,
    TestRun,
    TestSummary,
    TestType,
)
from app.shared import filestore, permissions
from app.shared.errors import AppError, NotFound
from matcore import curves, parsers, registry, units
from matcore.parsers import ParsedTest, ParseError

logger = logging.getLogger(__name__)

#: 정규화 곡선의 키. 지금은 하나지만 DMA 온도-주파수 스윕은 구간별로 여럿이 된다.
RAW_CURVE = "raw"


def _now() -> datetime:
    return datetime.now(UTC)


# --- 조회 범위 --------------------------------------------------------------


def visible_runs(db: Session, user: User) -> Select[tuple[TestRun]]:
    """시험의 가시 범위는 **재료를 따라간다.**

    시험에 별도의 공개 규칙을 두지 않는 이유: 규칙이 둘이 되면 "재료는 보이는데
    그 시험은 안 보인다" 또는 그 반대가 생기고, 어느 쪽이 맞는지 그때그때
    판단해야 한다.
    """
    query = select(TestRun).where(TestRun.deleted_at.is_(None))
    if user.is_system_admin:
        return query
    return query.where(
        TestRun.specimen_id.in_(
            select(Specimen.id)
            .join(Sample, Sample.id == Specimen.sample_id)
            .where(Sample.material_id.in_(permissions.visible_material_ids(db, user)))
        )
    )


def get_run(db: Session, user: User, run_id: uuid.UUID) -> TestRun:
    run = db.scalar(visible_runs(db, user).where(TestRun.id == run_id))
    if run is None:
        raise NotFound("MNX-TESTS-0001", "시험을 찾을 수 없습니다.")
    return run


def get_test_type(db: Session, key: str) -> TestType:
    test_type = db.scalar(select(TestType).where(TestType.key == key))
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

    if field.dimension and resolved.dimension != field.dimension:
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
    if not test_type.parser_key:
        return _fail(db, run, f"'{test_type.label}' 에는 파서가 없습니다.")
    if not run.source_path:
        return _fail(db, run, "원본 파일이 등록되지 않았습니다.")

    run.status = "parsing"
    db.commit()

    parsers.load_builtin()
    try:
        plugin = registry.get(test_type.parser_key)
    except KeyError:
        return _fail(db, run, f"등록되지 않은 파서입니다: {test_type.parser_key}")

    data = filestore.read_bytes(run.source_path)  # 인프라 오류는 그대로 올린다
    try:
        parsed: ParsedTest = plugin.fn(data)
    except ParseError as exc:
        return _fail(db, run, str(exc))
    except Exception as exc:  # 파서 버그도 그 파일에서는 계속 난다
        logger.exception("파서가 예상치 못한 예외를 냈습니다 (run=%s)", run.id)
        return _fail(db, run, f"파일을 읽는 중 오류가 났습니다: {exc}")

    missing = _missing_required_channels(db, test_type, parsed)
    if missing:
        return _fail(
            db,
            run,
            f"필수 채널이 없습니다: {', '.join(missing)}. "
            f"장비 설정이나 시험 종류 정의를 확인하세요.",
        )

    _store_curve(db, run, parsed, parser_version=plugin.version)
    _store_summary(db, run, parsed)

    run.source_metadata = dict(parsed.metadata)
    run.parser_version = plugin.version
    run.status = "parsed"
    run.parse_error = None
    if parsed.warnings:
        # 경고는 실패가 아니지만 사라지면 안 된다. 상세 화면이 그대로 보여 준다.
        run.source_metadata = {
            **run.source_metadata,
            "_warnings": " / ".join(parsed.warnings),
        }
    db.commit()
    logger.info(
        "파싱 완료 %s — %d행 %d채널 (경고 %d)",
        run.record_name,
        parsed.row_count,
        len(parsed.channels),
        len(parsed.warnings),
    )
    return "parsed"


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
    present = {channel.key for channel in parsed.channels}
    return [key for key in required if key not in present]


def _store_curve(
    db: Session, run: TestRun, parsed: ParsedTest, *, parser_version: str
) -> None:
    """Parquet 을 쓰고 Curve 행을 만든다. 다시 파싱하면 이전 것을 갈아치운다.

    Curve 는 불변이지만 **재파싱은 새 사실이 아니라 같은 원본의 다시 읽기**다.
    파서를 고쳐 다시 돌렸을 때 옛 곡선이 남아 있으면 어느 것이 현재인지 화면이
    판단해야 한다.
    """
    directory = f"{filestore.run_dir(run.id, run.created_at)}/curves"
    payload = curves.to_parquet(parsed.channels)
    stored = filestore.write_bytes(
        payload, relative_dir=directory, filename=f"{RAW_CURVE}.parquet"
    )

    existing = db.scalar(
        select(Curve).where(Curve.test_run_id == run.id, Curve.key == RAW_CURVE)
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    db.add(
        Curve(
            test_run_id=run.id,
            key=RAW_CURVE,
            label=f"원본 정규화 (parser {parser_version})",
            storage_path=stored.relative_path,
            row_count=parsed.row_count,
            sha256=stored.sha256,
            byte_size=stored.size,
            channels=[channel.key for channel in parsed.channels],
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


# --- 오펀 정리 --------------------------------------------------------------


def cleanup_orphans(db: Session, *, dry_run: bool = True) -> dict[str, Any]:
    """DB 에 없는 시험 폴더를 찾는다(그리고 `dry_run=False` 면 지운다).

    **방향이 중요하다.** DB 를 훑어 파일을 확인하는 방식으로는 오펀을 찾을 수
    없다 — 오펀은 정의상 DB 에 없다. 파일시스템에서 시작해 DB 를 조회해야 한다.

    기본이 `dry_run` 인 이유: 이 잡의 실수는 되돌릴 수 없다. 먼저 목록을 보고
    납득한 뒤에 지운다.
    """
    found: list[str] = []
    removed: list[str] = []

    for relative in filestore.existing_run_dirs():
        raw_id = relative.rsplit("/", 1)[-1]
        try:
            run_id = uuid.UUID(raw_id)
        except ValueError:
            # 우리가 만들지 않은 폴더다. 남의 파일을 지우지 않는다.
            logger.warning("시험 폴더 이름이 UUID 가 아닙니다: %s", relative)
            continue
        if db.get(TestRun, run_id) is not None:
            continue
        found.append(relative)
        if not dry_run and filestore.delete_dir(relative):
            removed.append(relative)

    logger.info(
        "오펀 정리: 발견 %d건, 삭제 %d건 (dry_run=%s)", len(found), len(removed), dry_run
    )
    return {"found": found, "removed": removed, "dry_run": dry_run}


# --- 곡선 읽기 --------------------------------------------------------------


def curve_points(
    db: Session, run: TestRun, *, x: str, y: str, max_points: int
) -> dict[str, Any]:
    """차트가 쓸 점들. 필요한 두 열만 읽고 축약한다.

    전부 보내지 않는 이유는 크기다. 3만 점이면 JSON 이 수 MB 가 되고, 그 대부분은
    화면 픽셀 하나에 겹쳐 그려진다.
    """
    curve = db.scalar(select(Curve).where(Curve.test_run_id == run.id, Curve.key == RAW_CURVE))
    if curve is None:
        raise NotFound("MNX-TESTS-0009", "정규화된 곡선이 아직 없습니다.")

    available = set(curve.channels)
    missing = [key for key in (x, y) if key not in available]
    if missing:
        raise AppError(
            "MNX-TESTS-0010",
            f"이 시험에 없는 채널입니다: {', '.join(missing)} "
            f"(있는 것: {', '.join(sorted(available))})",
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
    "cleanup_orphans",
    "condition_fields",
    "curve_points",
    "default_axes",
    "get_run",
    "get_test_type",
    "next_run_seq",
    "normalize_conditions",
    "parse_run",
    "run_counts",
    "upload_limit",
    "visible_runs",
]
