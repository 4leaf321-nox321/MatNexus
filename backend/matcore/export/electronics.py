"""전자 · 전기 CAE(ECAE) 렌더러 — Ansys Electronics Desktop · CST Studio Suite · Simcenter
Flotherm.

구조 해석 솔버(Abaqus · LS-DYNA …)와 다른 점이 하나 있다 — **파일 형식이 단위를 정해 두었다.**
AEDT 의 `.amat` · CST 의 `.mtd` · Flotherm 의 FloXML 은 SI 로 읽힌다(CST 는 단위를 파일에
선언한다). 그래서 이 형식들은 고른 단위계와 상관없이 SI 덱을 받는다
(`Renderer.fixed_units`). mm·N·tonne 숫자를 그대로 적으면 밀도가 10¹² 배 틀린 재료가 오류
없이 들어간다.

## 양식의 근거 (2026-10-02, 공개 자료로 대조)

    AEDT .amat     PyAEDT 저장소의 예제 재료 파일(`iron_pyaedt.amat` · `Materials.amat`)과
                   공개 HFSS 프로젝트의 주파수 데이터셋(`permittivity='pwl($Dk,Freq)'`).
                   주파수는 Hz(`Freq`), 데이터셋 X 는 Hz 로 적고 DimUnits 도 Hz 로 둔다.
    CST .mtd       CST 재료 라이브러리 파일(`[Definition]` 의 VBA 명령 · `.Create`).
                   주파수 분산은 `.DispersiveFittingFormatEps "Real_Tand"` 와
                   `.AddDispersionFittingValueEps "f", "eps'", "tanδ", "weight"`(Schott 유리
                   재료 파일). 영률은 kN/mm²(= GPa) · 열팽창은 1e-6/K 다 — CST 가 쓴 라이브러리
                   779개 중 기계 물성이 든 44개의 `[Attributes]` 가 전부 그 단위로 적혀 있고
                   값도 맞다(구리 120 · 17, 알루미늄 69 · 23). `.MaterialUnit` 과 상관없다.
    FloXML         Flotherm 의 XML 스키마(`XmlAttributes.xsd` — `isotropic_material_att`,
                   `electrical_resistivity`, `surface_att`)와 공식 예제. 스키마를 통과하는지
                   시험이 본다. 온도는 원소마다 단위가 달라 온도 표 · 계수는 싣지 않는다
                   (`render_flotherm`).

**AEDT · CST 로 실제로 읽어 보지는 못했다**(사내에 사용권이 없다) — 문법은 위 파일들과 글자로
대조했다. 처음 쓰는 사람은 한 재료로 읽혀 값이 그대로인지 먼저 본다(`docs/adr/0052`).

## 없는 값을 만들지 않는다

비투자율을 모르면 1 을 적지 않는다 — 안 적으면 솔버의 기본값(1)이 쓰이고, 적으면 그것이 잰
값처럼 보인다. 전도율과 저항률은 **정의로 서로 옮긴다**(σ = 1/ρ) — 지어낸 값이 아니므로 옮기되
그 사실을 적는다.

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from matcore import units
from matcore.export import (
    Deck,
    ExportError,
    Need,
    Rendered,
    header_lines,
    register_renderer,
    template,
)
from matcore.export.systems import SI


def _g(value: float) -> str:
    """사람이 읽는 숫자 — 유효숫자 열 자리. 세 형식 모두 자유 형식이다."""
    return f"{value:.10g}"


def notes_text(deck: Deck, *, quote: str = "plain", sep: str = " / ") -> str:
    """근거 줄을 **한 줄로** — 주석 기호가 없는 형식이 자기 메모 칸에 적는다.

    `quote` 는 그 칸의 글자 규칙이다. AEDT 는 작은따옴표로 감싸고 줄 끝 `\\` 를 이어 쓰기로
    읽는다 — 둘 다 바꿔 둔다. FloXML 은 XML 이라 `& < >` 를 바꾼다.
    """
    text = sep.join(line.replace("\n", " ") for line in header_lines(deck))
    if quote == "aedt":
        return text.replace("\\", "/").replace("'", '"')
    if quote == "xml":
        return escape(text)
    return text


# 정의판(템플릿)이 같은 줄을 쓰게 넘긴다 — `matcore/export/__init__.py` 의
# `_register_template_blocks` 와 같은 자리다(이 모듈이 읽힐 때 붙는다).
template.register_block(
    "notes_line",
    lambda deck, prefix="", suffix="", quote="plain", sep=" / ": [
        f"{prefix}{notes_text(deck, quote=str(quote), sep=str(sep))}{suffix}"
    ],
)
template.register_block(
    "header_lines",
    lambda deck, prefix="": [f"{prefix}{line}" for line in header_lines(deck)],
)


def conductivity(deck: Deck) -> tuple[float | None, str | None]:
    """전기전도율과 **옮겼다는 말**. 저항률만 있으면 σ = 1/ρ."""
    sigma = deck.number("electrical", "conductivity")
    if sigma is not None:
        return sigma, None
    rho = deck.number("electrical", "resistivity")
    if rho is not None and rho > 0:
        return 1 / rho, "전기전도율이 카드에 없어 체적저항률에서 σ = 1/ρ 로 옮겼습니다."
    return None, None


def resistivity(deck: Deck) -> tuple[float | None, str | None]:
    """체적저항률과 **옮겼다는 말**. 전도율만 있으면 ρ = 1/σ."""
    rho = deck.number("electrical", "resistivity")
    if rho is not None:
        return rho, None
    sigma = deck.number("electrical", "conductivity")
    if sigma is not None and sigma > 0:
        return 1 / sigma, "체적저항률이 카드에 없어 전기전도율에서 ρ = 1/σ 로 옮겼습니다."
    return None, None


def frequency_series(deck: Deck, column: str) -> list[tuple[float, float]]:
    """전기 블록의 주파수 표에서 한 열 — 주파수 순. **같은 주파수가 둘이면 멈춘다** — 솔버의
    구간 선형 표는 x 가 늘기만 해야 하고, 겹친 점은 어느 값이 이기는지 솔버마다 다르다."""
    points = sorted(
        (float(row["frequency"]), float(row[column]))
        for row in deck.rows("electrical")
        if isinstance(row.get("frequency"), int | float)
        and isinstance(row.get(column), int | float)
    )
    if len({at for at, _ in points}) != len(points):
        raise ExportError(
            f"전기 · 전자기 물성의 주파수 표({column})에 같은 주파수가 두 번 있습니다 — "
            "표는 주파수가 늘기만 해야 합니다."
        )
    return points


#: (칸, 이름) — 주파수를 타는 전자기 값. 노트에 이름이 그대로 들어간다.
EM_SLOTS = (
    ("relative_permittivity", "비유전율"),
    ("loss_tangent", "유전손실"),
    ("relative_permeability", "비투자율"),
)

_EMPTY = (
    "{label} 로 낼 전자기 값이 카드에 없습니다 — 비유전율 · 유전손실 · 비투자율 · "
    "전기전도율(또는 체적저항률) 가운데 하나는 있어야 합니다."
)

_TEMPERATURE_TABLES = (
    "열물성 · 탄성의 온도 표는 싣지 않았습니다 — 기준 값(첫 줄) 하나씩입니다. 온도 의존이 "
    "필요하면 솔버에서 따로 답니다."
)


def _has_em(deck: Deck) -> bool:
    return any(
        deck.number("electrical", key) is not None
        for key in (*(slot for slot, _ in EM_SLOTS), "conductivity", "resistivity")
    )


def _temperature_tables(deck: Deck) -> bool:
    return len(deck.rows("thermal")) > 1 or len(deck.rows("elastic")) > 1


# ── Ansys Electronics Desktop ────────────────────────────────────────────────

#: 카드 칸 → AEDT 재료 속성 이름(PyAEDT `MatProperties.aedtname`).
_AEDT_EM = (
    ("relative_permittivity", "permittivity"),
    ("loss_tangent", "dielectric_loss_tangent"),
    ("relative_permeability", "permeability"),
)
_AEDT_OTHER = (
    ("thermal", "thermal_conductivity", "thermal_conductivity"),
    ("elastic", "density", "mass_density"),
    ("thermal", "specific_heat", "specific_heat"),
    ("thermal", "thermal_expansion", "thermal_expansion_coefficient"),
    ("elastic", "youngs_modulus", "youngs_modulus"),
    ("elastic", "poisson_ratio", "poissons_ratio"),
)


@register_renderer(
    key="aedt",
    label="Ansys Electronics Desktop (전자기 재료)",
    extension="amat",
    describe=(
        "HFSS · Maxwell · Q3D · Icepak 가 읽는 재료 라이브러리(.amat) — 비유전율 · 유전손실 · "
        "비투자율 · 전기전도율(주파수 표는 pwl 데이터셋)과 열 · 구조 물성. 단위는 SI 고정."
    ),
    keywords=("$begin 'MaterialDef'",),
    needs=(
        Need("electrical"),
        Need("thermal", optional=True),
        Need("elastic", optional=True),
    ),
    fixed_units=SI,
)
def render_aedt(deck: Deck) -> Rendered:
    """AEDT 재료 하나. **주파수 표가 있으면 `pwl($데이터셋,Freq)` 로** — AEDT 가 주파수마다
    구간 선형으로 읽는다(HFSS 의 Dk/Df 표 재료가 이 모양이다). 표가 없으면 값 하나다.

    데이터셋 이름은 재료 번호로 짓는다(`$MNX<번호>_permittivity`) — 재료 이름의 `-` 는 식에서
    빼기로 읽히고, 같은 프로젝트에 재료가 여럿 들어가도 이름이 안 겹쳐야 한다.
    """
    if not _has_em(deck):
        raise ExportError(_EMPTY.format(label="AEDT 재료"))
    name = deck.name
    notes: list[str] = []
    physics = ["'Electromagnetic'"]
    if (
        deck.number("thermal", "thermal_conductivity") is not None
        or deck.number("thermal", "specific_heat") is not None
    ):
        physics.append("'Thermal'")
    if deck.number("elastic", "youngs_modulus") is not None:
        physics.append("'Structural'")
    lines = [
        f"$begin '{name}'",
        "\t$begin 'MaterialDef'",
        f"\t\t$begin '{name}'",
        "\t\t\tCoordinateSystemType='Cartesian'",
        "\t\t\tBulkOrSurfaceType=1",
        "\t\t\t$begin 'PhysicsTypes'",
        f"\t\t\t\tset({', '.join(physics)})",
        "\t\t\t$end 'PhysicsTypes'",
        "\t\t\t$begin 'AttachedData'",
        "\t\t\t\t$begin 'MatNotesData'",
        "\t\t\t\t\tproperty_data='notes_data'",
        f"\t\t\t\t\tNotes='{notes_text(deck, quote='aedt')}'",
        "\t\t\t\t$end 'MatNotesData'",
        "\t\t\t$end 'AttachedData'",
    ]
    datasets: list[tuple[str, list[tuple[float, float]]]] = []
    for (key, prop), (_, label) in zip(_AEDT_EM, EM_SLOTS, strict=True):
        points = frequency_series(deck, key)
        if len(points) >= 2:
            dataset = f"$MNX{deck.solver_id}_{prop}"
            lines.append(f"\t\t\t{prop}='pwl({dataset},Freq)'")
            datasets.append((dataset, points))
            continue
        value = deck.number("electrical", key)
        if value is None:
            continue
        lines.append(f"\t\t\t{prop}='{_g(value)}'")
        at = deck.number("electrical", f"{key}_frequency_hz")
        if at is not None:
            notes.append(
                f"{label}은 {at:.6g} Hz 의 값 하나로 실었습니다 — AEDT 는 모든 주파수에서 "
                "이 값을 씁니다."
            )
    sigma, said = conductivity(deck)
    if sigma is not None:
        lines.append(f"\t\t\tconductivity='{_g(sigma)}'")
        if said:
            notes.append(said)
    for block, key, prop in _AEDT_OTHER:
        value = deck.number(block, key)
        if value is not None:
            lines.append(f"\t\t\t{prop}='{_g(value)}'")
    if _temperature_tables(deck):
        notes.append(_TEMPERATURE_TABLES)
    lines.extend([f"\t\t$end '{name}'", "\t$end 'MaterialDef'"])
    if datasets:
        lines.append("\t$begin 'RefDatasets'")
        for dataset, points in datasets:
            xs = ", ".join(f"'{_g(at)}'" for at, _ in points)
            ys = ", ".join(f"'{_g(value)}'" for _, value in points)
            lines.extend(
                [
                    f"\t\t$begin '{dataset}'",
                    "\t\t\tDimUnits[2: 'Hz', '']",
                    f"\t\t\tX({xs})",
                    f"\t\t\tY({ys})",
                    f"\t\t$end '{dataset}'",
                ]
            )
        lines.append("\t$end 'RefDatasets'")
    lines.append(f"$end '{name}'")
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


# ── CST Studio Suite ─────────────────────────────────────────────────────────


def _dispersion(deck: Deck) -> list[tuple[float, float, float]]:
    """CST 분산 맞춤에 넘길 점 — **비유전율과 유전손실이 같은 주파수에 둘 다 있는 줄만.**
    `Real_Tand` 는 한 줄에 둘을 받는다. 한쪽만 있는 줄을 다른 쪽의 값으로 채우면 지어낸다."""
    points = sorted(
        (
            float(row["frequency"]),
            float(row["relative_permittivity"]),
            float(row["loss_tangent"]),
        )
        for row in deck.rows("electrical")
        if isinstance(row.get("frequency"), int | float)
        and isinstance(row.get("relative_permittivity"), int | float)
        and isinstance(row.get("loss_tangent"), int | float)
    )
    if len({at for at, _, _ in points}) != len(points):
        raise ExportError(
            "전기 · 전자기 물성의 주파수 표에 같은 주파수가 두 번 있습니다 — "
            "표는 주파수가 늘기만 해야 합니다."
        )
    return points


@register_renderer(
    key="cst",
    label="CST Studio Suite (전자기 재료)",
    extension="mtd",
    describe=(
        "CST 재료 라이브러리(.mtd) — 비유전율 · 유전손실(주파수 표는 분산 맞춤 점으로) · "
        "비투자율 · 전기전도율과 밀도 · 열 · 구조 물성. 단위는 파일에 SI 로 선언한다."
    ),
    keywords=("[Definition]", ".Create"),
    needs=(
        Need("electrical"),
        Need("thermal", optional=True),
        Need("elastic", optional=True),
    ),
    fixed_units=SI,
)
def render_cst(deck: Deck) -> Rendered:
    """CST 재료 하나. **분산은 CST 가 맞춘다** — 주파수별 (εr, tan δ) 점을 넘기면 CST 가 Nth
    Order 모형을 맞춰 시간 영역 해석에 쓴다. 맞춘 식이 점을 따르는지는 CST 의 맞춤 결과 창이
    보여 준다 — 여기서 맞추지 않는다.
    """
    if not _has_em(deck):
        raise ExportError(_EMPTY.format(label="CST 재료"))
    notes: list[str] = []
    eps = deck.number("electrical", "relative_permittivity")
    tan = deck.number("electrical", "loss_tangent")
    mu = deck.number("electrical", "relative_permeability")
    # 표는 **먼저 다 읽는다** — 겹친 주파수는 어느 표에 있든 쓰기 전에 멈춘다.
    series = {key: frequency_series(deck, key) for key, _ in EM_SLOTS}
    points = _dispersion(deck)
    lines = [
        "[Definition]",
        '     .FrqType "all"',
        '     .Type "Normal"',
        '     .MaterialUnit "Frequency", "Hz"',
        '     .MaterialUnit "Geometry", "m"',
        '     .MaterialUnit "Time", "s"',
        '     .MaterialUnit "Temperature", "Kelvin"',
    ]
    if eps is not None:
        lines.append(f'     .Epsilon "{_g(eps)}"')
    if mu is not None:
        lines.append(f'     .Mu "{_g(mu)}"')
    sigma, said = conductivity(deck)
    if sigma is not None:
        lines.append(f'     .Sigma "{_g(sigma)}"')
        if said:
            notes.append(said)
    if tan is not None and len(points) < 2:
        at = deck.number("electrical", "loss_tangent_frequency_hz")
        lines.append(f'     .TanD "{_g(tan)}"')
        if at is not None:
            lines.append(f'     .TanDFreq "{_g(at)}"')
        lines.extend(['     .TanDGiven "True"', '     .TanDModel "ConstTanD"'])
        if at is None:
            notes.append(
                "유전손실을 잰 주파수가 카드에 없어 .TanDFreq 를 안 적었습니다 — CST 는 그 "
                "손실을 어느 주파수에 맞출지 모르고 기본값을 씁니다."
            )
    lines.append('     .DispModelEps "None"')
    if len(points) >= 2:
        lines.extend(
            [
                '     .DispersiveFittingSchemeEps "Nth Order"',
                '     .MaximalOrderNthModelFitEps "10"',
                '     .ErrorLimitNthModelFitEps "0.1"',
                '     .UseOnlyDataInSimFreqRangeNthModelEps "False"',
                '     .DispersiveFittingFormatEps "Real_Tand"',
            ]
        )
        lines.extend(
            "     .AddDispersionFittingValueEps "
            f'"{_g(at)}", "{_g(value)}", "{_g(loss)}", "1.0"'
            for at, value, loss in points
        )
        lines.append('     .UseGeneralDispersionEps "True"')
        notes.append(
            f"주파수 {len(points)}점의 비유전율 · 유전손실을 CST 의 분산 맞춤(Nth Order)으로 "
            "넘겼습니다 — 맞춘 식이 점을 따르는지는 CST 의 맞춤 결과 창에서 봅니다."
        )
    elif len(series["relative_permittivity"]) >= 2 or len(series["loss_tangent"]) >= 2:
        notes.append(
            "비유전율 · 유전손실이 같은 주파수에 함께 있는 점이 둘이 안 돼 분산 맞춤을 안 "
            "적었습니다 — 값 하나씩입니다."
        )
    if len(series["relative_permeability"]) >= 2:
        notes.append(
            "비투자율의 주파수 표는 싣지 않았습니다 — 값 하나(가장 낮은 주파수)입니다."
        )
    density = deck.number("elastic", "density")
    if density is not None:
        lines.append(f'     .Rho "{_g(density)}"')
    k = deck.number("thermal", "thermal_conductivity")
    cp = deck.number("thermal", "specific_heat")
    if k is not None or cp is not None:
        lines.append('     .ThermalType "Normal"')
    if k is not None:
        lines.append(f'     .ThermalConductivity "{_g(k)}"')
    if cp is not None:
        lines.append(f'     .SpecificHeat "{_g(cp)}", "J/K/kg"')
    modulus = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    if modulus is not None and poisson is not None:
        # CST 의 영률 칸은 kN/mm²(= GPa) 다 — 금 재료 파일이 78 이다.
        lines.extend(
            [
                '     .MechanicsType "Isotropic"',
                f'     .YoungsModulus "{_g(units.from_si(modulus, "GPa"))}"',
                f'     .PoissonsRatio "{_g(poisson)}"',
            ]
        )
    alpha = deck.number("thermal", "thermal_expansion")
    if alpha is not None:
        # 1e-6/K 로 적힌다 — 금 재료 파일이 14 다.
        lines.append(f'     .ThermalExpansionRate "{_g(units.from_si(alpha, "ppm/K"))}"')
    if _temperature_tables(deck):
        notes.append(_TEMPERATURE_TABLES)
    lines.extend(
        [
            '     .Colour "0.5", "0.5", "0.5"',
            '     .Wireframe "False"',
            '     .Transparency "0"',
            "     .Create",
            "",
            "[Type]",
            "FrqType: all",
            "Normal",
            "",
            "[Description]",
            *header_lines(deck),
        ]
    )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))


# ── Simcenter Flotherm (FloXML) ──────────────────────────────────────────────


def _conductivity_curve(deck: Deck) -> list[tuple[float, float]]:
    """열전도율의 온도 표 — 온도 순. 두 점이 안 되면 값 하나로 적는다."""
    return sorted(
        (float(row["temperature"]), float(row["thermal_conductivity"]))
        for row in deck.rows("thermal")
        if isinstance(row.get("temperature"), int | float)
        and isinstance(row.get("thermal_conductivity"), int | float)
    )


@register_renderer(
    key="flotherm",
    label="Simcenter Flotherm (전자 냉각 재료)",
    extension="xml",
    describe=(
        "FloXML 재료 · 표면 — 밀도 · 비열 · 열전도율 · 전기 저항률(줄 발열) · 방사율, 값 "
        "하나씩. 프로젝트로 읽어 재료를 라이브러리에 저장한다. SI."
    ),
    keywords=("<isotropic_material_att>", "</xml_case>"),
    needs=(
        Need("thermal", values=("thermal_conductivity", "specific_heat")),
        Need("elastic", values=("density",)),
        Need("electrical", optional=True),
        Need("optical", optional=True),
    ),
    media_type="application/xml; charset=utf-8",
    fixed_units=SI,
)
def render_flotherm(deck: Deck) -> Rendered:
    """FloXML 프로젝트 하나에 재료 하나 — 형상은 비어 있다(`<geometry />`).

    Flotherm 은 재료를 라이브러리 파일로 받는 길이 없어 FloXML 프로젝트로 읽은 뒤 재료를
    라이브러리에 저장한다(Siemens 의 재료 자동화 예제가 이 길이다). 방사율은 재료가 아니라
    **표면** 속성이라 `surface_att` 를 하나 만들어 재료에 단다.

    ## 온도 표는 싣지 않는다 (2026-10-03, 공개 자료 대조)

    FloXML 의 온도 단위는 **원소마다 다르다.** 열전도 온도 의존(`tref`)과 주변 온도는
    켈빈이다 — Siemens 의 재료 · IGBT 매크로가 사람이 적은 °C 에 273.15 를 더해 쓴다. 그런데
    제어 곡선의 온도는 °C 로 보이고(공식 예제 50 · 75 · 100 · 125), 제3자는 고정 온도가 °C
    라고 적었다. **열전도 곡선(`conductivity_curve`)의 온도와 전기 저항률의 기준 온도
    (`t_ref`)는 공개 근거가 없다** — 매크로는 그 값을 바꾸지 않고 넘기고, 예제는 0 뿐이다.
    저항률 계수(`coeff`)가 상대값(1/K)인지 절대값(Ω·m/K)인지도 모른다 — 열전도 쪽 계수는
    절대값(W/(m·K²))이다.

    틀리면 조용히 틀린다 — 곡선이 273 K 밀리거나, 구리의 저항률이 10⁸ 배가 된다. 그래서
    **값 하나(기준 값)만 적고 표 · 계수는 싣지 않았다고 말한다.** 온도 의존이 필요하면
    Flotherm 화면에서 넣는다. 처음에는 재료 스프레드시트의 열 머리 「Reference Temperature
    (deg C)」 만 보고 °C 로 적었다 — 매크로가 더하는 273.15 를 못 봤다.
    """
    name = deck.name
    density = deck.number("elastic", "density")
    cp = deck.number("thermal", "specific_heat")
    k = deck.number("thermal", "thermal_conductivity")
    assert density is not None and cp is not None and k is not None  # needs 가 막는다
    notes: list[str] = []
    material = [
        "         <isotropic_material_att>",
        f"            <name>{name}</name>",
        f"            <density>{_g(density)}</density>",
        f"            <specific_heat>{_g(cp)}</specific_heat>",
        "            <input_method>single_value</input_method>",
        f"            <conductivity>{_g(k)}</conductivity>",
    ]
    if len(_conductivity_curve(deck)) >= 2:
        notes.append(
            "열전도율의 온도 표는 싣지 않았습니다 — FloXML 곡선의 온도 단위(°C · K)를 "
            "공개 자료로 확인하지 못했습니다. 기준 값(첫 줄) 하나를 적었습니다. 온도 의존이 "
            "필요하면 Flotherm 화면에서 표로 넣으세요."
        )

    rho, said = resistivity(deck)
    tcr = deck.number("electrical", "resistivity_temperature_coefficient")
    if rho is not None:
        if said:
            notes.append(said)
        material.extend(
            [
                "            <electrical_resistivity>",
                "               <type>constant</type>",
                f"               <resistivity_value>{_g(rho)}</resistivity_value>",
                "            </electrical_resistivity>",
            ]
        )
    if tcr is not None:
        notes.append(
            "저항온도계수는 싣지 않았습니다 — FloXML 저항률 계수가 상대값(1/K)인지 절대값"
            "(Ω·m/K)인지, 기준 온도의 단위가 무엇인지 공개 자료로 확인하지 못했습니다. "
            "저항률은 상수로 적었습니다."
        )

    emissivity = deck.number("optical", "emissivity")
    if emissivity is not None:
        if not 0 <= emissivity <= 1:
            raise ExportError(
                f"방사율이 0~1 밖입니다({emissivity:g}) — 값이나 단위(%)를 확인하세요."
            )
        material.append(f"            <surface>{name}_surface</surface>")
    material.extend(
        [
            f"            <notes>{notes_text(deck, quote='xml')}</notes>",
            "         </isotropic_material_att>",
        ]
    )
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>',
        "<xml_case>",
        f"   <name>{name}</name>",
        "   <attributes>",
        "      <materials>",
        *material,
        "      </materials>",
    ]
    if emissivity is not None:
        lines.extend(
            [
                "      <surfaces>",
                "         <surface_att>",
                f"            <name>{name}_surface</name>",
                f"            <emissivity>{_g(emissivity)}</emissivity>",
                "         </surface_att>",
                "      </surfaces>",
            ]
        )
    lines.extend(["   </attributes>", "   <geometry />", "</xml_case>"])
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
