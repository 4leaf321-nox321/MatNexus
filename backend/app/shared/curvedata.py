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

from collections.abc import Mapping, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample, Specimen
from app.modules.tests.models import Curve, TestChannel, TestRun
from app.modules.vocabulary.services import Field
from app.shared import filestore, specimen_size
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


#: 파이프라인이 `@declared_…` 로 참조할 수 있는 선언 물성. **이름을 여기 적는다** —
#: 기준정보의 항목 이름(사람이 고치는 말)과 참조 키(레시피에 적히는 말)를 잇는 자리다.
DECLARED_KEYS = {"탄성계수": "youngs_modulus", "포아송비": "poisson_ratio", "밀도": "density"}


def declared_scalars(db: Session, run: TestRun) -> list[processing.Scalar]:
    """재료에 **사람이 적어 둔** 물성을 파이프라인에 넘긴다(ADR 0016).

    ## 왜 필요한가

    탄성 구간에 점이 몇 개 없는 곡선이 있다. 장비가 성기게 찍었거나, 그 재료가
    거의 곧바로 항복한다 — 그러면 탄성계수 단계가 **값을 거절한다**(그것이 맞다:
    두어 점을 지나는 직선은 언제나 R²≈1 이라 맞았는지 알 수 없다). 그런데 항복강도는
    탄성계수가 있어야 그을 수 있어서, 거기서 처리가 통째로 막힌다.

    실사용에서 그 막다른 길이 나왔다(2026-09-02: 「자동으로 해도 안 된다. 탄성구간에
    점이 실제로 적을 수도 있잖아?」). 답은 **아는 값을 쓰는 것**이다 — 강판의
    탄성계수는 재료에 적혀 있고, 그것이 선언 물성이 있는 이유다.

    레시피에 이렇게 적는다:

        {"plugin": "tensile.elastic_modulus",
         "options": {"method": "manual", "youngs_modulus": "@declared_youngs_modulus"}}

    **잰 값과 한 글자도 안 겹치는 이름을 준다**(`declared_` 접두어). 결과를 보는
    사람이 잰 값인지 적은 값인지 구별할 수 있어야 하고, 그 구별이 카드에 근거를
    박는 이유 전부다.

    없는 값은 넘기지 않는다 — 참조가 「그 값이 없습니다」 로 실패하는 편이,
    0 이 조용히 섞이는 것보다 낫다.
    """
    specimen = db.get(Specimen, run.specimen_id)
    if specimen is None:
        return []
    sample = db.get(Sample, specimen.sample_id)
    material = db.get(Material, sample.material_id) if sample else None
    if material is None:
        return []

    given: list[processing.Scalar] = []
    for row in material.declared_properties or []:
        key = DECLARED_KEYS.get(str(row.get("item")))
        if key is None:
            continue
        # **대푯값은 첫 점이다.** 온도를 타는 값이면 가장 낮은 온도(대개 상온)다.
        points = [
            point
            for point in (row.get("points") or [])
            if isinstance(point.get("value_si"), int | float)
        ]
        if not points:
            continue
        given.append(
            processing.Scalar(
                f"declared_{key}",
                f"재료에 적은 {row.get('item')}",
                float(points[0]["value_si"]),
                str(row.get("si_unit") or ""),
            )
        )
    return given


def specimen_scalars(db: Session, run: TestRun) -> list[processing.Scalar]:
    """시편 치수를 파이프라인이 `@` 로 참조할 수 있게 넘긴다.

    **규격에서 물려받은 값도 넘어간다.** 시편이 비어 있어도 그 규격이 공칭을
    갖고 있으면 그것으로 돈다(`specimen_size`) — 시편 41개 중 치수가 있는 것이
    3개뿐이라 처리가 첫 단계에서 막히던 문제가 여기서 풀린다. 잰 값이 있으면
    그것이 이긴다.

    **읽는 순서는 셋이다** — 이 시험이 잰 값 → 시편에 적힌 값 → 규격 공칭.
    치수는 그 시험에서 잰 값이라 앞엣것이 이긴다(`specimen_size.sizes_of`).

    **없는 값은 넘기지 않는다.** 0 이나 기본값으로 채우면 응력이 조용히 틀린다 —
    단면적이 잘못되면 자릿수가 통째로 어긋나는데 숫자는 그럴듯해 보인다. 없으면
    `@specimen_area` 참조가 "그 값이 없습니다" 로 실패하고, 그게 맞다.
    """
    specimen = db.get(Specimen, run.specimen_id)
    if specimen is None:
        return []

    # **이 시험이 잰 값이 먼저다.** 같은 시편에 시험이 여럿이면 시편 한 벌을
    # 나눠 쓰게 되는데, 치수는 그 시험에서 잰 값이다(실사용에서 나왔다).
    sizes = specimen_size.sizes_of(db, specimen, run.dimensions or {})
    given: list[processing.Scalar] = [
        processing.Scalar(
            f"specimen_{item.key}", f"시편 {item.label}", item.value, item.si_unit
        )
        for item in sizes.items
    ]

    # 단면적은 **규격이 고른 식**으로 낸다 — 평판은 폭 곱하기 두께, 환봉은
    # π(직경/2)². 식을 안 골랐으면 옛 규칙(폭·두께)으로 되돌아간다.
    area = specimen_size.area_of(db, specimen, run.dimensions or {})
    if area:
        given.append(processing.Scalar("specimen_area", "시편 초기 단면적", area, "m2"))
    return given


def condition_scalars(db: Session, run: TestRun) -> list[processing.Scalar]:
    """이 시험의 **조건**을 파이프라인이 `@` 로 참조할 수 있게 넘긴다.

    ## 왜 필요했나

    실사용에서 나왔다 — *"거긴 시험 종류에서 정의하잖아? 그럼 거기서 정의된 걸
    처리에서 받아가서 정의하도록 해야 하는데, 그게 지금은 안 돼"*.

    맞는 지적이다. 시험 종류가 조건을 선언하고(속도·온도·예하중), 업로드가 그
    값을 받아 SI 로 담는데, **처리는 그것을 볼 길이 없었다.** 시편 치수만
    넘어가고 있었다.

    처리에는 조건을 써야 하는 자리가 실제로 있다 — 변형률 속도로 나누는 보정,
    온도에 따른 시프트, 예하중 빼기. 그때마다 사람이 숫자를 손으로 옮겨 적으면,
    그 숫자는 **조건이 고쳐져도 안 따라간다.**

    ## 숫자만 넘긴다

    `sensor_type` 같은 글자 조건은 계산에 못 쓴다. 넘기면 `@sensor_type` 이
    이어 붙는 자리에 뜨는데, 고르고 나면 파이프라인이 "숫자가 아닙니다" 로
    멈춘다 — 고를 수 있는데 못 쓰는 것이 가장 나쁘다.

    ## 이름에 접두어를 둔다

    `condition_` 을 붙인다. 조건 키는 시험 종류가 정하므로 채널 이름과 겹칠 수
    있고(둘 다 `temperature` 를 쓸 수 있다), 겹치면 어느 것이 이어졌는지 알 수
    없게 된다.
    """
    from app.modules.tests.models import TestConditionField

    fields = list(
        db.scalars(
            select(TestConditionField)
            .where(TestConditionField.test_type_id == run.test_type_id)
            .order_by(TestConditionField.sort_order)
        )
    )
    given: list[processing.Scalar] = []
    for field in fields:
        if field.value_type != "number":
            continue
        value = (run.conditions or {}).get(field.key)
        if not isinstance(value, int | float):
            continue
        given.append(
            processing.Scalar(
                f"condition_{field.key}",
                field.label,
                float(value),
                field.si_unit or "1",
            )
        )
    return given


def specimen_sources(db: Session, run: TestRun) -> dict[str, str]:
    """`specimen_scalars` 가 낸 값이 **어디서 왔는가.** 키는 같은 이름이다.

    `matcore.processing.Scalar` 에 넣지 않는다 — 그 층은 계산만 알아야 하고,
    출처는 화면이 사람에게 설명하려고 쓰는 값이다.

        run       이 시험이 잰 값 (그 파일의 a0·b0)
        measured  시편에 적힌 값
        nominal   규격이 정한 공칭

    **왜 보여 줘야 하나:** 치수가 세 곳에 살 수 있게 되면서 "어느 게 맞느냐" 를
    묻게 됐다. 답이 안 보이면 그 자리가 조용히 틀리는 자리가 된다.
    """
    specimen = db.get(Specimen, run.specimen_id)
    if specimen is None:
        return {}
    sizes = specimen_size.sizes_of(db, specimen, run.dimensions or {})
    return {f"specimen_{item.key}": item.source for item in sizes.items}


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
    "thickness": ("specimen_thickness", "specimen_thickness_a0", "thickness"),
    "width": ("specimen_width", "specimen_width_b0", "width"),
    "gauge_length": ("gauge_length", "specimen_gauge_length", "l0", "specimen_length"),
}


def _as_metres(raw: object, unit_hint: str | None) -> float | None:
    """`"0.989 mm"` · `"0.986"`(+단위 힌트) 을 m 로.

    **단위를 못 찾으면 포기한다.** 숫자만 있고 단위를 모를 때 mm 라고 가정하면,
    m 로 적힌 파일에서 1000배 틀린 시편이 만들어진다 — 그 뒤 응력이 통째로
    어긋나는데 숫자는 그럴듯하다.

    **길이가 아닌 단위도 포기한다.** 파일이 `"1.2 kg"` 이라고 적어 오면 `kg` 은
    아는 단위라 환산이 무사히 끝나고, 그 1.2 가 아래 범위 검사까지 통과해
    **두께 1.2 m 짜리 시편**이 된다. 프로파일은 열마다 단위를 지정할 수 있으므로
    이것은 가정이 아니라 한 글자 오타면 나는 일이다.
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
        found = units.unit_of(symbol)
    except units.UnknownUnit:
        return None
    if not units.same_dimension(found.dimension, "length"):
        return None
    metres = units.to_si(value, symbol)
    if not (0 < metres < 10):
        # 길이는 맞는데 자릿수가 틀린 경우 — 시편이 10m 일 리 없다.
        return None
    return metres


def _candidates(field: Field) -> tuple[str, ...]:
    """이 칸을 가리킬 만한 파일 항목 이름들. **앞엣것이 먼저다.**

    ## 기호로도 찾는다

    **장비 파일의 항목 이름이 곧 규격 기호다.** Zwick 은 두께를 `a0`, 폭을 `b0`,
    직경을 `d0` 로 적는다 — 규격서 도면의 글자를 그대로 쓴 것이다. 규격의 칸이
    그 글자를 갖고 있으므로(`symbol`), 이름이 안 맞아도 글자로 이을 수 있다.

    그래서 규격에 칸을 더하고 기호를 적어 두면 **파일 채우기가 저절로 따라온다.**
    전에는 두께·폭·게이지 셋만 아는 표가 코드에 박혀 있어서, 환봉 파일의 직경은
    갈 곳이 없었다.
    """
    names = [*DIMENSION_ALIASES.get(field.key, ()), field.key, f"specimen_{field.key}"]
    if field.symbol:
        mark = field.symbol.strip().lower()
        # `Specimen diameter d0` → `specimen_diameter_d0`. 글자만으로도 받는다 —
        # 항목 이름이 `d0` 하나인 파일이 있다.
        names += [
            mark,
            f"specimen_{mark}",
            f"{field.key}_{mark}",
            f"specimen_{field.key}_{mark}",
        ]
    return tuple(dict.fromkeys(names))


def instrument_dimensions(
    metadata: Mapping[str, object], fields: Sequence[Field] = ()
) -> dict[str, float]:
    """장비 파일이 준 시편 치수. 못 찾은 것은 빠진 채로 온다.

    `fields` 는 그 시편의 **규격이 선언한 칸**이다. 주면 그 칸들을 이름과 기호로
    찾고, 안 주면 옛 셋(두께·폭·게이지)만 찾는다.
    """
    known = list(fields) or [
        Field(
            key=key,
            label=key,
            dimension="length",
            si_unit="m",
            is_required=False,
            help=None,
            inherited=False,
        )
        for key in DIMENSION_ALIASES
    ]

    found: dict[str, float] = {}
    for field in known:
        if field.kind != "number":
            continue
        for alias in _candidates(field):
            if alias not in metadata:
                continue
            metres = _as_metres(
                metadata[alias], str(metadata.get(f"{alias}_unit") or "") or None
            )
            if metres is not None:
                found[field.key] = metres
                break
    return found
