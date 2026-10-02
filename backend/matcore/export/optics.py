"""광학 설계 · 광 시뮬레이션 렌더러 — Zemax OpticStudio · CODE V · n,k 표(Lumerical · COMSOL).

세 형식 모두 **파장을 µm · nm 로 받는다** — 파일 형식이 정한 단위라 고른 계와 상관없이 SI 덱을
받아(`Renderer.fixed_units`) 여기서 `matcore.units` 로 옮긴다.

## 양식의 근거 (2026-10-02, 공개 자료로 대조)

    Zemax AGF     Ansys Optics 의 「Zemax AGF material catalog file format」 과 공개
                  카탈로그 파일(Schott · Zeon) — `NM 이름 식번호 MIL nd vd` ·
                  `ED TCE TCE100 밀도 ΔPgF` · `CD 계수…` · `TD D0 D1 D2 E0 E1 λtk Tref` ·
                  `OD` · `LD λmin λmax` · `IT λ 투과율 두께mm`. 식 번호 1 이 Schott 식이다
                  (Zeon 플라스틱 카탈로그가 이 식).
    CODE V        사설 유리 `PRV` / `PWL 파장(nm)…` / `'이름' 굴절률…` / `END`
                  (공개 `.seq` 파일).
    n,k 표        파장 · n · k 세 열 — Lumerical 재료 데이터베이스의 Import data
                  (sampled data)와 COMSOL 보간 함수가 읽는 꼴. 머리줄이 없다(단위는 읽을 때
                  고른다: µm).

## 굴절률 점을 어디서 읽나

블록의 표(`rows` — 파장 · 굴절률 · 소광계수)가 먼저다. 표가 없으면 값 하나
(`refractive_index`)와
그 파장(`refractive_index_wavelength_m`)이다. 파장을 모르는 굴절률은 **어느 형식으로도 못
낸다** — 파장 없는 n 은 광학 설계에서 뜻이 없다.

## AGF 는 코드로만 낸다

AGF 는 분산식의 계수를 받는다. 점에서 계수를 맞추는 일(`matcore.dispersion`)은 정의(템플릿)
문법이 할 일이 아니다 — 그래서 정의판이 없다(`tests/unit/test_export_twins.py` 의 `CODE_ONLY`).

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

import math

from matcore import dispersion, units
from matcore.export import Deck, ExportError, Need, Rendered, register_renderer
from matcore.export.systems import SI
from matcore.export.template import alnum_name

#: AGF 의 내부 투과율(`IT`)을 적는 두께. 유리 카탈로그가 10 mm · 25 mm 를 흔히 쓴다.
TRANSMITTANCE_THICKNESS_MM = 10.0


def _g(value: float) -> str:
    return f"{value:.10g}"


def _rows(deck: Deck) -> list[dict[str, float]]:
    """굴절률이 있는 표 줄 — 파장 순. 같은 파장이 둘이면 멈춘다."""
    found = sorted(
        (
            {
                "wavelength": float(row["wavelength"]),
                "refractive_index": float(row["refractive_index"]),
                **(
                    {"extinction_coefficient": float(row["extinction_coefficient"])}
                    if isinstance(row.get("extinction_coefficient"), int | float)
                    else {}
                ),
            }
            for row in deck.rows("optical")
            if isinstance(row.get("wavelength"), int | float)
            and isinstance(row.get("refractive_index"), int | float)
        ),
        key=lambda one: one["wavelength"],
    )
    if len({one["wavelength"] for one in found}) != len(found):
        raise ExportError(
            "광학 물성의 파장 표에 같은 파장이 두 번 있습니다 — 하나만 남기세요."
        )
    return found


def index_points(deck: Deck) -> list[dict[str, float]]:
    """굴절률 점 — 표가 있으면 표, 없으면 값 하나(그 파장과 함께). 파장 순, SI(m)."""
    table = _rows(deck)
    if table:
        return table
    value = deck.number("optical", "refractive_index")
    at = deck.number("optical", "refractive_index_wavelength_m")
    if value is None or at is None:
        return []
    one = {"wavelength": at, "refractive_index": value}
    k = deck.number("optical", "extinction_coefficient")
    if k is not None and deck.number("optical", "extinction_coefficient_wavelength_m") == at:
        one["extinction_coefficient"] = k
    return [one]


_NO_WAVELENGTH = (
    "굴절률을 잰 파장이 카드에 없습니다 — {label} 는 파장마다 굴절률을 받습니다. 재료의 선언 "
    "물성에서 굴절률에 파장을 적어 주세요(d선이면 587.6 nm)."
)


# ── CODE V ───────────────────────────────────────────────────────────────────


@register_renderer(
    key="codev_prv",
    label="CODE V (사설 유리)",
    extension="seq",
    describe=(
        "PRV · PWL · END — 파장별 굴절률을 그대로 사설 카탈로그로(식으로 맞추지 않는다). "
        "파장은 nm. 명령 창에 붙여 넣거나 시퀀스 파일로 읽는다."
    ),
    keywords=("PRV", "PWL", "END"),
    needs=(Need("optical", values=("refractive_index",)),),
    fixed_units=SI,
)
def render_codev(deck: Deck) -> Rendered:
    """CODE V 사설 유리. **점을 그대로 넘긴다** — CODE V 가 파장 사이를 자기 식으로 잇는다.

    ## 유리 이름은 영숫자만

    CODE V 는 면에 적은 유리 이름 `NAME_CATALOG` 를 「CATALOG 의 NAME」 으로 읽는다. 재료
    이름의 `_` 를 그대로 두면 `PMMA_OPT` 가 「OPT 카탈로그의 PMMA」 가 되어 사설 유리를 못
    찾는다 — CODE V 가 쓴 렌즈 파일에 우리 PRV 를 끼워 ray-optics 리더로 읽어 확인했다
    (2026-10-03). 그래서 영숫자만 남긴 이름을 쓰고, 그 이름을 늘 알린다.
    """
    points = index_points(deck)
    if not points:
        raise ExportError(_NO_WAVELENGTH.format(label="CODE V"))
    glass = alnum_name(deck.name)
    notes: list[str] = [
        f"유리 이름은 {glass} 입니다 — CODE V 는 이름의 '_' 를 「유리_카탈로그」 로 읽어 "
        "영숫자만 남겼습니다. 면에는 이 이름을 적습니다."
    ]
    if len(points) == 1:
        notes.append(
            "굴절률이 파장 하나뿐이라 분산이 없는 재료로 읽힙니다 — 색수차를 보려면 파장별 "
            "굴절률을 더 적어 주세요."
        )
    wavelengths = " ".join(_g(units.from_si(one["wavelength"], "nm")) for one in points)
    indices = " ".join(f"{one['refractive_index']:.6f}" for one in points)
    lines = [
        f"! MatNexus property card: {deck.name} (provenance: see the card in MatNexus)",
        "PRV",
        f"PWL {wavelengths}",
        f"'{glass}' {indices}",
        "END",
    ]
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


# ── n,k 표 ───────────────────────────────────────────────────────────────────


@register_renderer(
    key="nk_table",
    label="광학 n·k 표 (Lumerical · COMSOL)",
    extension="txt",
    suffix="_nk",
    describe=(
        "파장(µm) · n · k 세 열, 머리줄 없음 — Lumerical 재료 데이터베이스의 Import data"
        "(sampled data)와 COMSOL 보간 함수가 읽는다. 읽을 때 파장 단위를 µm 로 고른다."
    ),
    needs=(Need("optical", values=("refractive_index",)),),
    fixed_units=SI,
)
def render_nk_table(deck: Deck) -> Rendered:
    """세 열을 늘 채운다 — 읽는 쪽(Lumerical)이 세 열을 요구한다. 소광계수가 없는 파장은
    k = 0(흡수 없음)으로 적고 **몇 개를 그렇게 적었는지** 말한다. 머리줄이 없는 형식이라 근거는
    파일에 못 적는다 — 근거가 필요하면 중립 JSON 을 함께 받는다."""
    points = index_points(deck)
    if not points:
        raise ExportError(_NO_WAVELENGTH.format(label="n·k 표"))
    notes: list[str] = []
    missing = sum(1 for one in points if "extinction_coefficient" not in one)
    if missing:
        notes.append(
            f"소광계수가 없는 파장 {missing}개는 k = 0(흡수 없음)으로 적었습니다 — 이 표는 "
            "세 열을 요구합니다."
        )
    lines = [
        "\t".join(
            (
                _g(units.from_si(one["wavelength"], "um")),
                _g(one["refractive_index"]),
                _g(one.get("extinction_coefficient", 0.0)),
            )
        )
        for one in points
    ]
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


# ── Zemax OpticStudio AGF ────────────────────────────────────────────────────


def _mil(nd: float, vd: float) -> str:
    """유리 코드 — nd 의 소수 셋째 자리까지와 νd 의 열 배(`509560` = 1.509 · 56.0)."""
    return f"{round((nd - 1) * 1000):03d}{round(vd * 10):03d}"


@register_renderer(
    key="zemax_agf",
    label="Zemax OpticStudio (유리 카탈로그)",
    extension="agf",
    describe=(
        "AGF 유리 카탈로그 — 파장별 굴절률(3점 이상)을 Schott 분산식으로 맞춰 계수로 적는다. "
        "nd · νd · 밀도 · 열팽창 · 내부 투과율(소광계수가 있으면)도 함께. 파장은 µm."
    ),
    keywords=("NM ", "CD ", "LD "),
    needs=(Need("optical", rows_min=dispersion.MIN_POINTS),),
    fixed_units=SI,
)
def render_zemax_agf(deck: Deck) -> Rendered:
    """AGF 유리 하나. **맞춘 식이 잰 점을 얼마나 따르는지 늘 적는다** — 카탈로그 굴절률은 소수
    다섯째 자리를 다투는데, 식이 그만큼 못 따르면 그 유리로 한 설계가 통째로 어긋난다."""
    points = _rows(deck)
    try:
        fit = dispersion.fit_schott(
            [
                (units.from_si(one["wavelength"], "um"), one["refractive_index"])
                for one in points
            ]
        )
        nd, vd = fit.nd, fit.vd
    except dispersion.DispersionError as exc:
        raise ExportError(f"Zemax 유리로 낼 수 없습니다 — {exc}") from exc

    notes = [
        f"Schott 식(항 {fit.terms}개)을 파장 {fit.points}점"
        f"({fit.wavelength_min_um:.4g}~{fit.wavelength_max_um:.4g} µm)에 맞췄습니다 — 잰 "
        f"점에서 최대 {fit.max_residual:.1e} 벗어납니다."
    ]
    if fit.max_residual > 1e-4:
        notes.append(
            "맞춘 식이 잰 점에서 1e-4 넘게 벗어납니다 — 광학 설계에서 무시하기 어려운 "
            "크기입니다. 잘못 적힌 점이 없는지, 점이 고르게 퍼졌는지 보세요."
        )
    if not (fit.covers(dispersion.LINE_F) and fit.covers(dispersion.LINE_C)):
        notes.append(
            "nd · νd 는 잰 파장 범위(F~C선, 486~656 nm)를 다 덮지 못해 식으로 외삽한 값입니다."
        )
    stated = deck.number("optical", "abbe_number")
    if stated is not None and abs(vd - stated) > 0.02 * abs(stated):
        notes.append(
            f"맞춘 식의 νd({vd:.2f})가 카드에 적힌 아베수({stated:.2f})와 2% 넘게 다릅니다 — "
            "어느 쪽이 맞는지 보세요."
        )

    alpha = deck.number("thermal", "thermal_expansion")
    density = deck.number("elastic", "density")
    if alpha is None:
        notes.append(
            "선팽창계수가 카드에 없어 TCE 를 0 으로 적었습니다 — 열 해석 전에 채우세요."
        )
    if density is None:
        notes.append("밀도가 카드에 없어 0 으로 적었습니다 — 무게 계산 전에 채우세요.")
    measured = deck.number("optical", "refractive_index_temperature_k")
    if measured is None:
        notes.append(
            "굴절률을 잰 온도가 카드에 없어 기준 온도를 20 °C 로 적었습니다 — dn/dT(TD)가 "
            "0 이라 굴절률에는 영향이 없습니다."
        )
    tref = units.from_si(measured, "degC") if measured is not None else 20.0
    tce = units.from_si(alpha, "ppm/K") if alpha is not None else 0.0
    grams = units.from_si(density, "g/cm3") if density is not None else 0.0

    lines = [
        f"CC MatNexus property card {deck.name} - Schott formula fitted to measured indices",
        f"NM {deck.name} 1 {_mil(nd, vd)} {nd:.6f} {vd:.2f}",
        f"GC fitted to {fit.points} points, {fit.terms} terms, "
        f"max |dn| {fit.max_residual:.1e}",
        f"ED {tce:.6f} 0.000000 {grams:.6f} 0.000000 0",
        "CD " + " ".join(f"{one:.10e}" for one in fit.coefficients),
        f"TD 0 0 0 0 0 0 {tref:.2f}",
        "OD -1 -1 -1 -1 -1 -1",
        f"LD {fit.wavelength_min_um:.6g} {fit.wavelength_max_um:.6g}",
    ]
    absorbing = [one for one in points if "extinction_coefficient" in one]
    if absorbing:
        # 내부 투과율 T = exp(-4πk·d/λ) — 소광계수의 정의 그대로(Beer-Lambert). 지어낸 값이
        # 아니라 옮긴 값이지만, 두께를 우리가 골랐으므로 그것을 적는다.
        thickness = units.to_si(TRANSMITTANCE_THICKNESS_MM, "mm")
        for one in absorbing:
            transmittance = math.exp(
                -4 * math.pi * one["extinction_coefficient"] * thickness / one["wavelength"]
            )
            lines.append(
                f"IT {units.from_si(one['wavelength'], 'um'):.6g} {transmittance:.6f} "
                f"{TRANSMITTANCE_THICKNESS_MM:g}"
            )
        notes.append(
            f"소광계수에서 두께 {TRANSMITTANCE_THICKNESS_MM:g} mm 의 내부 투과율"
            "(T = exp(-4πk·d/λ))을 셈해 IT 줄로 적었습니다."
        )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
