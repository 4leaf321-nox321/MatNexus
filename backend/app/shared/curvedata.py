"""저장된 곡선을 계산 커널이 쓰는 `Frame` 으로 — **저장소와 matcore 사이의 다리.**

`matcore` 는 DB 도 파일시스템도 모른다(그것이 이 설계의 전제다). 그런데 곡선은
Parquet 파일에 있고, 단위는 시험종류 정의에 있고, 시편 치수는 `Specimen` 에 있다.
그 셋을 모아 `Frame` 을 만드는 일이 어딘가에는 있어야 한다.

**왜 `shared` 인가.** 처음에는 처리 모듈 안에 두었는데, Phase 3~4 에서 통계·적합·
내보내기가 전부 같은 것을 필요로 한다. 각자 자기 버전을 갖게 두면 "처리는 이
단위로 읽는데 통계는 저 단위로 읽는" 어긋남이 생기고, 그 어긋남은 숫자로만
드러나서 아무도 못 본다. 재료 가시 범위를 `permissions` 한 곳에 둔 것과 같은
판단이다.

여기는 **읽기만 한다.** 계산도 저장도 하지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Specimen
from app.modules.tests.models import Curve, TestChannel, TestRun
from app.shared import filestore
from app.shared.errors import NotFound
from matcore import curves, processing, units

#: 정규화 곡선의 기본 키. 표가 하나뿐인 파일(대부분)에서 쓰인다.
RAW_CURVE = "raw"


def curves_of(db: Session, run_id: object) -> list[Curve]:
    """시험의 곡선 전부. **`raw` 만 보면 안 된다.**

    한 파일이 곡선을 여럿 낸다(TA DMA850 주파수-온도 스윕은 8벌). 그때 키는 표
    이름의 slug 이고 `raw` 는 아예 없다 — `raw` 만 찾던 화면들이 저장된 곡선을
    하나도 못 봤다. `raw` 를 맨 앞에 두어 표가 하나뿐인 파일에서 예전과 같은
    것이 기본이 되게 한다.
    """
    rows = list(db.scalars(select(Curve).where(Curve.test_run_id == run_id)))
    return sorted(rows, key=lambda c: (c.key != RAW_CURVE, c.key))


def channel_units(db: Session, test_type_id: object) -> dict[str, str]:
    """채널 키 → 저장 단위.

    계산은 **단위를 믿고** 돈다. 변형률이 % 로 들어오면 100배 어긋나는데 곡선을
    봐서는 알 수 없다. 그래서 정의에 적힌 단위를 값과 함께 실어 보낸다.
    """
    rows = db.execute(
        select(TestChannel.key, TestChannel.si_unit).where(
            TestChannel.test_type_id == test_type_id
        )
    )
    return {key: si_unit for key, si_unit in rows}


def load_frame(
    db: Session, run: TestRun, curve_key: str | None
) -> tuple[processing.Frame, Curve]:
    """곡선 하나를 `Frame` 으로 읽는다."""
    available = curves_of(db, run.id)
    if not available:
        raise NotFound(
            "MNX-PROCESSING-0001",
            "정규화된 곡선이 아직 없습니다. 파일이 읽히기를 기다리거나 다시 읽으세요.",
        )
    curve = (
        next((item for item in available if item.key == curve_key), None)
        if curve_key
        else available[0]
    )
    if curve is None:
        keys = ", ".join(item.key for item in available)
        raise NotFound(
            "MNX-PROCESSING-0002", f"'{curve_key}' 곡선이 없습니다. 있는 곡선: {keys}"
        )

    raw = curves.read_columns(filestore.read_bytes(curve.storage_path))
    units = channel_units(db, run.test_type_id)
    columns = {
        name: np.asarray(
            [np.nan if value is None else float(value) for value in values], dtype=np.float64
        )
        for name, values in raw.items()
    }
    return processing.Frame(columns, {name: units.get(name, "1") for name in columns}), curve


def specimen_scalars(db: Session, run: TestRun) -> list[processing.Scalar]:
    """시편 치수를 파이프라인이 `@` 로 참조할 수 있게 넘긴다.

    **없는 값은 넘기지 않는다.** 0 이나 기본값으로 채우면 응력이 조용히 틀린다 —
    단면적이 잘못되면 자릿수가 통째로 어긋나는데 숫자는 그럴듯해 보인다. 없으면
    `@specimen_area` 참조가 "그 값이 없습니다" 로 실패하고, 그게 맞다.

    일괄 등록으로 만든 시편은 치수가 비어 있는 것이 정상이라 이 실패는 자주 난다.
    """
    specimen = db.get(Specimen, run.specimen_id)
    if specimen is None:
        return []
    given: list[processing.Scalar] = []
    if specimen.gauge_length_m:
        given.append(
            processing.Scalar(
                "specimen_gauge_length", "시편 게이지 길이", specimen.gauge_length_m, "m"
            )
        )
    if specimen.width_m:
        given.append(processing.Scalar("specimen_width", "시편 폭", specimen.width_m, "m"))
    if specimen.thickness_m:
        given.append(
            processing.Scalar("specimen_thickness", "시편 두께", specimen.thickness_m, "m")
        )
    if specimen.width_m and specimen.thickness_m:
        given.append(
            processing.Scalar(
                "specimen_area",
                "시편 초기 단면적",
                specimen.width_m * specimen.thickness_m,
                "m2",
            )
        )
    return given


# --- 장비가 준 시편 치수 ------------------------------------------------------

#: 파일 메타데이터에서 시편 치수를 찾는 이름들.
#:
#: **파서마다 이름이 다르다.** Zwick 은 규격 기호를 그대로 쓰고(`a0`=두께,
#: `b0`=폭), 프로파일로 읽는 파일은 프로파일에 적힌 이름을 쓴다. 실측:
#:
#:     Zwick .tra   specimen_thickness_a0 = "0.986",  specimen_width_b0 = "12.473"
#:     TA DMA .csv  specimen_thickness    = "0.989 mm", specimen_width = "4.938 mm"
#:
#: 값의 모양도 다르다 — 한쪽은 숫자만 오고 단위가 별도 키에 있고, 다른 쪽은
#: `"0.989 mm"` 한 문자열이다. 여기서 둘 다 받는다.
#:
#: 파서 출력 키를 통일하지 않는 이유: 이미 저장된 `source_metadata` 가 있고,
#: 그것을 바꾸려면 마이그레이션이 필요하다. 읽는 쪽에서 별칭을 아는 편이 싸다.
DIMENSION_ALIASES: dict[str, tuple[str, ...]] = {
    "thickness_m": ("specimen_thickness", "specimen_thickness_a0", "thickness"),
    "width_m": ("specimen_width", "specimen_width_b0", "width"),
    "gauge_length_m": ("gauge_length", "specimen_gauge_length", "l0", "specimen_length"),
}


def _as_metres(raw: object, unit_hint: str | None) -> float | None:
    """`"0.989 mm"` · `"0.986"`(+단위 힌트) 을 m 로.

    **단위를 못 찾으면 포기한다.** 숫자만 있고 단위를 모를 때 mm 라고 가정하면,
    m 로 적힌 파일에서 1000배 틀린 시편이 만들어진다 — 그 뒤 응력이 통째로
    어긋나는데 숫자는 그럴듯하다.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    parts = text.split()
    number_text, symbol = (parts[0], parts[1]) if len(parts) >= 2 else (text, unit_hint)
    if not symbol:
        return None
    try:
        value = float(number_text)
    except ValueError:
        return None
    try:
        metres = units.to_si(value, symbol)
    except units.UnknownUnit:
        return None
    if not (0 < metres < 10):
        # 시편이 10m 일 리 없다. 단위를 잘못 읽었다는 신호다.
        return None
    return metres


def instrument_dimensions(metadata: Mapping[str, object]) -> dict[str, float]:
    """장비 파일이 준 시편 치수. 못 찾은 것은 빠진 채로 온다."""
    found: dict[str, float] = {}
    for field, aliases in DIMENSION_ALIASES.items():
        for alias in aliases:
            if alias not in metadata:
                continue
            metres = _as_metres(
                metadata[alias], str(metadata.get(f"{alias}_unit") or "") or None
            )
            if metres is not None:
                found[field] = metres
                break
    return found
