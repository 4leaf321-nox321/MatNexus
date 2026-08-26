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
      "metadata":["Operator", "Instrument name", "rundate"],
      "record":  {"Operator": {"field": "operator"},          # 시험 기록의 칸에 채운다
                  "rundate":  {"field": "tested_at", "format": "%Y-%m-%d"}},
      "identity":{"material_code": {"field": "material_grade"}}, # 어느 재료의 것인지 짚는다
      "conditions":{"Test speed": {"field": "speed_elastic",     # 시험 조건에 채운다
                                   "unit": "mm/min"}}
    }

`record` 와 `identity` 는 **이름표만 붙인다.** 어느 컬럼인지, 채워도 되는지는
이 층이 모른다 — 그 판단은 DB 를 아는 쪽에 있다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
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

#: 키로 쓸 수 없는 글자. **한글은 남긴다.**
#:
#: 전에는 `[^0-9a-z]+` 였다. 그러면 한글 라벨이 통째로 지워져 전부 `unnamed` 이
#: 되고, **두 개가 있으면 하나가 조용히 덮인다** — `작업자` 와 `재료` 를 함께
#: 보관하면 나중에 넣은 것만 남았다. 국산 장비와 사내 내보내기는 라벨이 한글이다.
#:
#: `\w` 는 유니코드라 한글·숫자·밑줄을 남긴다. 영문 라벨의 결과는 전과 같다 —
#: `Instrument name` → `instrument_name`, `Tan(delta)` → `tan_delta`, `#` → `unnamed`.
_SLUG = re.compile(r"[^\w]+", re.UNICODE)


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
    record = _build_labels(profile.get("record"), structure, warnings, dates=True)
    identity = _build_labels(profile.get("identity"), structure, warnings, dates=False)
    values, given_units = _build_conditions(profile.get("conditions"), structure)
    _keep_sources(profile, structure, metadata)

    return ParsedTest(
        curves=tuple(curves),
        channels=curves[0].channels if len(curves) == 1 else (),
        summary=tuple(summary),
        metadata=metadata,
        warnings=tuple(warnings),
        record=record,
        identity=identity,
        conditions=values,
        condition_units=given_units,
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
                # **겹치면 덮지 않는다.** 다르게 적힌 두 라벨이 같은 키로
                # 줄어들 수 있고(`A-1` 과 `A 1`), 그때 조용히 하나를 잃는다.
                metadata[_free_key(metadata, slug(label))] = raw
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


def _free_key(taken: Mapping[str, str], want: str) -> str:
    """안 쓰인 키. 겹치면 번호를 붙인다 — **조용히 덮지 않는다.**"""
    if want not in taken:
        return want
    for number in range(2, 100):
        candidate = f"{want}_{number}"
        if candidate not in taken:
            return candidate
    return f"{want}_{len(taken)}"


def _build_conditions(
    rules: Any, structure: TabularFile
) -> tuple[dict[str, str], dict[str, str]]:
    """`conditions` — **시험 조건에 채울 값과 그 단위.**

    ## 왜 값과 단위를 함께 내나

    안 보내면 읽는 쪽이 정의의 `si_unit` 으로 해석한다. 실제로 그래서 사고가
    났다 — 정의가 `m/s` 인데 화면은 `mm/min` 으로 라벨을 붙여 놓고 값은 그대로
    보냈고, 서버가 10 을 10 m/s 로 저장했는데 뜻한 것은 10 mm/min 이었다.
    **6만 배**이고 숫자는 그럴듯하다.

    파일도 같은 함정에 있다. `.tra` 의 속도 칸은 `mm/min` 인데 정의는 `m/s` 다.

    ## 단위를 어디서 가져오나 — 셋, 앞엣것이 이긴다

        ① 프로파일이 적은 것        {"field": "speed_elastic", "unit": "mm/min"}
        ② 값에 붙어 온 것            "5 mm/min"
        ③ 없음 → 읽는 쪽이 정의의 SI 로 본다 (폼이 단위를 안 줄 때와 같다)

    ## 여기서 변환하지 않는다

    조건이 무엇인지는 **시험 종류가 선언한다** — 인장은 속도·예하중이고 DMA 는
    진폭이다. 이 층은 그 정의를 모른다. 원문을 그대로 넘기고, 검증과 SI 변환은
    폼으로 들어온 조건과 **같은 함수**가 한다.
    """
    if not isinstance(rules, dict) or not rules:
        return {}, {}

    found = dict(structure.meta)
    values: dict[str, str] = {}
    units: dict[str, str] = {}
    for label, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        field_name = str(rule.get("field") or "").strip()
        if not field_name:
            continue
        raw = str(found.get(label, "")).strip()
        if not raw or raw.lower() in UNKNOWN_TEXTS:
            continue

        told = str(rule.get("unit") or "").strip()
        text, inline = _split_value_unit(raw)
        if told:
            # 프로파일이 적은 것이 이긴다. 값에 붙어 온 것은 떼어 낸다 —
            # `"5 mm/min"` 을 통째로 넘기면 숫자로 못 읽는다.
            values[field_name] = text if inline else raw
            units[field_name] = told
        elif inline:
            values[field_name] = text
            units[field_name] = inline
        else:
            values[field_name] = raw
    return values, units


def _keep_sources(
    profile: dict[str, Any], structure: TabularFile, metadata: dict[str, str]
) -> None:
    """`record`·`identity` 가 읽은 라벨의 **원문을 남긴다.**

    ## 왜 따로 하나

    보관 목록(`metadata`)은 ⑤ 에서 「그대로 보관」으로 고른 것만 담는다. 그런데
    「시험 칸에 채움」·「어느 재료·시료·시편인지」로 고른 라벨은 그 목록에 안
    들어가므로, 그대로 두면 **원문이 사라진다.**

    실측으로 드러났다. `Operator` 를 시험 칸에 채우게 하면 시험자 칸은 채워지는데
    `source_metadata` 에 `홍길동` 이 없었다. 시험은 통과했는데, 그 시험이 보관
    목록이 **아예 없는** 프로파일로 확인한 것이었다 — 화면으로 만든 프로파일은
    목록을 항상 적으므로 조건이 달랐다.

    ## 왜 남겨야 하나

    「파일에는 뭐라고 적혀 있었나」 에 답할 수 있어야 한다. 특히 시험일이 그렇다 —
    날짜 형식이 안 맞아 못 읽으면 칸도 비고 원문도 없어서, **파일에 무엇이 적혀
    있었는지 알 방법이 아예 사라진다.**

    보관 목록에서 「버림」으로 고른 것과 부딪히지 않는다. 사람이 그 라벨에 준
    역할은 「버림」이 아니라 「채움」이다 — 원문을 지우겠다고 말한 적이 없다.
    """
    labels: set[str] = set()
    for where in ("record", "identity"):
        rules = profile.get(where)
        if isinstance(rules, dict):
            labels |= {str(label) for label in rules}
    if not labels:
        return

    for label, raw in structure.meta:
        if label not in labels:
            continue
        key = slug(label)
        # 이미 다른 역할이 담아 뒀으면 덮지 않는다.
        if key not in metadata:
            metadata[key] = raw


def _build_labels(
    rules: Any,
    structure: TabularFile,
    warnings: list[str],
    *,
    dates: bool,
) -> dict[str, str]:
    """`record` · `identity` 를 만든다 — **메타 라벨을 칸 이름으로 옮긴다.**

    ## 원문을 가져가지 않는다

    여기서 고른 라벨도 `metadata` 에 그대로 남는다(`_build_meta` 가 따로 돈다).
    가져가 버리면 "파일에는 뭐라고 적혀 있었나" 에 못 답하게 되는데, 그건 원본
    보관의 뜻을 반쯤 없앤다.

    ## 빈 값은 "안 적었다" 다

    `""` · `Unknown` · `-` 는 값이 아니다. 그대로 넣으면 시험자가 `Unknown` 인
    기록이 생기고, 그 뒤로는 그 칸이 비어 있었다는 사실을 알 수 없다.

    ## 날짜를 짐작하지 않는다

    `05/06/2020` 은 6월 5일일 수도 5월 6일일 수도 있다. **둘 다 그럴듯해서**
    화면 어디에도 티가 안 난다. 그래서 ISO 로 읽히지 않으면 프로파일이 형식을
    선언했을 때만 읽고, 아니면 경고를 남기고 **안 넣는다.**
    """
    if not isinstance(rules, dict) or not rules:
        return {}

    values = dict(structure.meta)
    out: dict[str, str] = {}
    for label, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        field_name = str(rule.get("field") or "").strip()
        if not field_name:
            continue
        raw = str(values.get(label, "")).strip()
        if not raw or raw.lower() in UNKNOWN_TEXTS:
            continue
        if dates and rule.get("format"):
            parsed = _as_iso(raw, str(rule["format"]))
            if parsed is None:
                warnings.append(
                    f"'{label}' 의 {raw!r} 를 날짜 형식 {rule['format']!r} 로 못 읽어 "
                    f"비워 둡니다."
                )
                continue
            raw = parsed
        out[field_name] = raw
    return out


def _as_iso(raw: str, pattern: str) -> str | None:
    """장비가 적은 날짜를 ISO 로. 못 읽으면 None — **짐작하지 않는다.**"""
    from datetime import datetime

    try:
        return datetime.strptime(raw, pattern).isoformat()
    except ValueError:
        return None


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
