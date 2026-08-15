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
      "tables":  {"mode": "all", "include": "^Temperature Sweep"},
      "columns": {"Angular frequency": {"channel": "angular_frequency"}},
      "summary": {"Force maximum": {"key": "tensile_strength"}},
      "specimen":{"Thickness": "specimen_thickness"},
      "metadata":["Operator", "Instrument name", "rundate"]
    }
"""

from __future__ import annotations

import re
from typing import Any

from matcore import units
from matcore.parsers import Channel, CurveData, ParsedTest, ParseError, SummaryValue
from matcore.readers.tabular import ReadOptions, Table, TabularFile, read

#: 장비 표기 → `matcore.units` 심볼. 단위표를 늘리는 대신 여기서 흡수한다 —
#: `°C` 와 `degC` 는 같은 것이고, 표에 둘 다 넣으면 어느 쪽이 정본인지 흐려진다.
UNIT_ALIASES = {
    "°c": "degC",
    "℃": "degC",
    "degc": "degC",
    "°": "deg",
    "n/mm2": "MPa",
    "n/mm²": "MPa",
    "mm/mm": "1",
    "": "1",
    "-": "1",
}

#: 값 없음을 뜻하는 문자열. 숫자 칸에 그대로 들어온다.
UNKNOWN_TEXTS = {"unknown", "n/a", "na", "-", ""}

_SLUG = re.compile(r"[^0-9a-z]+")


def slug(text: str) -> str:
    return _SLUG.sub("_", text.strip().lower()).strip("_") or "unnamed"


def unit_symbol(raw: str | None) -> str | None:
    """장비가 적은 단위를 우리 심볼로. 모르면 None — 그러면 변환하지 않는다."""
    if raw is None:
        return None
    text = raw.strip()
    alias = UNIT_ALIASES.get(text.lower())
    if alias:
        return alias
    return text if text in units.UNITS else None


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
    curves = [
        _build_curve(table, columns, warnings, single=len(tables) == 1) for table in tables
    ]
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
) -> list[Table]:
    rule = profile.get("tables") or {}
    mode = str(rule.get("mode") or "first")
    include = rule.get("include")

    tables = list(structure.tables)
    if include:
        pattern = re.compile(str(include))
        kept = [t for t in tables if t.name and pattern.search(t.name)]
        skipped = [t.name for t in tables if t not in kept]
        if skipped:
            # 버렸다는 사실을 남긴다. 조용히 빠지면 "왜 곡선이 6개뿐이지" 가 된다.
            warnings.append(
                f"표 {len(skipped)}개를 규칙에 안 맞아 건너뛰었습니다: "
                f"{', '.join(str(name) for name in skipped[:5])}"
            )
        tables = kept

    return tables[:1] if mode == "first" else tables


def _build_curve(
    table: Table, columns: dict[str, Any], warnings: list[str], *, single: bool
) -> CurveData:
    channels: list[Channel] = []
    used: set[str] = set()

    for index, name in enumerate(table.header):
        mapping = columns.get(name) or {}
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
            if raw_unit:
                warnings.append(f"'{name}' 의 단위 {raw_unit!r} 를 몰라 원값 그대로 둡니다.")
            si_unit = str(raw_unit or "?")
            values = tuple(numbers)
        else:
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
    return CurveData(key=key, label=table.name, channels=tuple(channels))


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
            metadata[str(specimen_rules[label])] = raw
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
