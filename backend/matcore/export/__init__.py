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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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


class ExportError(Exception):
    """이 카드로는 이 솔버 덱을 만들 수 없다.

    메시지는 **사용자가 읽는다.** 무엇이 없고 어디서 채우면 되는지 적는다.
    """


@dataclass(frozen=True)
class Card:
    """내보낼 물성 한 벌. **전부 SI 다.**"""

    name: str
    """솔버 덱 안의 재료 이름. ASCII 로 정리된 것이 들어온다."""
    solver_id: int
    youngs_modulus: float | None = None
    poisson_ratio: float | None = None
    density: float | None = None
    points: tuple[tuple[float, float], ...] = ()
    """(진소성변형률, 진응력). 정리 전 원본이 들어온다 — 정리는 여기서 한다."""
    provenance: tuple[str, ...] = ()
    """어디서 나온 값인지. **카드 주석으로 들어간다** — 덱만 받은 사람이 되짚을
    수 있어야 한다."""

    prony: tuple[tuple[float, float], ...] = ()
    """(gᵢ, τᵢ). 점탄성 상대 탄성률과 완화시간 — `matcore.prony` 가 낸 것.

    **이게 있으면 `youngs_modulus` 는 순간 탄성률(E₀)이다.** Abaqus 는
    `*VISCOELASTIC` 이 있을 때 `*ELASTIC` 을 순간 탄성률로 읽는다. 평형
    탄성률로 넣으면 재료가 통째로 무르게 계산된다."""
    prony_reference_temperature: float | None = None
    """마스터커브를 겹친 기준 온도(K). **이 카드가 유효한 온도다** — 다른
    온도의 해석에 그대로 쓰면 안 된다는 사실이 덱에 적혀야 한다."""


@dataclass(frozen=True)
class Rendered:
    text: str
    notes: tuple[str, ...] = field(default=())
    """내보내면서 한 일. **조용히 하지 않았다는 증거다.**"""


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
            f"자국이라, 그중 마지막(항복점, {ordered[keep][1] / 1e6:.4g} MPa)만 남기고 "
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
            f"{ordered[0][1] / 1e6:.4g} MPa 는 그대로). 솔버는 첫 점을 항복점으로 읽습니다."
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
            raise ExportError(
                f"{index}번째 점에서 응력이 떨어집니다 "
                f"({ordered[index - 1][1] / 1e6:.5g} → {ordered[index][1] / 1e6:.5g} MPa). "
                f"네킹 뒤 구간이 섞였을 수 있습니다 — 'tensile.necking_candidate' 가 "
                f"제시한 위치에서 자르고 다시 처리하세요. 여기서 눕혀 내보내면 그 덱은 "
                f"실제와 다른 재료가 됩니다."
            )

    if len(ordered) < MIN_POINTS:
        raise ExportError(f"정리하고 나니 {len(ordered)}점입니다. 표가 너무 짧습니다.")
    return ordered, notes


#: 값 이름의 한국어. 오류 메시지와 형식 목록이 같은 말을 쓴다.
VALUE_LABELS = {
    "youngs_modulus": "탄성계수",
    "poisson_ratio": "푸아송비",
    "density": "밀도",
    "prony": "Prony 계수",
    "points": "소성 표",
}


def _require(card: Card, names: tuple[str, ...], *, solver: str) -> None:
    """이 솔버가 반드시 있어야 하는 값. **없으면 거부한다.**

    `None` 만 보면 안 된다 — Prony 계수처럼 **빈 튜플이 기본값**인 것은 없는
    것과 같은데 `None` 이 아니다. 실제로 그래서 검사를 빠져나갔다.
    """
    missing = [
        VALUE_LABELS[name]
        for name in names
        if getattr(card, name) is None or getattr(card, name) == ()
    ]
    if missing:
        raise ExportError(
            f"{solver} 카드에 {', '.join(missing)} 가 필요한데 카드에 없습니다. "
            f"푸아송비와 밀도는 인장시험이 주지 않습니다 — 카드를 만들 때 넣거나, "
            f"아는 값이 없으면 이 솔버로는 내보낼 수 없습니다. "
            f"기본값으로 채워 내보내면 그것이 측정값인지 덱만 봐서는 알 수 없습니다."
        )


def _free(value: float) -> str:
    """자유 형식 숫자. Abaqus·JSON 이 쓴다."""
    return f"{value:.12E}"


def _fixed(value: float) -> str:
    """OpenRadioss 고정 20칸. **칸이 어긋나면 다른 필드로 읽힌다.**"""
    return f"{value:>20.9E}"


def _header(card: Card, comment: str) -> list[str]:
    """근거를 카드 안에 적는다.

    **덱만 받은 사람이 되짚을 수 있어야 한다.** 파일이 메일로 돌아다니는 동안
    이 주석이 유일한 출처 표시다.
    """
    return [f"{comment} {line}" for line in ("MatNexus 물성 카드", *card.provenance)]


def render_abaqus(card: Card) -> Rendered:
    """Abaqus `*MATERIAL` 덱.

    **단위 키워드가 없는 솔버다.** 그래서 단위를 주석으로 선언한다 — 값은 SI 그대로
    나가고, 덱의 다른 재료도 SI 여야 한다는 사실을 사람이 읽게 한다.
    """
    points, notes = prepare(card.points)

    lines = _header(card, "**")
    lines.append("** Consistent units: kg, m, s, Pa")
    if card.density is None:
        # *DENSITY 는 Abaqus 에서 선택이다. 빼되 **왜 뺐는지 적는다** — 동적
        # 해석을 돌리려던 사람이 덱만 보고 알 수 있어야 한다.
        notes.append("밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append(
            "** DENSITY: 측정값이 없어 비웠습니다. "
            "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
        )
    lines.append(f"*MATERIAL, NAME={card.name}")
    if card.density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(card.density)},")
    lines.append("*ELASTIC, TYPE=ISOTROPIC")
    assert card.youngs_modulus is not None and card.poisson_ratio is not None
    lines.append(f"{_free(card.youngs_modulus)}, {_free(card.poisson_ratio)}")
    # EXTRAPOLATION=CONSTANT — 표 밖에서 응력을 일정하게 둔다. 기본값(오류 중단)
    # 보다 낫다고 볼 수도 있지만, 여기서는 **적합 구간 밖을 외삽하지 않는다** 는
    # 이 프로젝트의 태도와 같은 말이다: 모르는 구간에서 값을 지어내지 않는다.
    lines.append("*PLASTIC, HARDENING=ISOTROPIC, EXTRAPOLATION=CONSTANT")
    # **응력이 먼저, 소성변형률이 나중이다.** OpenRadioss 와 순서가 반대다.
    lines.extend(f"{_free(stress)}, {_free(strain)}" for strain, stress in points)
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def render_abaqus_viscoelastic(card: Card) -> Rendered:
    """Abaqus `*VISCOELASTIC, TIME=PRONY` 덱. 선형 점탄성.

    ## `*ELASTIC` 이 순간 탄성률이다

    Abaqus 는 `*VISCOELASTIC` 이 붙어 있으면 `*ELASTIC` 을 **순간(t=0) 탄성률**로
    읽는다. 평형 탄성률을 넣으면 재료가 통째로 무르게 계산되는데, 덱은 멀쩡히
    돌고 결과도 그럴듯하다.

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
    if not card.prony:
        raise ExportError(
            "점탄성 카드인데 Prony 계수가 없습니다. 마스터커브를 만들고 "
            "Prony 를 맞춘 뒤에 내보내세요."
        )
    if card.youngs_modulus is None or card.poisson_ratio is None:
        raise ExportError("순간 탄성률과 푸아송비가 있어야 *ELASTIC 을 쓸 수 있습니다.")

    notes: list[str] = []
    lines = _header(card, "**")
    lines.append("** Consistent units: kg, m, s, Pa")
    lines.append("** ELASTIC = instantaneous (t=0) moduli — Abaqus reads it that way")
    lines.append("**          when *VISCOELASTIC is present.")
    if card.prony_reference_temperature is not None:
        celsius = card.prony_reference_temperature - 273.15
        lines.append(
            f"** Valid at {card.prony_reference_temperature:.2f} K ({celsius:.2f} C) only —"
        )
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

    if card.density is None:
        notes.append("밀도가 카드에 없어 *DENSITY 를 빼고 그 사실을 덱 주석에 적었습니다.")
        lines.append(
            "** DENSITY: 측정값이 없어 비웠습니다. "
            "동적 해석에는 이 덱이 그대로 쓰이지 못합니다."
        )

    lines.append(f"*MATERIAL, NAME={card.name}")
    if card.density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(card.density)},")
    lines.append("*ELASTIC, TYPE=ISOTROPIC")
    lines.append(f"{_free(card.youngs_modulus)}, {_free(card.poisson_ratio)}")
    lines.append("*VISCOELASTIC, TIME=PRONY, TYPE=ISOTROPIC")
    # 행 하나가 g, k, τ. 순서가 뒤바뀌면 솔버가 오류 없이 다른 재료를 만든다.
    lines.extend(f"{_free(g)}, 0.0, {_free(tau)}" for g, tau in card.prony)

    total = sum(g for g, _ in card.prony)
    if total >= 1.0:
        raise ExportError(
            f"Prony 상대 탄성률의 합이 {total:.4f} 로 1 이상입니다. "
            f"평형 탄성률이 0 이하라는 뜻이라 Abaqus 가 거부합니다."
        )
    notes.append(
        f"Prony {len(card.prony)}항, 상대 탄성률 합 {total:.4f} "
        f"(평형 탄성률은 순간의 {1 - total:.4f} 배)."
    )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def render_openradioss(card: Card) -> Rendered:
    """OpenRadioss `/MAT/LAW36` + `/FUNCT`.

    **고정 20칸 형식이다.** 칸이 하나 어긋나면 다른 필드로 읽히고, 솔버는 오류 없이
    엉뚱한 재료로 계산한다.
    """
    points, notes = prepare(card.points)
    assert (
        card.youngs_modulus is not None
        and card.poisson_ratio is not None
        and card.density is not None
    )

    lines = ["#RADIOSS STARTER", *_header(card, "#")]
    # **단위를 선언한다.** Abaqus 와 달리 이 솔버는 단위 블록이 있어서 값이 아니라
    # 선언으로 맞출 수 있다.
    lines.extend(["/UNIT/1", "MNX_SI_KG_M_S", f"{'kg':<20}{'m':<20}s"])
    lines.append(f"/MAT/LAW36/{card.solver_id}/1")
    lines.append(card.name)
    lines.append(f"#{'RHO_I':>19}")
    lines.append(_fixed(card.density))
    lines.append(f"#{'E':>19}{'nu':>20}{'Eps_p_max':>20}{'Eps_t':>20}{'Eps_m':>20}")
    lines.append(_fixed(card.youngs_modulus) + _fixed(card.poisson_ratio))
    lines.append(
        f"#{'N_funct':>9}{'F_smooth':>10}{'C_hard':>20}{'F_cut':>20}{'Eps_f':>20}{'VP':>20}"
    )
    lines.append(f"{1:>10}")
    lines.append(f"#{'fct_IDp':>9}{'Fscale':>20}{'Fct_IDE':>10}{'EInf':>20}{'CE':>20}")
    lines.append("# func_ID1")
    lines.append(f"{card.solver_id:>10}")
    lines.append(f"#{'Fscale_1':>19}")
    lines.append(_fixed(1.0))
    lines.append(f"#{'Eps_dot_1':>19}")
    # 변형률 속도 하나짜리 표다. 속도 의존을 넣으려면 곡선이 여러 개 있어야 하고,
    # 그것은 시험이 여러 속도로 있어야 한다는 뜻이다.
    lines.append(_fixed(0.0))
    lines.append(f"/FUNCT/{card.solver_id}")
    lines.append(f"{card.name}_TRUE_STRESS_VS_TRUE_PLASTIC_STRAIN")
    lines.append(f"#{'X':>19}{'Y':>20}")
    # **소성변형률이 먼저, 응력이 나중이다.** Abaqus 와 순서가 반대다.
    lines.extend(f"{strain:>20.12E}{stress:>20.9E}" for strain, stress in points)
    lines.append("/END")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


def render_json(card: Card) -> Rendered:
    """솔버 중립 JSON.

    **우리가 안 만든 솔버를 쓰는 사람이 있다.** 카드를 데이터로 내보내면 각자
    자기 덱을 만들 수 있다. 단위를 필드 이름에 박아 두는 이유는 같다 — 파일이
    돌아다니는 동안 단위가 어디에 적혀 있었는지 잊힌다.
    """
    import json

    points, notes = prepare(card.points)
    body: dict[str, Any] = {
        "schema": "matnexus.property-card/1",
        "name": card.name,
        "units": {"length": "m", "mass": "kg", "time": "s", "stress": "Pa"},
        "elastic": {
            "youngs_modulus_pa": card.youngs_modulus,
            "poisson_ratio": card.poisson_ratio,
            "density_kg_per_m3": card.density,
        },
        "plasticity": {
            "type": "tabulated_isotropic",
            "points": [
                {"true_plastic_strain": strain, "true_stress_pa": stress}
                for strain, stress in points
            ],
        },
        "provenance": list(card.provenance),
        "notes": notes,
    }
    # 정렬해서 쓴다. 같은 카드는 언제 내보내도 같은 바이트여야 한다 — 두 파일이
    # 다른지 보려고 열어 보는 일이 실제로 생긴다.
    return Rendered(
        text=json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    extension: str
    describe: str
    render: Callable[[Card], Rendered]
    keywords: tuple[str, ...]
    """이 형식이면 반드시 들어 있어야 하는 문자열. 쓴 뒤 확인한다."""
    requires: tuple[str, ...] = ()
    """없으면 이 형식으로 내보낼 수 없는 값. **화면이 미리 알려 줄 수 있어야 한다** —
    내려받기를 누른 뒤에 "푸아송비가 없습니다" 를 보는 것은 늦다."""
    media_type: str = "text/plain; charset=utf-8"


FORMATS: dict[str, Format] = {
    "abaqus": Format(
        key="abaqus",
        label="Abaqus",
        extension="inp",
        describe="*MATERIAL / *ELASTIC / *PLASTIC — 표 형식 소성. 단위는 SI(kg·m·s·Pa).",
        render=render_abaqus,
        keywords=("*MATERIAL", "*ELASTIC", "*PLASTIC"),
        # 밀도는 빠져도 된다 — *DENSITY 는 선택 키워드다. 대신 왜 없는지 덱에 적는다.
        #
        # **표는 빠지면 안 된다.** 전에는 `requires` 에 없어서 검사를 지나고
        # `render` 안에서 터졌다 — 그러면 화면이 "이 형식은 아직 못 낸다" 를
        # 미리 말할 수 없다. 점탄성 카드가 생기면서 실제로 걸리는 자리가 됐다.
        requires=("youngs_modulus", "poisson_ratio", "points"),
    ),
    "openradioss": Format(
        key="openradioss",
        label="OpenRadioss",
        extension="rad",
        describe="/MAT/LAW36 + /FUNCT — 표 형식 소성. /UNIT 블록으로 단위를 선언한다.",
        render=render_openradioss,
        keywords=("/MAT/LAW36", "/FUNCT/", "/UNIT/1", "/END"),
        # LAW36 은 RHO_I 가 자리 있는 필드다. 비울 수 없다.
        requires=("youngs_modulus", "poisson_ratio", "density", "points"),
    ),
    "abaqus_viscoelastic": Format(
        key="abaqus_viscoelastic",
        label="Abaqus (점탄성)",
        extension="inp",
        describe=(
            "*ELASTIC + *VISCOELASTIC, TIME=PRONY — 선형 점탄성. 기준 온도 하나에서 유효."
        ),
        render=render_abaqus_viscoelastic,
        keywords=("*MATERIAL", "*ELASTIC", "*VISCOELASTIC"),
        # **OpenRadioss 는 없다.** LAW62 는 고무 초탄성(Ogden)+Prony 경로라
        # 선형 점탄성과 다른 모형이다. 65 도 같은 이유로 Abaqus 만 낸다.
        requires=("youngs_modulus", "poisson_ratio", "prony"),
    ),
    "json": Format(
        key="json",
        label="중립 JSON",
        extension="json",
        describe="솔버 중립 — 우리가 만들지 않은 솔버를 쓰는 사람이 직접 덱을 만든다.",
        render=render_json,
        keywords=("matnexus.property-card",),
        media_type="application/json; charset=utf-8",
    ),
}


def missing_for(card: Card, format_key: str) -> tuple[str, ...]:
    """이 형식으로 내보내려면 카드에 더 있어야 하는 것. 사람이 읽는 이름으로.

    **누르기 전에 알아야 한다.** `requires` 의 독스트링이 처음부터 그렇게 적혀
    있었는데 그것을 읽는 곳이 없었다 — 화면은 형식을 전부 보여 주고, 못 내는
    형식은 내려받기를 누른 뒤에야 알려 줬다.
    """
    target = FORMATS.get(format_key)
    if target is None:
        return ()
    return tuple(
        VALUE_LABELS[name]
        for name in target.requires
        if getattr(card, name) is None or getattr(card, name) == ()
    )


def available_formats(card: Card) -> tuple[str, ...]:
    """이 카드로 지금 낼 수 있는 형식."""
    return tuple(key for key in FORMATS if not missing_for(card, key))


def render(format_key: str, card: Card) -> Rendered:
    """카드를 솔버 텍스트로 만든다.

    **쓰고 나서 다시 읽는다.** 키워드가 빠진 파일은 솔버가 오류 없이 무시하기도
    한다 — 그러면 해석은 도는데 재료가 안 들어간 채로 돈다.
    """
    target = FORMATS.get(format_key)
    if target is None:
        known = ", ".join(sorted(FORMATS))
        raise ExportError(f"모르는 형식입니다: {format_key}. 있는 것: {known}")

    # **필요한 값 검사가 여기 한 곳에 있다.** 형식마다 흩어져 있으면 새 형식이
    # 붙을 때 빠뜨리고, 빠뜨린 형식은 0 을 써서 내보낸다.
    _require(card, target.requires, solver=target.label)
    result = target.render(card)
    missing = [word for word in target.keywords if word not in result.text]
    if missing:
        raise ExportError(
            f"{target.label} 카드에 있어야 할 키워드가 빠졌습니다: {', '.join(missing)}. "
            f"내보내기 코드의 문제입니다 — 이대로 쓰면 솔버가 재료 없이 해석을 돌립니다."
        )
    return result
