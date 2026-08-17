"""Zwick 인장시험 `.tra` 파서.

실제 파일(`002_Material/.../Example.tra`)을 읽고 확인한 구조:

    "Strain (plastic) at break",54.2415,"%"        ← 결과 요약 (여러 줄)
    "Yield strain","Unknown"                       ← 장비가 못 구하면 문자열
    "Force maximum",282.128,"MPa"
    "Specimen thickness a0",0.986,"mm"
    "Standard extensometer ","Standard load cell ","Specimen width"   ← 채널 이름
    "mm","N","mm"                                                     ← 채널 단위
    1.46484e-007,19.4642,12.473                                       ← 수치
    ...

**요약부의 줄 수가 파일마다 같다고 가정하지 않는다.** 장비 설정에 따라 항목이
늘고 준다. 그래서 "처음으로 모든 칸이 숫자인 줄"을 찾아 거기서부터 데이터로 보고,
그 바로 위 두 줄을 단위와 이름으로 읽는다. 줄 번호를 고정하면 항목이 하나 늘어난
파일에서 채널 이름 자리에 요약값이 들어오는데, **그래도 파싱은 성공해 버린다** —
그런 실패가 가장 나쁘다.

**장비가 주는 것은 응력-변형률이 아니다.** 변위(mm)·하중(N)·시편폭(mm) 이다.
공칭↔진응력 변환과 n·r 값 재계산은 MatNexus 가 한다. 요약부에 장비가 계산한 값이
이미 들어 있지만, 그것은 `source="instrument"` 로 따로 보관해 우리 계산과 나란히
둔다 — 섞으면 나중에 계산식을 고쳤을 때 무엇이 바뀐 값인지 알 수 없다.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence

from matcore import registry, units
from matcore.parsers import Channel, ParsedTest, ParseError, SummaryValue

#: 채널 이름(원문) → 우리 키. 원문에 뒤따르는 공백이 있어 정규화 후 비교한다.
#: 여기에 없는 채널은 버리지 않고 slug 로 담되 경고를 남긴다 — 장비 설정이 바뀌어
#: 채널이 하나 늘었을 때, 조용히 사라지면 아무도 모른다.
CHANNEL_KEYS = {
    "standard extensometer": "displacement",
    "standard load cell": "force",
    "specimen width": "specimen_width",
    # 아래 둘은 **코퍼스에 사례가 없는 추정**이다(Zwick 이 크로스헤드·로드셀에
    # 쓰는 다른 표기). 맞을 가능성이 높아 두지만, 실제 파일로 확인되기 전까지는
    # 근거가 관측이 아니라 짐작이라는 것을 알고 있어야 한다.
    "standard travel": "displacement",
    "standard force": "force",
}

#: 요약 항목(원문, `{...}` 제거·소문자) → 우리 키.
SUMMARY_KEYS = {
    "strain (plastic) at break": "strain_plastic_at_break",
    "strain at break": "strain_at_break",
    "yield strain": "yield_strain",
    "strain (plastic) at fmax": "strain_plastic_at_fmax",
    "strain at fmax": "strain_at_fmax",
    "work hardening coefficient k": "hardening_k",
    "work hardening exponent n": "hardening_n",
    "vertical anisotropy r": "anisotropy_r",
    "upper yield point": "upper_yield",
    "lower yield point": "lower_yield",
    # **'Force maximum' 은 힘이 아니라 응력이다.** 단위가 MPa 이고, 실제로
    # Fmax/A0 와 0.1% 안에서 일치한다(3466.4 N / (0.986*12.473) mm2 = 281.9 MPa
    # vs 파일값 282.128 MPa). 이름을 그대로 두면 우리가 계산한 인장강도와
    # 나란히 놓을 때 서로 다른 물리량으로 보인다 — key 는 물리량 이름이어야 한다.
    "force maximum": "tensile_strength",
    # 바로 위 `force maximum` 과 **같은 이유**로 이름을 맞춘다. 그런데 이것만
    # `proof_stress_02` 로 남아 있어서, 장비가 잰 항복강도와 우리가 계산한
    # 항복강도가 요약값 표에서 다른 줄에 섰다 — 나란히 두려고 source 를 나눈
    # 것인데 정작 짝이 안 맞았다. 실측: 장비 160.0 MPa vs 우리 249.5 MPa 로
    # 56% 차이가 났는데, 그것을 눈으로 찾아야 했다.
    #
    # 오프셋(0.2%)은 값이 아니라 이름에 있었다. 별도 항목으로 낸다 — 우리 계산도
    # `proof_offset` 을 따로 내므로 그래야 짝이 맞는다.
    "force at proof stress 0.2%": "proof_stress",
}

#: 결과가 아니라 **입력**인 항목. 시편의 물리적 치수라서 시험 요약값이 아니다.
#: 화면이 이 값으로 시편 실측치를 채워 주도록 metadata 로 보낸다.
#:
#: 키에 `_a0`·`_b0` 를 붙이는 이유: `specimen_width` 는 **채널 이름과 겹친다**.
#: 곡선의 시편폭(시험 중 계속 변하는 값)과 초기 폭 b0(고정값)는 다른 것이다.
SPECIMEN_FIELDS = {
    "specimen number": "specimen_number",
    "specimen thickness a0": "specimen_thickness_a0",
    "specimen width b0": "specimen_width_b0",
}

#: DB 컬럼 길이(TestSummary.key/label). 모르는 항목의 slug 가 넘칠 수 있는데,
#: 그때 DB 가 거부하면 파일 전체가 실패한다. 파서가 먼저 자른다.
MAX_KEY = 50
MAX_LABEL = 100

#: 장비가 "못 구했다"를 적는 방식. 숫자 자리에 그대로 들어온다.
UNKNOWN_TEXTS = {"unknown", "n/a", "na", "-", ""}

#: 원문 단위 → matcore.units 심볼. 장비 표기가 우리 표기와 다른 것만 적는다.
UNIT_ALIASES = {
    "": "1",
    " ": "1",
    "-": "1",
    "%": "%",
    "mpa": "MPa",
    "gpa": "GPa",
    "kpa": "kPa",
    "pa": "Pa",
    "n": "N",
    "kn": "kN",
    "mm": "mm",
    "m": "m",
    "s": "s",
    "mm/min": "mm/min",
    "1/s": "1/s",
    "°c": "degC",
    "c": "degC",
    "k": "K",
}

_BRACED = re.compile(r"\{[^}]*\}")
_SLUG = re.compile(r"[^0-9a-z]+")


def _decode(data: bytes) -> tuple[str, str | None]:
    """바이트를 텍스트로. 추측했으면 그 사실을 함께 돌려준다.

    **인코딩은 자동으로 판정할 수 없다.** 폴백 사슬을 길게 두면 "엄격하게
    검사한다"는 착각만 생긴다 — 실측하면 cp949 는 `\\x81\\x8d` 같은 바이트쌍을
    멀쩡히 받아들이고, cp1252 는 정의되지 않은 5바이트를 빼면 무엇이든 받는다.
    즉 사슬 끝에 단일바이트 코덱을 두는 순간 UnicodeDecodeError 는 사실상 나지
    않고, 잘못된 인코딩이 조용히 통과한다. 숫자는 멀쩡한데 라벨만 깨지는 그 실패는
    발견이 가장 늦다.

    그래서 판정하는 척하지 않는다. UTF-8 이 아니면 Zwick 의 모국 코드페이지인
    CP1252 로 읽되 **추측했다고 경고한다.** 경고는 `TestRun` 에 남아 화면에
    보이므로, 라벨이 이상하면 사람이 원인을 바로 안다.

    관측된 `.tra` 44개는 전부 BOM 없는 순수 ASCII 라 실제로는 첫 줄에서 끝난다.
    """
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        pass
    try:
        return (
            data.decode("cp1252"),
            "UTF-8 이 아니어서 CP1252 로 읽었습니다 — 라벨이 깨져 보이면 "
            "원본 인코딩을 확인하세요.",
        )
    except UnicodeDecodeError as exc:
        raise ParseError(
            f"파일 인코딩을 알 수 없습니다 (UTF-8·CP1252 모두 실패): {exc}"
        ) from exc


def _rows(text: str) -> tuple[list[list[str]], str]:
    """구분자를 판정하고 줄을 자른다.

    독일어 로케일 장비는 `;` 로 나누고 소수점에 `,` 를 쓴다. 이 경우 `,` 로
    자르면 한 숫자가 두 칸이 되는데, 칸 수만 맞으면 그럴듯해 보인다.
    """
    for delimiter in (",", ";", "\t"):
        rows = [
            row
            for row in csv.reader(io.StringIO(text), delimiter=delimiter)
            if any(cell.strip() for cell in row)
        ]
        if (
            any(len(row) >= 2 for row in rows)
            and _find_data_start(rows, delimiter) is not None
        ):
            return rows, delimiter
    raise ParseError(
        "수치 데이터 블록을 찾지 못했습니다. Zwick .tra 형식이 맞는지 확인하세요."
    )


def _to_float(cell: str, delimiter: str) -> float | None:
    text = cell.strip().strip('"').strip()
    if not text:
        return None
    if delimiter == ";" and "," in text:
        # 유럽식 표기(1.234,56)에서만 `.` 이 천단위 구분자다. 쉼표가 없는데도
        # 점을 지우면 지수 표기 `1.46484e-007` 이 `146484e-007` 이 되어, 값이
        # 10^5 배 어긋난 채로 **파싱은 성공한다.**
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _all_numeric(row: Sequence[str], delimiter: str) -> bool:
    return len(row) >= 2 and all(_to_float(cell, delimiter) is not None for cell in row)


def _find_data_start(rows: Sequence[Sequence[str]], delimiter: str) -> int | None:
    """처음으로 모든 칸이 숫자인 줄. 그 위 두 줄이 이름과 단위다.

    데이터 줄이 **연속으로 두 줄 이상** 나오는 곳을 찾는다. 요약부에도 우연히
    모든 칸이 숫자인 줄이 있을 수 있는데(`"Specimen number",4," "` 는 아니지만
    장비 설정에 따라 라벨 없는 줄이 나올 수 있다), 데이터 블록은 반드시 길다.
    """
    for index in range(len(rows) - 1):
        if _all_numeric(rows[index], delimiter) and _all_numeric(rows[index + 1], delimiter):
            return index
    return None


def _normalize_label(label: str) -> str:
    return _BRACED.sub("", label).strip().strip('"').strip().lower()


def _slug(label: str) -> str:
    return _SLUG.sub("_", _normalize_label(label)).strip("_") or "unnamed"


def _unit_symbol(raw: str) -> str | None:
    """원문 단위를 matcore 심볼로. 모르면 None — 그러면 변환하지 않는다."""
    text = raw.strip().strip('"').strip()
    return UNIT_ALIASES.get(text.lower(), text if text in units.UNITS else None)


def parse(data: bytes) -> ParsedTest:
    """`.tra` 바이트 → 채널·요약값·메타데이터."""
    text, encoding_warning = _decode(data)
    rows, delimiter = _rows(text)
    start = _find_data_start(rows, delimiter)
    if start is None or start < 2:
        raise ParseError(
            "채널 이름·단위 줄을 찾지 못했습니다. 수치 블록 위에 두 줄이 있어야 합니다."
        )

    names = [cell.strip().strip('"').strip() for cell in rows[start - 2]]
    raw_units = [cell.strip().strip('"').strip() for cell in rows[start - 1]]
    body = rows[start:]
    width = len(rows[start])

    if len(names) != width or len(raw_units) != width:
        raise ParseError(
            f"채널 이름 {len(names)}개·단위 {len(raw_units)}개가 "
            f"데이터 열 {width}개와 맞지 않습니다."
        )

    warnings: list[str] = [encoding_warning] if encoding_warning else []
    columns: list[list[float | None]] = [[] for _ in range(width)]
    for line_no, row in enumerate(body, start=start + 1):
        if len(row) != width:
            # 마지막 줄이 잘린 파일이 실제로 온다. 그 줄만 버리고 계속한다.
            warnings.append(f"{line_no}번째 줄의 열 개수가 달라 건너뛰었습니다.")
            continue
        for index, cell in enumerate(row):
            columns[index].append(_to_float(cell, delimiter))

    if not columns[0]:
        raise ParseError("수치 데이터가 한 줄도 없습니다.")

    channels = _build_channels(names, raw_units, columns, warnings)
    summary, metadata = _build_summary(rows[: start - 2], delimiter, warnings)
    return ParsedTest(
        channels=tuple(channels),
        summary=tuple(summary),
        metadata=metadata,
        warnings=tuple(warnings),
    )


def _build_channels(
    names: Sequence[str],
    raw_units: Sequence[str],
    columns: Sequence[list[float | None]],
    warnings: list[str],
) -> list[Channel]:
    channels: list[Channel] = []
    for index, (name, raw_unit) in enumerate(zip(names, raw_units, strict=True)):
        normalized = _normalize_label(name)
        key = CHANNEL_KEYS.get(normalized)
        if key is None:
            key = _slug(name)
            warnings.append(f"모르는 채널이라 '{key}' 로 담았습니다: {name!r}")

        symbol = _unit_symbol(raw_unit)
        if symbol is None:
            warnings.append(f"채널 '{key}' 의 단위 {raw_unit!r} 를 몰라 원값 그대로 둡니다.")
            values = tuple(columns[index])
            si_unit = raw_unit or "?"
        else:
            si_unit = units.SI_UNITS[units.unit_of(symbol).dimension]
            values = tuple(
                None if value is None else units.to_si(value, symbol)
                for value in columns[index]
            )

        _warn_if_sensor_dropped(key, values, warnings)
        channels.append(
            Channel(
                key=key,
                label=name.strip() or key,
                si_unit=si_unit,
                values=values,
                source_unit=raw_unit or None,
            )
        )
    return channels


def _warn_if_sensor_dropped(
    key: str, values: Sequence[float | None], warnings: list[str]
) -> None:
    """값이 있다가 정확히 0 으로 끝나면 센서가 놓친 것이다.

    실측(`Example.tra`): 마지막 두 행의 `Specimen width` 가 `0.0` 이다. 시편이
    파단하면서 폭 센서가 추적을 잃은 것이지, 폭이 0 이 된 것이 아니다.

    파서가 값을 고치지는 않는다 — 원본을 왜곡하면 나중에 무엇이 진짜였는지 알 수
    없다. 다만 **진응력은 폭으로 나눈다.** 이 경고 없이 그대로 계산하면 마지막
    두 점에서 응력이 무한대가 되고, 그 곡선은 차트에서만 이상해 보인다.
    """
    numbers = [value for value in values if value is not None]
    if len(numbers) < 3 or numbers[-1] != 0.0:
        return
    if max(numbers) > 0:
        trailing = len(numbers) - len(list(_takewhile_nonzero(numbers)))
        warnings.append(
            f"채널 '{key}' 의 마지막 {trailing}개 값이 0 입니다 — "
            f"파단 후 센서가 놓친 구간으로 보입니다. 이 값으로 나누지 마세요."
        )


def _takewhile_nonzero(numbers: Sequence[float]) -> list[float]:
    """뒤에서부터 0 이 이어지는 구간을 뺀 앞부분."""
    end = len(numbers)
    while end > 0 and numbers[end - 1] == 0.0:
        end -= 1
    return list(numbers[:end])


def _unique_key(base: str, label: str, used: set[str], warnings: list[str]) -> str:
    """요약 key 가 겹치지 않게 한다.

    `{...}` 를 떼서 key 를 만들기 때문에, 한 파일에 `k{lo 5 - 10}` 와
    `k{lo 10 - 15}` 가 함께 오면 둘 다 `hardening_k` 가 된다. 그러면
    `uq_test_summaries_run_key(test_run_id, key, source)` 를 위반해 **파일 전체가
    저장되지 않는다.**

    첫 번째는 매핑된 key 를 그대로 쓴다 — 우리 계산값과 나란히 놓는 축이라
    안정적이어야 한다. 두 번째부터는 괄호 안 내용(적합 구간)을 붙여 구분한다.
    """
    key = base[:MAX_KEY]
    if key not in used:
        used.add(key)
        return key

    braced = _BRACED.search(label)
    suffix = _SLUG.sub("_", braced.group(0).lower()).strip("_") if braced else ""
    candidate = f"{key}_{suffix}"[:MAX_KEY] if suffix else key
    counter = 2
    while candidate in used:
        candidate = f"{key}_{counter}"[:MAX_KEY]
        counter += 1
    used.add(candidate)
    warnings.append(f"같은 항목이 여러 번 나와 '{candidate}' 로 구분했습니다: {label!r}")
    return candidate


def _build_summary(
    rows: Sequence[Sequence[str]], delimiter: str, warnings: list[str]
) -> tuple[list[SummaryValue], dict[str, str]]:
    """요약부를 읽는다. 결과값과 시편 치수를 나눈다.

    `Specimen thickness a0` 는 시험 **결과**가 아니라 **입력**이다. 요약값에
    섞어 두면 나중에 "우리가 계산한 두께" 같은 이상한 것이 생긴다.
    """
    summary: list[SummaryValue] = []
    metadata: dict[str, str] = {}
    used: set[str] = set()

    for row in rows:
        if len(row) < 2:
            continue
        label = row[0].strip().strip('"').strip()
        if not label:
            continue
        normalized = _normalize_label(label)
        raw_value = row[1].strip().strip('"').strip()
        # `"Yield strain","Unknown"` 처럼 값이 Unknown 이면 **단위 칸 자체가 없다.**
        # row[2] 를 무조건 읽으면 IndexError 가 난다.
        raw_unit = row[2].strip().strip('"').strip() if len(row) > 2 else ""

        if normalized in SPECIMEN_FIELDS:
            metadata[SPECIMEN_FIELDS[normalized]] = raw_value
            if raw_unit:
                metadata[f"{SPECIMEN_FIELDS[normalized]}_unit"] = raw_unit
            continue

        key = _unique_key(SUMMARY_KEYS.get(normalized, _slug(label)), label, used, warnings)
        label = label[:MAX_LABEL]
        if raw_value.lower() in UNKNOWN_TEXTS:
            # 장비가 못 구한 것과 0 은 다르다. 숫자 칸을 비우고 사실만 남긴다.
            summary.append(SummaryValue(key=key, label=label, text=raw_value or "Unknown"))
            continue

        number = _to_float(raw_value, delimiter)
        if number is None:
            summary.append(SummaryValue(key=key, label=label, text=raw_value))
            continue

        symbol = _unit_symbol(raw_unit)
        if symbol is None:
            warnings.append(f"요약값 '{key}' 의 단위 {raw_unit!r} 를 몰라 원값 그대로 둡니다.")
            summary.append(
                SummaryValue(
                    key=key,
                    label=label,
                    value=number,
                    si_unit=None,
                    source_unit=raw_unit or None,
                )
            )
            continue

        dimension = units.unit_of(symbol).dimension
        summary.append(
            SummaryValue(
                key=key,
                label=label,
                value=units.to_si(number, symbol),
                si_unit=units.SI_UNITS[dimension],
                source_unit=raw_unit or None,
            )
        )

    return summary, metadata


@registry.register(
    id="zwick_tra",
    kind="parser",
    label="Zwick 인장 (.tra)",
    produces="curve",
    applies_to=("tensile",),
    version="1",
    extensions=(".tra",),
)
def zwick_tra(data: bytes) -> ParsedTest:
    return parse(data)
