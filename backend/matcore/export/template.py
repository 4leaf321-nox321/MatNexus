"""덱을 **파일 정의로** 만든다 — ADR 0023 의 1단계.

새 솔버를 붙이려면 지금은 파이썬 함수를 짜고 배포해야 한다. 쓰는 솔버가
Abaqus·OptiStruct·Radioss·ANSYS Mechanical·LS-DYNA… 로 늘면 그 사슬이 매번 돈다.
장비 파일을 **읽는** 규칙은 이미 데이터로 옮겼다(ADR 0006) — 내보내는 쪽만 코드다.

## 이 모듈이 하는 일과 안 하는 일

    템플릿이 하는 것          코드가 하는 것
    ─────────────────────    ──────────────────────────
    키워드 이름·차례·자리       표 정리(`prepare` — 중복·정렬·단조성)
    값을 어디에 꽂나           온도별 표의 빈 칸 검사
    **칸 폭과 정렬**          단위 환산
    있으면 넣고 없으면 빼기      「이 값이 물리적으로 말이 되나」
    빠졌을 때 적을 말

**계산이 필요하면 그것은 새 솔버가 아니라 새 물성이다** — `register_block` ·
`register_family` 로 간다. 이 선을 못 지키는 솔버는 그냥 코드로 짠다.

## 칸 폭이 이 설계의 뼈대다

자유 형식만 가정하면 절반의 솔버에서 다시 코드로 돌아가야 한다:

    Abaqus        자유 형식
    OpenRadioss   고정 20칸
    OptiStruct    Nastran 벌크 데이터 — 고정 8칸
    LS-DYNA       키워드 카드 — 고정 10칸

**칸이 어긋나면 다른 필드로 읽힌다.** 값이 틀리는 것이 아니라 다른 값이 되는
것이고, 덱을 읽는 솔버는 그것을 오류로 알려 주지 않는다.

## 줄 하나가 표현하는 것

    {"text": "*MATERIAL, NAME={name}"}                 글자 그대로(치환 가능)
    {"block": "elastic"}                               코드가 만드는 줄 묶음
    {"fields": [...], "join": ", ", "suffix": ","}     값 여럿을 한 줄에
    {"prefix": "MP,EX,", "fields": [...]}              값 앞에 붙는 글자
    {"rows": "table", "x": ..., "y": ..., "fields": [...]}   점 표를 정리해 반복
    {"rows": "viscoelastic", "fields": [...]}          표를 **있는 그대로** 반복
    {"const": 0.0, "format": "free"}                   값 대신 상수 (Prony 의 체적항)
    {"expr": "true_stress / 1000"}                     값·열을 **계산해서** (`expr.py`)
    {"text": "1, 0, 0", "plain": true}                 카드 값이 안 드는 줄 — 옵션 숫자
    {"when": "elastic.density"}                        그 값이 있을 때만
    {"when": "missing:elastic.density", "note": "..."} 없을 때만 + 사람에게 할 말
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, NoReturn

from matcore.export import expr as expressions

if TYPE_CHECKING:  # 순환을 피한다 — 그쪽이 이 모듈을 쓴다
    from matcore.export import Rendered


def _fail(message: str) -> NoReturn:
    """**오류 종류는 하나로 둔다.** `ExportError` 는 `matcore.export` 에 사는데
    그쪽이 이 모듈을 쓰므로, 맨 위에서 부르면 순환이 된다 — 던질 때 부른다."""
    from matcore.export import ExportError

    raise ExportError(message)


#: 값 하나를 글자로 바꾸는 법. **여기 없는 이름을 쓰면 거절한다** — 조용히 자유
#: 형식으로 떨어지면 고정폭 솔버가 말없이 틀린 덱을 받는다.
FORMATS: dict[str, Callable[[float, Sequence[Any]], str]] = {
    # Abaqus·JSON 이 쓰는 자유 형식.
    "free": lambda value, args: f"{value:.12E}",
    # 고정폭. `["fixed", 20, 9]` → 20칸 오른쪽 맞춤, 지수부 9자리.
    "fixed": lambda value, args: f"{value:>{int(args[0])}.{int(args[1])}E}",
    # **왼쪽 맞춤 고정폭.** Nastran·OptiStruct 벌크 데이터가 이쪽이다 —
    # `MAT1    1       210000. .3      `. 오른쪽 맞춤만 두면 그 솔버의 덱을
    # 낼 수 없고, 칸이 밀린 덱은 솔버가 오류로 알려 주지 않는다.
    "fixed_left": lambda value, args: f"{value:<{int(args[0])}.{int(args[1])}E}",
}

#: 코드가 만들어 주는 줄 묶음. 검증·분기가 있는 것들이 여기 산다.
#: `matcore.export` 가 자기 함수를 넣는다 — 이 모듈이 그쪽을 import 하면
#: 순환이 된다(그쪽이 이 모듈을 쓴다).
BLOCKS: dict[str, Callable[[Any], list[str]]] = {}


def register_block(name: str, make: Callable[[Any], list[str]]) -> None:
    BLOCKS[name] = make


def _format(value: float, spec: Any) -> str:
    """`"free"` 또는 `["fixed", 20, 9]`."""
    name, args = (spec, ()) if isinstance(spec, str) else (spec[0], spec[1:])
    make = FORMATS.get(str(name))
    if make is None:
        _fail(
            f"모르는 숫자 형식입니다: {name}. "
            f"쓸 수 있는 것은 {', '.join(sorted(FORMATS))} 입니다."
        )
    return make(value, args)


def _lookup(deck: Any, path: str) -> float | None:
    """`elastic.density` 처럼 **블록.값**으로 집는다."""
    block, _, key = path.partition(".")
    if not key:
        _fail(f"값 자리는 '블록.값' 이어야 합니다: {path}")
    found = deck.number(block, key)
    return None if found is None else float(found)


def _compute(deck: Any, field: Mapping[str, Any], row: Mapping[str, Any] | None) -> float:
    """`expr` 칸 — 열 이름은 그 줄에서, `블록.값` 은 덱에서 찾아 계산한다.

    열에 상수를 나누거나(`true_stress / 1000`) 값 둘을 엮는(`E / (2*(1+nu))`) 자리.
    **덱에 없는 이름은 값 칸과 같은 말로 거절한다** — `when` 으로 걸러야 하는 줄이다.
    """
    text = str(field["expr"])

    def resolve(name: str) -> float | None:
        if "." in name:
            return _lookup(deck, name)
        if row is None:
            _fail(f"값 줄의 식에서는 '블록.값' 으로 적어야 합니다: {name} ({text})")
        if name not in row:
            _fail(f"표에 없는 열입니다: {name} ({text}). 있는 것: {', '.join(map(str, row))}")
        return float(row[name])

    try:
        return expressions.evaluate(text, resolve)
    except expressions.MissingName as exc:
        _fail(f"값이 없습니다: {exc.name} ({text}). `when` 으로 걸러야 하는 줄입니다.")
    except expressions.BadExpression as exc:
        _fail(str(exc))


def _cell(row: Mapping[str, Any], field: Mapping[str, Any], deck: Any = None) -> str:
    """표 한 줄에서 칸 하나.

    **상수 칸이 있다.** Abaqus 의 Prony 는 `g, k, τ` 셋인데 `k`(체적)는 DMA 가
    재지 않아 코드가 `0.0` 을 적는다. 그런 자리를 정의로 표현할 수 없으면 곡선
    물성은 전부 코드로 남는다.
    """
    fmt = field.get("format", "free")
    if "expr" in field:
        return _format(_compute(deck, field, row), fmt)
    if "const" in field:
        # **글자로 주면 글자 그대로 나간다.** Prony 의 체적항을 코드가
        # `0.000000000000E+00` 이 아니라 `0.0` 으로 적는다 — 덱에는 그런 리터럴이
        # 흔하고, 포맷을 거치면 그 자리가 바이트로 달라진다.
        const = field["const"]
        return const if isinstance(const, str) else _format(float(const), fmt)
    name = str(field["value"])
    if name not in row:
        _fail(f"표에 없는 열입니다: {name}. 있는 것: {', '.join(map(str, row))}")
    return _format(float(row[name]), fmt)


def _keep(deck: Any, when: str | None) -> bool:
    """`when` 판정. 없으면 항상 그린다."""
    if not when:
        return True
    if when.startswith("missing:"):
        return _lookup(deck, when[len("missing:") :]) is None
    return _lookup(deck, when) is not None


def render(spec: Mapping[str, Any], deck: Any) -> Rendered:
    """정의 한 벌로 덱을 만든다.

    **표 정리를 먼저 한다.** `prepare` 가 남기는 말(중복을 묶었다·거꾸로 간 점을
    버렸다)은 줄에서 나온 말보다 앞선다 — 코드 렌더러가 그 차례로 쌓았고, 그
    차례가 곧 「무엇을 먼저 알아야 하나」 다.
    """
    # 순환을 피해 여기서 부른다. **`Rendered` 는 `matcore.export` 의 것을 쓴다** —
    # 같은 모양을 하나 더 두면 라우트가 어느 쪽을 받는지 흐려진다.
    from matcore.export import Rendered, prepare

    lines: list[str] = []
    notes: list[str] = []
    tables: dict[str, list[dict[str, float]]] = {}

    for item in spec.get("lines", ()):
        rows_of = item.get("rows")
        if not rows_of or rows_of in tables:
            continue
        if "x" in item and "y" in item:
            # **점 표만 정리한다** — 중복을 묶고 단조성을 본다. 소성 곡선이 그렇다.
            x, y = str(item["x"]), str(item["y"])
            points, said = prepare(deck.pairs(rows_of, x, y))
            notes.extend(said)
            tables[rows_of] = [{x: first, y: second} for first, second in points]
        else:
            # **있는 그대로 읽는다.** Prony 항은 점이 아니다 — `(g, τ)` 를 τ 로
            # 정렬하거나 중복을 묶으면 **다른 재료가 된다.** 그리고 덱은 멀쩡히
            # 돌고 결과도 그럴듯하다.
            tables[rows_of] = deck.rows(rows_of)

    # **정의 줄마다 덱의 몇 줄이 됐는지 남긴다.** 줄은 뒤에만 붙으므로 이번 줄의
    # 시작이 곧 앞 줄의 끝이다 — `when` 으로 걸러진 줄은 빈 구간이다.
    starts: list[int] = []
    for item in spec.get("lines", ()):
        starts.append(len(lines))
        if not _keep(deck, item.get("when")):
            continue
        say = item.get("note")
        if say:
            notes.append(str(say))

        if "block" in item:
            make = BLOCKS.get(str(item["block"]))
            if make is None:
                _fail(
                    f"모르는 묶음입니다: {item['block']}. "
                    f"쓸 수 있는 것은 {', '.join(sorted(BLOCKS))} 입니다."
                )
            lines.extend(make(deck))
            continue

        if "rows" in item:
            join = str(item.get("join", ", "))
            prefix = str(item.get("prefix", ""))
            for row in tables[str(item["rows"])]:
                lines.append(
                    prefix + join.join(_cell(row, field, deck) for field in item["fields"])
                )
            continue

        if "fields" in item:
            join = str(item.get("join", ", "))
            parts = []
            for field in item["fields"]:
                if "const" in field:
                    # **값 줄에도 상수 칸이 있다.** Nastran 은 재료 번호가 값과
                    # 같은 줄에 오고, 그것은 카드에서 오는 값이 아니다. 표에만
                    # 상수를 두면 그 솔버는 이 줄을 못 적는다.
                    const = field["const"]
                    parts.append(
                        const
                        if isinstance(const, str)
                        else _format(float(const), field.get("format", "free"))
                    )
                    continue
                if "expr" in field:
                    parts.append(
                        _format(_compute(deck, field, None), field.get("format", "free"))
                    )
                    continue
                value = _lookup(deck, str(field["value"]))
                if value is None:
                    _fail(
                        f"값이 없습니다: {field['value']}. `when` 으로 걸러야 하는 줄입니다."
                    )
                parts.append(_format(value, field.get("format", "free")))
            # **값 앞에 글자가 붙는 솔버가 있다.** ANSYS APDL 은 `MP,EX,1,2.1E5`
            # 처럼 명령·물성 이름이 같은 줄에 오고, Nastran 벌크는 `MAT1` 이 첫
            # 칸을 차지한다. 그것을 못 적으면 그 솔버는 아예 정의로 못 붙인다.
            lines.append(
                str(item.get("prefix", "")) + join.join(parts) + str(item.get("suffix", ""))
            )
            continue

        # 글자 줄 — 키워드도, 카드 값이 안 드는 옵션 줄(`plain`)도 여기다. 렌더러에게
        # 둘은 같다. 구분은 편집기가 묶음으로 접을 때만 쓴다.
        text = str(item.get("text", ""))
        try:
            lines.append(text.format(name=deck.name, units=deck.units.declaration))
        except (KeyError, IndexError, ValueError) as exc:
            # **모르는 자리표는 이름을 대며 멈춘다.** `KeyError: 'id'` 로 나가면 정의의
            # 어느 줄인지 못 찾는다. 글자 그대로의 중괄호는 `{{` 로 적는다.
            _fail(
                f"글자 줄의 자리표를 모릅니다: {text!r} ({exc!r}). "
                "쓸 수 있는 것은 {name}·{units} 이고, 중괄호 자체는 {{ }} 로 적습니다."
            )

    ends = [*starts[1:], len(lines)]
    spans = tuple(
        (index, start, end)
        for index, (start, end) in enumerate(zip(starts, ends, strict=True))
    )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes), spans=spans)


#: 정의에 반드시 있어야 하는 것. 없으면 **저장 전에** 막는다 — 기동이나 내려받기
#: 시점에 터지면 그때는 화면에서 고칠 사람이 그 자리에 없다.
REQUIRED = ("key", "label", "extension", "describe", "lines")


def renderer_from_definition(definition: Mapping[str, Any]) -> Any:
    """정의 한 벌을 렌더러로 만든다. **`matcore` 는 DB 를 모른다** — dict 로 받는다.

    인풋 프로파일과 같은 규칙이다(ADR 0006): 행을 읽는 것은 앱이고, 여기 오는
    것은 이미 dict 다.

    **검증을 여기서 다 한다.** 저장하는 쪽이 이 함수를 그대로 불러 보면 「저장은
    됐는데 내려받을 때 터지는」 정의가 안 생긴다.
    """
    from matcore.export import Need, Renderer

    missing = [key for key in REQUIRED if not definition.get(key)]
    if missing:
        _fail(f"정의에 빠진 것이 있습니다: {', '.join(missing)}")

    lines = definition["lines"]
    if not isinstance(lines, list):
        _fail("`lines` 는 줄의 목록이어야 합니다.")
    # **식은 저장 전에 읽어 본다.** 값이 있는지는 카드마다 다르지만 문법과 허용 범위는
    # 지금 알 수 있고, 내려받을 때 터지면 그 자리에 고칠 사람이 없다.
    for at, line in enumerate(lines, start=1):
        for field in line.get("fields", ()) if isinstance(line, Mapping) else ():
            if isinstance(field, Mapping) and "expr" in field:
                try:
                    expressions.parse(str(field["expr"]))
                except expressions.BadExpression as exc:
                    _fail(f"{at}번 줄의 식: {exc}")

    needs = []
    for raw in definition.get("needs", ()):
        block = raw.get("block")
        if not block:
            _fail("`needs` 의 각 항목에는 `block` 이 있어야 합니다.")
        needs.append(
            Need(
                block=str(block),
                values=tuple(str(name) for name in raw.get("values", ())),
                rows_min=int(raw.get("rows_min", 0)),
                optional=bool(raw.get("optional", False)),
            )
        )

    spec = {"lines": lines}
    return Renderer(
        key=str(definition["key"]),
        label=str(definition["label"]),
        extension=str(definition["extension"]),
        describe=str(definition["describe"]),
        suffix=str(definition.get("suffix", "")),
        render=lambda deck: render(spec, deck),
        keywords=tuple(str(word) for word in definition.get("keywords", ())),
        needs=tuple(needs),
        media_type=str(definition.get("media_type", "text/plain; charset=utf-8")),
    )
