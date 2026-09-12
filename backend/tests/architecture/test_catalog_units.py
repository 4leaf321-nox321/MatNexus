"""문헌 정의의 단위는 **눈금 말고는 표가 안다.**

실측(2026-09-12): 문헌 정의 271종 가운데 77종(값 7,325건)의 단위를 `matcore.units`
가 몰랐다 — 박리강도 `N/m`(1,017건) · 체적저항률 `ohm·m`(661) · 표면에너지
`J/m²`(458) 같은 멀쩡한 SI 조합이다. 표가 모르면 그 물성은:

  - **사내 물성 항목에 못 이어진다** — 차원 검사(MNX-CATALOG-0029)가 막는다
  - 값으로 찾기에서 단위 환산이 안 된다
  - 새 정의도 그 단위로는 못 만든다(MNX-CATALOG-0036)

즉 7천 건이 검색·매핑·채우기에서 조용히 빠져 있었다. 표를 채운 뒤로는 **새로 들어오는
정의도 같은 규율을 지켜야** 한다 — 이관이 새 단위를 들고 오면 여기서 걸린다.

**눈금은 예외다.** HV·Shore·HR·HBW·HK·GU 는 환산할 수 없다. 표에 넣으면 환산할 수
있는 척하게 되므로 안 넣고, 대신 같은 기호끼리만 견준다(`property_search.same_symbol`).
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from matcore import units

SEED = Path(__file__).resolve().parents[2] / "seeds" / "catalog" / "materialtwin.db.gz"

#: 환산할 수 없는 눈금. **늘리지 않는다** — 새 기호를 여기 넣기 전에 그것이 정말
#: 환산 불가능한 눈금인지 본다. 조합 단위는 표에 넣는 것이 맞다.
SCALES = frozenset({"HV", "HBW", "HK", "HR", "ShoreA", "ShoreD", "ShoreOO", "GU"})


@pytest.fixture(scope="module")
def definition_units(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[list[tuple[str, str]]]:
    plain = tmp_path_factory.mktemp("catalog-units") / "materialtwin.db"
    with gzip.open(SEED, "rb") as packed, plain.open("wb") as out:
        shutil.copyfileobj(packed, out)
    con = sqlite3.connect(plain)
    try:
        yield [
            (key, unit)
            for key, unit in con.execute("select key, si_unit from property_definition")
            if (unit or "").strip()
        ]
    finally:
        con.close()


def test_눈금_말고는_표가_아는_단위다(definition_units: list[tuple[str, str]]) -> None:
    assert definition_units, "씨앗에서 정의를 하나도 못 읽었다 — 대조가 무의미하다"
    unknown = sorted(
        {unit for _key, unit in definition_units if units.canonical(unit) is None} - SCALES
    )
    assert not unknown, (
        "문헌 정의가 표에 없는 단위를 씁니다 — 그 물성은 사내 항목에 못 이어지고 "
        f"값으로 찾기에서 환산이 안 됩니다. `matcore/units.py` 에 더하세요: {unknown}"
    )


def test_눈금은_표에_없다() -> None:
    """넣는 순간 환산할 수 있는 척하게 된다 — HV 200 을 HRC 로 바꿔 주는 표는 없다."""
    present = sorted(one for one in SCALES if units.canonical(one) is not None)
    assert not present, f"환산할 수 없는 눈금이 단위표에 있습니다: {present}"
