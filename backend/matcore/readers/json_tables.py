"""JSON 안의 표를 찾는다. **여기도 의미는 모른다.**

층 1 의 나머지 절반이다. `tabular.py` 가 구분자 텍스트를 읽고, 여기가 JSON 을
읽는다. 둘 다 같은 `TabularFile` 을 내므로 **프로파일·곡선·처리는 어느 쪽에서
왔는지 모른다** — 그게 이 모듈이 성립하는 조건이다.

## 왜 필요했나

실파일 전수 조사에서 나온 것이다. 기존 앱(`MaterialAppVer2`)의 `.mtet`·`.mdss`·
`.mdft` 가 JSON 인데, 배열 안 숫자 줄이 연달아 나와서 구분자 리더가 "표 93개" 로
잡았다. **고유 파일 131개 중 59개가 그렇게 조용히 '성공'했다.** 그래서 일단
거절하게 막아 뒀는데, 거절만 하면 그 파일들은 영영 안 들어온다.

## 표를 어떻게 알아보나 — 이름이 아니라 모양으로

`"Raw Data"` 같은 이름을 찾지 않는다. 그건 이 앱 한 종류를 아는 것이고, 그러면
다음 장비에서 또 못 읽는다. 대신 **구조적 서명** 둘만 본다.

    열 지향   {"a": [1, 2, 3], "b": [4, 5, 6]}     길이가 같은 리스트들
    행 지향   [{"a": 1, "b": 4}, {"a": 2, "b": 5}]  같은 키를 가진 딕셔너리들

실측 282개(`002_Material`)는 전부 열 지향이었고, 블록 한 겹이 더 있는 것이
131개, 평면이 124개였다. 블록 이름(`Temperature Sweep (Multifrequency) - 2`)이
그대로 표 이름이 된다.

## 단위를 열 이름에서 뽑지 않는다

`Standard extensometer (mm)` 을 보면 `(mm)` 을 단위로 떼고 싶어진다. **안 한다.**

실측: 서로 다른 열 이름 17개 중 `Tan(delta)` 가 596번 나온다. 괄호를 단위로 떼면
`Tan` 이라는 열에 `delta` 라는 단위가 붙는다. 게다가 같은 열이 파일에 따라
`Standard extensometer (mm)` 로도 `Standard extensometer` 로도 온다(55회 대 33회)
— 뗀다고 일관돼지지도 않는다.

단위는 프로파일이 채널마다 선언한다. 그게 프로파일이 있는 이유다.
"""

from __future__ import annotations

import json
from typing import Any

from matcore.readers.tabular import ReadError, ReadOptions, Table, TabularFile

#: 표로 인정할 최소 행 수. 1행짜리는 표가 아니라 값 하나다 — 그것까지 표로 만들면
#: 메타 딕셔너리가 통째로 표가 된다.
MIN_ROWS = 2


def looks_like_json(text: str) -> bool:
    """JSON 리더로 보낼 것인가. **`[` 만으로는 안 된다.**

    처음에 `{` 또는 `[` 로 시작하면 JSON 이라고 봤는데, 시험이 바로 잡았다 —
    구분자 텍스트 포맷은 `[step]` 같은 **마커로 시작한다.** 그런 파일이 JSON
    리더로 가면 "1행 2칸: Expecting value" 로 죽는다. 읽히던 파일이 안 읽힌다.

    그래서 둘을 다르게 다룬다.

    * `{` 로 시작하면 JSON 이다. 표 형식 파일이 여는 중괄호로 시작하는 경우는
      없다. 여기서 파싱에 실패하면 **JSON 이 깨진 것**이므로 오류를 낸다 —
      조용히 텍스트 리더로 흘려보내면 잘린 JSON 이 '표 93개' 로 읽힌다
    * `[` 로 시작하면 **실제로 파싱될 때만** JSON 이다. 아니면 마커다
    """
    head = text.lstrip()
    if head[:1] == "{":
        return True
    if head[:1] != "[":
        return False
    try:
        json.loads(head)
    except ValueError:
        return False
    return True


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, dict | list)


def _as_text(value: Any) -> str:
    """**원문 문자열 그대로** 로 만든다.

    숫자로 바꾸는 것은 매핑을 정한 뒤의 일이다(`tabular.Table.rows` 와 같은 규칙).
    여기서 `float` 로 바꾸면 유효숫자가 조용히 깎이고, 프로파일이 되돌릴 수 없다.
    """
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _column_table(
    node: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]] | None:
    """열 지향 표인가. `{"a": [...], "b": [...]}` 이고 길이가 같아야 한다."""
    if not node:
        return None
    lengths = set()
    for value in node.values():
        if not isinstance(value, list) or not all(_is_scalar(item) for item in value):
            return None
        lengths.add(len(value))
    if len(lengths) != 1:
        # 길이가 다르면 표가 아니다. **여기서 짧은 쪽에 맞춰 자르지 않는다** —
        # 열마다 다른 점을 가리키는 곡선이 조용히 만들어진다.
        return None
    count = lengths.pop()
    if count < MIN_ROWS:
        return None
    header = tuple(str(key) for key in node)
    columns = list(node.values())
    rows = tuple(
        tuple(_as_text(column[index]) for column in columns) for index in range(count)
    )
    return header, rows


def _record_table(
    node: list[Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]] | None:
    """행 지향 표인가. `[{"a": 1}, {"a": 2}]` 이고 키가 같아야 한다."""
    if len(node) < MIN_ROWS or not all(isinstance(item, dict) for item in node):
        return None
    first = node[0]
    if not first or not all(_is_scalar(value) for value in first.values()):
        return None
    header = tuple(str(key) for key in first)
    for item in node[1:]:
        if tuple(str(key) for key in item) != header:
            return None
        if not all(_is_scalar(value) for value in item.values()):
            return None
    rows = tuple(tuple(_as_text(item[key]) for key in first) for item in node)
    return header, rows


class _Walker:
    """트리를 훑어 표와 메타로 가른다.

    표를 만나면 **그 안으로 안 들어간다.** 표 안의 열 이름이 메타 키로 새면
    메타가 수백 줄이 되고, 사람이 미리보기에서 아무것도 못 찾는다.
    """

    def __init__(self) -> None:
        self.tables: list[Table] = []
        self.meta: list[tuple[str, str]] = []
        self.warnings: list[str] = []

    def walk(self, node: Any, name: str | None = None) -> None:
        if isinstance(node, dict):
            found = _column_table(node)
            if found is not None:
                self._add(name, *found)
                return
            for key, value in node.items():
                if _is_scalar(value):
                    # 빈 키는 버린다 — 실측 파일마다 `"": {}` 가 하나씩 있다.
                    if str(key):
                        self.meta.append((str(key), _as_text(value)))
                else:
                    self.walk(value, str(key))
            return

        if isinstance(node, list):
            found = _record_table(node)
            if found is not None:
                self._add(name, *found)
                return
            if node and all(_is_scalar(item) for item in node):
                # 딸린 리스트 하나짜리. 표로 보기엔 열이 없고, 버리기엔 값이다.
                self.meta.append((name or "list", ", ".join(_as_text(item) for item in node)))
                return
            for index, item in enumerate(node):
                self.walk(item, f"{name or 'item'}[{index}]")

    def _add(
        self, name: str | None, header: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
    ) -> None:
        self.tables.append(
            Table(
                index=len(self.tables),
                name=name,
                header=header,
                units=(),
                rows=rows,
                # JSON 에는 줄 번호가 뜻이 없다. 표 차례로 대신한다 — 0 으로 두면
                # 화면이 "1번째 줄" 이라고 말하는데 그런 줄이 없다.
                first_line=len(self.tables) + 1,
            )
        )


def read_json(
    data: bytes,
    *,
    text: str,
    encoding: str,
    warnings: list[str],
    options: ReadOptions | None = None,
) -> TabularFile:
    """이미 디코드된 JSON 텍스트를 `TabularFile` 로.

    `tabular.read()` 가 디코드까지 마친 뒤 넘겨 준다 — 인코딩 추측을 두 번 하면
    두 경로가 서로 다른 답을 내는 날이 온다.
    """
    opts = options or ReadOptions()
    try:
        root = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReadError(
            f"JSON 으로 시작하는데 파싱에 실패했습니다"
            f"({exc.lineno}행 {exc.colno}칸: {exc.msg}). "
            f"파일이 잘렸거나 인코딩이 다를 수 있습니다."
        ) from None

    if opts.delimiter:
        warnings.append("JSON 이라 구분자 설정은 쓰이지 않습니다.")
    if opts.skip_lines:
        warnings.append("JSON 이라 '앞 줄 건너뛰기' 설정은 쓰이지 않습니다.")

    walker = _Walker()
    walker.walk(root)
    if not walker.tables:
        raise ReadError(
            "JSON 에서 표를 찾지 못했습니다. 길이가 같은 리스트들을 가진 객체"
            "(열 지향)나 같은 키를 가진 객체들의 배열(행 지향)이 있어야 합니다."
        )

    return TabularFile(
        encoding=encoding,
        # 구분자가 없다. 빈 문자열이 "JSON 이라 해당 없음" 이다.
        delimiter="",
        meta=tuple(walker.meta),
        tables=tuple(walker.tables),
        warnings=tuple(warnings + walker.warnings),
        line_count=len(text.splitlines()),
    )
