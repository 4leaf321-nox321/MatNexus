"""선언 물성 카드의 **조립기** — 재료에 적어 둔 값이 카드 블록이 되는 길.

시험 없이 만드는 카드(ADR 0016)가 이 함수들로 블록을 짓는다. 2026-09-28 에 카드 모듈
(`fitting/routes.py`)에서 여기로 옮겼다 — **문헌 덱도 같은 조립기를 쓰게 하려고**다.
문헌 재료의 값은 사내 물성 매핑을 거쳐 「반영했다면 적혔을」 선언 물성이 되고
(`shared/literature_material`), 그 가상 재료가 이 조립기를 지난다. 조립기가 둘이면
같은 문헌 값이 카드로 갈 때와 덱으로 갈 때 다른 모양이 된다.

`shared` 에 있는 이유: 카드(fitting)와 문헌 덱(catalog → `shared/litdeck`)이 함께 쓰는데,
모듈끼리는 `models` 말고 직접 못 부른다(`tests/architecture`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.materials.models import Material, Sample
from app.shared import declared_approval, display, property_names, tiers
from matcore import cards, synth


@dataclass(frozen=True)
class Inherited:
    """물려받은 값 하나와 **어디서 왔는지.**

    카드는 불변이라 값을 참조로 두면 안 된다 — 재료의 밀도를 고치는 순간 이미
    확정한 카드가 조용히 달라진다. 그래서 값은 복사한다. 대신 출처를 함께
    복사한다: 덱만 받은 사람이 7850 을 보고 그것이 실측인지 관례값인지 물을 때,
    답할 데가 있어야 한다.
    """

    value: float | None
    source: str
    """`sample` | `material` | `manual` | `measured` | `conflict` | `missing`."""
    detail: str | None = None
    """사람이 읽는 한 줄. 갈렸으면 무엇과 무엇이 갈렸는지 여기 적는다."""


def inherit_density(
    material: Material, samples: list[Sample], override: float | None
) -> Inherited:
    """시료 실측 → 재료 공칭 순. **로트마다 다를 수 있는 값이다.**

    강판은 로트가 달라도 7850 이지만 복합재·발포재·소결재는 실제로 다르다.
    그래서 실측이 있으면 그것을 먼저 쓴다.
    """
    if override is not None:
        return Inherited(override, "manual", "직접 입력한 값입니다.")

    measured = {s.density_si for s in samples if s.density_si is not None}
    if len(measured) == 1:
        value = next(iter(measured))
        return Inherited(
            value, "sample", f"시료에서 잰 값입니다 ({display.density_text(value)})."
        )
    if len(measured) > 1:
        # **말없이 하나 고르지 않는다.** 어느 로트의 값을 썼는지 모르는 카드는
        # 근거가 없는 것과 같다.
        joined = ", ".join(display.density_text(v) for v in sorted(measured))
        return Inherited(
            None,
            "conflict",
            f"시료마다 밀도가 다릅니다({joined}) — 쓸 값을 직접 넣으세요.",
        )
    if material.density_si is not None:
        return Inherited(
            material.density_si,
            "material",
            f"재료의 공칭값입니다 ({display.density_text(material.density_si)}).",
        )
    return Inherited(None, "missing", "재료에도 시료에도 밀도가 없습니다.")


def declared(material: Material, item: str) -> Inherited:
    """재료에 **사람이 적어 둔** 물성 하나(ADR 0016).

    시험이 안 주는 값들이다 — 탄성계수는 시험을 안 한 재료에서, 열물성은
    언제나 여기서 온다.

    출처를 `declared:<어디서>` 로 남긴다. `measured` 와 한 글자도 안 겹쳐야
    한다 — 덱을 받은 사람이 **잰 값인지 적은 값인지** 구별할 수 있어야 하고,
    그 구별이 이 저장소가 카드에 근거를 박는 이유 전부다. 자료 관리자가 승인한
    값이면 `+approved` 가 붙는다(ADR 0049) — 카드는 만들 때의 승인을 든다.
    """
    row = declared_row(material, item)
    if row is None:
        return Inherited(None, "missing", f"재료에 '{item}' 이 없습니다.")
    where = str(row.get("source") or "declared")
    reference = str(row.get("reference") or "").strip()
    points = declared_points(row)
    # **대푯값은 첫 점이다.** 온도를 안 타는 값이면 그것뿐이고, 표라면 가장 낮은
    # 온도(대개 상온)다 — 표 자체는 블록의 `rows` 로 따로 실린다.
    spread = (
        f" (온도 {len(points)}점: "
        f"{celsius(points[0]['temperature_k'])}~{celsius(points[-1]['temperature_k'])})"
        if len(points) > 1
        else ""
    )
    return Inherited(
        float(points[0]["value_si"]),
        tiers.declared_origin(where, approved=declared_approval.of(row) is not None),
        f"사람이 적은 값입니다 — {reference or '근거 문서 없음'}.{spread}",
    )


def celsius(kelvin: float | None) -> str:
    """섭씨로 적는다. **상온을 298 로 적는 사람은 없다.**

    환산은 `shared/display` 를 거친다. `- 273.15` 를 손으로 적으면 표 바깥에
    정본이 하나 더 생기고, 표를 바꾼 날 이 자리만 옛 값을 낸다 — 화면 쪽에서
    같은 부류를 다섯 군데 걷어냈다.
    """
    return "?" if kelvin is None else display.quantity(kelvin, "degC")


def declared_points(row: dict[str, Any]) -> list[dict[str, Any]]:
    """한 줄이 든 온도-값 점들. 값이 숫자가 아닌 점은 없는 것으로 본다."""
    return [
        point
        for point in (row.get("points") or [])
        if isinstance(point, dict) and isinstance(point.get("value_si"), (int, float))
    ]


def declared_row(material: Material, item: str) -> dict[str, Any] | None:
    """선언 물성 한 줄. 쓸 수 있는 점이 없으면 없는 것으로 본다."""
    for row in material.declared_properties or []:
        if str(row.get("item")) == item and declared_points(row):
            return dict(row)
    return None


#: 선언 물성이 아니라 **재료·시료가 드는 값** — 표의 열이 아니라 상수로 실린다.
#: 푸아송비는 재료 컬럼에서, 밀도는 시료 실측에서 온다.
FROM_RECORD = ("poisson_ratio", "density")


def declared_items(block: str) -> dict[str, str]:
    """이 항목란의 **칸 → 기준정보 항목 이름.** 항목란 선언에서 만든다.

    전에는 이 표를 라우터가 한글 이름으로 들고 있었다(`THERMAL_ITEMS`,
    `declared(material, "탄성계수")`). 그 자리가 둘이 되면서 선언 물성이 카드로
    가는 길이 **여섯 물성에 묶였고**, 새 물성은 이름을 코드에 더해야 했다.
    지금은 칸이 자기 물성 키를 들고(`Produced.property_key`), 키 ↔ 이름의 정본은
    기준정보 씨앗 하나다(`shared/property_names.builtin_item`).

    기본 항목이 아닌 키(확장이 선언한 것)는 여기서 빠진다 — 그쪽은 「사내 항목
    연결」 을 거쳐 `shared/declared_slots` 가 채운다.
    """
    cards.load_builtin()
    try:
        spec = cards.block(block)
    except KeyError:
        return {}
    found: dict[str, str] = {}
    for slot in spec.produces:
        if slot.key in FROM_RECORD:
            continue
        item = property_names.builtin_item(slot.property_key)
        if item:
            found[slot.key] = item
    return found


#: 물려받는 값의 저장 단위. **응답에 값과 함께 실린다** — SI 값만 주면 받는 쪽이
#: 단위를 짐작하고, 밀도에서 그것이 10¹² 배로 틀렸다(2026-09-06·09-11).
INHERITED_UNITS: dict[str, str] = {
    "youngs_modulus": "Pa",
    "poisson_ratio": "1",
    "density": "kg/m3",
    "thermal_expansion": "1/K",
    "specific_heat": "J/(kg.K)",
    "thermal_conductivity": "W/(m.K)",
}


def thermal_block(material: Material) -> dict[str, Any]:
    """선언 물성에서 열물성 블록을 만든다. 셋 다 없으면 빈 dict.

    **하나만 있어도 낸다.** 열팽창만 아는 재료로 열응력 해석은 돌아간다 —
    셋을 다 요구하면 그 재료는 영영 덱이 안 나온다.

    기준 온도는 **값들이 서로 다른 온도에서 왔으면 안 적는다.** 하나를 골라
    적으면 나머지 둘이 그 온도의 값인 것처럼 보인다.
    """
    values: dict[str, Any] = {}
    temperatures: set[float | None] = set()
    for key, item in declared_items("thermal").items():
        found = declared(material, item)
        if found.value is None:
            continue
        values[key] = found.value
        values[f"{key}_source"] = found.source
        # **근거 문서를 카드 안에 복사한다.** 재료의 선언 물성을 나중에 고쳐도
        # 이미 확정한 카드가 무엇을 근거로 했는지는 그대로 남아야 한다 —
        # 값을 복사하면서 근거를 참조로 두면 그 둘이 어긋난다.
        row = declared_row(material, item) or {}
        if row.get("reference"):
            values[f"{key}_reference"] = str(row["reference"])
        # **물성마다 자기 온도를 든다.** 한 통에 모아 두면 「비열을 잰 온도」가
        # 열팽창의 기준 온도로 나가는 일이 생긴다 — 실제로 그랬다(§10.5).
        points = declared_points(row)
        if len(points) == 1 and isinstance(points[0].get("temperature_k"), (int, float)):
            values[f"{key}_temperature"] = float(points[0]["temperature_k"])
            temperatures.add(float(points[0]["temperature_k"]))
        else:
            # 표인 물성은 온도를 하나로 말할 수 없다. **그것을 셈에 넣지 않으면**
            # 나머지 둘이 우연히 같을 때 「전부 그 온도」로 읽힌다.
            temperatures.add(None)

    # 블록 전체의 기준 온도. **전부 한 점이고 그 온도가 같을 때만** 뜻이 있다.
    if values and len(temperatures) == 1 and None not in temperatures:
        values["reference_temperature"] = next(iter(temperatures))
    return values


def item_of(block: str, slot: str) -> str:
    """칸 하나가 받는 기준정보 항목 이름. 없으면 빈 글자 — 그러면 값이 안 실린다.

    **틀린 값이 실리는 것보다 안 실리는 것이 낫다**(항목을 지우거나 이름을 바꾼
    경우가 그렇다).
    """
    return declared_items(block).get(slot, "")


def constants(values: dict[str, Any]) -> dict[str, float]:
    """온도를 안 타는 값들 — 표의 모든 줄에 같이 실린다.

    **푸아송비와 밀도가 그렇다.** 선언 물성이 아니라 재료 컬럼이나 측정에서
    오는데, 표에 안 실으면 `*ELASTIC` 이 줄을 못 만든다 — 한 줄에 `(E, ν, T)`
    가 다 있어야 하기 때문이다.
    """
    return {
        key: float(values[key])
        for key in ("poisson_ratio", "density")
        if isinstance(values.get(key), (int, float))
    }


def temperature_aware(
    block: str, values: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """블록 하나. **표는 온도를 탈 때만 붙는다.**

    한 온도짜리에 표를 붙이면 솔버가 「이 온도에서만 유효」로 읽고, 그 밖에서
    외삽 규칙이 달라진다 — 상수인 재료가 갑자기 온도 의존이 된다.
    """
    if not values:
        return {}
    payload: dict[str, Any] = {"values": values}
    if len(rows) > 1:
        payload["rows"] = rows
    return {block: payload}


def declared_blocks(
    db: Session,
    material: Material,
    poisson_override: float | None,
    density_override: float | None,
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, str, Inherited]]]:
    """적어 둔 값만으로 만들 블록들과 **그 근거 목록.**

    미리보기와 저장이 **같은 함수를 쓴다.** 각자 만들면 화면이 "실린다" 고 한
    값이 안 실리거나 그 반대가 되는데, 그때 사람은 화면을 믿을 근거를 잃는다
    (`FitPreviewOut.elastic` 이 같은 이유로 적합 응답에 실린다).

    밀도는 **시료 실측을 여전히 먼저 본다.** 시험을 안 했어도 시료의 밀도는 잰
    값일 수 있고, 이 경로가 그것을 무시하면 같은 재료가 어느 버튼을 눌렀느냐에
    따라 다른 밀도를 갖는다.
    """
    modulus_item = item_of("elastic", "youngs_modulus")
    stated = declared(material, modulus_item)
    stated_row = declared_row(material, modulus_item)
    poisson = inherit_poisson(material, poisson_override)
    # **지운 시료는 안 본다.** 밀도를 잘못 적어 지운 시료의 값이 카드에
    # 「실측」으로 박히면, 지운 그 값으로 해석을 돌리게 된다.
    samples = list(
        db.scalars(
            select(Sample).where(
                Sample.material_id == material.id, Sample.deleted_at.is_(None)
            )
        )
    )
    density = inherit_density(material, samples, density_override)

    elastic: dict[str, Any] = {
        **(
            {
                "youngs_modulus": stated.value,
                "youngs_modulus_source": stated.source,
                **(
                    {"youngs_modulus_reference": str(stated_row["reference"])}
                    if stated_row and stated_row.get("reference")
                    else {}
                ),
            }
            if stated.value is not None
            else {}
        ),
        **(
            {"poisson_ratio": poisson.value, "poisson_ratio_source": poisson.source}
            if poisson.value is not None
            else {}
        ),
        **(
            {"density": density.value, "density_source": density.source}
            if density.value is not None
            else {}
        ),
    }
    thermal = thermal_block(material)

    found = [
        (key, label, one)
        for key, label, one in (
            ("youngs_modulus", modulus_item, stated),
            ("poisson_ratio", "푸아송비", poisson),
            ("density", "밀도", density),
            *(
                (key, label, declared(material, label))
                for key, label in declared_items("thermal").items()
                if key in thermal
            ),
        )
        if one.value is not None
    ]
    return elastic, thermal, found


#: 합성 소성 표의 재료가 되는 선언 물성 — **물성 키로 든다.**
#:
#: 이 셋은 카드 항목란의 칸이 아니라 곡선을 짓는 입력이라 항목란에서 끌어올 자리가
#: 없다. 그래서 키를 여기 적되 **이름은 안 적는다** — 이름의 정본은 기준정보
#: 씨앗이고, 키는 사람이 고치지 않는 식별자다.
SYNTH_KEYS = (
    "mechanical.yield_strength",
    "mechanical.tensile_strength",
    "mechanical.elongation_at_break",
)


def synth_items() -> list[str]:
    """합성에 쓰는 항목 이름 셋 — 순서는 `SYNTH_KEYS` 그대로(항복·인장·연신)."""
    return [property_names.builtin_item(key) or "" for key in SYNTH_KEYS]


def synthetic_plastic(
    material: Material, elastic: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]] | str:
    """선언 스칼라로 소성 표를 짓는다 — 못 지으면 **이유 문자열**을 돌려준다.

    E 는 elastic 블록에 이미 선 값(선언 탄성계수)을 그대로 쓴다 — 합성이 다른
    E 를 쓰면 카드 안에서 탄성과 소성이 서로 다른 재료가 된다.
    """
    E = elastic.get("youngs_modulus")
    if not isinstance(E, (int, float)):
        return "탄성계수가 없습니다 — 선언 물성에 먼저 적으세요."
    items = synth_items()
    scalars = {item: declared(material, item) for item in items}
    yield_item, tensile_item, elongation_item = items
    curve = synth.synthesize(
        float(E),
        scalars[yield_item].value,
        scalars[tensile_item].value,
        scalars[elongation_item].value,
    )
    if curve is None:
        return "항복강도(또는 인장강도)가 없습니다 — 지어낼 근거가 없습니다."
    if not curve.table_rows:
        return f"소성 표가 안 나오는 재료입니다({curve.model})."
    # 첫 줄에 모델, 둘째 줄에 주의 — 둘 다 "합성" 으로 시작해야 덱 각주까지
    # 따라간다(네킹 줄과 같은 규칙). 접두어는 여기서 한 번만 붙인다.
    notes = [
        f"합성 소성 표 — 실측이 아니다. 모델: {curve.model}",
        f"합성 주의 — {curve.note}",
    ]
    for item in items:
        one = scalars[item]
        if one.value is None:
            continue
        row = declared_row(material, item) or {}
        reference = str(row.get("reference") or "").strip()
        notes.append(
            f"합성 입력 {item}: {one.source}" + (f" — {reference}" if reference else "")
        )
    return [dict(one) for one in curve.table_rows], notes


def declared_table(
    material: Material,
    columns: dict[str, str],
    *,
    constants: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """여러 물성을 온도 격자에 올린 표. `columns` 는 `{블록 열: 물성 항목}`.

    온도를 **합집합으로 모으고 값이 없는 칸은 비워 둔다.** 0 으로 채우면 비열
    0 인 재료가 되고, 빼 버리면 그 온도가 통째로 사라진다.

    ## 점이 하나면 상수다

    모든 줄에 같은 값을 쓴다. **지어내는 것이 아니라 명시된 모형 가정**이고,
    빼 두면 솔버가 그 온도에서 그 값을 모른다. `constants` 도 같은 자리다 —
    선언 물성이 아니라 재료 컬럼이나 측정에서 온 값들이다(푸아송비·밀도).

    ## 격자가 어긋나는지는 여기서 안 본다

    `*ELASTIC` 은 한 줄에 `(E, ν, T)` 를 받으므로 둘이 같은 온도에 있어야
    하지만, `*EXPANSION` 은 자기 표를 따로 갖는다 — **블록마다 다르다.** 그
    판단은 그 키워드를 아는 렌더러가 한다(`_elastic_lines`).
    """
    grids: dict[str, dict[float, float]] = {}
    singles: dict[str, float] = dict(constants or {})
    for column, item in columns.items():
        points = declared_points(declared_row(material, item) or {})
        if not points:
            continue
        if len(points) == 1:
            singles[column] = float(points[0]["value_si"])
            continue
        grids[column] = {
            float(point["temperature_k"]): float(point["value_si"]) for point in points
        }

    if not grids:
        return []

    rows: list[dict[str, Any]] = []
    for temperature in sorted({one for found in grids.values() for one in found}):
        row: dict[str, Any] = {"temperature": temperature, **singles}
        for column, found in grids.items():
            if temperature in found:
                row[column] = found[temperature]
        rows.append(row)
    return rows


def inherit_poisson(material: Material, override: float | None) -> Inherited:
    """**재료에서만 온다.** 로트마다 달라지는 값이 아니다."""
    if override is not None:
        return Inherited(override, "manual", "직접 입력한 값입니다.")
    if material.poisson_ratio is not None:
        return Inherited(material.poisson_ratio, "material", "재료에 적힌 값입니다.")
    return Inherited(
        None,
        "missing",
        "재료에 푸아송비가 없습니다 — 인장시험은 이 값을 주지 않습니다.",
    )
