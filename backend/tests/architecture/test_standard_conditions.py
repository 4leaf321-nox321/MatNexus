"""표준 조건·등급 레지스트리가 **단위 표·문헌 등급과 어긋나지 않는다.**

둘 다 코드 레지스트리다(ADR 0028 의 판단). 표에 두면 누가 고친 순간 저장된 값의 뜻이
바뀌는데 그것은 검색이 이상해질 때에야 드러난다 — 여기서 CI 가 먼저 잡는다.
"""

from __future__ import annotations

import pytest

from app.modules.catalog.models import QUALITY_TIERS
from app.modules.materials import declared
from app.shared import standard_conditions, tiers
from matcore import units


@pytest.mark.parametrize(
    "one", list(standard_conditions.STANDARD.values()), ids=lambda o: o.key
)
def test_표준_조건의_단위는_단위_표가_안다(one: standard_conditions.StandardCondition) -> None:
    """모르는 단위면 값 검색이 조건 값을 환산하지 못해 조용히 안 걸린다."""
    assert units.canonical(one.si_unit) is not None, f"{one.key}: {one.si_unit}"
    # 저장 단위는 그 차원의 SI 여야 한다 — 「1 K 는 1 K」.
    assert units.to_si(1.0, one.si_unit) == pytest.approx(1.0) or one.si_unit == "K"


def test_별칭은_키와_겹치지_않고_소문자다() -> None:
    seen: dict[str, str] = {}
    for one in standard_conditions.STANDARD.values():
        for name in (one.key, *one.aliases):
            assert name == name.lower(), f"{name} — 견줄 때 소문자로 낮추므로 소문자로 적는다"
            assert name not in seen or seen[name] == one.key, (
                f"'{name}' 이 {seen.get(name)} 와 {one.key} 둘을 가리킨다"
            )
            seen[name] = one.key


def test_별칭_풀이가_단위를_본다() -> None:
    """이름만 온도인 칸(`temperature`, 저장 단위 s)을 온도로 읽으면 초를 켈빈으로 읽는다."""
    assert standard_conditions.resolve("temp", si_unit="K") == "temperature"
    assert standard_conditions.resolve("temperature", si_unit="s") is None
    assert standard_conditions.resolve("temperature_c", si_unit="degC") == "temperature"
    assert standard_conditions.resolve("clamp") is None
    assert standard_conditions.resolve(None) is None


def test_사내_등급_척도는_문헌_등급과_같은_번호다() -> None:
    assert set(tiers.TIER_LABELS) == set(QUALITY_TIERS) == {1, 2, 3, 4}


def test_선언_출처마다_등급이_있다() -> None:
    """출처를 더했는데 등급표에 없으면 4 로 떨어진다 — 그것이 의도인지 여기서 묻는다."""
    missing = set(declared.SOURCES) - set(tiers.DECLARED_TIERS)
    assert not missing, f"등급이 안 정해진 선언 출처: {missing}"
