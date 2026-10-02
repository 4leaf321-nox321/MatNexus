"""솔버 카드 — **물성이 해석으로 넘어가는 마지막 한 걸음.**

여기서 나온 텍스트가 그대로 솔버 덱에 들어간다. 그래서 이 패키지의 태도는 앞
단계들과 조금 다르다 — 앞에서는 "모르면 말한다" 였지만, 여기서는 **"모르면 쓰지
않는다"** 다. 카드에 적힌 숫자는 전부 어디선가 잰 값이어야 한다.

## 단위를 바꾸지 않는다

전부 SI(kg·m·s·Pa) 그대로 쓴다. 환산 계수는 1.0 이다. mm·ton·s 로 푸는 사람이
있지만, 우리가 환산해서 내보내면 **그 덱의 다른 재료가 SI 인지 확인할 길이
없다** — 단위계가 섞인 덱은 조용히 1000배 틀린 답을 낸다. 대신 단위를 **선언**한다:
OpenRadioss 는 `/UNIT/1` 블록으로, Abaqus 는 단위 키워드가 없으므로 주석으로.

65도 같은 판단이었다 — 변환 엔진이 있는데도 익스포트 경로에 두지 않고, 정본이
아닌 단위가 들어오면 거부했다.

## 없는 값을 만들지 않는다

푸아송비가 없으면 0.3 을 넣지 않고 **거부한다.** `*ELASTIC` 은 값 두 개를 받는
키워드라 하나를 비울 수 없고, 0.3 을 넣으면 그것이 측정값인지 우리가 채운 값인지
덱만 봐서는 알 수 없다.

## 조용히 고치지 않는다

솔버는 표에 규칙을 요구한다 — 첫 점의 소성변형률이 0, 변형률은 순증가, 응력은
감소하지 않음. 우리 데이터가 그 규칙을 어기면 **고쳐서 내보내지 않고** 무엇이
문제이고 무엇을 하면 되는지 말한다. 다만 탄성 구간을 0 으로 자른 흔적(같은 0 이
여러 점)만은 한 점으로 모으는데, 그것은 값을 바꾸는 것이 아니라 **처리 단계가
남긴 자국을 지우는 것**이고, 그 사실도 카드 주석에 적는다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from matcore.export import systems as systems  # 재수출 — 앱이 key 로 고른다
from matcore.export import template
from matcore.export.systems import SI, UnitSystem
from matcore.export.systems import SYSTEMS as SYSTEMS  # 재수출 — 앱이 목록을 보여 준다

#: 표의 최소·최대 점 수. 2점이면 직선 하나이고, 5000점이 넘으면 솔버가 읽다
#: 지친다(65도 같은 상한).
MIN_POINTS = 2
MAX_POINTS = 5000

#: 솔버가 받는 재료 이름. 한글·공백·점이 들어가면 솔버가 못 읽거나 잘라 버린다.
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")

#: 솔버 덱 안에서 재료를 가리키는 번호. 우리 id 는 UUID 라 그대로 못 쓴다.
MAX_SOLVER_ID = 9_999_999

#: 첫 점을 항복점(소성변형률 0)으로 볼 수 있는 한계. 0.01% 변형이다.
#:
#: **왜 필요한가:** 진소성변형률 축에서 재샘플하면 시편마다 최솟값이 미세하게
#: 달라 공통 시작이 0 이 아니라 2e-6 같은 값이 된다. 격자 간격보다 네 자릿수
#: 작아서 그 점의 응력은 사실상 항복강도 그대로다. 이보다 크면 **진짜로 항복점이
#: 빠진 것**이라 거부한다 — 0.01% 를 넘는 소성변형은 이미 소성 구간이다.
YIELD_ANCHOR_TOLERANCE = 1e-4

#: 첫 구간의 응력 상승이 뒤 구간들의 **중앙값보다 몇 배**면 이상하다고 보나.
#:
#: **첫 점의 «값»을 보는 검사다.** 위의 앵커 검사는 첫 점의 *변형률*이 0 인지만
#: 본다 — 값은 지금까지 아무도 안 봤다. 그런데 솔버는 그 점을 초기 항복으로
#: 읽는다(LS-DYNA 는 SIGY 를 거기서 가져온다). 그 수가 틀리면 **성형 해석에서
#: 가장 많이 쓰이는 값이 틀린다.**
#:
#: 실측(2026-09-10): 첫 점 173.4 MPa 뒤 곧바로 352.7 MPa 였다(+103%). 뒤 구간은
#: 점마다 0.7% 씩 올랐다. 변형률은 0 이라 기존 검사를 전부 통과했고, 그래서
#: **덱은 멀쩡히 돌면서 항복만 절반**이 됐다.
#:
#: 중앙값에 견주는 이유는 표마다 점 간격이 달라서다 — 절대값으로 문턱을 두면
#: 성긴 표에서 늘 걸린다.
FIRST_RISE_FACTOR = 5.0

#: 그리고 **첫 점 대비 상대 상승**도 이만큼은 돼야 짚는다. 잔 노이즈 수준의
#: 들쭉날쭉에 매번 경고를 달면 그 문장이 경고로 안 읽힌다.
FIRST_RISE_RELATIVE = 0.05


class ExportError(Exception):
    """이 카드로는 이 솔버 덱을 만들 수 없다.

    메시지는 **사용자가 읽는다.** 무엇이 없고 어디서 채우면 되는지 적는다.
    """


@dataclass(frozen=True)
class Need:
    """이 솔버가 **어느 물성 블록을 먹는지.**

    전에는 `Card` 의 필드 이름을 가리켰다(`("youngs_modulus", "prony")`). 그래서
    새 물성이 붙을 때마다 그 dataclass 에 칸을 뚫어야 했고, 그것이 **중심 코드를
    고쳐야 하는 마지막 자리**였다.

    지금은 블록 이름을 가리킨다. 블록은 레지스트리의 데이터라(ADR 0012) 새 물성이
    붙어도 이 파일은 안 커진다.
    """

    block: str
    values: tuple[str, ...] = ()
    """이 블록에서 반드시 있어야 하는 값."""
    rows_min: int = 0
    """이 블록의 표에 최소 몇 줄이 있어야 하는가."""
    at_least: tuple[tuple[str, float], ...] = ()
    """값이 이만큼은 돼야 한다 — `(("rate_count", 2),)`. 있느냐만 보면 「낼 수 있다」 고
    말해 놓고 렌더러가 거절한다(2026-09-05 실측: 속도가 하나뿐인 카드에 abaqus_rate)."""
    optional: bool = False
    """없어도 덱은 나온다. **다만 덱에 그 사실을 적는다** — 밀도가 그렇다."""


@dataclass(frozen=True)
class Deck:
    """솔버 덱으로 나갈 것 — **물성 블록을 그대로 들고 있다.**

    전에는 `Card` 라는 **정해진 양식**이었다. 칸이 미리 뚫려 있어서(탄성계수·
    푸아송비·밀도·소성표·Prony·초탄성 계수) 물성이 늘 때마다 이 파일에 칸을 더해야
    했다. 점탄성이 2칸, 초탄성이 3칸을 뚫었다.

    지금은 카드가 가진 블록을 통째로 받고, 무엇이 필요한지는 **렌더러가 선언한다**.

    ## 값은 전부 SI 다

    블록에 담기는 순간 SI 로 저장된다(ADR 0012). 여기서 환산하지 않는다 — 단위계가
    섞인 덱은 조용히 1000배 틀린 답을 낸다.
    """

    name: str
    """솔버 덱 안의 재료 이름. ASCII 로 정리된 것이 들어온다."""
    solver_id: int
    blocks: Mapping[str, Any] = field(default_factory=dict)
    """`{블록 key: {"values": {...}, "rows": [...], "notes": [...]}}`."""
    provenance: tuple[str, ...] = ()
    """어디서 나온 값인지. **카드 주석으로 들어간다** — 덱만 받은 사람이 되짚을
    수 있어야 한다."""
    units: UnitSystem = SI
    """이 덱의 숫자가 **어느 단위계인가.**

    `render` 가 환산한 뒤 이 값을 세워서 렌더러에 넘긴다. 렌더러는 여기를 읽어
    선언 줄을 쓴다 — 기호를 손으로 적으면 값과 선언이 갈라지는 날이 온다.

    기본이 SI 인 이유: 고르지 않으면 전과 같은 것이 나가야 한다."""

    def has(self, block: str) -> bool:
        return bool(self.blocks.get(block))

    def values(self, block: str) -> dict[str, Any]:
        payload = self.blocks.get(block) or {}
        got = payload.get("values") if isinstance(payload, Mapping) else None
        return dict(got) if isinstance(got, Mapping) else {}

    def rows(self, block: str) -> list[dict[str, Any]]:
        payload = self.blocks.get(block) or {}
        got = payload.get("rows") if isinstance(payload, Mapping) else None
        return [dict(row) for row in got] if isinstance(got, list) else []

    def number(self, block: str, key: str) -> float | None:
        """숫자 하나. **없으면 없는 채로 준다** — 0 으로 바꾸지 않는다."""
        value = self.values(block).get(key)
        return float(value) if isinstance(value, int | float) else None

    def pairs(self, block: str, x: str, y: str) -> tuple[tuple[float, float], ...]:
        """표에서 두 열을 뽑아 점 목록으로."""
        return tuple(
            (float(row[x]), float(row[y])) for row in self.rows(block) if x in row and y in row
        )


@dataclass(frozen=True)
class Rendered:
    text: str
    notes: tuple[str, ...] = field(default=())
    """내보내면서 한 일. **조용히 하지 않았다는 증거다.**"""
    spans: tuple[tuple[int, int, int], ...] = field(default=())
    """정의의 줄 → 덱의 줄. `(정의 줄 번호, 시작 줄, 끝 줄)` — 끝은 포함하지 않는다.
    코드 렌더러는 비워 둔다. 정의 편집기가 「어느 정의가 어느 줄이 됐나」 를 잇는 데 쓴다."""


def sanitize_name(raw: str, *, fallback: str = "MATERIAL") -> str:
    """솔버가 읽을 수 있는 이름으로 만든다.

    한글 이름이 그대로 들어가면 솔버가 못 읽거나 말없이 잘라 버린다. 바꾼 사실은
    카드 주석에 남는다 — 이름이 달라져 있으면 덱을 받은 사람이 혼란스럽다.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_-")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"{fallback}_{cleaned}".strip("_-")
    cleaned = cleaned[:80]
    if not NAME_PATTERN.match(cleaned):
        raise ExportError(
            f"'{raw}' 를 솔버가 읽는 이름으로 바꾸지 못했습니다. "
            f"영문자로 시작하고 영문·숫자·밑줄·붙임표만 쓰는 이름을 카드에 지어 주세요."
        )
    return cleaned


def solver_id_from(value: str) -> int:
    """UUID 에서 덱 안에서 쓸 번호를 만든다.

    **파일 안에서만 뜻이 있는 번호다.** 덱을 합칠 때 겹치면 사람이 바꾸면 된다 —
    우리가 전역으로 유일한 번호를 관리하기 시작하면, 그 번호를 어느 덱에 썼는지도
    관리해야 한다.
    """
    digits = int(re.sub(r"[^0-9a-f]", "", value.lower()) or "1", 16)
    return 1 + digits % MAX_SOLVER_ID


def prepare(
    points: tuple[tuple[float, float], ...],
) -> tuple[list[tuple[float, float]], list[str]]:
    """표를 솔버가 받는 모양으로 정리한다. **못 고칠 것은 거부한다.**

    유일하게 고치는 것은 탄성 구간을 0 으로 자른 자국이다(같은 0 이 여러 점).
    `tensile.true_plastic` 의 `clip_zero` 가 남긴 것이라 값이 아니라 자국이고,
    그중 **마지막 점**이 항복점이다 — 첫 점을 쓰면 응력이 0 에 가까운 곳을
    항복강도라고 적게 된다.
    """
    if len(points) < MIN_POINTS:
        raise ExportError(f"표가 {len(points)}점입니다. {MIN_POINTS}점 이상이어야 합니다.")
    if len(points) > MAX_POINTS:
        raise ExportError(
            f"표가 {len(points)}점입니다. {MAX_POINTS}점을 넘으면 솔버가 읽기 어렵습니다 "
            f"— 레시피의 재샘플 점 수를 줄이세요."
        )

    notes: list[str] = []
    ordered = list(points)

    zeros = [index for index, (strain, _) in enumerate(ordered) if strain <= 0.0]
    if len(zeros) > 1:
        # 마지막 0 점이 항복점이다. 앞의 것들은 탄성 구간이 잘린 자국이다.
        keep = zeros[-1]
        notes.append(
            f"소성변형률이 0 인 점이 {len(zeros)}개였습니다. 탄성 구간을 0 으로 자른 "
            f"자국이라, 그중 마지막(항복점, 응력 {ordered[keep][1]:.5g})만 남기고 "
            f"앞의 {len(zeros) - 1}점을 뺐습니다."
        )
        ordered = ordered[keep:]

    if 0.0 < ordered[0][0] <= YIELD_ANCHOR_TOLERANCE:
        # **값을 지어내는 것이 아니라 자리를 맞추는 것이다.** 진소성변형률 축에서
        # 재샘플하면 첫 점이 정확히 0 이 아니라 2e-6 처럼 나온다 — 격자 간격보다
        # 네 자릿수 작아서 응력은 사실상 항복점 그대로다. 솔버는 첫 점을 0 으로
        # 요구하므로 그 자리만 옮기고, 옮겼다는 사실을 적는다.
        notes.append(
            f"첫 점의 소성변형률이 {ordered[0][0]:.3g} 였습니다 — "
            f"{YIELD_ANCHOR_TOLERANCE:.0e} 이하라 0 으로 맞췄습니다(응력 "
            f"{ordered[0][1]:.5g} 는 그대로). 솔버는 첫 점을 항복점으로 읽습니다."
        )
        ordered[0] = (0.0, ordered[0][1])

    if ordered[0][0] != 0.0:
        raise ExportError(
            f"첫 점의 소성변형률이 {ordered[0][0]:.5g} 입니다 — 0 이어야 합니다 "
            f"(허용 오차 {YIELD_ANCHOR_TOLERANCE:.0e}). 솔버는 첫 점을 항복점으로 "
            f"읽습니다. 처리 레시피의 '진응력·진소성변형률' 단계에서 '음의 "
            f"소성변형률'을 '0 으로 자름'으로 두거나, 진소성변형률 축 재샘플의 "
            f"시작을 0 에 붙이세요."
        )

    for index in range(1, len(ordered)):
        if ordered[index][0] <= ordered[index - 1][0]:
            raise ExportError(
                f"{index}번째 점의 소성변형률이 앞 점보다 크지 않습니다 "
                f"({ordered[index - 1][0]:.6g} → {ordered[index][0]:.6g}). "
                f"솔버는 순증가를 요구합니다 — 레시피에 '중복 x 정리' 단계를 넣으세요."
            )
        if ordered[index][1] < ordered[index - 1][1]:
            # **연화를 숨기지 않는다.** 값을 눕혀서 내보내면 그 덱은 실제와 다른
            # 재료가 되고, 아무도 그 사실을 모른다.
            #
            # 숫자에 단위를 안 붙인다. 이 함수는 `to_system` 뒤에 불려 값이 이미 덱의
            # 계라, `/1e6 MPa` 로 적으면 255 MPa 가 「0.000255 MPa」 로 나왔다(2026-09-05).
            raise ExportError(
                f"{index}번째 점에서 응력이 떨어집니다 "
                f"({ordered[index - 1][1]:.6g} → {ordered[index][1]:.6g}, 덱의 응력 단위). "
                f"네킹 뒤 구간이 섞였을 수 있습니다 — 'tensile.necking_candidate' 가 "
                f"제시한 위치에서 자르고 다시 처리하세요. 여기서 눕혀 내보내면 그 덱은 "
                f"실제와 다른 재료가 됩니다."
            )

    if len(ordered) < MIN_POINTS:
        raise ExportError(f"정리하고 나니 {len(ordered)}점입니다. 표가 너무 짧습니다.")

    suspect = _first_point_suspect(ordered)
    if suspect is not None:
        notes.append(suspect)
    return ordered, notes


def _first_point_suspect(ordered: list[tuple[float, float]]) -> str | None:
    """첫 점의 **값**이 항복점 같지 않으면 그 사실을 적는다. **막지는 않는다.**

    경화 곡선은 점마다 조금씩 오른다. 첫 구간만 뒤 구간들과 자릿수가 다르게
    뛰면, 첫 점은 항복점이 아니라 **재샘플이 항복 앞에서 끌어온 자국**일 가능성이
    크다 — 그 점의 변형률이 0 이라 앵커 검사는 통과한다.

    막지 않는 이유는 위의 네킹과 같다. 항복 직후에 실제로 가파른 재료가 있고,
    거부하면 사람은 시스템 밖에서 표를 고쳐 근거 없는 덱을 만든다. 대신 **덱
    각주에 적어** 받는 사람이 보게 한다.
    """
    if len(ordered) < 4:
        # 점이 서넛이면 「전형적인 상승」 이라 할 것이 없다.
        return None
    rises = [ordered[index][1] - ordered[index - 1][1] for index in range(1, len(ordered))]
    first, rest = rises[0], sorted(rises[1:])
    typical = rest[len(rest) // 2]
    if first <= 0.0 or typical <= 0.0 or ordered[0][1] <= 0.0:
        return None
    if first < FIRST_RISE_FACTOR * typical:
        return None
    if first / ordered[0][1] < FIRST_RISE_RELATIVE:
        return None
    return (
        f"**첫 점이 항복점 값이 아닐 수 있습니다.** 첫 점 {ordered[0][1]:.5g} 에서 "
        f"다음 점 {ordered[1][1]:.5g} 로 {first / ordered[0][1]:.0%} 뛰는데, 뒤 "
        f"구간은 한 점에 {typical:.4g} 씩 오릅니다(모두 덱의 응력 단위) — "
        f"{first / typical:.0f}배입니다. 솔버는 첫 점을 초기 항복으로 읽으므로, "
        f"이 값이 틀리면 항복강도가 틀린 덱이 됩니다. 처리에서 탄성 구간을 자른 "
        f"자리와 진소성변형률 축 재샘플의 시작을 확인하세요."
    )


#: 값 이름의 한국어. 오류 메시지와 형식 목록이 같은 말을 쓴다.
def _label(block: str, key: str | None = None) -> str:
    """사람이 읽는 이름. **레지스트리가 이미 갖고 있다** — 여기서 다시 적지 않는다.

    등록되지 않은 블록이면 key 를 그대로 쓴다. 이름을 모른다고 침묵하는 것보다
    낫다 — 그 상황 자체가 알려야 할 일이다.
    """
    from matcore import cards

    try:
        spec = cards.block(block)
    except KeyError:
        return f"{block}.{key}" if key else block
    if key is None:
        return spec.label
    # **값의 이름만 쓴다.** "탄성 탄성계수" 는 읽기 나쁘고, 값 이름은 이미
    # 그 자체로 알아볼 수 있게 지어져 있다(탄성계수·푸아송비·밀도).
    for item in (*spec.produces, *spec.rows):
        if item.key == key:
            return item.label
    return f"{spec.label} {key}"


def _resolve(target: str | Renderer) -> Renderer | None:
    """`key` 든 **이미 만들어진 렌더러** 든 받는다.

    **DB 정의로 만든 렌더러를 전역 레지스트리에 얹지 않기 위해서다.** 얹으면
    요청 하나가 프로세스 전체를 바꾸고, 부서마다 정의가 다르면 옆 요청이 남의
    솔버로 덱을 낸다. 그래서 만든 것을 그대로 들고 다닌다.
    """
    if isinstance(target, str):
        return _RENDERERS.get(target)
    return target


def missing_for(deck: Deck, format_key: str | Renderer) -> tuple[str, ...]:
    """이 형식으로 내보내려면 덱에 더 있어야 하는 것. 사람이 읽는 이름으로.

    **누르기 전에 알아야 한다.** 내려받기를 누른 뒤에 "푸아송비가 없습니다" 를
    보는 것은 늦다.
    """
    target = _resolve(format_key)
    if target is None:
        return ()
    missing: list[str] = []
    for need in target.needs:
        if need.optional:
            continue
        if not deck.has(need.block):
            missing.append(_label(need.block))
            continue
        values = deck.values(need.block)
        missing.extend(
            _label(need.block, key) for key in need.values if values.get(key) is None
        )
        if need.rows_min and len(deck.rows(need.block)) < need.rows_min:
            missing.append(f"{_label(need.block)}(표 {need.rows_min}줄 이상)")
        for key, floor in need.at_least:
            found = values.get(key)
            if found is None or float(found) < floor:
                missing.append(f"{_label(need.block, key)} {floor:g} 이상")
    return tuple(missing)


def requires_labels(format_key: str | Renderer) -> tuple[str, ...]:
    """이 형식이 **반드시** 요구하는 것. 카드를 보기 전에도 답할 수 있다.

    화면의 형식 목록에 그대로 뜬다 — *"이 솔버는 밀도가 있어야 합니다"* 를 카드를
    고르기 전에 알 수 있어야 한다. 선택인 것(`optional`)은 안 넣는다.
    """
    target = _resolve(format_key)
    if target is None:
        return ()
    out: list[str] = []
    for need in target.needs:
        if need.optional:
            continue
        out.extend(_label(need.block, key) for key in need.values)
        # **블록만 요구하면 블록 이름이다** — 값도 표도 안 적은 요구(`Need("electrical")`)가
        # 빈 목록이 되면 화면이 「 가 있어야 냅니다」 로 앞이 빈 말을 한다(2026-10-02).
        if not need.values:
            out.append(_label(need.block))
    return tuple(dict.fromkeys(out))


def available_formats(deck: Deck) -> tuple[str, ...]:
    """이 덱으로 지금 낼 수 있는 형식."""
    return tuple(key for key in _RENDERERS if not missing_for(deck, key))


def blocks_in_decks() -> set[str]:
    """어느 블록이든 하나라도 솔버가 먹는가.

    화면이 "이 물성은 덱에 안 실림" 을 말하는 근거다. 전에는 블록이 스스로
    선언했는데(`to_card is not None`), **실제로 쓰이는지와 어긋날 수 있었다** —
    지금은 렌더러들이 실제로 요구하는 것에서 계산한다.
    """
    return {need.block for item in _RENDERERS.values() for need in item.needs}


@dataclass(frozen=True)
class Renderer:
    """솔버 하나가 덱을 만드는 법."""

    key: str
    label: str
    extension: str
    describe: str
    render: Callable[[Deck], Rendered]
    suffix: str = ""
    """파일 이름 뒤에 붙는 꼬리. **같은 확장자를 내는 형식끼리 구별한다.**

    한 카드가 `/MAT/LAW36`(역학)과 `/HEAT/MAT`(열)을 함께 낼 수 있는데, 둘 다
    `.rad` 라 이름이 같으면 받는 쪽에 `SECC_MD.rad` 와 `SECC_MD (1).rad` 가
    생긴다 — **어느 쪽이 열인지 알 수 없고, 덮어쓰면 하나를 잃는다.**

    `(확장자, 꼬리)` 짝은 형식마다 달라야 한다. 시험이 그것을 지킨다."""
    keywords: tuple[str, ...] = ()
    """이 형식이면 반드시 들어 있어야 하는 문자열. 쓴 뒤 확인한다 — 키워드가
    빠진 파일은 솔버가 오류 없이 무시하기도 한다."""
    needs: tuple[Need, ...] = ()
    media_type: str = "text/plain; charset=utf-8"
    solver: str = ""
    """어느 솔버의 덱인가 — 여러 재료를 한 파일로 합칠 때 그 솔버의 규약을 고른다.

    비면 key 앞부분(`dyna_elastic` → `dyna`)이나 확장자로 짐작한다(`shared/litdeck`).
    화면에서 만든 정의는 key 가 `deck_1a2b3c4d` 라 앞부분이 솔버가 아니다 — 그래서
    정의가 이 칸을 적을 수 있다."""
    fixed_units: UnitSystem | None = None
    """**단위를 형식이 정한다** — 고른 계와 상관없이 이 계로 받는다(2026-10-02).

    Abaqus · ANSYS 는 단위가 없는 솔버라 고른 계로 옮겨 적는다. AEDT(`.amat`) · CST(`.mtd`) ·
    FloXML · Zemax 는 그렇지 않다 — 파일 형식이 단위를 정해 두었고(SI, 파장은 µm), 읽는
    쪽이 그 단위로 읽는다. 여기에 mm·N·tonne 숫자를 적으면 밀도가 10¹² 배 틀린 재료가
    **오류 없이** 들어간다. 그래서 이 형식은 늘 이 계의 덱을 받고(`render` 가 바꾼다), 파일
    이름도 이 계를 말한다(`effective_system`). 형식 고유의 단위(µm · GPa)로는 렌더러가
    `matcore.units` 로 옮긴다."""


_RENDERERS: dict[str, Renderer] = {}


def register_renderer(
    *,
    key: str,
    label: str,
    extension: str,
    describe: str,
    suffix: str = "",
    keywords: tuple[str, ...] = (),
    needs: tuple[Need, ...] = (),
    media_type: str = "text/plain; charset=utf-8",
    fixed_units: UnitSystem | None = None,
) -> Callable[[Callable[[Deck], Rendered]], Callable[[Deck], Rendered]]:
    """솔버 하나를 등록한다. **등록하면 API·화면·내려받기가 따라온다.**

    전에는 `FORMATS` 라는 딕셔너리에 손으로 줄을 적었다. 그러면 새 솔버나 새
    물성을 **이 파일 안에서만** 더할 수 있고, 확장 폴더에서는 못 붙인다.
    """

    def decorator(fn: Callable[[Deck], Rendered]) -> Callable[[Deck], Rendered]:
        add_renderer(
            Renderer(
                key=key,
                label=label,
                extension=extension,
                describe=describe,
                suffix=suffix,
                render=fn,
                keywords=keywords,
                needs=needs,
                media_type=media_type,
                fixed_units=fixed_units,
            )
        )
        return fn

    return decorator


def effective_system(target: Renderer, system: UnitSystem) -> UnitSystem:
    """이 형식으로 낼 때 **실제로 쓰이는 계** — 형식이 단위를 정했으면 그것(`fixed_units`).

    덱을 그리는 `render` 와 파일 이름 · 검사 결과를 적는 자리가 **같은 답을 봐야 한다.**
    내용은 SI 인데 이름이 `_mm_n_tonne` 이면 받는 사람은 이름을 믿는다.
    """
    return target.fixed_units or system


def add_renderer(item: Renderer) -> Renderer:
    """이미 만들어진 렌더러를 등록한다.

    `register_renderer` 가 부르고, **되돌리기가 쓴다** — 시험이 레지스트리를
    건드린 뒤 원래대로 돌려놓을 길이 있어야 한다(`cards.register_block` 과 같다).
    """
    if item.key in _RENDERERS:
        raise ValueError(f"솔버 형식 key 중복: {item.key}")
    _RENDERERS[item.key] = item
    return item


def renderer(key: str) -> Renderer:
    try:
        return _RENDERERS[key]
    except KeyError:
        known = ", ".join(sorted(_RENDERERS))
        raise ExportError(f"모르는 형식입니다: {key}. 있는 것: {known}") from None


def list_renderers() -> list[Renderer]:
    return list(_RENDERERS.values())


def clear_renderers() -> None:
    """테스트 전용."""
    _RENDERERS.clear()


def _free(value: float) -> str:
    """자유 형식 숫자. Abaqus·JSON 이 쓴다."""
    return f"{value:.12E}"


def _fixed(value: float) -> str:
    """OpenRadioss 고정 20칸. **칸이 어긋나면 다른 필드로 읽힌다.**"""
    return f"{value:>20.9E}"


def header_lines(deck: Deck) -> list[str]:
    """근거 줄 — 주석 기호 없이. 주석이 없는 형식(AEDT 의 Notes · FloXML 의 notes · CST 의
    설명 칸)은 이 줄들을 자기 자리에 적는다."""
    # **안 바꾼 값이 있으면 여기서 말한다.** `to_system` 이 남긴 것이고,
    # 조용히 남는 것과 적혀서 남는 것은 다르다.
    said = deck.blocks.get("_units")
    left = list(said.get("notes", [])) if isinstance(said, Mapping) else []
    return ["MatNexus 물성 카드", *deck.provenance, *left]


def _header(deck: Deck, comment: str) -> list[str]:
    """근거를 카드 안에 적는다.

    **덱만 받은 사람이 되짚을 수 있어야 한다.** 파일이 메일로 돌아다니는 동안
    이 주석이 유일한 출처 표시다.
    """
    return [f"{comment} {line}" for line in header_lines(deck)]


#: `*EXPANSION` 등이 받는 값 ↔ 블록 키. 값이 하나인 키워드들이라 표가 아니다.
THERMAL_KEYWORDS: tuple[tuple[str, str, str], ...] = (
    ("thermal_expansion", "*EXPANSION, TYPE=ISO", "1/K"),
    ("specific_heat", "*SPECIFIC HEAT", "J/(kg.K)"),
    ("thermal_conductivity", "*CONDUCTIVITY, TYPE=ISO", "W/(m.K)"),
)


def elastic_by_temperature(deck: Deck) -> list[tuple[float, float, float]]:
    """온도별 탄성 표 — `(온도, 탄성계수, 푸아송비)` 를 온도 순으로. **두 줄이 안 되면 빈
    목록이다** — 상수 재료이고, 그때는 블록의 값(`values`)을 쓴다.

    **줄을 조용히 버리지 않는다.** 솔버는 한 온도에 E·ν 를 함께 받으므로 하나라도
    비면 그 온도를 낼 수 없는데, 그냥 빼면 덱은 나가고 그 구간에서 솔버가 이웃 온도의
    값을 쓴다 — 오류 없이 다른 재료가 된다.

    **온도 순으로 준다.** 솔버마다 표를 오름차순으로 요구한다(`MPTEMP`·`TABLEM1`) —
    어긋난 차례를 받아 주는 솔버도 있고 거절하는 솔버도 있어서, 한곳에서 맞춘다.
    """
    needed = ("temperature", "youngs_modulus", "poisson_ratio")
    given = deck.rows("elastic")
    rows = [
        row for row in given if all(isinstance(row.get(key), (int, float)) for key in needed)
    ]
    if len(rows) < len(given):
        holes = sorted(
            {
                key
                for row in given
                for key in needed
                if not isinstance(row.get(key), (int, float))
            }
        )
        raise ExportError(
            f"온도별 탄성 표에 빈 칸이 있습니다({', '.join(holes)}). 솔버는 한 온도에 "
            f"탄성계수·푸아송비·온도가 다 있어야 받습니다 — 빈 칸을 이웃 값으로 메우는 "
            f"것은 값을 지어내는 일이라 하지 않습니다."
        )
    if len(rows) < 2:
        return []
    return sorted(
        (float(row["temperature"]), float(row["youngs_modulus"]), float(row["poisson_ratio"]))
        for row in rows
    )


def rate_curves(
    deck: Deck,
) -> tuple[list[tuple[float, list[tuple[float, float]]]], list[str]]:
    """속도별 소성 표를 **속도마다 나눠 정리한다** — `([(속도, 점들)], 남길 말)`.

    행은 `rate_table` 의 `(속도, 소성변형률, 응력)` 이다. 곡선마다 `prepare` 를 따로
    돈다 — 한 속도의 표가 규칙을 어기면 그 속도를 짚어 말한다. **속도가 하나뿐이면
    거부한다**: 그 덱은 탄소성 형식이 낼 것이고, 여기서 내면 속도 의존이 있는 척이 된다.
    """
    by_rate: dict[float, list[tuple[float, float]]] = {}
    for row in deck.rows("rate_table"):
        try:
            rate = float(row["strain_rate"])
            by_rate.setdefault(rate, []).append(
                (float(row["plastic_strain"]), float(row["true_stress"]))
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExportError(
                "속도별 소성 표의 행에 속도·변형률·응력이 다 있어야 합니다."
            ) from exc
    if len(by_rate) < 2:
        raise ExportError(
            "속도가 하나뿐입니다. 속도 의존 덱은 둘 이상의 속도가 있어야 합니다 — "
            "하나면 탄소성 형식을 쓰세요."
        )
    curves: list[tuple[float, list[tuple[float, float]]]] = []
    notes: list[str] = []
    for rate in sorted(by_rate):
        points, said = prepare(tuple(sorted(by_rate[rate])))
        notes.extend(f"속도 {rate:.3g} 1/s: {line}" for line in said)
        curves.append((rate, points))
    return curves, notes


def prony_terms(deck: Deck, *, limit: int | None = None) -> tuple[tuple[float, float], ...]:
    """Prony 항 — `(상대 탄성률 gᵢ, 완화시간 τᵢ)`, 카드에 적힌 차례 그대로.

    **정렬하지 않는다.** Prony 는 점이 아니라 항이라 차례를 바꿔도 같은 재료지만, 덱이
    카드와 같은 차례여야 사람이 두 화면을 나란히 대조한다.

    거부하는 것 셋 — 항이 없다 · 항이 솔버의 상한을 넘는다 · **gᵢ 의 합이 1 이상이다**
    (평형 탄성률이 0 이하라는 뜻이라 솔버가 거부하거나 발산한다).
    """
    terms = tuple(
        (float(row["relative_modulus"]), float(row["relaxation_time_s"]))
        for row in deck.rows("viscoelastic")
        if isinstance(row.get("relative_modulus"), int | float)
        and isinstance(row.get("relaxation_time_s"), int | float)
    )
    if not terms:
        raise ExportError(
            "점탄성 카드인데 Prony 계수가 없습니다. 마스터커브를 만들고 "
            "Prony 를 맞춘 뒤에 내보내세요."
        )
    if limit is not None and len(terms) > limit:
        raise ExportError(
            f"Prony 가 {len(terms)}항입니다 — 이 솔버는 {limit}항까지 받습니다. "
            f"적합의 항 수를 줄이세요."
        )
    if any(tau <= 0.0 for _, tau in terms):
        raise ExportError("완화시간이 0 이하인 Prony 항이 있습니다 — 적합을 다시 보세요.")
    total = sum(g for g, _ in terms)
    if total >= 1.0:
        raise ExportError(
            f"Prony 상대 탄성률의 합이 {total:.4f} 로 1 이상입니다. "
            f"평형 탄성률이 0 이하라는 뜻이라 솔버가 거부합니다."
        )
    return terms


#: 초탄성 식 → 계수 이름. **순서가 아니라 이름으로 찾는다** — 파라미터가 하나 늘어난
#: 식이 붙으면 배열 순서로 넘긴 쪽부터 조용히 어긋난다(65 가 그랬다).
HYPERELASTIC_PARAMETERS: dict[str, tuple[str, ...]] = {
    "neo_hookean": ("c10",),
    "mooney_rivlin": ("c10", "c01"),
    "yeoh": ("c10", "c20", "c30"),
    "ogden_1": ("mu", "alpha"),
}


def hyperelastic_terms(deck: Deck) -> tuple[str, dict[str, float]]:
    """초탄성 카드의 `(식, {계수: 값})`. 모르는 식이거나 계수가 빠지면 거부한다.

    **Ogden 의 μ 는 Abaqus 규약이다**(`matcore/fitting/hyperelastic.py`): 초기
    전단탄성률이 μ 그 자체다. 솔버마다 같은 기호를 다르게 쓰므로(μ/α 규약이면
    G = μα/2) 렌더러가 제 솔버의 규약으로 옮긴다 — 옮긴 식을 덱에 적는다.
    """
    family = deck.values("hyperelastic").get("family")
    if not family:
        raise ExportError("초탄성 카드가 아닙니다. 어느 식으로 맞췄는지가 없습니다.")
    names = HYPERELASTIC_PARAMETERS.get(str(family))
    if names is None:
        known = ", ".join(sorted(HYPERELASTIC_PARAMETERS))
        raise ExportError(
            f"'{family}' 는 덱으로 옮기는 법을 모르는 식입니다. 있는 것: {known}"
        )
    values = {
        str(row["name"]): float(row["value"])
        for row in deck.rows("hyperelastic")
        if "name" in row and isinstance(row.get("value"), int | float)
    }
    missing = [name for name in names if name not in values]
    if missing:
        raise ExportError(
            f"{family} 에 필요한 계수가 없습니다: {', '.join(missing)}. "
            f"카드가 다른 식으로 맞춰졌을 수 있습니다."
        )
    return str(family), {name: values[name] for name in names}


def _elastic_lines(deck: Deck, youngs: float | None, poisson: float | None) -> list[str]:
    """`*ELASTIC` — 한 줄이거나 온도별 표.

    **온도 열은 표가 있을 때만 붙인다.** 한 온도짜리에 붙이면 솔버가 「이
    온도에서만 유효」로 읽고, 그 밖에서 외삽 규칙이 달라진다 — 상수인 재료가
    갑자기 온도 의존이 된다.
    """
    assert youngs is not None and poisson is not None
    rows = elastic_by_temperature(deck)
    if not rows:
        return ["*ELASTIC, TYPE=ISOTROPIC", f"{_free(youngs)}, {_free(poisson)}"]

    lines = [
        f"** ELASTIC: 온도 {len(rows)}점 "
        f"({rows[0][0]:.5g}~{rows[-1][0]:.5g} K). "
        f"표 밖에서는 끝값이 유지됩니다.",
        "*ELASTIC, TYPE=ISOTROPIC",
    ]
    lines.extend(
        f"{_free(one_e)}, {_free(one_nu)}, {_free(temperature)}"
        for temperature, one_e, one_nu in rows
    )
    return lines


def _thermal_lines(deck: Deck) -> list[str]:
    """열물성 키워드. 블록이 없으면 **한 줄도 안 낸다.**

    ## 셋을 묶지 않는다

    열팽창만 아는 재료로 열응력 해석은 돌아가고, 전도도만 아는 재료로 정상
    열해석은 돌아간다. 셋을 다 요구하면 그 재료는 영영 덱이 안 나온다.

    ## `ZERO=` 를 함부로 안 붙인다 — 대신 없다고 적는다

    `*EXPANSION` 의 `ZERO` 는 **할선 열팽창계수의 기준 온도(θ₀)**다. 안 적으면
    Abaqus 는 **0** 을 쓴다(키워드 레퍼런스 「The default is ZERO=0」) — 해석의
    초기 온도가 아니다. 전에는 여기에 「초기 온도를 쓴다」 고 적혀 있었고, 그래서
    표로 적은 α 가 0 K 기준 할선값으로 읽히는 덱이 **아무 말 없이** 나갔다
    (2026-09-30, 가이드를 고치다 드러났다). α 가 값 하나면 θ₀ 가 결과에 안 들어가
    상관없고, 온도별 표면 들어간다 — 20 °C 기준 α 가 20e-6 → 30e-6 /K 로 오르면
    100 K 올릴 때 열변형이 두 배로 나온다.

    카드에 기준 온도가 있을 때만 적는다 — 없는데 293.15 를 적어 넣으면 **덱은
    멀쩡히 돌고 열응력만 통째로 어긋난다.** 표를 낼 때 기준 온도가 없으면 그
    사실을 덱에 적는다(ANSYS `REFT` · Nastran `TREF` 와 같다).
    """
    if not deck.has("thermal"):
        return []
    lines: list[str] = []
    # **열팽창 자신의 온도다.** 블록의 기준 온도를 쓰면 「비열을 잰 온도」가
    # `ZERO` 로 나가는 일이 생긴다 — `ZERO` 는 열변형이 0 이 되는 온도이고
    # 다른 물성의 측정 온도와 아무 관계가 없다.
    #
    # 표로 적힌 열팽창에 기준 온도가 없으면 `ZERO` 를 안 붙이고 **없다고 적는다.**
    # 표는 「이 온도에서 α 가 얼마」를 말할 뿐 어느 온도 기준의 할선값인지는
    # 말하지 않는다. Abaqus 는 그때 0 을 쓴다 — 받는 사람이 채워야 한다.
    zero = deck.number("thermal", "thermal_expansion_temperature")
    rows = deck.rows("thermal")
    for key, keyword, unit in THERMAL_KEYWORDS:
        # **표가 있으면 표가 이긴다.** 값은 첫 줄의 것이므로 둘 다 내면 같은
        # 물성이 두 번 실린다.
        table = [
            (float(row["temperature"]), float(row[key]))
            for row in rows
            if isinstance(row.get(key), (int, float))
            and isinstance(row.get("temperature"), (int, float))
        ]
        value = deck.number("thermal", key)
        if not table and value is None:
            continue
        source = deck.values("thermal").get(f"{key}_source")
        # **잰 값인지 적은 값인지 덱에서 보인다.** 덱만 받은 사람이 이 숫자의
        # 무게를 알 수 있어야 한다.
        # **덱의 계로 적는다.** SI 기호를 박아 두면 값은 mJ/(tonne·K) 인데
        # 주석은 J/(kg·K) 라고 말한다 — 받는 사람은 주석을 믿는다.
        try:
            shown = deck.units.symbol(unit)
        except KeyError as error:  # pragma: no cover - to_system 이 먼저 막는다
            raise ExportError(
                f"{deck.units.label} 에 '{unit}' 의 기호가 없습니다({key})."
            ) from error
        lines.append(f"** {key}: {shown}, source={source or 'unknown'}")
        head = keyword
        if key == "thermal_expansion" and zero is not None:
            head = f"{keyword}, ZERO={_free(zero)}"
        if len(table) > 1:
            # **온도가 표에 있으면 그 사실을 적는다.** 표 밖에서 솔버는 끝값을
            # 붙드는데, 덱만 받은 사람은 어디까지가 적힌 것인지 알 수 없다.
            lines.append(
                f"** {key}: 표 밖에서는 끝값이 유지됩니다 "
                f"({table[0][0]:.5g}~{table[-1][0]:.5g} K 가 적힌 구간)"
            )
            if key == "thermal_expansion" and zero is None:
                lines.append(
                    "** ZERO not on the card - Abaqus uses ZERO=0 (0 K). Set ZERO= to the"
                )
                lines.append("**   reference temperature of the secant CTE before use.")
            lines.append(head)
            lines.extend(f"{_free(one)}, {_free(temperature)}" for temperature, one in table)
        else:
            # 표가 없으면 값 하나. 둘 다 없으면 위에서 이미 건너뛰었다.
            only = table[0][1] if table else value
            assert only is not None
            lines.append(head)
            lines.append(f"{_free(only)},")
    return lines


@register_renderer(
    key="abaqus",
    label="Abaqus (탄소성)",
    extension="inp",
    describe="*MATERIAL / *ELASTIC / *PLASTIC — 표 형식 소성. 단위는 덱 머리에 적힌다.",
    keywords=("*MATERIAL", "*ELASTIC", "*PLASTIC"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        # 밀도는 빠져도 된다 — *DENSITY 는 선택 키워드다. 대신 왜 없는지 덱에 적는다.
        Need("elastic", values=("density",), optional=True),
        # 열물성은 셋 다 선택이다. 있으면 싣고 없으면 그 키워드가 안 나간다.
        Need("thermal", optional=True),
        # **표는 빠지면 안 된다.** 전에는 검사를 지나 `render` 안에서 터졌고,
        # 그러면 화면이 "이 형식은 아직 못 낸다" 를 미리 말할 수 없다.
        Need("table", rows_min=MIN_POINTS),
    ),
)
def render_abaqus(deck: Deck) -> Rendered:
    """Abaqus `*MATERIAL` 덱.

    **단위 키워드가 없는 솔버다.** 그래서 단위를 주석으로 선언한다 — 값은 SI 그대로
    나가고, 덱의 다른 재료도 SI 여야 한다는 사실을 사람이 읽게 한다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))

    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    if density is None:
        # *DENSITY 는 Abaqus 에서 선택이다. 빼되 **왜 뺐는지 적는다** — 동적
        # 해석을 돌리려던 사람이 덱만 보고 알 수 있어야 한다.
        notes.append("밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append(
            "** DENSITY: 측정값이 없어 비웠습니다. "
            "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
        )
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    lines.extend(_elastic_lines(deck, youngs, poisson))
    # **`EXTRAPOLATION=` 을 안 붙인다**(2026-10-03, 공개 자료 대조). 표 밖에서 응력을 일정하게
    # 두는 것이 Abaqus 의 기본이고, 그 매개변수는 2022 에 생겼다 — 2017 키워드 참조서의
    # `*PLASTIC` 에 없다. 기본값을 굳이 적으면 2021 이전 판이 모르는 매개변수로 멈추고, 2022
    # 이후에는 아무것도 바뀌지 않는다. 전에는 「기본값이 오류 중단」 이라고 잘못 알고 적었다.
    lines.extend(_thermal_lines(deck))
    lines.append("*PLASTIC, HARDENING=ISOTROPIC")
    # **응력이 먼저, 소성변형률이 나중이다.** OpenRadioss 와 순서가 반대다.
    lines.extend(f"{_free(stress)}, {_free(strain)}" for strain, stress in points)
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


#: ADR 0023 1단계 — **위 `render_abaqus` 를 파일 정의로 다시 적은 것.**
#:
#: 시험이 둘을 같은 덱에 대고 바이트로 견준다. 여기가 맞으면 「배포 없이 새 솔버」
#: 가 가능하다는 뜻이고, 어긋나면 그 자리가 곧 템플릿에 없는 표현이다.
#:
#: **검증과 정리는 여기 없다.** 온도별 표의 빈 칸 검사(`_elastic_lines`)와 표 정리
#: (`prepare`)는 코드에 남는다 — 그것은 조판이 아니라 계산이다.
ABAQUS_TEMPLATE: dict[str, Any] = {
    "lines": [
        {"block": "header"},
        {"text": "** Consistent units: {units}"},
        {
            "when": "missing:elastic.density",
            "text": (
                "** DENSITY: 측정값이 없어 비웠습니다. "
                "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
            ),
            "note": "밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.",
        },
        {"text": "*MATERIAL, NAME={name}"},
        {"when": "elastic.density", "text": "*DENSITY"},
        {
            "when": "elastic.density",
            "fields": [{"value": "elastic.density", "format": "free"}],
            "suffix": ",",
        },
        {"block": "elastic"},
        {"block": "thermal"},
        {"text": "*PLASTIC, HARDENING=ISOTROPIC"},
        {
            # **응력이 먼저, 소성변형률이 나중이다.** OpenRadioss 와 반대이고,
            # 템플릿이 표현해야 하는 것이 정확히 이런 차이다.
            "rows": "table",
            "x": "plastic_strain",
            "y": "true_stress",
            "fields": [
                {"value": "true_stress", "format": "free"},
                {"value": "plastic_strain", "format": "free"},
            ],
        },
    ],
}


def _register_template_blocks() -> None:
    """코드가 만드는 줄 묶음을 템플릿 쪽에 넘긴다.

    **여기서 넘기는 이유는 순환이다** — `template` 이 이 모듈을 맨 위에서 부르면
    서로를 기다린다. 넘기는 것은 조판이 아니라 데이터·검증이 있는 것뿐이다:

        header        출처·등급 줄 — 카드 밖(DB)에서 온다. `comment` 로 주석 기호를 준다
                      (Abaqus `**` · LS-DYNA·Nastran `$` · ANSYS `!` · Radioss `#`)
        elastic       Abaqus *ELASTIC — 온도별 표의 빈 칸을 검사한다
        thermal       Abaqus 열 키워드 — 표가 이기고, ZERO 는 기준 온도가 있을 때만
        radioss_unit  Radioss /UNIT — 우리 기호를 Radioss 단위 코드로(tonne → Mg)
    """
    template.register_block("header", lambda deck, comment="**": _header(deck, str(comment)))
    # 출처 줄만 — 머리 제목·단위 말 없이(Johnson-Cook 덱의 머리가 이 모양이다).
    template.register_block(
        "provenance",
        lambda deck, comment="**": [f"{comment} {line}" for line in deck.provenance],
    )
    template.register_block("radioss_unit", lambda deck: _unit_block(deck))
    template.register_block(
        "elastic",
        lambda deck: _elastic_lines(
            deck,
            deck.number("elastic", "youngs_modulus"),
            deck.number("elastic", "poisson_ratio"),
        ),
    )
    template.register_block("thermal", _thermal_lines)


_register_template_blocks()


@register_renderer(
    key="abaqus_viscoelastic",
    label="Abaqus (점탄성)",
    extension="inp",
    suffix="_viscoelastic",
    describe=("*ELASTIC + *VISCOELASTIC, TIME=PRONY — 선형 점탄성. 기준 온도 하나에서 유효."),
    keywords=("*MATERIAL", "*ELASTIC", "*VISCOELASTIC"),
    needs=(
        # 다른 솔버의 점탄성은 각 모듈에 있다(ansys·dyna·bulk·radioss). Radioss 는 LAW62
        # 가 아니라 LAW42+Prony 다 — μ 가 장기 전단탄성률이고 Gᵢ 가 더해진다(2026-09-27,
        # OpenRadioss sigeps42 로 확인). 작은 변형에서 선형 점탄성과 같다.
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("thermal", optional=True),
        Need("viscoelastic", rows_min=1),
    ),
)
def render_abaqus_viscoelastic(deck: Deck) -> Rendered:
    """Abaqus `*VISCOELASTIC, TIME=PRONY` 덱. 선형 점탄성.

    ## `*ELASTIC` 에 순간 탄성률을 적고, 그렇다고 `MODULI=` 로 말한다

    카드의 탄성률은 순간(t=0) 값 E₀ 다. 그런데 Abaqus 는 `*VISCOELASTIC` 이 붙은
    `*ELASTIC` 을 **기본으로 장기(LONG TERM) 탄성률**로 읽는다(키워드 레퍼런스
    「MODULI=LONG TERM (default)」). 전에는 여기에 「순간으로 읽는다」 고 적혀 있었고
    `MODULI=` 없이 E₀ 를 냈다 — Abaqus 는 E₀ 를 장기값으로 받아 순간 강성을
    E₀/(1-Σg) 로 올린다. Σg = 0.99 면 100 배 딱딱한데 **덱은 멀쩡히 돈다**
    (2026-09-30, 가이드를 고치다 드러났다). 다른 해석 프로그램은 제 규약대로 맞게
    나가고 있었다(ANSYS · Nastran 은 순간값, OptiStruct 는 장기값으로 옮김,
    LS-DYNA · Radioss 는 G∞ 를 따로 적음).

    ## 체적 완화를 0 으로 둔다 — 안 잰 값이다

    Prony 행은 `g, k, τ` 셋이다. `g` 는 전단, `k` 는 체적 상대 탄성률인데
    **DMA 는 체적을 재지 않는다.** 지어내지 않고 0 으로 둔다 — 체적은 순수
    탄성이라는 뜻이고, 흔히 쓰는 가정이다. 그 사실을 덱 주석에 적는다.

    그리고 우리가 잰 것은 인장·굽힘 `E` 인데 Abaqus 의 `g` 는 **전단** 비율이다.
    같게 쓰는 것은 **푸아송비가 시간에 따라 안 변한다**는 가정이고, 이것도 흔한
    가정이지만 가정은 가정이라 적는다.

    ## 온도가 하나뿐이다

    마스터커브는 기준 온도 하나에서만 유효하다. 다른 온도로 해석하려면
    `*TRS`(WLF 이동)를 함께 줘야 하는데, 그건 이동인자를 카드에 싣는 별개의
    일이다. 지금은 **유효 온도를 주석에 적고 끝낸다** — 조용히 온도 의존을
    없는 셈 치는 것보다 낫다.
    """
    prony = tuple(
        (float(row["relative_modulus"]), float(row["relaxation_time_s"]))
        for row in deck.rows("viscoelastic")
        if "relative_modulus" in row and "relaxation_time_s" in row
    )
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    reference = deck.number("viscoelastic", "reference_temperature_k")
    if not prony:
        raise ExportError(
            "점탄성 카드인데 Prony 계수가 없습니다. 마스터커브를 만들고 "
            "Prony 를 맞춘 뒤에 내보내세요."
        )
    if youngs is None or poisson is None:
        raise ExportError("순간 탄성률과 푸아송비가 있어야 *ELASTIC 을 쓸 수 있습니다.")

    notes: list[str] = []
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    lines.append("** ELASTIC = instantaneous (t=0) moduli - MODULI=INSTANTANEOUS says so")
    lines.append("**          (Abaqus default with *VISCOELASTIC is LONG TERM).")
    if reference is not None:
        celsius = reference - 273.15
        lines.append(f"** Valid at {reference:.2f} K ({celsius:.2f} C) only -")
        lines.append(
            "**   master curve reference temperature. Add *TRS for other temperatures."
        )
        notes.append(
            f"기준 온도 {celsius:.1f} °C 에서만 유효하다는 사실을 덱 주석에 적었습니다 — "
            f"다른 온도로 해석하려면 *TRS 가 따로 필요합니다."
        )
    else:
        notes.append(
            "기준 온도가 카드에 없어 덱에 적지 못했습니다. 이 카드가 어느 온도의 "
            "것인지 덱만으로는 알 수 없습니다."
        )
    lines.append(
        "** Bulk relaxation (k) not measured by DMA — emitted as zero (elastic bulk)."
    )
    lines.append("** Shear ratios taken from tensile/flexural E — assumes constant Poisson.")

    if density is None:
        notes.append("밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append(
            "** DENSITY: 측정값이 없어 비웠습니다. "
            "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
        )

    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    lines.append("*ELASTIC, TYPE=ISOTROPIC, MODULI=INSTANTANEOUS")
    lines.append(f"{_free(youngs)}, {_free(poisson)}")
    lines.extend(_thermal_lines(deck))
    lines.append("*VISCOELASTIC, TIME=PRONY, TYPE=ISOTROPIC")
    # 행 하나가 g, k, τ. 순서가 뒤바뀌면 솔버가 오류 없이 다른 재료를 만든다.
    lines.extend(f"{_free(g)}, 0.0, {_free(tau)}" for g, tau in prony)

    total = sum(g for g, _ in prony)
    if total >= 1.0:
        raise ExportError(
            f"Prony 상대 탄성률의 합이 {total:.4f} 로 1 이상입니다. "
            f"평형 탄성률이 0 이하라는 뜻이라 Abaqus 가 거부합니다."
        )
    notes.append(
        f"Prony {len(prony)}항, 상대 탄성률 합 {total:.4f} "
        f"(평형 탄성률은 순간의 {1 - total:.4f} 배)."
    )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


#: 식 → (Abaqus 키워드, 계수 이름 순서).
#:
#: **순서가 아니라 이름으로 찾는다.** 65 는 배열 순서로 넘겼는데, 파라미터가 하나
#: 늘어난 식이 붙으면 그때부터 조용히 어긋난다 — 덱은 돌고 재료만 다르다.
HYPERELASTIC_KEYWORDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "neo_hookean": ("NEO HOOKE", ("c10",)),
    "mooney_rivlin": ("MOONEY-RIVLIN", ("c10", "c01")),
    "yeoh": ("YEOH", ("c10", "c20", "c30")),
    "ogden_1": ("OGDEN, N=1", ("mu", "alpha")),
}

#: 비압축 계수 D — **카드에 푸아송비가 없거나 0.5 일 때**의 값(`hyperelastic_bulk`).
#:
#: Abaqus 에서 `D=0` 은 완전 비압축이고 **하이브리드 요소(C3D8H 등)를 요구한다.**
#: 일반 요소로 돌리면 오류로 멈춘다 — 조용히 틀리는 것보다 낫지만, 그 사실을
#: 모르면 "덱이 안 돌아간다" 로만 보인다. 그래서 덱 주석에 적는다.
INCOMPRESSIBLE_D = 0.0

#: 고무치고 낮은 푸아송비. 이보다 낮으면 체적이 쉽게 변하는 재료로 계산된다고 알린다
#: (LS-DYNA 초탄성과 같은 문턱).
RUBBER_POISSON_FLOOR = 0.49


def initial_shear(family: str, values: Mapping[str, float]) -> float:
    """초기 전단탄성률 μ0. 다항식 꼴은 2(C10 + C01) — Neo-Hookean · Yeoh 는 2·C10 —
    Ogden 은 카드의 μ 그대로다(우리 μ 는 Abaqus 규약, G = μ)."""
    if family == "ogden_1":
        return values["mu"]
    if family == "mooney_rivlin":
        return 2.0 * (values["c10"] + values["c01"])
    return 2.0 * values["c10"]


def hyperelastic_bulk(
    deck: Deck, family: str, values: Mapping[str, float]
) -> tuple[float, float, float] | None:
    """카드의 푸아송비로 `(ν, μ0, K)` — 비압축 계수는 D = 2/K 다(Abaqus D1 · ANSYS d 둘 다).

    K = 2μ0(1+ν) / (3(1-2ν)) 는 E = 2μ0(1+ν) 와 K = E/(3(1-2ν)) 를 이은 것이다.
    **ν 가 없거나 0.5 면 None** — 완전 비압축(`INCOMPRESSIBLE_D`)이다.

    전에는 ν 가 있어도 Abaqus · ANSYS 만 늘 D = 0 이었다. Nastran · OptiStruct · LS-DYNA ·
    Radioss 는 같은 카드의 ν 로 체적 강성을 만들어서, **같은 카드가 솔버마다 다른 체적 거동**이
    됐다 — 한쪽은 하이브리드 요소를 요구하는 완전 비압축, 다른 쪽은 ν = 0.4995 의 고무
    (2026-10-03 공개 덱 대조: 공개 Abaqus 고무 덱 10벌이 모두 D1 을 적었다).
    """
    poisson = deck.number("elastic", "poisson_ratio")
    if poisson is None or poisson == 0.5:
        return None
    if not 0.0 < poisson < 0.5:
        raise ExportError(
            f"푸아송비가 {poisson:g} 입니다 — 0 보다 크고 0.5 이하여야 합니다"
            f"(0.5 는 완전 비압축)."
        )
    shear = initial_shear(family, values)
    return poisson, shear, 2.0 * shear * (1.0 + poisson) / (3.0 * (1.0 - 2.0 * poisson))


def low_rubber_poisson(poisson: float) -> str | None:
    """고무치고 낮은 ν 를 짚는 말 — 없으면 None."""
    if poisson >= RUBBER_POISSON_FLOOR:
        return None
    return (
        f"푸아송비가 {poisson:g} 로 고무치고 낮습니다 — 체적이 쉽게 변하는 재료로 "
        f"계산됩니다. 보통 0.495~0.4995 입니다."
    )


@register_renderer(
    key="abaqus_hyperelastic",
    label="Abaqus (초탄성)",
    extension="inp",
    suffix="_hyperelastic",
    describe=(
        "*HYPERELASTIC — 고무 초탄성, 공칭 응력 기준. D1 은 카드의 푸아송비로 만들고"
        "(D1 = 2/K), 없으면 D=0(완전 비압축)이라 하이브리드 요소가 필요하다."
    ),
    keywords=("*MATERIAL", "*HYPERELASTIC"),
    needs=(
        # `family` 를 `values` 로 요구하지 않는다 — 그건 내부 key 라 화면에
        # "초탄성 family 가 필요합니다" 로 뜬다. 없으면 아래에서 짚는다.
        Need("hyperelastic", rows_min=1),
        Need("elastic", values=("poisson_ratio", "density"), optional=True),
        # 열물성은 셋 다 선택이다. 있으면 싣고 없으면 그 키워드가 안 나간다.
        Need("thermal", optional=True),
    ),
)
def render_abaqus_hyperelastic(deck: Deck) -> Rendered:
    """Abaqus `*HYPERELASTIC` 덱. 고무 초탄성.

    ## 계수를 그대로 낸다 — 표가 아니다

    Abaqus 는 시험 데이터를 주고 자기가 맞추게 할 수도 있다(`*UNIAXIAL TEST DATA`).
    그 길을 안 쓴다 — **어느 식을 어느 구간에 맞췄는지가 우리 쪽에 남아야** 카드가
    자기 근거를 들 수 있고, 솔버마다 다른 적합기가 다른 답을 내는 것도 막는다.

    ## D1 은 카드의 푸아송비에서 — 없으면 D = 0

    비압축 계수는 재지 않는다(구속 압축 시험이 따로 든다). 카드의 ν 로 D1 = 2/K 를
    만든다 — 다른 솔버 형식이 같은 ν 로 체적 강성을 만드는 것과 같게(`hyperelastic_bulk`).
    ν 가 없거나 0.5 면 D = 0, **완전 비압축**이고 Abaqus 는 그때 하이브리드 요소를
    요구한다. 지어내지 않고 그 사실을 적는다.
    """
    family = deck.values("hyperelastic").get("family")
    density = deck.number("elastic", "density")
    if not family:
        raise ExportError("초탄성 카드가 아닙니다. 어느 식으로 맞췄는지가 없습니다.")
    target = HYPERELASTIC_KEYWORDS.get(str(family))
    if target is None:
        known = ", ".join(sorted(HYPERELASTIC_KEYWORDS))
        raise ExportError(f"'{family}' 는 Abaqus 매핑이 없는 식입니다. 있는 것: {known}")
    keyword, order = target

    values = {
        str(row["name"]): float(row["value"])
        for row in deck.rows("hyperelastic")
        if "name" in row and "value" in row
    }
    missing = [name for name in order if name not in values]
    if missing:
        raise ExportError(
            f"{keyword} 에 필요한 계수가 없습니다: {', '.join(missing)}. "
            f"카드가 다른 식으로 맞춰졌을 수 있습니다."
        )

    compressible = hyperelastic_bulk(deck, str(family), values)
    notes: list[str] = []
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    lines.append("** Nominal (engineering) stress-strain basis — not true stress.")
    if compressible is None:
        compressibility = INCOMPRESSIBLE_D
        # **D=0 은 요소 종류를 강제한다.** 모르면 "덱이 안 돌아간다" 로만 보인다.
        lines.append(
            "** D = 0 : fully incompressible — requires hybrid elements (e.g. C3D8H)."
        )
        notes.append(
            "비압축 계수 D 를 0 으로 두었습니다(카드에 푸아송비가 없거나 0.5 입니다) — 완전 "
            "비압축이라는 뜻이고, Abaqus 는 그때 하이브리드 요소를 요구합니다."
        )
    else:
        poisson, shear, bulk = compressible
        compressibility = 2.0 / bulk
        lines.append(
            f"** D1 = 2/K from the card nu={poisson:g}: mu0 = {shear:.6g}, K = {bulk:.6g}."
        )
        said = low_rubber_poisson(poisson)
        if said:
            notes.append(said)
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    else:
        notes.append("밀도가 없어 *DENSITY 를 비웠습니다 — 동적 해석에는 그대로 못 씁니다.")

    lines.extend(_thermal_lines(deck))
    lines.append(f"*HYPERELASTIC, {keyword}")
    lines.append(", ".join([*(_free(values[name]) for name in order), _free(compressibility)]))
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="openradioss",
    label="Radioss (탄소성)",
    extension="rad",
    describe=(
        "/MAT/LAW36 + /FUNCT — 표 형식 소성. /UNIT 블록으로 단위를 선언한다"
        "(OpenRadioss·Altair Radioss 공통 Starter 형식)."
    ),
    keywords=("/MAT/LAW36", "/FUNCT/", "/UNIT/1", "/END"),
    needs=(
        # LAW36 은 RHO_I 가 자리 있는 필드다. 비울 수 없다.
        Need("elastic", values=("youngs_modulus", "poisson_ratio", "density")),
        Need("table", rows_min=MIN_POINTS),
    ),
)
def render_openradioss(deck: Deck) -> Rendered:
    """OpenRadioss `/MAT/LAW36` + `/FUNCT`.

    **고정 20칸 형식이다.** 칸이 하나 어긋나면 다른 필드로 읽히고, 솔버는 오류 없이
    엉뚱한 재료로 계산한다.
    """
    points, notes = prepare(deck.pairs("table", "plastic_strain", "true_stress"))
    lines = ["#RADIOSS STARTER", *_header(deck, "#")]
    # **단위를 선언한다.** Abaqus 와 달리 이 솔버는 단위 블록이 있어서 값이 아니라
    # 선언으로 맞출 수 있다.
    lines.extend(_unit_block(deck))
    # 변형률 속도 하나짜리 표다. 속도 의존을 넣으려면 곡선이 여러 개 있어야 하고,
    # 그것은 시험이 여러 속도로 있어야 한다는 뜻이다(`openradioss_rate`).
    lines.extend(law36_lines(deck, [(0.0, deck.solver_id, points)]))
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def _chunks(items: list[str], size: int = 5) -> list[str]:
    """Radioss 가 한 줄에 다섯씩 받는 목록 — 함수 번호·배율·속도."""
    return ["".join(items[start : start + size]) for start in range(0, len(items), size)]


def law36_lines(
    deck: Deck,
    curves: list[tuple[float, int, list[tuple[float, float]]]],
    *,
    fsmooth: int | None = None,
    vp: int | None = None,
) -> list[str]:
    """`/MAT/LAW36` + 곡선마다 `/FUNCT` — `curves` 는 `(속도, 함수 번호, 점들)`.

    칸은 파서의 형식 문자열 그대로다(OpenRadioss `matl36_plas_tab.cfg`):

        N_funct·Fsmooth   10칸 둘
        Chard·Fcut·Eps_f  20칸 셋, 그다음 **10칸이 빈다**
        VP                **91~100열** — 80열 다음에 바로 적으면 빈 칸에 떨어져 0 으로 읽힌다

    **`fct_IDp` 줄은 비어 있어도 적는다.** 파서가 그 줄을 무조건 읽는다 — 전에 이 줄의
    주석만 쓰고 값 줄을 빼서, 곡선 번호가 압력 의존 함수(`fct_IDp`) 자리로 가고 줄이
    하나씩 밀렸다(2026-09-27, 파서 형식으로 확인).

    곡선 번호·배율·속도는 **다섯씩 한 줄**이고, 셋이 차례로 선다(섞이지 않는다).
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    assert youngs is not None and poisson is not None and density is not None
    count = len(curves)
    lines = [f"/MAT/LAW36/{deck.solver_id}/1", deck.name]
    lines.append(f"#{'RHO_I':>19}")
    lines.append(_fixed(density))
    lines.append(f"#{'E':>19}{'nu':>20}{'Eps_p_max':>20}{'Eps_t':>20}{'Eps_m':>20}")
    lines.append(_fixed(youngs) + _fixed(poisson))
    lines.append(
        f"#{'N_funct':>9}{'Fsmooth':>10}{'Chard':>20}{'Fcut':>20}{'Eps_f':>20}"
        f"{'':>10}{'VP':>10}"
    )
    head = f"{count:>10}" + (f"{fsmooth:>10}" if fsmooth is not None else "")
    if vp is not None:
        head = f"{head:<90}{vp:>10}"
    lines.append(head)
    lines.append(f"#{'fct_IDp':>9}{'Fscale':>20}{'Fct_IDE':>10}{'Einf':>20}{'CE':>20}")
    lines.append(f"{0:>10}")
    lines.append("#" + "".join(f"{f'fct_ID{index}':>10}" for index in range(1, 6))[1:])
    lines.extend(_chunks([f"{fid:>10}" for _, fid, _ in curves]))
    lines.append("#" + "".join(f"{f'Fscale_{index}':>20}" for index in range(1, 6))[1:])
    lines.extend(_chunks([_fixed(1.0) for _ in curves]))
    lines.append("#" + "".join(f"{f'Eps_dot_{index}':>20}" for index in range(1, 6))[1:])
    lines.extend(_chunks([_fixed(rate) for rate, _, _ in curves]))
    for rate, fid, points in curves:
        lines.append(f"/FUNCT/{fid}")
        # 제목 줄은 100자까지다 — 속도를 붙일 때는 이름을 줄여 속도가 잘리지 않게 한다.
        lines.append(
            f"{deck.name[:60]}_TRUE_STRESS_AT_RATE_{rate:.4g}"
            if count > 1
            else f"{deck.name}_TRUE_STRESS_VS_TRUE_PLASTIC_STRAIN"
        )
        lines.append(f"#{'X':>19}{'Y':>20}")
        # **소성변형률이 먼저, 응력이 나중이다.** Abaqus 와 순서가 반대다.
        lines.extend(f"{strain:>20.12E}{stress:>20.9E}" for strain, stress in points)
    return lines


def _thermal_points(deck: Deck, key: str) -> list[tuple[float, float]]:
    """온도-값 점들. 표가 있으면 표, 없으면 값 하나(온도는 기준 온도)."""
    rows = [
        (float(row["temperature"]), float(row[key]))
        for row in deck.rows("thermal")
        if isinstance(row.get(key), (int, float))
        and isinstance(row.get("temperature"), (int, float))
    ]
    if rows:
        return sorted(rows)
    value = deck.number("thermal", key)
    if value is None:
        return []
    zero = deck.number("thermal", "reference_temperature")
    return [(zero if zero is not None else 0.0, value)]


def _linear_in_temperature(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """`값 = a + b·T` 로 맞춘다. `(a, b, 가장 큰 상대 어긋남)`.

    ## 왜 직선인가 — 우리가 고른 것이 아니다

    Abaqus 는 온도-값 **표**를 그대로 받지만 OpenRadioss `/HEAT/MAT` 은
    전도도를 **`AS + BS·T` 두 계수로** 받는다. 표를 그 두 수로 바꾸는 것은
    솔버가 요구하는 모양이지 우리가 고른 근사가 아니다.

    ## 어긋남을 숨기지 않는다

    점이 둘이면 직선이 정확히 지나가고, 셋 이상이면 **맞추는 것**이다. 그
    어긋남을 말하지 않으면 사람은 표를 넣은 대로 나갔다고 믿는다 — 실제로는
    직선으로 눌린 값이 솔버에 간다.

    **몇 %부터 문제인지는 판정하지 않는다.** 그것은 규격과 용도가 정하고, 여기서
    상수로 박으면 그 숫자가 곧 규격 행세를 한다(밀시트 대조와 같은 판단).
    """
    if len(points) == 1:
        return points[0][1], 0.0, 0.0

    import numpy as np

    temperatures = np.array([one for one, _ in points], dtype=float)
    values = np.array([one for _, one in points], dtype=float)
    slope, intercept = (float(one) for one in np.polyfit(temperatures, values, 1))
    fitted = intercept + slope * temperatures
    scale = float(np.max(np.abs(values)))
    gap = float(np.max(np.abs(fitted - values)) / scale) if scale > 0 else 0.0
    return intercept, slope, gap


@register_renderer(
    key="openradioss_thermal",
    label="Radioss (열물성)",
    extension="rad",
    suffix="_thermal",
    describe=(
        "/HEAT/MAT — 열해석용 재료. 체적 열용량(RHOCP(밀도 곱하기 비열))과 전도도를 받는다. "
        "전도도는 표가 아니라 `AS + BS·T` 두 계수다."
    ),
    keywords=("/HEAT/MAT", "/UNIT/1", "/END"),
    needs=(
        # **RHOCP 로 들어간다** — 밀도 곱하기 비열이다. 비열만으로는 못 만들고,
        # 0 을 넣으면 열용량 0 인 재료가 된다.
        Need("elastic", values=("density",)),
        Need("thermal", values=("specific_heat",)),
    ),
)
def render_openradioss_thermal(deck: Deck) -> Rendered:
    """OpenRadioss `/HEAT/MAT`.

    ## 왜 `/MAT/LAW36` 과 같은 파일에 못 넣나

    Radioss 는 **열물성을 별도 블록으로 받는다** — Abaqus 처럼 `*MATERIAL` 아래
    키워드를 이어 붙이는 구조가 아니다. 그래서 렌더러도 따로다. 두 파일을 같은
    `mat_ID` 로 묶어 쓴다.

    ## Cp 가 아니라 RHOCP(밀도 곱하기 비열) 다

    `/HEAT/MAT` 은 **체적 열용량**을 받는다(J/(m³·K)). 우리가 담은 것은 질량
    기준 비열(J/(kg·K))이라 밀도를 곱해야 한다 — 그 곱을 안 하고 넣으면 밀도
    배만큼 틀린 재료가 되고, **덱은 멀쩡히 돌고 온도만 안 오른다.**

    ## 전도도는 표가 아니라 직선이다

    `AS + BS·T`. 우리가 고른 근사가 아니라 이 솔버가 요구하는 모양이다. 맞춘
    어긋남을 덱 주석에 적는다 — 안 적으면 사람은 표를 넣은 대로 나갔다고 믿는다.

    ## 열팽창은 여기 없다

    Radioss 에서 열팽창은 **역학 법칙 쪽**이 받는다(`/MAT/LAW` 계열). 이 블록에
    넣을 자리가 없어서 **조용히 빼지 않고 그 사실을 적는다** — 넣은 줄 알고 열응력
    해석을 돌리면 팽창이 0 인 재료가 된다.
    """
    density = deck.number("elastic", "density")
    assert density is not None

    heats = _thermal_points(deck, "specific_heat")
    if not heats:
        raise ExportError(
            "비열이 없어 체적 열용량(RHOCP(밀도 곱하기 비열))을 만들 수 없습니다."
        )

    notes: list[str] = []
    lines = ["#RADIOSS STARTER", *_header(deck, "#")]
    lines.extend(_unit_block(deck))

    # RHOCP(밀도 곱하기 비열). **비열이 온도를 타면 첫 점을 쓴다** — 이 필드는 상수 하나다.
    volumetric = density * heats[0][1]
    if len(heats) > 1:
        notes.append(
            f"비열이 온도 {len(heats)}점으로 적혀 있는데 /HEAT/MAT 의 RHOCP 는 상수 "
            f"한 칸입니다. 가장 낮은 온도({heats[0][0]:.5g} K)의 값을 썼습니다."
        )

    conductivities = _thermal_points(deck, "thermal_conductivity")
    if conductivities:
        intercept, slope, gap = _linear_in_temperature(conductivities)
        if len(conductivities) > 2:
            notes.append(
                f"전도도를 AS + BS·T 직선으로 맞췄습니다 — {len(conductivities)}점에서 "
                f"가장 큰 어긋남 {gap * 100:.3g}%. /HEAT/MAT 이 표를 안 받습니다."
            )
    else:
        # **0 을 넣지 않는다.** 전도도 0 은 열이 안 퍼지는 재료다.
        raise ExportError(
            "열전도율이 없습니다. /HEAT/MAT 의 AS 는 자리 있는 필드라 비울 수 없고, "
            "0 을 넣으면 열이 안 퍼지는 재료가 됩니다."
        )

    expansion = _thermal_points(deck, "thermal_expansion")
    if expansion:
        notes.append(
            "선팽창계수(CTE)는 /HEAT/MAT 에 자리가 없습니다 — Radioss 에서는 역학 법칙 쪽이 "
            "받습니다. 이 덱에는 안 실렸습니다."
        )
        lines.append(
            "# EXPANSION: 이 블록에 자리가 없어 안 실었습니다. 역학 법칙 쪽에 넣으세요."
        )

    initial = conductivities[0][0]
    lines.append(
        f"# RHOCP = density x specific_heat = {_free(density)} x {_free(heats[0][1])}"
    )
    lines.append(f"# CONDUCTIVITY = AS + BS*T  ({len(conductivities)} point(s))")
    # **제목 줄이 없는 블록이다**(OpenRadioss `mat_HEAT.cfg`). 전에는 `/MAT` 처럼 이름을
    # 한 줄 적어서, 그 줄이 T0·RHOCP 줄로 읽히고 값이 한 줄씩 밀렸다(2026-09-27).
    # 이름은 주석으로 남긴다 — 덱에서 짝을 찾을 때 쓴다.
    lines.append(f"# {deck.name}")
    lines.append(f"/HEAT/MAT/{deck.solver_id}/1")
    lines.append(f"#{'T0':>19}{'RHOCP':>20}{'AS':>20}{'BS':>20}")
    lines.append(_fixed(initial) + _fixed(volumetric) + _fixed(intercept) + _fixed(slope))
    # 둘째 줄도 파서가 무조건 읽는다. 비우면 기본값(녹는점 1e20 · EFRAC 1)이다 — 0 을
    # 적으면 녹는점이 0 인 재료가 된다.
    lines.append(f"#{'T_melt':>19}{'AL':>20}{'BL':>20}{'EFRAC':>20}")
    lines.append("")
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="abaqus_rate",
    label="Abaqus (속도 의존)",
    extension="inp",
    suffix="_rate",
    describe="*ELASTIC + 속도별 *PLASTIC, RATE= — 변형률 속도 의존 소성 표.",
    keywords=("*MATERIAL", "*ELASTIC", "*PLASTIC"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        # 속도가 하나뿐이면 이 덱을 낼 이유가 없다 — 그건 `abaqus` 가 한다. **미리
        # 말한다**: 있느냐만 보면 메뉴는 「가능」 인데 내려받기가 422 였다(2026-09-05).
        Need(
            "rate_table",
            values=("rate_count",),
            at_least=(("rate_count", 2),),
            rows_min=2 * MIN_POINTS,
        ),
    ),
)
def render_abaqus_rate(deck: Deck) -> Rendered:
    """Abaqus 속도 의존 소성 — **속도마다 `*PLASTIC, RATE=` 한 벌.**

    Abaqus 는 `*PLASTIC` 을 속도별로 반복해 주면 그 사이를 보간한다. 식(Cowper-
    Symonds·Johnson-Cook)으로도 줄 수 있지만(`*RATE DEPENDENT`), **표가 잰 것이고
    식은 요약**이다 — 표를 싣고 식은 주석으로 적는다. 표 밖 속도는 Abaqus 가
    가장자리 값을 쓴다(Abaqus 의 기본 — `EXTRAPOLATION=` 은 2022 에 생겨 안 적는다).

    행은 `rate_table` 을 속도로 나눈다. **속도가 하나뿐이면 거부한다** — 그 덱은
    `abaqus` 가 낼 것이고, 여기서 내면 속도 의존이 있는 척이 된다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    curves, curve_notes = rate_curves(deck)

    notes: list[str] = []
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    rates = [rate for rate, _ in curves]
    lines.append(
        f"** Rate dependent plasticity: {len(rates)} strain rates "
        f"({_free(rates[0])} ~ {_free(rates[-1])} 1/s), tabular, interpolated by Abaqus"
    )
    model = deck.values("rate_table").get("model")
    if model == "cowper_symonds":
        d, p = deck.number("rate_table", "cs_d"), deck.number("rate_table", "cs_p")
        if d is not None and p is not None:
            lines.append(
                "** Cowper-Symonds summary (not used by this deck): "
                f"D={_free(d)} 1/s, p={_free(p)}"
            )
    elif model == "johnson_cook":
        c = deck.number("rate_table", "jc_c")
        if c is not None:
            lines.append(f"** Johnson-Cook summary (not used by this deck): C={_free(c)}")
    if density is None:
        notes.append("밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append(
            "** DENSITY: 측정값이 없어 비웠습니다. "
            "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
        )
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    lines.extend(_elastic_lines(deck, youngs, poisson))
    lines.extend(_thermal_lines(deck))
    notes.extend(curve_notes)
    for rate, points in curves:
        lines.append(f"*PLASTIC, HARDENING=ISOTROPIC, RATE={_free(rate)}")
        lines.extend(f"{_free(stress)}, {_free(strain)}" for strain, stress in points)
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="abaqus_lve",
    label="Abaqus (선형탄성구간 · DMA)",
    extension="inp",
    suffix="_lve",
    describe="*ELASTIC 만 — DMA 변형률 스윕의 선형 구간 저장 탄성률. 소성 없음.",
    keywords=("*MATERIAL", "*ELASTIC"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("lve", values=("youngs_modulus", "lve_strain_limit")),
    ),
)
def render_abaqus_lve(deck: Deck) -> Rendered:
    """Abaqus 선형 탄성 덱 — **DMA 저장 탄성률을 E 로.**

    소성 표가 없으므로 `abaqus` 형식은 이 카드를 못 낸다. 그런데 소변형·진동 해석은
    `*ELASTIC` 만으로 돌고, DMA 의 선형 구간 E′ 가 그 자리에 맞는 값이다. **유효 범위가
    있다** — 한계 변형률과 재던 주파수·온도를 덱에 적는다. 그 밖에서 이 덱을 쓰면
    조용히 틀린다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    limit = deck.number("lve", "lve_strain_limit")
    frequency = deck.number("lve", "frequency_hz")
    temperature = deck.number("lve", "temperature_k")
    count = deck.number("lve", "sample_count")

    notes: list[str] = []
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    lines.append(
        "** ELASTIC is the DMA storage modulus in the linear viscoelastic range"
        + (f", valid up to strain {_free(limit)}" if limit is not None else "")
        + (f", at {_free(frequency)} Hz" if frequency is not None else "")
        + (f", {_free(temperature)} K" if temperature is not None else "")
        + (f", from {int(count)} specimen(s)" if count is not None else "")
    )
    lines.append("** No plasticity: use for small-strain / vibration analyses only")
    if density is None:
        notes.append("밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append(
            "** DENSITY: 측정값이 없어 비웠습니다. "
            "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
        )
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    lines.extend(_elastic_lines(deck, youngs, poisson))
    lines.extend(_thermal_lines(deck))
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="abaqus_elastic",
    label="Abaqus (선형)",
    extension="inp",
    suffix="_elastic",
    describe=(
        "*ELASTIC(+*DENSITY·열물성) — 선형 탄성. 소성 표가 없는 카드(문헌·선언 값·DMA 선형 "
        "구간)용. 온도별 표면 온도 열이 붙는다."
    ),
    keywords=("*MATERIAL", "*ELASTIC"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        Need("lve", optional=True),
    ),
)
def render_abaqus_elastic(deck: Deck) -> Rendered:
    """Abaqus 선형 탄성 — **소성 표가 없는 카드를 위한 자리.**

    전에는 Abaqus 형식이 소성 표(`abaqus`)나 DMA 선형 구간(`abaqus_lve`)을 요구해서, 문헌
    값이나 선언 물성만 든 카드는 다른 솔버로는 나가는데 Abaqus 로만 못 나갔다(2026-09-27,
    형식 표를 솔버·물성 모델로 채우면서 드러났다). 선형탄성구간 카드면 유효 한계를 적는다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")
    limit = deck.number("lve", "lve_strain_limit")

    notes: list[str] = []
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    if limit is not None:
        lines.append(
            f"** ELASTIC is the DMA storage modulus in the linear range - valid up to strain "
            f"{_free(limit)}"
        )
    lines.append("** No plasticity: use for small-strain / vibration analyses only")
    if density is None:
        notes.append("밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append(
            "** DENSITY: 측정값이 없어 비웠습니다. "
            "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
        )
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    lines.extend(_elastic_lines(deck, youngs, poisson))
    lines.extend(_thermal_lines(deck))
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="abaqus_thermal",
    label="Abaqus (열물성)",
    extension="inp",
    suffix="_thermal",
    describe=(
        "*CONDUCTIVITY·*SPECIFIC HEAT·*DENSITY(·*EXPANSION) — 열전도 해석용. 탄성 값이 없는 "
        "열물성 카드도 낸다."
    ),
    keywords=("*MATERIAL", "*CONDUCTIVITY"),
    needs=(
        Need("thermal", values=("thermal_conductivity",)),
        Need("elastic", values=("density",), optional=True),
    ),
)
def render_abaqus_thermal(deck: Deck) -> Rendered:
    """Abaqus 열물성 — **탄성이 없는 카드**를 위한 자리.

    다른 Abaqus 형식도 열물성을 곁들여 싣지만 모두 탄성계수·푸아송비를 요구한다. 핸드북의
    열물성만 든 카드는 그래서 Abaqus 로 못 나갔다. 과도 열해석은 밀도 곱하기 비열이 열용량이라,
    밀도가 없으면 그 사실을 적는다(정상 해석에는 상관없다).
    """
    density = deck.number("elastic", "density")
    notes: list[str] = []
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    lines.append("** Heat transfer material - pair it with the structural material if needed.")
    if density is None:
        notes.append(
            "밀도가 카드에 없어 *DENSITY 를 뺐습니다 — 과도 열해석의 열용량(밀도 곱하기 "
            "비열)이 서지 않습니다. 정상 해석에는 상관없습니다."
        )
        lines.append("** DENSITY: not on the card - transient heat capacity needs it.")
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    lines.extend(_thermal_lines(deck))
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


@register_renderer(
    key="json",
    label="중립 JSON",
    extension="json",
    describe="솔버 중립 — 우리가 만들지 않은 솔버를 쓰는 사람이 직접 덱을 만든다.",
    keywords=("matnexus.property-card",),
    media_type="application/json; charset=utf-8",
)
def render_json(deck: Deck) -> Rendered:
    """솔버 중립 JSON — **카드가 가진 것을 그대로.**

    우리가 안 만든 솔버를 쓰는 사람이 있다. 카드를 데이터로 내보내면 각자 자기
    덱을 만들 수 있다.

    ## 스스로 설명하는 파일이다

    값 옆에 **이름과 단위를 함께 적는다.** 파일이 돌아다니는 동안 단위가 어디에
    적혀 있었는지 잊히고, `youngs_modulus: 200000000000` 만 남으면 그것이 Pa 인지
    MPa 인지 받는 사람이 알 수 없다. 뜻은 레지스트리가 이미 갖고 있다(ADR 0012).

    ## 정해진 칸이 없다

    전에는 `elastic`·`plasticity` 라는 칸을 손으로 적었고, 물성이 늘면 이 함수도
    커졌다. 지금은 카드에 실린 블록을 그대로 낸다 — **새 물성이 저절로 따라온다.**
    """
    import json

    from matcore import cards

    # **여기서도 부른다.** 이 렌더러는 블록 선언에서 이름과 단위를 가져오는데,
    # 아무도 부르지 않은 상태로 들어오면 선언이 비어 `values` 만 남는다 — 그러면
    # 파일이 "스스로 설명한다" 는 약속을 조용히 어긴다.
    #
    # 실제로 그랬다: 시험을 파일 단위로 돌리면 실패하고 디렉터리로 돌리면
    # 통과했다(다른 시험이 먼저 불러 줬다). `load_builtin` 은 여러 번 불러도
    # 되므로 부르는 쪽마다 부른다.
    cards.load_builtin()

    def in_file(si_unit: Any) -> str | None:
        """이 파일의 계에서 그 물리량을 무엇으로 적었나. **`si_unit` 만 두면 거짓말이다** —
        mm·N·tonne 파일에서 값은 MPa 인데 곁에 `si_unit: "Pa"` 만 적혀 있으면 받는 쪽은 Pa
        로 읽는다(2026-09-24, 재료 내보내기의 밀도가 그렇게 읽혔다)."""
        if not isinstance(si_unit, str):
            return None
        try:
            return deck.units.symbol(si_unit)
        except KeyError:
            return None

    blocks: dict[str, Any] = {}
    for key, payload in deck.blocks.items():
        try:
            spec: Any = cards.block(key)
        except KeyError:
            spec = None
        blocks[key] = {
            "label": spec.label if spec else key,
            "values": deck.values(key),
            # 값의 뜻과 단위. **받는 사람이 되짚을 수 있어야 한다.** `unit` 이 이 파일의
            # 숫자의 단위이고, `si_unit` 은 같은 물리량의 SI 기호다.
            "declared": (
                {
                    item.key: {
                        "label": item.label,
                        "unit": in_file(item.si_unit),
                        "si_unit": item.si_unit,
                    }
                    for item in (*spec.produces, *spec.rows)
                }
                if spec
                else {}
            ),
            # 행이 자기 단위를 들면(경화식 파라미터) 그 행의 숫자도 이 계로 옮겨져 있다 —
            # 그 단위를 행마다 적는다.
            "rows": [
                {**row, "unit": in_file(row["si_unit"])}
                if isinstance(row, Mapping) and isinstance(row.get("si_unit"), str)
                else row
                for row in deck.rows(key)
            ],
            "notes": list(payload.get("notes", [])) if isinstance(payload, Mapping) else [],
        }

    body: dict[str, Any] = {
        "schema": "matnexus.property-card/2",
        "name": deck.name,
        # **덱의 계를 적는다.** 박아 두면 값은 바뀌는데 선언이 안 바뀐다.
        "units": {
            "length": deck.units.length,
            "mass": deck.units.mass,
            "time": deck.units.time,
            "stress": deck.units.symbol("Pa"),
            "system": deck.units.key,
            # SI 기호 → 이 계의 기호, 전부. 받는 쪽이 값마다 `unit` 을 안 읽어도 계를 안다.
            "symbols": dict(deck.units.symbols),
        },
        "blocks": blocks,
        "provenance": list(deck.provenance),
    }
    # 정렬해서 쓴다. 같은 카드는 언제 내보내도 같은 바이트여야 한다 — 두 파일이
    # 다른지 보려고 열어 보는 일이 실제로 생긴다.
    return Rendered(text=json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _unit_block(deck: Deck) -> list[str]:
    """OpenRadioss `/UNIT/1`. **덱이 자기 단위계를 말한다.**

    전에는 `MNX_SI_KG_M_S` 가 박혀 있었다. 단위계를 고를 수 있게 되는 순간 그
    이름은 거짓말이 된다 — 그리고 그 거짓말은 **솔버가 그대로 믿는다.**
    """
    system = deck.units
    name = f"MNX_{system.mass}_{system.length}_{system.time}".upper()
    return [
        "/UNIT/1",
        name,
        f"#{'MU_M':>19}{'MU_L':>20}{'MU_T':>20}",
        _radioss_unit(system.mass, "g")
        + _radioss_unit(system.length, "m")
        + _radioss_unit(system.time, "s"),
    ]


#: Radioss 단위 코드 = SI 접두사 + 밑 글자(질량 `g` · 길이 `m` · 시간 `s`). 파서가 **끝 글자**
#: 를 보고 차원을 가른다(OpenRadioss `unit_code.F`).
_RADIOSS_PREFIXES = (
    "y", "z", "a", "f", "p", "n", "mu", "u", "m", "c", "d", "", "da", "h", "k", "K",
    "M", "G", "T", "P", "E", "Z", "Y",
)  # fmt: skip

#: 우리 기호 → Radioss 코드. **`tonne` 은 오류 573 이다** — 끝 글자가 `g` 가 아니라서
#: 못 읽는다. 톤의 정식 표기는 메가그램 `Mg` 다(2026-09-27, 파서로 확인). 전에는
#: 기본 계(mm·N·tonne)로 낸 모든 Radioss 덱의 `/UNIT` 가 `tonne` 이었다.
_RADIOSS_ALIASES = {"tonne": "Mg", "t": "Mg"}


def _radioss_unit(symbol: str, base: str) -> str:
    """단위 하나를 `/UNIT` 의 20칸으로. 코드로 못 적으면 **SI 기본 단위에 대한 배수**로
    적는다 — 파서가 둘 다 받는다. 모르는 글자를 그대로 두면 Starter 가 멈춘다."""
    code = _RADIOSS_ALIASES.get(symbol, symbol)
    if code.endswith(base) and code[: -len(base)] in _RADIOSS_PREFIXES:
        return f"{code:>20}"
    from matcore import units

    return f"{float(units.unit_of(symbol).factor):>20.9E}"


def block_spec(key: str) -> Any:
    """등록된 블록 선언. 없으면 `None` — 확장이 안 붙은 상태도 있다.

    `cards` 를 늦게 부른다. 이 패키지가 위에서 부르면 순환이 된다(265줄이 같다).
    """
    from matcore import cards

    try:
        return cards.block(key)
    except KeyError:
        return None


def _unit_of(spec: Any, key: str, row: Mapping[str, Any] | None) -> str | None:
    """이 값이 무슨 물리량인가. **행이 자기 단위를 들면 그것이 이긴다.**

    경화식 파라미터는 식마다 단위가 다르다 — Voce 의 `b` 는 무차원이고 `q` 는
    Pa 다. 열 선언 하나로는 못 적어서, 행에 `si_unit` 을 실어 보낸다
    (`matcore/cards/__init__.py` 머리말).
    """
    if row is not None:
        told = row.get("si_unit")
        if isinstance(told, str) and told:
            return told
    if spec is None:
        return None
    for item in (*spec.produces, *spec.rows):
        if item.key == key:
            found = item.si_unit
            return str(found) if isinstance(found, str) else None
    return None


#: **이름이 단위를 말하는 값** — 선언 물성이 칸에 붙여 두는 조건(`<칸>_frequency_hz` ·
#: `_wavelength_m` · `_temperature_k`, `shared/declared_slots`). 계를 바꿔도 옮기지 않는다:
#: 이름이 Hz · m · K 라고 말하는데 숫자만 mm 가 되면 받는 쪽은 이름을 믿는다. 뜻을 아는
#: 값이라 「단위가 선언돼 있지 않아 SI 로 남긴 값」 에도 안 적는다(2026-10-02).
SELF_DESCRIBED = ("_frequency_hz", "_wavelength_m", "_temperature_k")


def to_system(deck: Deck, system: UnitSystem) -> Deck:
    """덱의 숫자를 그 단위계로 옮긴다. **렌더러는 이 일을 모른다.**

    렌더러마다 환산하게 두면 새 렌더러가 붙을 때마다 빠뜨릴 자리가 생기고,
    빠뜨린 렌더러는 **오류 없이** SI 를 그 계의 기호로 적어 내보낸다. 확장이
    등록한 렌더러(`register_renderer`)도 고칠 필요가 없어야 한다.

    ## 선언된 것만 바꾸고, 나머지는 **말한다**

    처음에는 단위를 모르는 숫자를 만나면 멈추게 했다. 실제 카드가 바로 걸렸다 —
    경화식 블록은 `values` 가 **열려 있다.** 식마다 다른 파라미터가 들어오므로
    (`**extras`) 선언에 다 적을 수가 없다. 그리고 그 블록은 애초에 덱에 안
    실린다(`matcore/cards/mechanical.py`).

    그래서 규칙을 바꿨다. 선언된 값은 바꾸고, **선언 안 된 숫자는 그대로 두되
    이름을 돌려준다.** 부르는 쪽이 그것을 덱 주석에 적는다 — 조용히 남는 것과
    적혀서 남는 것은 다르다.

    **선언은 됐는데 이 계에 기호가 없으면** 그때는 멈춘다. 그건 표의 구멍이지
    데이터의 성질이 아니다.
    """
    if system is SI:
        # 인수가 전부 1 이라 결과는 같지만, 굳이 새 dict 를 만들지 않는다.
        return replace(deck, units=SI)

    untouched: list[str] = []

    def moved(value: Any, si_unit: str | None, where: str) -> Any:
        if not isinstance(value, int | float) or isinstance(value, bool):
            return value
        if si_unit is None and where.endswith(SELF_DESCRIBED):
            return value
        if si_unit is None:
            # 뜻을 모르는 숫자다. 바꾸지 않고 **이름을 남긴다.**
            untouched.append(where)
            return value
        try:
            return system.convert(float(value), si_unit)
        except KeyError as error:
            raise ExportError(
                f"{system.label} 에는 '{si_unit}' 을 쓸 기호가 정해져 있지 "
                f"않습니다('{where}'). `matcore/export/systems.py` 에 적거나 "
                f"SI 로 내보내세요."
            ) from error

    blocks: dict[str, Any] = {}
    for name, payload in deck.blocks.items():
        if not isinstance(payload, Mapping):
            blocks[name] = payload
            continue
        spec = block_spec(name)
        moved_values = {
            key: moved(value, _unit_of(spec, key, None), f"{name}.{key}")
            for key, value in (payload.get("values") or {}).items()
        }
        moved_rows = [
            {
                key: moved(value, _unit_of(spec, key, row), f"{name}[].{key}")
                for key, value in row.items()
            }
            for row in (payload.get("rows") or [])
            if isinstance(row, Mapping)
        ]
        blocks[name] = {
            **payload,
            **({"values": moved_values} if "values" in payload else {}),
            **({"rows": moved_rows} if "rows" in payload else {}),
        }
    if untouched:
        # **조용히 남기지 않는다.** 덱 주석에 그대로 들어간다.
        blocks = {
            **blocks,
            "_units": {
                "notes": [f"단위가 선언돼 있지 않아 SI 로 남긴 값: {', '.join(untouched)}"]
            },
        }
    return replace(deck, blocks=blocks, units=system)


def render(format_key: str | Renderer, deck: Deck, system: UnitSystem = SI) -> Rendered:
    """덱을 솔버 텍스트로 만든다.

    **쓰고 나서 다시 읽는다.** 키워드가 빠진 파일은 솔버가 오류 없이 무시하기도
    한다 — 그러면 해석은 도는데 재료가 안 들어간 채로 돈다.

    `system` 은 **여기서 한 번** 적용된다(`to_system`). 렌더러는 이미 그 계로
    바뀐 덱을 받고, 선언 줄만 `deck.units` 에서 읽는다.
    """
    found = _resolve(format_key)
    if found is None:
        raise ExportError(
            f"모르는 형식입니다: {format_key}. 있는 것: {', '.join(sorted(_RENDERERS))}"
        )
    target = found

    # **모자란 것 검사가 여기 한 곳에 있다.** 형식마다 흩어져 있으면 새 형식이
    # 붙을 때 빠뜨리고, 빠뜨린 형식은 0 을 써서 내보낸다.
    missing = missing_for(deck, target)
    if missing:
        raise ExportError(
            f"{target.label} 덱에 {', '.join(missing)} 가 필요한데 카드에 없습니다. "
            f"푸아송비와 밀도는 인장시험이 주지 않습니다 — 카드를 만들 때 넣거나, "
            f"아는 값이 없으면 이 솔버로는 내보낼 수 없습니다. "
            f"기본값으로 채워 내보내면 그것이 측정값인지 덱만 봐서는 알 수 없습니다."
        )

    # **형식이 단위를 정했으면 그 계로** — 고른 계가 무엇이든(`Renderer.fixed_units`).
    result = target.render(to_system(deck, effective_system(target, system)))
    absent = [word for word in target.keywords if word not in result.text]
    if absent:
        raise ExportError(
            f"{target.label} 덱에 있어야 할 키워드가 빠졌습니다: {', '.join(absent)}. "
            f"내보내기 코드의 문제입니다 — 이대로 쓰면 솔버가 재료 없이 해석을 돌립니다."
        )
    return result
