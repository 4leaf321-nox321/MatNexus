"""온도별 소성 표 — 카드 블록과 Abaqus 덱. **중심 코드는 이 확장의 이름을 모른다.**

    블록   `temperature_table` — 온도(K)·진소성변형률·진응력 행. `table` 은 기준
           온도(가장 낮은 묶음) 하나이고 이 블록이 온도 전부를 든다 — 속도 카드의
           `rate_table` 과 같은 나눔이다.
    덱     Abaqus `*PLASTIC` 은 데이터 줄 셋째 열이 온도다. 온도별로 행을 나눠 싣고
           Abaqus 가 온도 사이를 보간한다. Johnson-Cook m 은 요약이라 주석으로만.

LS-DYNA 는 `*MAT_106` + `*DEFINE_TABLE` 이 필요한데 카드 다섯 장의 자리를 검증할
실측이 없어 아직 안 낸다 — 지어내지 않는다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.export import (
    MIN_POINTS,
    Deck,
    ExportError,
    Need,
    Rendered,
    _elastic_lines,
    _free,
    _header,
    _thermal_lines,
    prepare,
    register_renderer,
)
from matcore.registry import Produced

TEMPERATURE_TABLE = register_block(
    BlockSpec(
        key="temperature_table",
        label="온도별 소성 표",
        help=(
            "온도마다 진소성변형률·진응력의 표. **`table` 은 기준 온도(가장 낮은 것) "
            "하나이고, 이 블록이 나머지 온도를 든다** — 온도 의존을 안 받는 솔버는 "
            "`table` 만 읽고, 받는 솔버는 이 표를 온도별로 나눠 싣는다(Abaqus *PLASTIC "
            "온도 열). 행은 온도 순, 같은 온도 안에서 변형률 순이다."
        ),
        produces=(
            Produced(
                key="source",
                label="표를 만든 방법",
                si_unit="1",
                help=(
                    "`temperature_family` — 온도 묶음별로 시편 곡선을 공통 구간에 "
                    "보간해 평균한 것."
                ),
            ),
            Produced(key="temperature_count", label="온도 묶음 수", si_unit="1"),
            Produced(
                key="reference_temperature",
                label="기준 온도",
                si_unit="K",
                help="응력비의 분모가 되는 온도. 가장 낮은 묶음이다.",
            ),
            Produced(
                key="model",
                label="온도 연화 식",
                si_unit="1",
                help="`none`·`johnson_cook`. 표와 별개로, 요약한 식이다.",
            ),
            Produced(key="melt_temperature", label="녹는점", si_unit="K"),
            Produced(key="jc_m", label="Johnson-Cook m", si_unit="1"),
            Produced(key="model_r_squared", label="식의 R²", si_unit="1"),
            # 연화 기울기(Pa/K)는 묶음 결과에만 둔다 — 덱 단위계 표가 그 단위를 모르고,
            # 덱에 실을 값도 아니다(표가 잰 것이고 기울기는 요약이다).
        ),
        rows=(
            Produced(key="temperature", label="온도", si_unit="K"),
            Produced(key="plastic_strain", label="진소성변형률", si_unit="1"),
            Produced(key="true_stress", label="진응력", si_unit="Pa"),
        ),
        order=36,
        kind_priority=1,
    )
)


@register_renderer(
    key="abaqus_temperature",
    label="Abaqus (온도 의존)",
    extension="inp",
    suffix="_temperature",
    describe="*ELASTIC + 온도별 *PLASTIC — 온도 의존 소성 표(데이터 줄 셋째 열이 온도).",
    keywords=("*MATERIAL", "*ELASTIC", "*PLASTIC"),
    needs=(
        Need("elastic", values=("youngs_modulus", "poisson_ratio")),
        Need("elastic", values=("density",), optional=True),
        Need("thermal", optional=True),
        # 온도가 하나뿐이면 이 덱을 낼 이유가 없다 — 그건 `abaqus` 가 한다.
        Need(
            "temperature_table",
            values=("temperature_count",),
            at_least=(("temperature_count", 2),),
            rows_min=2 * MIN_POINTS,
        ),
    ),
)
def render_abaqus_temperature(deck: Deck) -> Rendered:
    """Abaqus 온도 의존 소성 — **`*PLASTIC` 한 벌, 행마다 온도.**

    Abaqus `*PLASTIC` 데이터 줄은 `응력, 소성변형률, 온도` 다. 온도 순으로 이어 적으면
    Abaqus 가 온도 사이를 보간한다. 표 밖 온도는 가장자리 값을 쓴다. `*ELASTIC` 은
    온도 하나의 값이다 — 온도별 탄성계수는 재지 않았으므로 그렇게 적는다.
    """
    youngs = deck.number("elastic", "youngs_modulus")
    poisson = deck.number("elastic", "poisson_ratio")
    density = deck.number("elastic", "density")

    by_temperature: dict[float, list[tuple[float, float]]] = {}
    for row in deck.rows("temperature_table"):
        try:
            temperature = float(row["temperature"])
            by_temperature.setdefault(temperature, []).append(
                (float(row["plastic_strain"]), float(row["true_stress"]))
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ExportError(
                "온도별 소성 표의 행에 온도·변형률·응력이 다 있어야 합니다."
            ) from exc
    if len(by_temperature) < 2:
        raise ExportError(
            "온도가 하나뿐입니다. 온도 의존 덱은 둘 이상의 온도가 있어야 합니다 — "
            "하나면 Abaqus 형식을 쓰세요."
        )

    notes: list[str] = [
        "*ELASTIC 은 온도 하나의 값입니다 — 온도별 탄성계수는 재지 않았습니다."
    ]
    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    temperatures = sorted(by_temperature)
    lines.append(
        f"** Temperature dependent plasticity: {len(temperatures)} temperatures "
        f"({_free(temperatures[0])} ~ {_free(temperatures[-1])} K), tabular, "
        f"interpolated by Abaqus"
    )
    summary = deck.values("temperature_table")
    if summary.get("model") == "johnson_cook":
        m = deck.number("temperature_table", "jc_m")
        melt = deck.number("temperature_table", "melt_temperature")
        if m is not None:
            lines.append(
                "** Johnson-Cook thermal softening summary (not used by this deck): "
                f"m={_free(m)}" + (f", Tmelt={_free(melt)} K" if melt is not None else "")
            )
    lines.append(
        "** *ELASTIC is a single-temperature value (modulus not measured per temperature)"
    )
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
    lines.append("*PLASTIC, HARDENING=ISOTROPIC")
    for temperature in temperatures:
        points, said = prepare(tuple(sorted(by_temperature[temperature])))
        notes.extend(f"온도 {temperature:.1f} K: {line}" for line in said)
        lines.extend(
            f"{_free(stress)}, {_free(strain)}, {_free(temperature)}"
            for strain, stress in points
        )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
