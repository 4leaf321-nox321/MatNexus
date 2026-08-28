"""파일 하나가 시험이 되는 길 — **화면 업로드와 장비 커넥터가 같은 길을 쓴다.**

## 왜 shared 에 있나

시험을 만드는 자리가 둘이 됐다. 사람이 화면에서 올리는 것(`tests`)과 장비 PC 가
밀어 넣는 것(`pipelines`). 모듈끼리 직접 부르지 않으므로, 둘이 같아야 하는 것을
여기 둔다 — 종류 감지 · 회차 받기 · 이름 짓기 · 파싱 큐 넣기.

같아야 하는 이유는 규칙이 아니라 사고다. 회차 충돌 재시도(`contention`)를 한쪽만
갖고 있으면 다른 쪽은 같은 순간에 두 파일이 오면 500 을 낸다. 장비는 배치로
보내므로 **그쪽이 더 자주 부딪힌다.**

## 감지는 가시 범위가 아니라 부서로 본다

화면의 `/test-types/detect` 는 **보는 사람**의 가시 범위로 프로파일을 고른다.
커넥터에는 사람이 없다 — 커넥터가 속한 **부서**의 것과 전역을 본다. 그것이
`parse_run` 이 파싱할 때 보는 범위와 같다. 감지와 파싱이 다른 범위를 보면
「감지는 됐는데 파싱은 못 읽는」 상태가 생긴다.
"""

from __future__ import annotations

import contextlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.jobs import kinds, queue
from app.modules.materials.models import Specimen
from app.modules.tests.models import FormatProfile, TestRun, TestType
from app.shared import contention, filestore
from matcore import naming, parsers, readers, registry
from matcore.readers import profile as profiles

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Detected:
    """이 파일을 무엇으로 읽을 수 있나."""

    test_type: TestType | None
    profile: FormatProfile | None
    reason: str

    @property
    def found(self) -> bool:
        return self.test_type is not None


def _extensions(parser_key: str | None) -> list[str]:
    if not parser_key:
        return []
    parsers.load_builtin()
    try:
        plugin = registry.get(parser_key)
    except KeyError:
        return []
    return [str(one).lower() for one in plugin.meta.get("extensions", ())]


def detect(db: Session, *, workspace_id: uuid.UUID, filename: str, data: bytes) -> Detected:
    """어느 시험 종류인가. **프로파일의 지문이 먼저, 확장자는 그다음.**

    `.csv` 는 어느 장비나 쓰지만 헤더의 열 이름은 그 장비의 것이다.
    """
    suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""

    candidates = list(
        db.scalars(
            select(FormatProfile)
            .where(
                FormatProfile.is_active.is_(True),
                or_(
                    FormatProfile.owner_workspace_id.is_(None),
                    FormatProfile.owner_workspace_id == workspace_id,
                ),
            )
            # 내 부서 것이 전역보다 먼저 — `_pick_reader` 와 같은 순서다.
            .order_by(
                FormatProfile.owner_workspace_id.is_(None),
                FormatProfile.priority.desc(),
                FormatProfile.key,
            )
        )
    )
    try:
        structure = readers.sniff(data)
    except readers.ReadError:
        structure = None

    if structure is not None:
        for candidate in candidates:
            if not profiles.matches(
                candidate.definition, filename=filename, structure=structure
            ):
                continue
            test_type = db.get(TestType, candidate.test_type_id)
            if test_type is None or not test_type.is_active:
                continue
            return Detected(
                test_type, candidate, f"'{candidate.label}' 프로파일의 지문이 맞습니다."
            )

    if suffix:
        matched = [
            test_type
            for test_type in db.scalars(
                select(TestType)
                .where(TestType.is_active.is_(True))
                .order_by(TestType.sort_order, TestType.label)
            )
            if suffix in _extensions(test_type.parser_key)
        ]
        if len(matched) == 1:
            return Detected(matched[0], None, f"{suffix} 를 읽는 종류가 하나입니다.")
        if len(matched) > 1:
            # **여럿이면 고르지 않는다.** 하나를 찍으면 그럴듯해 보이는데 틀린다.
            names = ", ".join(t.label for t in matched)
            return Detected(
                None, None, f"{suffix} 를 읽는 종류가 {len(matched)}개입니다: {names}."
            )

    return Detected(None, None, "맞는 프로파일도 확장자도 없습니다. 형식 프로파일을 만드세요.")


def parse_with(detected: Detected, data: bytes) -> parsers.ParsedTest:
    """감지한 것으로 읽는다. 실패는 `ParseError` 로 올라온다."""
    if detected.profile is not None:
        return profiles.apply(detected.profile.definition, data)
    if detected.test_type is not None and detected.test_type.parser_key:
        parsers.load_builtin()
        plugin = registry.get(detected.test_type.parser_key)
        result: parsers.ParsedTest = plugin.fn(data)
        return result
    raise parsers.ParseError("읽을 방법이 없습니다.")


@dataclass(frozen=True)
class Source:
    """이미 filestore 에 있는 원본."""

    relative_path: str
    filename: str
    sha256: str
    size: int


def create_run(
    db: Session,
    *,
    specimen: Specimen,
    test_type: TestType,
    source: Source,
    registered_by_id: uuid.UUID | None,
    tested_at: datetime | None = None,
    operator: str | None = None,
    instrument: str | None = None,
    note: str | None = None,
    profile_id: uuid.UUID | None = None,
    conflict_code: str,
) -> TestRun:
    """저장된 원본으로 시험을 만들고 파싱을 큐에 넣는다. **커밋은 부르는 쪽이 한다.**

    원본은 `test-runs/…/source/` 로 **옮긴다.** 복사하면 두 벌이 되고, 정리 잡이
    어느 것을 지워야 하는지 모른다.
    """
    from app.modules.vocabulary import services as vocabulary_services

    def _make() -> TestRun:
        # 번호 읽기부터 flush 까지 한 덩이 — 다시 할 때 번호도 다시 읽어야 한다.
        seq_no = _next_seq(db, specimen.id, test_type.id)
        made = TestRun(
            workspace_id=specimen.workspace_id,
            specimen_id=specimen.id,
            test_type_id=test_type.id,
            seq_no=seq_no,
            record_name=naming.test_run_name(
                specimen=specimen.record_name, type_abbr=test_type.abbr, seq_no=seq_no
            ),
            conditions={},
            input_units={},
            tested_at=tested_at,
            operator=operator,
            note=note,
            status="uploaded",
            registered_by_id=registered_by_id,
            parse_profile_id=profile_id,
        )
        vocabulary_services.apply_bindings(
            db,
            made,
            vocabulary_services.TEST_RUN_BINDINGS,
            {"instrument": instrument},
            created_by_id=registered_by_id,
        )
        db.add(made)
        db.flush()
        return made

    run = contention.with_retry(
        db,
        _make,
        code=conflict_code,
        message="같은 순간에 이 시편에 시험이 여럿 올라오고 있습니다. 다시 시도해 주세요.",
    )
    db.refresh(run)

    target_dir = f"{filestore.run_dir(run.id, run.created_at)}/source"
    moved = move_source(source, target_dir)
    run.source_filename = source.filename
    run.source_path = moved
    run.source_sha256 = source.sha256
    run.source_bytes = source.size

    queue.enqueue(db, kind=kinds.TESTS_PARSE_UPLOAD, payload={"test_run_id": str(run.id)})
    return run


def move_source(source: Source, target_dir: str) -> str:
    """원본을 옮기고 새 상대경로를 돌려준다."""
    origin = filestore.resolve(source.relative_path)
    destination_dir = filestore.resolve(target_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / origin.name
    os.replace(origin, destination)
    # 비워진 폴더는 치운다 — 남겨 두면 오펀 탐색이 「파일 없는 폴더」 를 센다.
    # `source/` 와 그 위 항목 폴더까지, 비어 있는 동안만.
    for empty in (origin.parent, origin.parent.parent):
        with contextlib.suppress(OSError):
            empty.rmdir()
    return f"{target_dir}/{origin.name}"


def _next_seq(db: Session, specimen_id: uuid.UUID, test_type_id: uuid.UUID) -> int:
    """회차. 지운 회차의 번호는 다시 안 쓴다 — `tests.services.next_run_seq` 와 같다."""
    from sqlalchemy import func

    highest = db.scalar(
        select(func.max(TestRun.seq_no)).where(
            TestRun.specimen_id == specimen_id, TestRun.test_type_id == test_type_id
        )
    )
    return int(highest or 0) + 1


def summarize(parsed: parsers.ParsedTest) -> dict[str, Any]:
    """사람이 「맞는 파일인가」 를 볼 만큼만."""
    curves = parsed.curves or ()
    first = curves[0] if curves else None
    channels = [c.key for c in first.channels] if first else [c.key for c in parsed.channels]
    rows = 0
    if first and first.channels:
        rows = len(first.channels[0].values)
    elif parsed.channels:
        rows = len(parsed.channels[0].values)
    return {
        "channels": channels[:12],
        "row_count": rows,
        "curve_count": len(curves),
        "summary": {s.key: s.value for s in parsed.summary[:8]},
        "identity": dict(parsed.identity),
        "record": dict(parsed.record),
        "warnings": list(parsed.warnings[:5]),
    }
