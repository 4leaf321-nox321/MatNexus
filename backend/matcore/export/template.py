"""덱을 **파일 정의로** 만든다 — ADR 0023(1단계) · ADR 0038(문법을 넓혔다).

새 솔버를 붙이려면 파이썬 함수를 짜고 배포해야 했다. 장비 파일을 **읽는** 규칙은 이미
데이터로 옮겼다(ADR 0006) — 내보내는 쪽도 데이터로 옮긴다. 그리고 데이터여야 **화면에서
고칠 수 있다** — 코드로 만든 기본 형식은 틀려도 고칠 길이 없었다(ADR 0037).

## 이 모듈이 하는 일과 안 하는 일

    템플릿이 하는 것                          코드가 하는 것
    ───────────────────────────────────    ──────────────────────────────────
    키워드 이름·차례·자리 · 칸 폭과 정렬          표 정리(`prepare` — 중복·정렬·단조성)
    값을 어디에 꽂나 · 식으로 옮기기(2μ/α)        단위 환산(`to_system`)
    있으면 넣고 없으면 빼기 · 조건으로 가르기      출처 머리(`header`) · Abaqus 온도표 검사
    표 거르기·정렬·묶기 · 첫 점·합·개수           Radioss 단위 코드(`radioss_unit`)
    값 검사(`fail`) — 코드판이 거절하던 것        JSON 처럼 구조를 통째로 적는 형식

**ADR 0023 은 「계산이 필요하면 코드로」 였다.** 기본 형식을 정의로 옮겨 보니 막힌 자리가
큰 계산이 아니라 **표의 첫 점·합·개수와 조건 둘**이었다(ADR 0037 「정의판」). 그 정도는
식으로 적는다 — 그래야 틀렸을 때 화면에서 고친다.

## 칸 폭이 이 설계의 뼈대다

    Abaqus 자유 형식 · OpenRadioss 고정 20칸 · LS-DYNA 고정 10칸 · Nastran 큰칸 16칸

**칸이 어긋나면 다른 필드로 읽힌다.** 값이 틀리는 것이 아니라 다른 값이 되는 것이고,
덱을 읽는 솔버는 그것을 오류로 알려 주지 않는다.

## 문법

정의는 `lines`(줄 목록)와 `tables`(표 정의, 선택)다.

    {"text": "*MATERIAL, NAME={name}"}          글자 — 자리표 {name} {name_alnum} {units} {id}
                                                {식:형식}
    {"fields": [...], "prefix": "MP,EX,{id},"}   값 여럿을 한 줄에(join·suffix)
    {"rows": "curve", "fields": [...]}          표를 줄마다 — 열 이름·_index·_count
    {"each": "curves", "as": "curve",           묶음마다 줄 여럿 — _key·_index·_size
     "lines": [...]}
    {"pack": [칸...], "per_line": 4,            칸을 N 개씩 끊어 잇는다 — Nastran 큰칸 ·
     "first": "MAT1*   ", "next": "*       "}   Radioss 다섯씩 · ANSYS TBDATA(_line)
    {"block": "header", "comment": "$"}         코드가 만드는 줄 묶음
    {"fail": "…{식}…", "when": 조건}            조건이면 멈추고 그 말을 한다
    {"note": "…"}                              덱에는 안 적고 사람에게만 남긴다
    "when": "elastic.density"                  있을 때만 · "missing:elastic.density" 없을 때만
    "when": "has(a.b) and c.d < 0.5"            그 밖에는 식 — 빠진 값은 거짓
    "units.Pa == \"MPa\""                        단위계의 기호 — 응력 단위를 이름으로 적는 형식
    "has(options.fail_from_elongation)"         내보낼 때 고른 것(`Deck.options`) — 켜면 1

칸: `{"value": "블록.값" | "열"}` · `{"expr": 식}` · `{"const": 글자}`, 형식은 `"free"` ·
`["fixed", 폭, 자릿수]` · `["fixed_left", 폭, 자릿수]` · `["fit", 폭]`(폭에 드는 만큼 정밀하게,
`fit`) · `["spec", ">10d"]`(파이썬 형식).
칸에도 `when` 을 달고 `default` 로 대신 적을 글자를 준다 — 큰칸의 빈 필드가 그렇다.

**단위가 정해진 형식**은 `"units": "si"` 를 적는다 — 고른 계와 상관없이 그 계의 덱을
받는다(`Renderer.fixed_units`, 2026-10-02). AEDT · CST · FloXML 처럼 파일 형식이 단위를 정해
둔 것이 그렇다.

표 정의(`tables`): `{"of": 표, "where": 조건, "sort": 열, "x": 열, "y": 열, "by": 열}`.
`x`·`y` 를 주면 점 표로 정리하고(`prepare`), `by` 를 주면 그 열의 값마다 묶는다(속도별·
온도별 곡선). `clip: "shortest"` 는 묶은 곡선을 가장 짧은 끝에서 자른다(LS-DYNA 표).
"""

from __future__ import annotations

import math
import re
import string
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING, Any, NoReturn

from matcore.export import expr as expressions

if TYPE_CHECKING:  # 순환을 피한다 — 그쪽이 이 모듈을 쓴다
    from matcore.export import Rendered


def _fail(message: str) -> NoReturn:
    """**오류 종류는 하나로 둔다.** `ExportError` 는 `matcore.export` 에 사는데
    그쪽이 이 모듈을 쓰므로, 맨 위에서 부르면 순환이 된다 — 던질 때 부른다."""
    from matcore.export import ExportError

    raise ExportError(message)


def fit(value: float, width: int) -> str:
    """`width` 칸에 드는 **가장 정밀한** 숫자 — 오른쪽 맞춤.

    되읽으면 같은 값이 되는 가장 짧은 글자(`repr`)가 들어가면 그것을 쓰고, 안 들어가면
    칸에 드는 것 가운데 값에 가장 가까운 것을 쓴다. 지수는 앞의 0 을 뗀다(`E-09` →
    `E-9`) — 그 한 칸이 유효숫자 하나다.

    **고정 자릿수(`1.930E+05`)로는 모자랐다.** 10칸 LS-DYNA 에서 유효숫자 4자리면 고무의
    푸아송비 0.49925 가 0.4993 이 되고, 체적 탄성률 K ∝ 1/(1-2ν) 가 7% 커진다 — 0.49999 는
    0.5000 이 되어 K 가 발산한다. 공개 덱에 둘 다 있다(2026-10-03 실측: LS-DYNA 참조 카드
    60장을 우리 렌더러로 다시 그려 PyDyna 로 견주었다).
    """
    number = float(value)
    if not math.isfinite(number):
        _fail(f"{value!r} 는 덱에 적을 수 있는 숫자가 아닙니다.")
    shortest = repr(number)
    if "e" not in shortest and len(shortest) <= width:
        return shortest.rjust(width)
    found: list[str] = []
    for digits in range(1, 17):
        mantissa, exponent = f"{number:.{digits}E}".split("E")
        text = f"{mantissa}E{int(exponent):+d}"
        if len(text) > width:
            break
        found = [text]
        if float(text) == number:
            break
    for decimals in range(width, 0, -1):
        text = f"{number:.{decimals}f}"
        if len(text) <= width:
            if float(text) != 0.0:
                found.append(text)
            break
    if not found:
        _fail(f"{number!r} 는 {width}칸에 들어가지 않습니다.")
    # 가까운 것 — 같으면 짧은 것(먼저 넣은 지수 표기가 이긴다).
    best = min(found, key=lambda text: (abs(float(text) - number), len(text)))
    return best.rjust(width)


#: 파이썬 형식 문자열 가운데 **허용하는 모양**. 폭은 세 자리까지 — 끝없는 폭으로 메모리를
#: 채우는 정의를 저장 전에 막는다.
_SPEC = re.compile(
    r"^(?:.?[<>=^])?[+\- ]?z?#?0?(?P<width>\d{1,3})?,?(?:\.\d{1,2})?(?P<type>[eEfFgGd%s])?$"
)


def _spec(value: Any, spec: str) -> str:
    """`["spec", ">10d"]` 칸 · `{식:>10d}` 자리표. **정수 형식은 정수만 받는다** — 3.5 를
    `d` 로 적으려 하면 반올림하지 않고 멈춘다(재료 번호가 조용히 바뀌면 안 된다)."""
    found = _SPEC.fullmatch(spec)
    if found is None:
        _fail(f"읽을 수 없는 형식입니다: {spec!r} — 예: '>10d', '.6g', '<16.8E'")
    kind = found.group("type")
    if kind == "d":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            _fail(f"정수 형식 '{spec}' 에 정수가 아닌 값이 왔습니다: {value!r}")
        if isinstance(value, float):
            if not value.is_integer():
                _fail(f"정수 형식 '{spec}' 에 정수가 아닌 값이 왔습니다: {value!r}")
            value = int(value)
    elif kind in ("s", None) and isinstance(value, str):
        pass
    elif isinstance(value, str):
        _fail(f"숫자 형식 '{spec}' 에 글자가 왔습니다: {value!r}")
    try:
        return format(value, spec)
    except (ValueError, TypeError) as exc:
        _fail(f"형식 '{spec}' 로 {value!r} 를 적을 수 없습니다: {exc}")


#: 값 하나를 글자로 바꾸는 법. **여기 없는 이름을 쓰면 거절한다** — 조용히 자유
#: 형식으로 떨어지면 고정폭 솔버가 말없이 틀린 덱을 받는다.
FORMATS: dict[str, Callable[[Any, Sequence[Any]], str]] = {
    # Abaqus·JSON 이 쓰는 자유 형식.
    "free": lambda value, args: f"{value:.12E}",
    # 고정폭. `["fixed", 20, 9]` → 20칸 오른쪽 맞춤, 지수부 9자리.
    "fixed": lambda value, args: f"{value:>{int(args[0])}.{int(args[1])}E}",
    # **왼쪽 맞춤 고정폭.** Nastran·OptiStruct 벌크 데이터가 이쪽이다 —
    # `MAT1    1       210000. .3      `. 오른쪽 맞춤만 두면 그 솔버의 덱을
    # 낼 수 없고, 칸이 밀린 덱은 솔버가 오류로 알려 주지 않는다.
    "fixed_left": lambda value, args: f"{value:<{int(args[0])}.{int(args[1])}E}",
    # 고정폭 · **칸에 드는 만큼 정밀하게** — `["fit", 10]`. LS-DYNA 10칸이 쓴다(`fit`).
    "fit": lambda value, args: fit(value, int(args[0])),
    # 파이썬 형식 그대로 — 정수 칸(`>10d`)·주석의 유효숫자(`.6g`). 모양은 `_SPEC` 이 막는다.
    "spec": lambda value, args: _spec(value, str(args[0])),
}

#: 코드가 만들어 주는 줄 묶음. 검증·분기가 있는 것들이 여기 산다. 줄에 적은 다른 칸
#: (`comment` 같은 것)이 인자로 간다. `matcore.export` 가 자기 함수를 넣는다 — 이 모듈이
#: 그쪽을 import 하면 순환이 된다(그쪽이 이 모듈을 쓴다).
BLOCKS: dict[str, Callable[..., list[str]]] = {}

#: 줄의 칸 가운데 묶음 인자가 **아닌** 것.
_LINE_KEYS = frozenset({"block", "when", "note"})


def register_block(name: str, make: Callable[..., list[str]]) -> None:
    BLOCKS[name] = make


def _format(value: Any, spec: Any) -> str:
    """`"free"` · `["fixed", 20, 9]` · `["fit", 10]` · `["spec", ">10d"]`."""
    name, args = (spec, ()) if isinstance(spec, str) else (spec[0], spec[1:])
    make = FORMATS.get(str(name))
    if make is None:
        _fail(
            f"모르는 숫자 형식입니다: {name}. "
            f"쓸 수 있는 것은 {', '.join(sorted(FORMATS))} 입니다."
        )
    if name != "spec" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        _fail(f"'{name}' 형식은 숫자를 적습니다 — {value!r} 는 숫자가 아닙니다.")
    return make(value, args)


#: 예전 조건 — `블록.값`(있을 때) · `missing:블록.값`(없을 때). **숫자가 있는가**만 본다.
_OLD_WHEN = re.compile(r"^(missing:)?([A-Za-z_]\w*)\.([A-Za-z_]\w*)$")


@dataclass
class _Group:
    """묶은 표의 한 묶음 — 속도 하나·온도 하나.

    점 곡선(`x`·`y`)이면 곡선의 첫·끝 점과 **앞 곡선 아래로 내려가는지**를 함께 든다 —
    LS-DYNA 표는 곡선이 교차하면 안 되고(`_below_prev`), 항복응력은 첫 곡선의 첫 점이다.
    """

    key: float
    rows: list[dict[str, Any]]
    clipped: bool = False
    ends: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Scope:
    """식이 이름을 찾는 곳 — 블록 값 · 지금 줄의 열 · 자리 변수 · 묶음 별칭."""

    render: _Render
    row: Mapping[str, Any] | None = None
    names: dict[str, Any] = field(default_factory=dict)
    aliases: dict[str, Any] = field(default_factory=dict)

    def child(
        self,
        *,
        row: Mapping[str, Any] | None = None,
        names: Mapping[str, Any] | None = None,
        aliases: Mapping[str, Any] | None = None,
    ) -> _Scope:
        return _Scope(
            self.render,
            row if row is not None else self.row,
            {**self.names, **(names or {})},
            {**self.aliases, **(aliases or {})},
        )

    def lookup(self, name: str) -> Any:
        if name.startswith("_"):
            if name in self.names:
                return self.names[name]
            known = ", ".join(sorted(self.names)) or "없음"
            raise expressions.BadExpression(
                f"여기서 쓸 수 없는 자리 변수입니다: {name}. 여기서 쓸 수 있는 것: {known}"
            )
        if "." in name:
            block, _, key = name.partition(".")
            if block == "units":
                # **이 단위계에서 그 SI 단위의 기호** — mm·N·tonne 면 `units.Pa` 가 "MPa".
                # 파일이 응력 단위를 이름으로 적는 형식(OptiStruct MATFAT 의 UNIT)이 쓴다.
                try:
                    return self.render.deck.units.symbol(key)
                except KeyError:
                    raise expressions.BadExpression(
                        f"모르는 SI 단위입니다: {name} — 예: units.Pa · units.m"
                    ) from None
            if block == "options":
                # **내보낼 때 고른 것**(`Deck.options`) — 켜져 있으면 1, 아니면 없는 값이라
                # `has(options.fail_from_elongation)` 로 묻는다. 코드판과 같은 결정을 읽는다.
                chosen = self.render.deck.options.get(key)
                if chosen is True:
                    return 1.0
                raise expressions.MissingName(name)
            value = self.render.deck.values(block).get(key)
            if isinstance(value, bool) or value is None:
                raise expressions.MissingName(name)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                return value
            raise expressions.MissingName(name)
        if self.row is None:
            if not name:
                # **빈 칸이다** — 예제 덱 초안은 무슨 값인지 모르는 칸을 비워 둔다(`scan`).
                # 이름 없이 「… 적어야 합니다: 」 로 끝나면 무엇이 비었는지 모른다.
                raise expressions.BadExpression(
                    "값이 비어 있는 칸이 있습니다 — 그 칸이 무슨 값인지 '블록.값'"
                    "(예: elastic.youngs_modulus)으로 적거나, 비워 둘 자리면 "
                    '{"const": ""} 로 둡니다.'
                )
            raise expressions.BadExpression(
                f"값 줄의 식에서는 '블록.값' 으로 적어야 합니다: {name}"
            )
        value = self.row.get(name)
        if value is None or isinstance(value, bool):
            raise expressions.MissingName(name)
        if isinstance(value, (int, float)):
            return float(value)
        return value

    def rows(self, table: str) -> list[_Scope]:
        data = self.render.table(table, self)
        count = len(data)
        out = []
        for index, entry in enumerate(data, start=1):
            if isinstance(entry, _Group):
                out.append(self.child(names=_group_names(entry, index, count)))
            else:
                out.append(self.child(row=entry, names={"_index": index, "_count": count}))
        return out


def _group_names(group: _Group, index: int, count: int) -> dict[str, Any]:
    return {
        "_key": group.key,
        "_index": index,
        "_count": count,
        "_size": len(group.rows),
        "_clipped": 1 if group.clipped else 0,
        **group.ends,
    }


class _Render:
    """정의 한 벌을 덱 하나로 그리는 동안의 상태 — 표 캐시와 남길 말."""

    def __init__(self, spec: Mapping[str, Any], deck: Any) -> None:
        self.deck = deck
        self.defs: Mapping[str, Any] = spec.get("tables") or {}
        # **예전 문법 — 표 줄에 x·y 를 적으면 그 블록을 점 표로 정리한다.** 첫 줄이 정한다.
        self.implicit: dict[str, tuple[str, str]] = {}
        for item in _walk(spec.get("lines", ())):
            rows_of = item.get("rows")
            if (
                isinstance(rows_of, str)
                and "x" in item
                and "y" in item
                and rows_of not in self.defs
                and rows_of not in self.implicit
            ):
                self.implicit[rows_of] = (str(item["x"]), str(item["y"]))
        self.cache: dict[str, list[Any]] = {}
        self.head_notes: list[str] = []
        self.line_notes: list[str] = []
        self.last_notes: list[str] = []
        self.root = _Scope(self, names={"_id": deck.solver_id})

    # ── 표 ────────────────────────────────────────────────────────────────

    def table(self, name: str, scope: _Scope) -> list[Any]:
        if name in scope.aliases:
            return list(scope.aliases[name])
        if name in self.cache:
            return self.cache[name]
        if name in self.defs:
            made = self._view(name, self.defs[name])
        elif name in self.implicit:
            from matcore.export import prepare

            x, y = self.implicit[name]
            points, said = prepare(self.deck.pairs(name, x, y))
            self.head_notes.extend(said)
            made = [{x: first, y: second} for first, second in points]
        else:
            # **있는 그대로 읽는다.** Prony 항은 점이 아니다 — `(g, τ)` 를 τ 로
            # 정렬하거나 중복을 묶으면 **다른 재료가 된다.**
            made = self.deck.rows(name)
        self.cache[name] = made
        return made

    def _view(self, name: str, spec: Mapping[str, Any]) -> list[Any]:
        from matcore.export import prepare

        source = str(spec.get("of") or name)
        if source == name and name in self.defs:
            base = self.deck.rows(name)
        else:
            base = self.table(source, self.root)
        if any(isinstance(one, _Group) for one in base):
            _fail(f"표 '{name}' 는 묶은 표('{source}')에서 만들 수 없습니다.")
        rows: list[dict[str, Any]] = [dict(one) for one in base]
        where = spec.get("where")
        if where:
            rows = [
                one for one in rows if expressions.truth(str(where), self.root.child(row=one))
            ]
        sort = spec.get("sort")
        if sort:
            # 열 하나 또는 여럿 — 여럿이면 앞 열부터(파이썬 튜플 정렬과 같다).
            columns = [str(one) for one in (sort if isinstance(sort, list) else [sort])]
            rows = sorted(
                rows,
                key=lambda one: tuple(_sortable(one.get(col), name, col) for col in columns),
            )
        said: list[str] = []
        x, y = spec.get("x"), spec.get("y")
        by = spec.get("by")
        if by:
            made: list[Any] = self._groups(name, spec, rows, str(by), said)
        elif x and y:
            points, said = prepare(_pairs(rows, str(x), str(y)))
            made = [{str(x): first, str(y): second} for first, second in points]
        else:
            made = rows
        # **남길 말의 자리.** 기본은 맨 앞(코드 렌더러 대부분이 표를 먼저 정리한다). `last` 면
        # 맨 뒤 — Abaqus 속도 의존처럼 밀도 말이 곡선 말보다 앞서는 형식.
        (self.last_notes if spec.get("notes") == "last" else self.head_notes).extend(said)
        return made

    def _groups(
        self,
        name: str,
        spec: Mapping[str, Any],
        rows: list[dict[str, Any]],
        by: str,
        said: list[str],
    ) -> list[_Group]:
        """`by` 의 값마다 묶는다 — 값 오름차순. `x`·`y` 가 있으면 묶음마다 **정렬한 뒤**
        정리한다(`prepare`). 남기는 말 앞에 `note` 를 붙인다(`속도 {_key:.3g} 1/s: `)."""
        from matcore.export import prepare

        grouped: dict[float, list[dict[str, Any]]] = {}
        for one in rows:
            # `by` 는 열 이름이거나 식이다 — `round(stress_ratio, 3)`.
            try:
                key = expressions.evaluate_any(by, self.root.child(row=one))
            except expressions.MissingName:
                key = None
            grouped.setdefault(_sortable(key, name, by), []).append(one)
        x, y = spec.get("x"), spec.get("y")
        groups: list[_Group] = []
        for key in sorted(grouped):
            members = grouped[key]
            if x and y:
                points, notes = prepare(tuple(sorted(_pairs(members, str(x), str(y)))))
                prefix = self.text(
                    str(spec.get("note", "")), self.root.child(names={"_key": key})
                )
                said.extend(f"{prefix}{line}" for line in notes)
                members = [{str(x): first, str(y): second} for first, second in points]
            groups.append(_Group(key, members))
        if x and y and groups:
            if spec.get("clip") == "shortest":
                groups = _clip(groups, str(x), str(y))
            _mark_ends(groups, str(x), str(y))
        return groups

    # ── 글자 ──────────────────────────────────────────────────────────────

    def text(self, template: str, scope: _Scope) -> str:
        """자리표를 채운다 — `{name}` · `{units}` · `{id}` · `{식}` · `{식:형식}`.

        중괄호 자체는 `{{ }}` 로 적는다. **모르는 자리표는 이름을 대며 멈춘다** —
        `KeyError: 'x'` 로 나가면 정의의 어느 줄인지 못 찾는다.
        """
        if "{" not in template and "}" not in template:
            return template
        out: list[str] = []
        try:
            parsed = list(string.Formatter().parse(template))
        except ValueError as exc:
            _fail(
                f"글자 줄의 중괄호를 읽을 수 없습니다: {template!r} ({exc}). "
                "중괄호 자체는 {{ }} 로 적고, 자리표 안의 비교는 != 대신 "
                "not (a == b) 로 적습니다."
            )
        for literal, name, spec, conversion in parsed:
            out.append(literal)
            if name is None:
                continue
            if conversion:
                _fail(
                    f"자리표에 ! 를 쓸 수 없습니다: {template!r} — "
                    "비교는 not (a == b) 로 적습니다."
                )
            value = self._placeholder(name.strip(), template, scope)
            if spec:
                out.append(_spec(value, spec))
            else:
                out.append(value if isinstance(value, str) else _plain(value))
        return "".join(out)

    def _placeholder(self, name: str, template: str, scope: _Scope) -> Any:
        if name == "name":
            return self.deck.name
        if name == "name_alnum":
            # **영숫자만** — CODE V 는 유리 이름의 `_` 를 「이름_카탈로그」 로 읽는다
            # (2026-10-03).
            return alnum_name(self.deck.name)
        if name == "units":
            return self.deck.units.declaration
        if name == "id":
            return self.deck.solver_id
        if not name:
            _fail(
                f"글자 줄의 자리표를 모릅니다: {template!r}. 쓸 수 있는 것은 {{name}}·"
                "{units}·{id}·{식} 이고, 중괄호 자체는 {{ }} 로 적습니다."
            )
        try:
            return expressions.evaluate_any(name, scope)
        except expressions.MissingName as exc:
            _fail(f"값이 없습니다: {exc.name} ({template}). `when` 으로 걸러야 하는 줄입니다.")
        except expressions.BadExpression as exc:
            _fail(
                f"글자 줄의 자리표를 모릅니다: {template!r} ({exc}). 쓸 수 있는 것은 "
                "{name}·{units}·{id}·{식} 이고, 중괄호 자체는 {{ }} 로 적습니다."
            )

    # ── 칸 ────────────────────────────────────────────────────────────────

    def keep(self, when: Any, scope: _Scope) -> bool:
        """`when` 판정. 없으면 항상 그린다."""
        if not when:
            return True
        found = _OLD_WHEN.fullmatch(str(when))
        if found:
            # **예전 뜻 그대로** — 숫자가 있는가. 글자 값은 늘 「없다」 였다.
            present = self.deck.number(found.group(2), found.group(3)) is not None
            return not present if found.group(1) else present
        try:
            return expressions.truth(str(when), scope)
        except expressions.BadExpression as exc:
            _fail(f"조건을 읽을 수 없습니다: {when!r} ({exc})")

    def cell(self, spec: Mapping[str, Any], scope: _Scope) -> str | None:
        """칸 하나. `None` 이면 **칸이 없다**(조건이 거짓이고 `default` 도 없다)."""
        default = spec.get("default")
        if "when" in spec and not self.keep(spec["when"], scope):
            return None if default is None else str(default)
        fmt = spec.get("format", "free")
        if "const" in spec:
            # **글자로 주면 글자 그대로 나간다.** Prony 의 체적항을 코드가 `0.0` 으로
            # 적는다 — 덱에는 그런 리터럴이 흔하고, 포맷을 거치면 바이트로 달라진다.
            # 형식이 `spec` 이면 그 폭으로 맞춘다(큰칸의 `PLASTIC`).
            const = spec["const"]
            if isinstance(const, str):
                return _format(const, fmt) if _is_spec(fmt) else const
            return _format(float(const), fmt)
        try:
            if "expr" in spec:
                value: Any = expressions.evaluate_any(str(spec["expr"]), scope)
            else:
                value = scope.lookup(str(spec.get("value", "")))
        except expressions.MissingName as exc:
            if default is not None:
                return str(default)
            self._missing(exc.name, spec, scope)
        except expressions.BadExpression as exc:
            _fail(str(exc))
        return _format(value, fmt)

    def _missing(self, name: str, spec: Mapping[str, Any], scope: _Scope) -> NoReturn:
        text = spec.get("expr") or spec.get("value")
        if (
            "." not in name
            and not name.startswith("_")
            and scope.row is not None
            and name not in scope.row
        ):
            have = ", ".join(map(str, scope.row))
            _fail(f"표에 없는 열입니다: {name}. 있는 것: {have}")
        where = f" ({text})" if "expr" in spec else ""
        _fail(f"값이 없습니다: {name}{where}. `when` 으로 걸러야 하는 줄입니다.")

    def cells(self, fields: Sequence[Mapping[str, Any]], scope: _Scope) -> list[str]:
        return [one for one in (self.cell(spec, scope) for spec in fields) if one is not None]

    # ── 줄 ────────────────────────────────────────────────────────────────

    def emit(self, item: Mapping[str, Any], out: list[str], scope: _Scope) -> None:
        if not isinstance(item, Mapping):
            _fail(f"줄은 {{…}} 모양이어야 합니다: {item!r}")
        if not self.keep(item.get("when"), scope):
            return
        say = item.get("note")
        if say:
            self.line_notes.append(self.text(str(say), scope))

        if "fail" in item:
            _fail(self.text(str(item["fail"]), scope))
        if "block" in item:
            self._block(item, out)
            return
        if "each" in item:
            self._each(item, out, scope)
            return
        if "pack" in item:
            self._pack(item, out, scope)
            return
        if "rows" in item:
            join = str(item.get("join", ", "))
            data = scope.rows(str(item["rows"]))
            for row in data:
                out.append(
                    self.text(str(item.get("prefix", "")), row)
                    + join.join(self.cells(item.get("fields", ()), row))
                    + self.text(str(item.get("suffix", "")), row)
                )
            return
        if "fields" in item:
            # **값 앞에 글자가 붙는 솔버가 있다.** ANSYS APDL 은 `MP,EX,1,2.1E5`
            # 처럼 명령·물성 이름이 같은 줄에 오고, Nastran 벌크는 `MAT1` 이 첫
            # 칸을 차지한다. 그것을 못 적으면 그 솔버는 아예 정의로 못 붙인다.
            join = str(item.get("join", ", "))
            out.append(
                self.text(str(item.get("prefix", "")), scope)
                + join.join(self.cells(item["fields"], scope))
                + self.text(str(item.get("suffix", "")), scope)
            )
            return
        if "text" not in item and say:
            # **말만 남기는 줄** — 덱에는 아무것도 안 적는다.
            return
        # 글자 줄 — 키워드도, 카드 값이 안 드는 옵션 줄(`plain`)도 여기다. 렌더러에게
        # 둘은 같다. 구분은 편집기가 묶음으로 접을 때만 쓴다.
        out.append(self.text(str(item.get("text", "")), scope))

    def _block(self, item: Mapping[str, Any], out: list[str]) -> None:
        make = BLOCKS.get(str(item["block"]))
        if make is None:
            _fail(
                f"모르는 묶음입니다: {item['block']}. "
                f"쓸 수 있는 것은 {', '.join(sorted(BLOCKS))} 입니다."
            )
        options = {key: value for key, value in item.items() if key not in _LINE_KEYS}
        try:
            out.extend(make(self.deck, **options))
        except TypeError as exc:
            _fail(f"묶음 '{item['block']}' 이 모르는 칸이 있습니다: {sorted(options)} ({exc})")

    def _each(self, item: Mapping[str, Any], out: list[str], scope: _Scope) -> None:
        """묶음(또는 줄)마다 줄 여럿. 묶음 안에서 `as` 이름이 **그 묶음의 표**다."""
        name = str(item["each"])
        alias = item.get("as")
        data = self.table(name, scope)
        count = len(data)
        for index, entry in enumerate(data, start=1):
            if isinstance(entry, _Group):
                child = scope.child(
                    names=_group_names(entry, index, count),
                    aliases={str(alias): entry.rows} if alias else None,
                )
            else:
                child = scope.child(row=entry, names={"_index": index, "_count": count})
            for sub in item.get("lines", ()):
                self.emit(sub, out, child)

    def _pack(self, item: Mapping[str, Any], out: list[str], scope: _Scope) -> None:
        """칸을 모아 `per_line` 개씩 끊는다.

        Nastran 큰칸: 논리 줄 8칸을 물리 줄 넷씩, 첫 줄 `MAT1*`·다음 줄 `*`, 빈 칸은
        16칸 공백, 끝은 `rstrip`. Radioss 목록: 다섯씩 한 줄. ANSYS: `TBDATA,{6*_line+1},`.
        """
        cells: list[str] = []
        for spec in item["pack"]:
            if "rows" in spec:
                for row in scope.rows(str(spec["rows"])):
                    if self.keep(spec.get("when"), row):
                        cells.extend(self.cells(spec.get("fields", ()), row))
            else:
                one = self.cell(spec, scope)
                if one is not None:
                    cells.append(one)
        pad_to = int(item.get("pad_to", 0) or 0)
        if pad_to:
            pad = str(item.get("pad", ""))
            if not cells:
                cells = [pad] * pad_to
            while len(cells) % pad_to:
                cells.append(pad)
        per = int(item.get("per_line", 0) or 0)
        if per < 1:
            _fail("pack 의 per_line 은 1 이상이어야 합니다.")
        join = str(item.get("join", ""))
        strip = bool(item.get("rstrip", False))
        for number, start in enumerate(range(0, len(cells), per)):
            here = scope.child(names={"_line": number})
            head = item.get("first" if number == 0 else "next", item.get("prefix", ""))
            text = (
                self.text(str(head or ""), here)
                + join.join(cells[start : start + per])
                + self.text(str(item.get("suffix", "")), here)
            )
            out.append(text.rstrip() if strip else text)


def alnum_name(name: str) -> str:
    """재료 이름에서 영숫자만 — 밑줄 · 붙임표를 다른 뜻으로 읽는 솔버를 위한 이름.

    CODE V 는 유리 이름 `N-BK7_SCHOTT` 을 「SCHOTT 카탈로그의 N-BK7」 로 읽는다. 사설 유리
    이름에 `_` 가 있으면 그 유리를 못 찾는다(ray-optics 의 CODE V 리더로 확인, 2026-10-03).
    """
    return re.sub(r"[^A-Za-z0-9]", "", name)


def _is_spec(fmt: Any) -> bool:
    return isinstance(fmt, (list, tuple)) and bool(fmt) and fmt[0] == "spec"


def _plain(value: Any) -> str:
    """형식 없이 적는 자리표 — 정수는 정수로(`{id}` → `4242`), 실수는 파이썬 그대로."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return str(value)


def _sortable(value: Any, table: str, column: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(
            f"표 '{table}' 를 '{column}' 로 정렬·묶을 수 없습니다 — 숫자가 아닌 줄이 있습니다."
        )
    return float(value)


def _pairs(
    rows: Sequence[Mapping[str, Any]], x: str, y: str
) -> tuple[tuple[float, float], ...]:
    """점 목록 — 두 열이 다 있는 줄만(`Deck.pairs` 와 같다)."""
    return tuple(
        (float(one[x]), float(one[y]))
        for one in rows
        if isinstance(one.get(x), (int, float)) and isinstance(one.get(y), (int, float))
    )


def _clip(groups: list[_Group], x: str, y: str) -> list[_Group]:
    """묶은 곡선을 **가장 짧은 끝**에서 자른다 — LS-DYNA 표는 곡선이 같은 x 에서 끝나야
    한다. 끝점은 이웃 두 점 사이의 직선으로 읽는다(잰 구간 안이다). 늘리지 않는다 — 긴
    곡선을 늘리는 것은 값을 지어내는 일이다."""
    end = min(group.rows[-1][x] for group in groups)
    out: list[_Group] = []
    for group in groups:
        points = [(one[x], one[y]) for one in group.rows]
        kept = [point for point in points if point[0] < end]
        exact = next((point for point in points if point[0] == end), None)
        if exact is not None:
            cut = [*kept, exact]
        else:
            after = next(point for point in points if point[0] > end)
            before = kept[-1]
            ratio = (end - before[0]) / (after[0] - before[0])
            cut = [*kept, (end, before[1] + ratio * (after[1] - before[1]))]
        out.append(
            _Group(
                group.key,
                [{x: first, y: second} for first, second in cut],
                clipped=points[-1][0] > end,
            )
        )
    return out


def _mark_ends(groups: list[_Group], x: str, y: str) -> None:
    """묶음마다 곡선의 첫·끝 점과 앞 묶음 — `_first_x` · `_first_y` · `_last_x` · `_last_y` ·
    `_prev_key` · `_below_prev`.

    `_below_prev` 는 **앞 곡선의 점(첫 점 빼고)에서 이 곡선이 더 낮은가**다 — 속도가
    높은데 응력이 낮으면 LS-DYNA 표의 곡선이 교차한다. 막지 않고 알린다(열 연화가 실제로
    그럴 수 있다).
    """
    previous: _Group | None = None
    for group in groups:
        points = [(one[x], one[y]) for one in group.rows]
        group.ends = {
            "_first_x": points[0][0] if points else None,
            "_first_y": points[0][1] if points else None,
            "_last_x": points[-1][0] if points else None,
            "_last_y": points[-1][1] if points else None,
            "_prev_key": previous.key if previous else None,
            "_below_prev": 0,
        }
        if previous is not None and points:
            low = [(one[x], one[y]) for one in previous.rows]
            if any(_value_at(points, at) < stress for at, stress in low[1:]):
                group.ends["_below_prev"] = 1
        previous = group


def _value_at(points: list[tuple[float, float]], at: float) -> float:
    """곡선의 x 에서 y — 이웃 두 점 사이의 직선, 밖이면 끝값."""
    for (x0, y0), (x1, y1) in pairwise(points):
        if x0 <= at <= x1:
            return y0 + (y1 - y0) * (at - x0) / (x1 - x0)
    return points[-1][1]


def _walk(lines: Any) -> list[Mapping[str, Any]]:
    """줄 전부 — `each` 안의 줄까지."""
    found: list[Mapping[str, Any]] = []
    for item in lines or ():
        if isinstance(item, Mapping):
            found.append(item)
            if "each" in item:
                found.extend(_walk(item.get("lines")))
    return found


def render(spec: Mapping[str, Any], deck: Any) -> Rendered:
    """정의 한 벌로 덱을 만든다.

    **표 정리에서 나온 말이 줄에서 나온 말보다 앞선다** — 코드 렌더러가 그 차례로 쌓았고,
    그 차례가 곧 「무엇을 먼저 알아야 하나」 다. 표 정의에 `"notes": "last"` 를 적으면
    그 표의 말을 맨 뒤로 보낸다(Abaqus 속도 의존처럼 밀도 말이 앞서는 형식).
    """
    # 순환을 피해 여기서 부른다. **`Rendered` 는 `matcore.export` 의 것을 쓴다** —
    # 같은 모양을 하나 더 두면 라우트가 어느 쪽을 받는지 흐려진다.
    from matcore.export import ExportError, Rendered

    state = _Render(spec, deck)
    lines: list[str] = []
    # **정의 줄마다 덱의 몇 줄이 됐는지 남긴다.** 줄은 뒤에만 붙으므로 이번 줄의
    # 시작이 곧 앞 줄의 끝이다 — `when` 으로 걸러진 줄은 빈 구간이다.
    starts: list[int] = []
    for item in spec.get("lines", ()):
        starts.append(len(lines))
        try:
            state.emit(item, lines, state.root)
        except expressions.BadExpression as exc:
            raise ExportError(str(exc)) from exc
    ends = [*starts[1:], len(lines)]
    spans = tuple(
        (index, start, end)
        for index, (start, end) in enumerate(zip(starts, ends, strict=True))
    )
    return Rendered(
        text="\n".join(lines) + "\n",
        notes=(*state.head_notes, *state.line_notes, *state.last_notes),
        spans=spans,
    )


# ── 저장 전 검사 ──────────────────────────────────────────────────────────────

#: 정의에 반드시 있어야 하는 것. 없으면 **저장 전에** 막는다 — 기동이나 내려받기
#: 시점에 터지면 그때는 화면에서 고칠 사람이 그 자리에 없다.
REQUIRED = ("key", "label", "extension", "describe", "lines")

#: 글자 자리표가 들 수 있는 칸.
_TEXT_KEYS = ("text", "prefix", "suffix", "note", "fail", "first", "next")


def _check_text(template: str, where: str) -> None:
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        _fail(
            f"{where}: 중괄호를 읽을 수 없습니다 ({exc}). 중괄호 자체는 {{{{ }}}} 로 적고, "
            "자리표 안의 비교는 != 대신 not (a == b) 로 적습니다."
        )
    for _, name, spec, conversion in parsed:
        if name is None:
            continue
        if conversion:
            _fail(f"{where}: 자리표에 ! 를 쓸 수 없습니다 — 비교는 not (a == b) 로 적습니다.")
        if not name.strip():
            _fail(
                f"{where}: 빈 자리표 {{}} 는 못 씁니다 — 중괄호 자체는 {{{{ }}}} 로 적습니다."
            )
        if name.strip() not in ("name", "name_alnum", "units", "id"):
            _check_expr(name, where)
        if spec and _SPEC.fullmatch(spec) is None:
            _fail(f"{where}: 읽을 수 없는 형식입니다: {spec!r}")


def _check_expr(text: Any, where: str) -> None:
    try:
        expressions.parse(str(text))
    except expressions.BadExpression as exc:
        _fail(f"{where}의 식: {exc}")


def _check_when(when: Any, where: str) -> None:
    if when and not _OLD_WHEN.fullmatch(str(when)):
        _check_expr(when, f"{where} 조건")


def _check_field(spec: Any, where: str) -> None:
    if not isinstance(spec, Mapping):
        _fail(f"{where}: 칸은 {{…}} 모양이어야 합니다.")
    if "expr" in spec:
        _check_expr(spec["expr"], where)
    _check_when(spec.get("when"), where)
    fmt: Any = spec.get("format")
    if _is_spec(fmt) and (len(fmt) < 2 or _SPEC.fullmatch(str(fmt[1])) is None):
        _fail(f"{where}: 읽을 수 없는 형식입니다: {fmt!r}")


def _check_lines(lines: Any, where: str) -> None:
    if not isinstance(lines, list):
        _fail(f"{where}: `lines` 는 줄의 목록이어야 합니다.")
    for at, line in enumerate(lines, start=1):
        here = f"{where}{at}번 줄"
        if not isinstance(line, Mapping):
            _fail(f"{here}: 줄은 {{…}} 모양이어야 합니다.")
        _check_when(line.get("when"), here)
        for key in _TEXT_KEYS:
            if isinstance(line.get(key), str):
                _check_text(line[key], here)
        for spec in line.get("fields", ()) or ():
            _check_field(spec, here)
        if "pack" in line:
            if not isinstance(line["pack"], list):
                _fail(f"{here}: pack 은 칸의 목록이어야 합니다.")
            if int(line.get("per_line", 0) or 0) < 1:
                _fail(f"{here}: pack 의 per_line 은 1 이상이어야 합니다.")
            for spec in line["pack"]:
                if isinstance(spec, Mapping) and "rows" in spec:
                    _check_when(spec.get("when"), here)
                    for one in spec.get("fields", ()) or ():
                        _check_field(one, here)
                else:
                    _check_field(spec, here)
        if "each" in line:
            _check_lines(line.get("lines"), f"{here} 안의 ")


def _check_tables(tables: Any) -> None:
    if tables is None:
        return
    if not isinstance(tables, Mapping):
        _fail("`tables` 는 {이름: 정의} 모양이어야 합니다.")
    for name, spec in tables.items():
        if not isinstance(spec, Mapping):
            _fail(f"표 '{name}' 의 정의는 {{…}} 모양이어야 합니다.")
        if spec.get("where"):
            _check_expr(spec["where"], f"표 '{name}' 의 where")
        if isinstance(spec.get("note"), str):
            _check_text(spec["note"], f"표 '{name}' 의 note")
        if spec.get("notes") not in (None, "head", "last"):
            _fail(f"표 '{name}' 의 notes 는 head 또는 last 입니다.")
        if spec.get("by"):
            _check_expr(spec["by"], f"표 '{name}' 의 by")
        if spec.get("clip") not in (None, "shortest"):
            _fail(f"표 '{name}' 의 clip 은 shortest 만 됩니다.")
        if bool(spec.get("x")) != bool(spec.get("y")):
            _fail(f"표 '{name}': x 와 y 는 함께 적습니다.")


def renderer_from_definition(definition: Mapping[str, Any]) -> Any:
    """정의 한 벌을 렌더러로 만든다. **`matcore` 는 DB 를 모른다** — dict 로 받는다.

    인풋 프로파일과 같은 규칙이다(ADR 0006): 행을 읽는 것은 앱이고, 여기 오는
    것은 이미 dict 다.

    **검증을 여기서 다 한다.** 저장하는 쪽이 이 함수를 그대로 불러 보면 「저장은
    됐는데 내려받을 때 터지는」 정의가 안 생긴다 — 식·자리표·형식·조건을 다 읽어 본다.
    값이 있는지는 카드마다 달라 내려받을 때 본다.
    """
    from matcore.export import Need, Renderer, systems

    missing = [key for key in REQUIRED if not definition.get(key)]
    if missing:
        _fail(f"정의에 빠진 것이 있습니다: {', '.join(missing)}")

    lines = definition["lines"]
    _check_lines(lines, "")
    _check_tables(definition.get("tables"))

    needs = []
    for raw in definition.get("needs", ()):
        block = raw.get("block")
        if not block:
            _fail("`needs` 의 각 항목에는 `block` 이 있어야 합니다.")
        at_least = raw.get("at_least") or {}
        if not isinstance(at_least, Mapping):
            _fail('`needs` 의 at_least 는 {값: 최소} 모양입니다 — {"rate_count": 2}.')
        needs.append(
            Need(
                block=str(block),
                values=tuple(str(name) for name in raw.get("values", ())),
                rows_min=int(raw.get("rows_min", 0)),
                at_least=tuple((str(key), float(floor)) for key, floor in at_least.items()),
                optional=bool(raw.get("optional", False)),
            )
        )

    fixed = definition.get("units")
    fixed_units = None
    if fixed:
        try:
            fixed_units = systems.get(str(fixed))
        except KeyError:
            known = ", ".join(one.key for one in systems.SYSTEMS)
            _fail(f"`units` 는 붙박이 단위계 key 입니다 — {known}. 받은 것: {fixed!r}")

    spec = {"lines": lines, "tables": definition.get("tables") or {}}
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
        solver=str(definition.get("solver", "") or ""),
        fixed_units=fixed_units,
    )
