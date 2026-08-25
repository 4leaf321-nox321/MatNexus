"""선언 물성 — **시험이 주지 않는 값을 사람이 적는다.**

탄성계수는 처리 결과에서만 왔고 열팽창계수·비열·열전도도는 자리가 아예 없었다.
그런데 그것들은 인장시험이 안 준다 — 핸드북·규격·밀시트에서 온다. 시험을 안 한
재료가 대부분인데, 그 재료로는 해석용 카드를 만들 수 없었다.

## 항목 목록은 기준정보가 정한다

`property_item` 축의 값이 곧 넣을 수 있는 물성이다(D7). 열해석을 안 하는 부서에
비열 칸이 뜰 이유가 없고, 반대로 목록을 코드에 박으면 필요한 항목 하나를 넣으려고
배포를 기다려야 한다.

값마다 **차원**을 든다(`attributes["dimension"]`). 그것이 여기서 하는 일의
절반이다 — 단위를 그 차원으로 검사하므로 **「비열 자리에 열전도도」가 막힌다.**
ADR 0013 이 *"밀도 자리에 온도를 넣어도 지금은 아무도 모른다"* 고 적어 둔
구멍이 이 축에서는 막혀 있다.

## 출처가 필수다

이 저장소는 **카드가 자기 근거를 들고 있어야 한다**는 원칙 위에 서 있다
(ADR 0009·0012). 값만 있고 어디서 왔는지 모르면 그 값으로 돌린 해석의 근거를
나중에 되짚을 수 없다 — 특히 선언 물성은 **사람이 적은 것**이라 더 그렇다.

`reference`(문서 이름)까지 받는 이유도 같다. `literature` 만으로는 어느 핸드북
몇 판인지 알 수 없고, 값이 의심스러울 때 확인할 길이 없다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.vocabulary.models import Vocabulary, VocabularyTerm
from app.shared.errors import AppError
from app.shared.text import clean, compare_key
from matcore import units

AXIS = "property_item"

#: 값이 **어디에 붙는가.** 이 갈래가 이 파일에서 하는 일의 나머지 절반이다.
#:
#:     문헌·규격   Grade 가 같으면 같다   E · ν · α · Cp · k   → 재료
#:     밀시트      로트마다 다르다        항복강도 · 인장강도    → 시료
#:
#: 밀시트는 **「이 로트가 규격에 맞나」를 증명하는 문서**지 물리 상수표가 아니다
#: (EN 10204 3.1). 그래서 거기 실린 값을 재료에 적으면 첫 로트의 값이 그 Grade
#: 전체의 값이 되고, 두 번째 로트가 들어오는 순간 둘 중 하나가 조용히 진다.
LEVELS = ("재료", "시료")
DEFAULT_LEVEL = "재료"

#: 값이 어디서 왔나. **추정도 출처다** — 「모름」을 두지 않는 이유는, 그것을
#: 두면 대부분이 거기로 가고 그때부터 이 칸이 뜻을 잃기 때문이다.
SOURCES = {
    "literature": "문헌",
    "standard": "규격",
    "datasheet": "밀시트·데이터시트",
    "estimate": "추정",
}


def catalog(db: Session, *, level: str | None = None) -> dict[str, dict[str, Any]]:
    """넣을 수 있는 물성 항목. `{값: {dimension, symbol, si_unit, level}}`.

    `level` 을 주면 그 층에 붙는 것만 준다. **주지 않으면 전부** 준다 — 이미
    저장된 값을 읽어 보여 줄 때는 층으로 거르면 안 되기 때문이다(항목의 층이
    나중에 바뀌어도 옛 값은 그대로 있다).

    감춘 값(`deprecated`)은 뺀다 — 피커에서 사라진 항목을 새로 넣을 수 있으면
    감춘 뜻이 없다. **이미 넣어 둔 값은 그대로 남는다**(지우는 것이 아니다).
    """
    axis = db.scalar(select(Vocabulary).where(Vocabulary.slug == AXIS))
    if axis is None:
        return {}
    found: dict[str, dict[str, Any]] = {}
    for term in db.scalars(
        select(VocabularyTerm).where(
            VocabularyTerm.vocabulary_id == axis.id, VocabularyTerm.status != "deprecated"
        )
    ):
        attributes = term.attributes or {}
        dimension = str(attributes.get("dimension") or "dimensionless")
        # **비면 재료로 본다.** 이 축은 재료 물성만 담던 때가 있었고, 그때 넣은
        # 값에는 이 칸이 없다 — 없다고 목록에서 빼면 쓰던 항목이 사라진다.
        at = str(attributes.get("level") or DEFAULT_LEVEL)
        if level is not None and at != level:
            continue
        found[term.value] = {
            "dimension": dimension,
            "symbol": attributes.get("symbol") or None,
            "si_unit": units.SI_UNITS.get(dimension, "1"),
            "level": at,
            # 같은 물성을 처리 결과가 낸다면 그 키. 있으면 「적은 값과 잰 값」을
            # 견줄 수 있다 — 밀시트 대조가 이것으로 돈다.
            "measured_key": attributes.get("measured_key") or None,
        }
    return found


def _points(given: list[Any], *, name: str, symbol: str) -> list[dict[str, Any]]:
    """온도-값 점들을 검사해 저장할 모양으로.

    **온도 오름차순으로 고정한다.** 뒤섞인 채로 솔버에 나가면 Abaqus 가 조용히
    이상한 보간을 한다 — 오류를 내지 않고, 결과만 틀린다.
    """
    made: list[dict[str, Any]] = []
    for point in given:
        if not isinstance(point, dict):
            raise AppError("MNX-MATERIALS-0024", f"'{name}' 의 값이 잘못됐습니다.", status=422)
        raw = point.get("value")
        if not isinstance(raw, (int, float)):
            raise AppError(
                "MNX-MATERIALS-0024", f"'{name}' 의 값이 숫자가 아닙니다.", status=422
            )
        temperature = point.get("temperature_k")
        made.append(
            {
                "temperature_k": float(temperature)
                if isinstance(temperature, (int, float))
                else None,
                "value_si": units.to_si(raw, symbol),
            }
        )

    if len(made) == 1:
        return made

    # **점이 둘 이상이면 온도가 전부 있어야 한다.** 하나라도 비면 그 값이 어느
    # 온도의 것인지 알 수 없고, 그것을 상온으로 치는 것은 지어내는 일이다.
    if any(point["temperature_k"] is None for point in made):
        raise AppError(
            "MNX-MATERIALS-0026",
            f"'{name}' 에 온도 없는 값이 섞여 있습니다. 값이 여럿이면 각각 어느 "
            f"온도의 것인지 적어야 합니다 — 안 그러면 그 값이 어느 온도에서 유효한지 "
            f"알 방법이 없습니다.",
            status=422,
        )
    temperatures = [point["temperature_k"] for point in made]
    if len(set(temperatures)) != len(temperatures):
        raise AppError(
            "MNX-MATERIALS-0026",
            f"'{name}' 에 같은 온도가 두 번 있습니다. 솔버는 둘 중 하나를 조용히 "
            f"고릅니다 — 어느 쪽인지 우리가 정해 두어야 합니다.",
            status=422,
        )
    return sorted(made, key=lambda point: point["temperature_k"])


def check(
    db: Session, rows: list[dict[str, Any]], *, level: str = DEFAULT_LEVEL
) -> list[dict[str, Any]]:
    """넣을 값들을 검사해 **저장할 모양**으로 바꾼다.

    `level` 이 그 층에 붙는 항목만 받게 한다 — 항복강도를 재료에 적으면 첫
    로트의 값이 그 Grade 전체의 값이 되고, 두 번째 로트가 들어오는 순간 둘 중
    하나가 조용히 진다.

    사람이 적은 단위(`input_unit`)는 그대로 남기고 값은 정본 SI 로 담는다 —
    시험 채널과 같은 규칙이다. `GPa` 로 적어도 저장은 `Pa` 이고, 화면이 적은
    단위로 되돌려 보여 준다.

    **한 항목을 두 번 넣지 못한다.** 탄성계수가 두 줄이면 카드가 어느 것을 쓸지
    정할 수 없고, 그 판단을 여기서 안 하면 나중에 조용히 하나가 이긴다.

    ## 한 줄이 표를 든다

    강판 탄성계수는 상온 206 GPa 가 400 °C 에서 170 GPa 쯤으로 떨어진다. 그렇다고
    줄을 여럿 두면 위의 규칙이 깨진다 — **항목은 하나이고 그 하나가 온도에 따라
    변할 뿐**이므로 줄 안에 점을 넣는다(`points`).

    점이 둘 이상이면 **온도가 전부 있어야 하고 서로 달라야 한다.** 온도 없는
    점이 섞이면 그 값이 어느 온도의 것인지 알 수 없고, 온도가 겹치면 솔버가
    둘 중 하나를 조용히 고른다.
    """
    known = catalog(db, level=level)
    if not known:
        raise AppError(
            "MNX-MATERIALS-0020",
            f"{level}에 넣을 수 있는 물성 항목이 하나도 없습니다. 기준정보의 "
            f"'물성 항목' 축에 먼저 넣고, '붙는 곳' 을 {level} 로 두세요.",
            status=422,
        )

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        name = clean(str(row.get("item") or ""))
        if name is None:
            raise AppError("MNX-MATERIALS-0021", "물성 항목이 비어 있습니다.", status=422)
        spec = known.get(name) or next(
            (item for value, item in known.items() if compare_key(value) == compare_key(name)),
            None,
        )
        if spec is None:
            # **다른 층의 항목인지 먼저 본다.** "등록된 항목이 아닙니다" 만
            # 말하면 기준정보에 뻔히 있는 이름을 두고 사람이 그것을 또 만든다.
            elsewhere = catalog(db).get(name)
            if elsewhere is not None:
                why = (
                    "로트마다 다른 값이라 시료에 적습니다"
                    if elsewhere["level"] == "시료"
                    else "Grade 가 같으면 같은 값이라 재료에 적습니다"
                )
                raise AppError(
                    "MNX-MATERIALS-0021",
                    f"'{name}' 은 {elsewhere['level']} 에 붙는 물성입니다. {why} — "
                    f"지금 적으려는 곳은 {level} 입니다.",
                    status=422,
                )
            raise AppError(
                "MNX-MATERIALS-0021",
                f"'{name}' 은 {level}에 넣을 수 있는 물성 항목이 아닙니다. 기준정보의 "
                f"'물성 항목' 축에 먼저 넣으세요 — 있는 것: {', '.join(sorted(known))}",
                status=422,
            )
        key = compare_key(name)
        if key in seen:
            raise AppError(
                "MNX-MATERIALS-0022",
                f"'{name}' 이 두 번 있습니다. 한 물성은 한 줄입니다 — 두 값이 있으면 "
                f"카드가 어느 것을 쓸지 정할 수 없습니다.",
                status=422,
            )
        seen.add(key)

        source = str(row.get("source") or "")
        if source not in SOURCES:
            raise AppError(
                "MNX-MATERIALS-0023",
                f"'{name}' 의 출처가 없습니다. 값만 있고 어디서 왔는지 모르면 그 값으로 "
                f"돌린 해석의 근거를 되짚을 수 없습니다 — {' · '.join(SOURCES.values())} "
                f"중 하나를 고르세요.",
                status=422,
            )
        reference = clean(str(row.get("reference") or ""))
        if reference is None:
            raise AppError(
                "MNX-MATERIALS-0023",
                f"'{name}' 의 근거 문서가 없습니다. '문헌' 만으로는 어느 핸드북 몇 판인지 "
                f"알 수 없습니다 — 'KS D 3512 표 3' 처럼 적으세요.",
                status=422,
            )

        given = row.get("points")
        if not isinstance(given, list) or not given:
            raise AppError(
                "MNX-MATERIALS-0024",
                f"'{name}' 에 값이 없습니다. 값 없는 항목은 「이 물성이 있다」고 "
                f"말하는 거짓말이 됩니다.",
                status=422,
            )
        symbol = str(row.get("input_unit") or spec["si_unit"])
        try:
            unit = units.unit_of(symbol)
        except units.UnknownUnit as caught:
            raise AppError("MNX-MATERIALS-0025", str(caught), status=422) from caught
        # **여기가 이 파일의 핵심이다.** 차원이 안 맞으면 값은 멀쩡한데 뜻이
        # 다르다 — 비열 자리에 열전도도를 넣어도 숫자는 그럴듯하다.
        if not units.same_dimension(unit.dimension, spec["dimension"]):
            raise AppError(
                "MNX-MATERIALS-0025",
                f"'{name}' 은 {spec['dimension']} 인데 '{symbol}' 은 "
                f"{unit.dimension} 입니다. 저장 단위는 {spec['si_unit']} 입니다.",
                status=422,
            )

        points = _points(given, name=name, symbol=symbol)
        out.append(
            {
                "item": name,
                "points": points,
                "input_unit": symbol,
                "source": source,
                "reference": reference,
                "note": clean(str(row.get("note") or "")),
            }
        )
    # 저장 순서를 항목 이름으로 고정한다. 넣은 순서대로 두면 같은 내용의 재료가
    # 서로 다른 순서를 갖고, 비교·감사에서 바뀐 것처럼 보인다.
    return sorted(out, key=lambda item: item["item"])
