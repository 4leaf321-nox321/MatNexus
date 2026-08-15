"""구분자 텍스트 파일의 구조를 알아낸다.

**장비별 지식을 하나도 넣지 않는다.** 실측으로 확인한 것: 이 규칙만으로 Zwick
`.tra` 와 TA DMA850 `.csv` 가 둘 다 읽힌다. 후자는 표가 8개고 열 구성이 표마다
다른데도 전부 잡힌다.

자동으로 **안 되는 것**이 하나 있다. `Storage modulus` 가 우리의 어느 채널인지는
기계가 알 수 없다. 그것만 사람이 한 번 매핑하고, 매핑은 프로파일로 저장돼 다음부터
자동으로 쓰인다.

자동 감지가 **틀릴 수 있다는 것**도 분명히 해 둔다. 실측: 같은 폴더의 DMA CSV 중
하나(`Example FreqTemp2.csv`)는 UTF-8 로 저장된 것을 CP949 로 읽어 다시 저장한
이중 손상 파일인데, 감지기는 CP949 로 "성공적으로" 읽는다. 글자만 깨지고 숫자는
멀쩡하다. 그래서 **사람이 미리보기로 확인하는 단계가 반드시 있어야 한다** —
이 모듈은 자기가 무엇을 추측했는지 `warnings` 로 남긴다.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from matcore import units

#: 시도할 인코딩 순서. UTF-8 이 아니면 한국 Windows(CP949) → 서유럽(CP1252).
#:
#: 사슬 끝에 단일바이트 코덱을 두면 UnicodeDecodeError 가 사실상 나지 않는다.
#: 그래서 "성공"이 곧 "맞다"가 아니다 — 첫 시도가 아니면 경고를 남긴다.
ENCODINGS = ("utf-8-sig", "cp949", "cp1252")

#: 구분자 후보. 열 수가 가장 일관된 것을 고른다.
DELIMITERS = (",", ";", "\t", "|")

#: 표 이름이 들어 있을 법한 줄. `[step]` 같은 대괄호 마커.
_MARKER = re.compile(r"^\[.+\]$")

#: 데이터 블록으로 인정하는 최소 행 수. 요약부에 우연히 숫자 줄이 하나 있어도
#: 표로 오인하지 않게 한다.
MIN_DATA_ROWS = 2


@dataclass(frozen=True)
class Table:
    """숫자 블록 하나와 그 머리."""

    index: int
    name: str | None
    """표 이름. `[step]` 다음의 한 칸짜리 줄 같은 것. 없을 수 있다."""
    header: tuple[str, ...]
    units: tuple[str, ...]
    """단위 줄이 없으면 빈 튜플."""
    rows: tuple[tuple[str, ...], ...]
    """**원문 문자열 그대로.** 숫자로 바꾸는 것은 매핑을 정한 뒤에 한다 —
    여기서 바꾸면 유럽식 소수점 같은 것을 프로파일이 뒤집을 수 없다."""
    first_line: int
    """데이터가 시작하는 줄 번호(1부터). 사람이 파일을 열어 볼 때 쓴다."""

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.header)


@dataclass(frozen=True)
class TabularFile:
    encoding: str
    delimiter: str
    meta: tuple[tuple[str, str], ...]
    """첫 표 앞의 키-값 줄들. 원문 그대로."""
    tables: tuple[Table, ...]
    warnings: tuple[str, ...] = ()
    """**추측한 것**을 남긴다. 사람이 미리보기에서 볼 근거다."""
    line_count: int = 0


@dataclass
class ReadOptions:
    """프로파일이 자동 감지를 덮어쓸 때 쓴다.

    자동이 틀리는 경우가 실제로 있으므로 손으로 고정할 길을 둔다. 다만 기본은
    전부 `None`(자동) 이다 — 새 장비를 붙일 때 손댈 것이 없어야 한다.
    """

    encoding: str | None = None
    delimiter: str | None = None
    has_units_row: bool | None = None
    """`None` 이면 단위 줄인지 스스로 판단한다."""
    skip_lines: int = 0
    extra: dict[str, str] = field(default_factory=dict)


class ReadError(ValueError):
    """구조 자체를 못 알아냈다. 프로파일이 있어도 소용없는 상태다."""


# --- 인코딩 -----------------------------------------------------------------


def decode(data: bytes, encoding: str | None = None) -> tuple[str, str, list[str]]:
    """(텍스트, 쓴 인코딩, 경고). 지정하면 그것만 쓴다."""
    warnings: list[str] = []
    if encoding:
        try:
            return data.decode(encoding), encoding, warnings
        except UnicodeDecodeError as exc:
            raise ReadError(f"{encoding} 로 읽지 못했습니다: {exc}") from exc

    for index, candidate in enumerate(ENCODINGS):
        try:
            text = data.decode(candidate)
        except UnicodeDecodeError:
            continue
        if index > 0:
            warnings.append(
                f"UTF-8 이 아니어서 {candidate} 로 추측했습니다 — "
                f"라벨이 깨져 보이면 원본 인코딩을 확인하세요."
            )
        return text, candidate, warnings

    raise ReadError(f"인코딩을 알 수 없습니다 ({' · '.join(ENCODINGS)} 모두 실패).")


# --- 구분자 -----------------------------------------------------------------


def _split(text: str, delimiter: str) -> list[list[str]]:
    return [
        [cell.strip().strip('"').strip() for cell in row]
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
    ]


def _consistency(rows: list[list[str]]) -> int:
    """같은 열 수가 몇 줄이나 이어지는가. 구분자가 맞으면 이 값이 크다."""
    widths = [len(row) for row in rows if len(row) > 1]
    if not widths:
        return 0
    common = max(set(widths), key=widths.count)
    return common * widths.count(common)


def sniff_delimiter(text: str) -> tuple[str, list[list[str]]]:
    best: tuple[int, str, list[list[str]]] | None = None
    for delimiter in DELIMITERS:
        rows = _split(text, delimiter)
        score = _consistency(rows)
        if best is None or score > best[0]:
            best = (score, delimiter, rows)
    if best is None or best[0] == 0:
        raise ReadError("구분자를 찾지 못했습니다. 표 형식 텍스트가 맞습니까?")
    return best[1], best[2]


# --- 숫자 판정 ---------------------------------------------------------------


def _is_number(cell: str) -> bool:
    if not cell:
        return False
    try:
        float(cell)
    except ValueError:
        return False
    return True


def _numeric_row(row: list[str]) -> bool:
    """빈 칸은 허용한다. **실측 근거**: DMA 변형률 스윕의 `Tan(delta)` 열이 전 행
    비어 있다. 빈 칸을 거절하면 그 표를 통째로 놓친다.

    다만 숫자가 하나도 없으면 데이터 줄이 아니다 — 빈 줄이 표로 잡히면 안 된다.
    """
    if len(row) < 2:
        return False
    seen = False
    for cell in row:
        if not cell:
            continue
        if not _is_number(cell):
            return False
        seen = True
    return seen


def _unit_likeness(row: list[str]) -> float:
    """이 줄이 단위 줄로 보이는 정도(0~1).

    **빈 칸은 세지 않는다 — 분모에서도 뺀다.** 처음에는 빈 칸을 "단위다움"에
    포함시켰는데, 그러면 엑셀이 내보낸 CSV 가 통째로 어긋난다. 실측:

        ,,,,,,,,,,, ...                    ← 엑셀 패딩
        ,strain,stress,fine strain, ...    ← 진짜 헤더, 67칸 중 4칸만 채움
        ,2.93E-09,1.58266399,0,0,, ...     ← 데이터

    빈 칸을 세면 헤더 줄의 단위다움이 63/67 = 0.94 가 되어 **헤더가 단위 줄로
    오인되고, 그 위의 빈 줄이 헤더가 된다.** 열 이름이 통째로 사라진다.

    빈 칸을 빼도 회귀는 없다. 실측: Zwick 3/3, DMA 8/8(빈 칸 하나 제외 7/7) 로
    여전히 1.0 이다.
    """
    filled = [cell for cell in row if cell]
    if not filled:
        return 0.0
    hits = sum(
        1
        for cell in filled
        if cell in {"-", "1"} or cell in units.UNITS or cell.lower() in _UNIT_ALIASES
    )
    return hits / len(filled)


#: 장비가 흔히 쓰는 표기. 단위 판정에만 쓴다 — 실제 변환은 프로파일이 정한다.
_UNIT_ALIASES = {
    "°c",
    "degc",
    "℃",
    "rad/s",
    "1/k",
    "°",
    "1/mpa",
    "mm/mm",
    "n/mm²",
    "n/mm2",
    "kgf",
    "%",
}

#: 이 값 이상이면 단위 줄로 본다. 절반을 넘으면 단위로 보는 것이 실측에 맞았다.
UNIT_ROW_THRESHOLD = 0.6


# --- 본체 -------------------------------------------------------------------


def read(data: bytes, options: ReadOptions | None = None) -> TabularFile:
    """바이트 → 구조. 프로파일이 있으면 `options` 로 자동 감지를 덮어쓴다."""
    opts = options or ReadOptions()
    text, encoding, warnings = decode(data, opts.encoding)

    if opts.skip_lines:
        text = "\n".join(text.splitlines()[opts.skip_lines :])

    if opts.delimiter:
        delimiter, rows = opts.delimiter, _split(text, opts.delimiter)
    else:
        delimiter, rows = sniff_delimiter(text)

    blocks = _find_blocks(rows)
    if not blocks:
        raise ReadError(
            f"숫자 데이터 블록을 찾지 못했습니다({MIN_DATA_ROWS}행 이상 이어지는 "
            f"숫자 줄이 없습니다)."
        )

    tables: list[Table] = []
    for index, (start, end) in enumerate(blocks):
        tables.append(_build_table(index, rows, start, end, opts, warnings))

    # **이름 있는 열이 하나도 없으면 표를 찾은 게 아니다.**
    #
    # 실측: 기존 앱의 `.mtet`·`.mdss`·`.mdft` 는 JSON 인데, 배열 안의 숫자 줄이
    # 연달아 나와 "표 93개" 로 잡혔다. 고유 파일 131개 중 **59개**가 이렇게
    # '성공' 했다. 열 이름이 없으니 매핑할 것도 없는데 성공으로 돌려주면, 화면은
    # 빈 표를 보여 주고 사람은 무엇이 잘못됐는지 알 수 없다.
    if not any(any(cell.strip() for cell in table.header) for table in tables):
        # 어긋난 내역이 있으면 **그것을 먼저** 보여 준다 — 사람이 고칠 근거다.
        # 그래도 마지막 힌트는 늘 붙인다. 원인이 파일 종류인 경우가 더 흔하고,
        # "실패" 만 보면 사람은 파일이 깨진 줄 안다.
        detail = " / ".join(warning for warning in warnings if "헤더" in warning)
        raise ReadError(
            "숫자 줄은 찾았지만 열 이름이 하나도 없습니다. "
            + (f"{detail}. " if detail else "")
            + "표 형식 파일이 맞습니까? (JSON·로그 파일일 수 있습니다.)"
        )

    meta = _meta_pairs(rows[: blocks[0][0]])
    return TabularFile(
        encoding=encoding,
        delimiter=delimiter,
        meta=tuple(meta),
        tables=tuple(tables),
        warnings=tuple(warnings),
        line_count=len(rows),
    )


def sniff(data: bytes) -> TabularFile:
    """자동 감지만. 미리보기 화면이 부른다."""
    return read(data, ReadOptions())


def _find_blocks(rows: list[list[str]]) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    index = 0
    while index < len(rows):
        if not _numeric_row(rows[index]):
            index += 1
            continue
        end = index
        width = len(rows[index])
        while end < len(rows) and _numeric_row(rows[end]) and len(rows[end]) == width:
            end += 1
        if end - index >= MIN_DATA_ROWS:
            blocks.append((index, end))
        index = max(end, index + 1)
    return blocks


def _build_table(
    index: int,
    rows: list[list[str]],
    start: int,
    end: int,
    opts: ReadOptions,
    warnings: list[str],
) -> Table:
    width = len(rows[start])
    above = rows[start - 1] if start >= 1 else []
    two_above = rows[start - 2] if start >= 2 else []

    if opts.has_units_row is None:
        # 칸 수가 데이터와 같은지는 **묻지 않는다.** 물으면, 칸 수가 어긋난 파일에서
        # 단위 줄을 헤더로 착각해 오류 메시지에 `rad/s, s, °C…` 를 "읽은 헤더" 라고
        # 적게 된다(실측). 사람이 고칠 근거가 되려면 진짜 헤더가 보여야 한다.
        has_units = bool(above) and _unit_likeness(above) >= UNIT_ROW_THRESHOLD
    else:
        has_units = opts.has_units_row

    if has_units:
        unit_row, header_row, name_at = above, two_above, start - 3
    else:
        unit_row, header_row, name_at = [], above, start - 2

    if len(header_row) != width:
        # **앞에서부터 맞춰 붙이지 않는다.** 실측(`Example.csv` 구버전): 헤더는
        # 8칸인데 데이터는 7칸이고, 빠진 것이 마지막이 아니라 6번째(`Tan(delta)`)
        # 였다. 앞에서부터 붙이면 손실탄성률 데이터에 `Storage modulus` 라는
        # 이름이 붙는다 — **틀린 이름은 이름이 없는 것보다 나쁘다.** 그럴듯해
        # 보여서 아무도 못 잡는다.
        #
        # 대신 못 쓴 줄을 경고에 그대로 실어 사람이 판단하게 한다.
        sample = ", ".join(cell for cell in header_row if cell)[:120]
        warnings.append(
            f"{index + 1}번째 표: 헤더 {len(header_row)}칸이 데이터 {width}칸과 "
            f"맞지 않아 열 이름을 비웠습니다. 어느 열이 빠졌는지 알 수 없어 "
            f"앞에서부터 붙이지 않습니다" + (f" — 읽은 헤더: {sample}" if sample else "")
        )
        header_row = [""] * width

    return Table(
        index=index,
        name=_table_name(rows, name_at),
        header=tuple(header_row),
        units=tuple(unit_row),
        rows=tuple(tuple(row) for row in rows[start:end]),
        first_line=start + 1,
    )


def _table_name(rows: list[list[str]], at: int) -> str | None:
    """헤더 위의 한 칸짜리 줄을 표 이름으로 본다.

    실측: DMA 는 `[step]` 다음 줄에 `Temperature Sweep (Multifrequency) - 2` 가
    온다. 마커 자체는 이름이 아니므로 그 위로 한 번 더 올라간다.
    """
    while at >= 0:
        row = rows[at]
        cells = [cell for cell in row if cell]
        if len(cells) == 1 and not _MARKER.match(cells[0]) and not _is_number(cells[0]):
            return cells[0]
        if len(cells) == 1 and _MARKER.match(cells[0]):
            at -= 1
            continue
        return None
    return None


def _meta_pairs(rows: list[list[str]]) -> list[tuple[str, str]]:
    """첫 표 앞의 키-값 줄.

    키가 빈 줄은 **앞 키의 이어지는 값**으로 본다. 실측: DMA 의
    `Procedure name` 이 세 줄에 걸쳐 있고 둘째·셋째 줄은 키가 비어 있다.
    """
    pairs: list[tuple[str, str]] = []
    for row in rows:
        cells = [cell for cell in row]
        while cells and not cells[-1]:
            cells.pop()
        if not cells:
            continue
        key, value = cells[0], " ".join(cells[1:]).strip()
        if not key and pairs and value:
            previous_key, previous_value = pairs[-1]
            pairs[-1] = (previous_key, f"{previous_value} / {value}")
            continue
        if key and (value or len(cells) >= 2):
            pairs.append((key, value))
    return pairs
