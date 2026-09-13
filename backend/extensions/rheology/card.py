"""유변 카드 블록과 Abaqus `*VISCOSITY` 덱.

    블록  `rheology` — 식·계수(행)·적합도·영전단 점도. 초탄성 블록과 같은 모양이다:
          계수는 식마다 이름과 단위가 달라 행이 자기 단위를 든다.
    덱    Abaqus `*VISCOSITY, DEFINITION=CROSS | CARREAU-YASUDA`. Abaqus 의 Cross 는
          지수를 `1-n` 으로 받으므로 우리 m 을 n = 1 - m 으로 돌려 적는다 — 그대로
          적으면 박화가 반대로 간다. Carreau 는 Carreau-Yasuda 의 a=2 다.

밀도는 있으면 `*DENSITY` 로 함께 낸다(CEL·유동 해석에 필요). 탄성은 안 낸다 —
유체 카드에 `*ELASTIC` 을 넣으면 솔버가 고체로 읽는다.
"""

from __future__ import annotations

from matcore.cards import BlockSpec, register_block
from matcore.export import (
    Deck,
    ExportError,
    Need,
    Rendered,
    _free,
    _header,
    register_renderer,
)
from matcore.registry import Produced

RHEOLOGY = register_block(
    BlockSpec(
        key="rheology",
        label="유변",
        help=(
            "점도-전단율 곡선에 맞춘 식과 계수. **로그 잔차로 맞춘 값이다** — 점도가 "
            "수십 배 내려가는 곡선이라 선형 RMSE 로는 박화 구간이 안 보인다."
        ),
        produces=(
            Produced(key="label", label="식", si_unit="1", help="Cross·Carreau 중 고른 것."),
            Produced(
                key="zero_shear_viscosity",
                label="영전단 점도",
                si_unit="Pa.s",
                help="전단율 → 0 의 점도. 식이 달라도 이 값은 비슷해야 한다.",
            ),
            Produced(
                key="onset_shear_rate",
                label="박화 시작 전단율",
                si_unit="1/s",
                help="1/lambda — 점도가 꺾이기 시작하는 전단율.",
            ),
            Produced(key="relative_rmse", label="상대 RMSE", si_unit="1"),
            Produced(key="r_squared", label="R²", si_unit="1"),
            Produced(key="max_residual", label="최대 잔차", si_unit="Pa.s"),
            Produced(key="strain_min", label="적합 구간 시작", si_unit="1/s", help="전단율."),
            Produced(key="strain_max", label="적합 구간 끝", si_unit="1/s", help="전단율."),
        ),
        rows=(
            Produced(key="name", label="파라미터", si_unit="1"),
            Produced(key="value", label="값", si_unit="1", help="행이 자기 단위를 든다."),
        ),
        order=40,
        kind_priority=2,
    )
)


@register_renderer(
    key="abaqus_viscosity",
    label="Abaqus (점도)",
    extension="inp",
    suffix="_viscosity",
    describe="*VISCOSITY, DEFINITION=CROSS | CARREAU-YASUDA — 전단 박화 점도.",
    keywords=("*MATERIAL", "*VISCOSITY"),
    needs=(
        Need("rheology", values=("label",), rows_min=4),
        Need("elastic", values=("density",), optional=True),
    ),
)
def render_abaqus_viscosity(deck: Deck) -> Rendered:
    """Abaqus `*VISCOSITY` — 식마다 데이터 줄의 자리가 다르다.

    CROSS            eta_0, eta_inf, lambda, n     (Abaqus: (lambda*rate)^(1-n))
    CARREAU-YASUDA   eta_0, eta_inf, lambda, n, a  (a=2 가 Carreau)
    """
    values = deck.values("rheology")
    family = str(values.get("family") or "")
    parameters = {
        str(row["name"]): float(row["value"])
        for row in deck.rows("rheology")
        if "name" in row and "value" in row
    }
    density = deck.number("elastic", "density")
    notes: list[str] = []

    lines = _header(deck, "**")
    lines.append(f"** Consistent units: {deck.units.declaration}")
    lines.append(f"*MATERIAL, NAME={deck.name}")
    if density is not None:
        lines.append("*DENSITY")
        lines.append(f"{_free(density)},")
    else:
        notes.append(
            "밀도가 카드에 없어 *DENSITY 를 뺐습니다 — 유동 해석에는 밀도가 필요합니다."
        )

    try:
        eta0, eta_inf, lam = parameters["eta_0"], parameters["eta_inf"], parameters["lambda"]
    except KeyError as exc:
        raise ExportError("유변 계수(eta_0·eta_inf·lambda)가 카드에 없습니다.") from exc

    if family == "cross":
        m = parameters.get("m")
        if m is None:
            raise ExportError("Cross 계수 m 이 카드에 없습니다.")
        # Abaqus Cross: eta = eta_inf + (eta_0 - eta_inf) / (1 + (lambda*rate)^(1-n)).
        n = 1.0 - m
        lines.append(f"** Cross: our exponent m={_free(m)} -> Abaqus n = 1 - m = {_free(n)}")
        lines.append("*VISCOSITY, DEFINITION=CROSS")
        lines.append(f"{_free(eta0)}, {_free(eta_inf)}, {_free(lam)}, {_free(n)}")
    elif family == "carreau":
        n = parameters.get("n")
        if n is None:
            raise ExportError("Carreau 계수 n 이 카드에 없습니다.")
        lines.append("** Carreau = Carreau-Yasuda with a = 2")
        lines.append("*VISCOSITY, DEFINITION=CARREAU-YASUDA")
        lines.append(f"{_free(eta0)}, {_free(eta_inf)}, {_free(lam)}, {_free(n)}, 2.0")
    else:
        raise ExportError(
            f"'{family or '?'}' 은 Abaqus *VISCOSITY 로 낼 수 없는 식입니다 — "
            "Cross·Carreau 만."
        )
    return Rendered(text="\n".join(lines) + "\n", notes=tuple(notes))
