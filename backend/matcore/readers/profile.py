"""층 2 — 형식 프로파일을 구조에 씌워 의미를 붙인다.

층 1(`tabular`)은 "3열짜리 표가 18행" 까지만 안다. 그 열이 변위인지 하중인지는
**사람이 한 번 정하고 프로파일로 저장한다.** 이 모듈이 그 프로파일을 적용한다.

프로파일은 **데이터다.** 관리 화면에서 만들고 고친다 — 새 장비가 들어올 때
배포하지 않아도 되는 이유가 이것이다. 그리고 **운영 서버에서 실제 파일로 만든다**
— 현장 파일이 개발자에게 갈 필요가 없다.

여기도 DB 를 모른다. 프로파일은 그냥 dict 로 받는다.

프로파일 모양(v1):

    {
      "reader":  {"encoding": null, "delimiter": null},   # null = 자동
      "match":   {"extensions": [".csv"], "header_any": ["Angular frequency"]},
      "tables":  {"mode": "all",
                  "include": "^Temperature Sweep",   # 측정
                  "derived": "^TTS"},                # 장비가 계산해 준 것
      "columns": {"Angular frequency": {"channel": "angular_frequency"}},
      "summary": {"Force maximum": {"key": "tensile_strength"}},
      "specimen":{"Thickness": "specimen_thickness",              # 값에 단위가 붙어 올 때
                  "Thickness (mm)": {"key": "specimen_thickness", "unit": "mm"}},
                                                                 # 단위가 이름에만 있을 때
      "metadata":["Operator", "Instrument name", "rundate"]
    }
"""

from __future__ import annotations

import re
from typing import Any

from matcore import units
from matcore.parsers import Channel, CurveData, ParsedTest, ParseError, SummaryValue
from matcore.readers.tabular import ReadOptions, Table, TabularFile, read

#: **파일을 읽을 때만** 뜻이 있는 표기.
#:
#: 단위 표기 별칭 자체는 `matcore.units.NOTATION_ALIASES` 로 올렸다 — 파일 읽기와
#: 입력 폼이 같은 것을 알아들어야 하는데, 여기에만 두었더니 사람이 폼에 `sec` 을
#: 치면 "모르는 단위" 였다.
#:
#: 여기 남은 둘은 **파일에만 있는 사정**이다. 빈 칸과 `-` 는 파일에서 "단위 없음"
#: 을 뜻하지만, 입력 폼에서 빈 칸은 "안 적었다" 이지 무차원이 아니다.
UNIT_ALIASES = {
    "": "1",
    "-": "1",
}

#: 값 없음을 뜻하는 문자열. 숫자 칸에 그대로 들어온다.
UNKNOWN_TEXTS = {"unknown", "n/a", "na", "-", ""}

_SLUG = re.compile(r"[^0-9a-z]+")


def slug(text: str) -> str:
    return _SLUG.sub("_", text.strip().lower()).strip("_") or "unnamed"


def unit_symbol(raw: str | None) -> str | None:
    """장비가 적은 단위를 우리 심볼로. 모르면 None — 그러면 변환하지 않는다.

    `MPa` 를 `Mpa`·`mpa` 로 적는 장비가 흔해서 대소문자만 다른 표기도 받는다.
    다만 **모호하면 받지 않는다** — `units.canonical` 이 그 판단을 한다.
    """
    if raw is None:
        return None
    text = raw.strip()
    alias = UNIT_ALIASES.get(text.lower())
    if alias:
        return alias
    return units.canonical(text)


def _case_only(raw: str, symbol: str) -> bool:
    """대소문자만 달랐나. `°C → degC` 같은 별칭 치환과 구분하려고 따로 본다 —
    별칭까지 경고하면 DMA 파일마다 경고가 뜨고, 그러면 아무도 안 본다."""
    return raw.strip() != symbol and raw.strip().lower() == symbol.lower()


def matches(profile: dict[str, Any], *, filename: str, structure: TabularFile) -> bool:
    """이 파일이 이 프로파일의 것인가.

    확장자만으로는 못 가른다 — `.csv` 는 어느 장비나 쓴다. 그래서 **헤더에 있는
    열 이름**을 지문으로 쓴다. 그것이 장비를 가장 잘 나타낸다.
    """
    match = profile.get("match") or {}

    extensions = [str(item).lower() for item in match.get("extensions", [])]
    if extensions:
        suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""
        if suffix not in extensions:
            return False

    header_any = [str(item) for item in match.get("header_any", [])]
    if header_any:
        headers = {cell for table in structure.tables for cell in table.header}
        if not any(name in headers for name in header_any):
            return False

    meta_any = [str(item) for item in match.get("meta_any", [])]
    if meta_any:
        keys = {key for key, _ in structure.meta}
        if not any(name in keys for name in meta_any):
            return False

    return bool(extensions or header_any or meta_any)


def read_options(profile: dict[str, Any]) -> ReadOptions:
    reader = profile.get("reader") or {}
    return ReadOptions(
        encoding=reader.get("encoding") or None,
        delimiter=reader.get("delimiter") or None,
        has_units_row=reader.get("has_units_row"),
        header_rows=int(reader.get("header_rows") or 1),
        skip_lines=int(reader.get("skip_lines") or 0),
    )


def apply(profile: dict[str, Any], data: bytes) -> ParsedTest:
    """프로파일로 파일을 읽어 곡선·요약값·메타를 만든다."""
    structure = read(data, read_options(profile))
    warnings = list(structure.warnings)

    tables = _select_tables(profile, structure, warnings)
    if not tables:
        raise ParseError("프로파일이 고른 표가 하나도 없습니다. 표 선택 규칙을 확인하세요.")

    columns: dict[str, Any] = profile.get("columns") or {}
    errors: list[str] = []
    curves = [
        _build_curve(table, columns, warnings, errors, single=len(tables) == 1, kind=kind)
        for table, kind in tables
    ]
    if errors:
        # **매핑한 열의 단위를 모르면 멈춘다.** 그냥 두면 원값이 SI 인 척 저장된다 —
        # 201242 MPa 가 201242 Pa 가 되어 10⁶ 배 틀리는데, 숫자는 멀쩡해 보이고
        # 뜻만 바뀌므로 화면 어디에도 티가 나지 않는다. 시험종류 편집에서 단위를
        # 잠그는 것과 같은 이유다.
        raise ParseError(
            "단위를 알 수 없는 열이 있습니다. 프로파일에서 그 열의 단위를 지정하세요"
            f" — {' / '.join(dict.fromkeys(errors))}"
        )
    summary, metadata = _build_meta(profile, structure, warnings)

    return ParsedTest(
        curves=tuple(curves),
        channels=curves[0].channels if len(curves) == 1 else (),
        summary=tuple(summary),
        metadata=metadata,
        warnings=tuple(warnings),
    )


def _select_tables(
    profile: dict[str, Any], structure: TabularFile, warnings: list[str]
) -> list[tuple[Table, str]]:
    """읽을 표와 **그 표가 무엇인지**(측정 / 처리결과).

    한 파일에 성격이 다른 곡선이 섞여 온다. 실측(TA DMA850 주파수-온도 스윕):

        Temperature Sweep - 2..7      측정 구간 6벌
        TTS - shift factors           장비가 맞춘 이동인자
        TTS - master curve (20.0 °C)  겹쳐 만든 마스터 곡선

    처음에는 `include` 에 안 맞는 표를 **버렸다.** 그러면 장비가 계산해 준 결과를
    잃는다. 그렇다고 다 같이 읽으면 Phase 3 의 처리가 마스터 곡선을 원본으로
    착각한다. **버리지도 섞지도 않고 무엇인지 적어 둔다.**

        "tables": {"mode": "all",
                   "include": "^Temperature Sweep",   ← 측정
                   "derived": "^TTS"}                 ← 장비가 계산한 것
    """
    rule = profile.get("tables") or {}
    mode = str(rule.get("mode") or "first")
    include = rule.get("include")
    derived = rule.get("derived")

    measured_pattern = re.compile(str(include)) if include else None
    derived_pattern = re.compile(str(derived)) if derived else None

    picked: list[tuple[Table, str]] = []
    skipped: list[str] = []
    for table in structure.tables:
        name = table.name or ""
        if derived_pattern and name and derived_pattern.search(name):
            picked.append((table, "derived"))
        elif measured_pattern is None or (name and measured_pattern.search(name)):
            picked.append((table, "measured"))
        else:
            skipped.append(name or f"표 {table.index + 1}")

    if skipped:
        # 버렸다는 사실을 남긴다. 조용히 빠지면 "왜 곡선이 6개뿐이지" 가 된다.
        warnings.append(
            f"표 {len(skipped)}개를 규칙에 안 맞아 건너뛰었습니다: "
            f"{', '.join(skipped[:5])}. 버리지 않으려면 프로파일의 표 규칙에 "
            f"측정 또는 처리결과로 넣으세요."
        )

    return picked[:1] if mode == "first" else picked


def _build_curve(
    table: Table,
    columns: dict[str, Any],
    warnings: list[str],
    errors: list[str],
    *,
    single: bool,
    kind: str = "measured",
) -> CurveData:
    channels: list[Channel] = []
    used: set[str] = set()

    for index, name in enumerate(table.header):
        mapping = columns.get(name) or {}
        if mapping.get("skip"):
            # **버릴 열을 적을 수 있어야 한다.** 옛 앱의 파일은 첫 열이 행 번호
            # (`#`)다 — 매핑을 안 하면 단위 모르는 채널로 저장되어, 곡선 고르는
            # 자리에 뜻 없는 계열이 하나 끼고 "이건 뭐냐" 를 매번 묻게 된다.
            # 실측 282개 전부에 이 열이 있다.
            continue
        mapped = bool(mapping.get("channel"))
        key = str(mapping.get("channel") or "") or slug(name)
        if key in used:
            key = f"{key}_{index}"
        used.add(key)

        raw_unit = mapping.get("unit") or (
            table.units[index] if index < len(table.units) else None
        )
        symbol = unit_symbol(raw_unit)

        raw_values = [row[index] if index < len(row) else "" for row in table.rows]
        numbers = [_to_float(value) for value in raw_values]

        if symbol is None:
            if mapped:
                # 매핑한 열은 정의된 채널로 저장된다. 단위를 모르는 채로 넣으면
                # 그 채널의 선언 단위인 척 저장된다.
                errors.append(
                    f"'{name}'"
                    + (
                        f" (단위 {raw_unit!r} 를 모릅니다)"
                        if raw_unit
                        else " (파일에 단위가 없습니다)"
                    )
                )
            elif raw_unit:
                # 매핑 안 한 열은 정의된 채널이 아니라 계산에 안 쓰인다. 막지 않고
                # 원값으로 둔다 — 사람이 나중에 매핑할 수도 있다.
                warnings.append(f"'{name}' 의 단위 {raw_unit!r} 를 몰라 원값 그대로 둡니다.")
            si_unit = str(raw_unit or "?")
            values = tuple(numbers)
        else:
            if raw_unit and _case_only(str(raw_unit), symbol):
                # 추측한 것은 남긴다. 대개는 맞지만 항상 맞는다고 할 수 없다.
                warnings.append(
                    f"'{name}' 의 단위 표기 {raw_unit!r} 를 {symbol} 로 읽었습니다."
                )
            si_unit = units.SI_UNITS[units.unit_of(symbol).dimension]
            values = tuple(
                None if value is None else units.to_si(value, symbol) for value in numbers
            )

        channels.append(
            Channel(
                key=key,
                label=name or key,
                si_unit=si_unit,
                values=values,
                source_unit=str(raw_unit) if raw_unit else None,
            )
        )

    key = "raw" if single else (slug(table.name) if table.name else f"table_{table.index + 1}")
    return CurveData(key=key, label=table.name, channels=tuple(channels), kind=kind)


def _build_meta(
    profile: dict[str, Any], structure: TabularFile, warnings: list[str]
) -> tuple[list[SummaryValue], dict[str, str]]:
    """메타 키-값을 요약값과 시편 정보로 가른다.

    `.tra` 의 요약부가 구조적으로는 메타 키-값과 같은 모양이라, 무엇이 **시험
    결과**이고 무엇이 **입력**인지는 프로파일이 정한다. 기계는 못 가른다.
    """
    summary_rules: dict[str, Any] = profile.get("summary") or {}
    specimen_rules: dict[str, Any] = profile.get("specimen") or {}

    # **없는 것과 빈 것을 구분한다.** 키가 아예 없으면 "메타에 관심 없음" 이므로
    # 전부 보관하고, 빈 목록이면 "하나도 보관하지 않기로 정했음" 이다. 둘을 같게
    # 두면 화면에서 메타를 전부 '버림' 으로 고른 순간 정반대로 전부 보관된다.
    raw_keep = profile.get("metadata")
    keep_meta = None if raw_keep is None else {str(item) for item in raw_keep}

    summary: list[SummaryValue] = []
    metadata: dict[str, str] = {}
    used_keys: set[str] = set()

    for label, raw in structure.meta:
        if label in specimen_rules:
            key, unit = _specimen_target(label, specimen_rules[label])
            metadata[key] = raw
            if unit:
                # **단위를 함께 남긴다.** 값만 남기면 시편 치수를 못 채운다 —
                # 읽는 쪽(`app/shared/curvedata.py`)은 숫자만 있고 단위를
                # 모르면 포기한다. mm 라고 가정하면 m 로 적은 파일에서 1000배
                # 틀린 시편이 만들어지고, 그 뒤 응력이 통째로 어긋나는데
                # 숫자는 그럴듯해서 화면 어디에도 티가 안 난다.
                #
                # `<키>_unit` 은 `.tra` 파서가 이미 쓰는 이름이다. 값에 단위가
                # 붙어 온 파일(`"50.0 mm"`)은 그쪽이 이긴다 — 선언은 힌트이고
                # 파일이 증거다.
                metadata[f"{key}_unit"] = unit
            continue

        rule = summary_rules.get(label)
        if rule is None:
            if keep_meta is None or label in keep_meta:
                metadata[slug(label)] = raw
            continue

        key = str(rule.get("key") or slug(label))
        if key in used_keys:
            key = f"{key}_{len(used_keys)}"
        used_keys.add(key)

        value, unit_text = _split_value_unit(raw)
        if value.lower() in UNKNOWN_TEXTS:
            summary.append(SummaryValue(key=key, label=label, text=value or "Unknown"))
            continue

        number = _to_float(value)
        if number is None:
            summary.append(SummaryValue(key=key, label=label, text=value))
            continue

        symbol = unit_symbol(rule.get("unit") or unit_text)
        if symbol is None:
            summary.append(
                SummaryValue(key=key, label=label, value=number, source_unit=unit_text or None)
            )
            continue

        summary.append(
            SummaryValue(
                key=key,
                label=label,
                value=units.to_si(number, symbol),
                si_unit=units.SI_UNITS[units.unit_of(symbol).dimension],
                source_unit=unit_text or None,
            )
        )

    return summary, metadata


def _specimen_target(label: str, rule: Any) -> tuple[str, str]:
    """시편 치수 규칙 하나를 (저장할 키, 단위) 로.

    두 모양을 받는다. 글자 하나면 키만 정한 것이고(값에 단위가 붙어 오는 파일),
    dict 면 단위까지 정한 것이다.

        "Thickness":      "specimen_thickness"                       # "0.989 mm"
        "Thickness (mm)": {"key": "specimen_thickness", "unit": "mm"} # "0.989"

    **뒤엣것이 필요한 이유:** 단위를 **열 이름 안에**만 갖고 오는 파일이 있다.
    옛 앱(`MaterialAppVer2`)의 `.mtet` 이 그렇다 — `Specimen thickness a0 (mm)`
    옆의 값은 `0.986` 뿐이다. 이름에서 단위를 자동으로 떼지 않는 이유는
    `readers/json_tables.py` 에 적었다(`Tan(delta)`).

    실측으로 드러났다: 기본 프로파일이 이 규칙으로 읽은 `.mtet` 은 시편 치수를
    **하나도 못 채웠다.** 오류도 안 났다 — 치수가 조용히 비고, 처리 1단계의
    `@specimen_area` 가 그제서야 "그 값이 없습니다" 로 멈춘다.
    """
    if isinstance(rule, dict):
        return str(rule.get("key") or slug(label)), str(rule.get("unit") or "")
    return str(rule), ""


def _split_value_unit(raw: str) -> tuple[str, str]:
    """`50.0 mm` 처럼 한 칸에 값과 단위가 붙어 오는 경우를 가른다.

    실측: TA DMA850 의 `Length,50.0 mm`. Zwick 은 단위를 따로 주므로 이 분리가
    필요 없지만, 붙여 주는 장비가 실재한다.
    """
    text = raw.strip()
    parts = text.split()
    if len(parts) == 2 and _to_float(parts[0]) is not None:
        return parts[0], parts[1]
    return text, ""


def _to_float(text: str) -> float | None:
    value = text.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
