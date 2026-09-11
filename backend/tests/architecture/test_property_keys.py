"""계산이 단 물성 이름표(`Produced.property_key`)가 **실재하는 문헌 정의인가.**

## 왜 (2026-09-12)

같은 물성이 세 이름으로 살았다 — 처리 결과 `proof_stress`, 사람이 적는 「항복강도」,
문헌 `mechanical.yield_strength`. 그것을 한 키로 묶는 이름표를 계산 선언에 달았는데,
그 키는 문자열이라 오타가 나도 아무 데서도 안 터진다 — 「항복강도 근처인 재료」 를
물었을 때 잰 값이 조용히 안 나올 뿐이다. 그래서 여기서 문헌 씨앗과 대조한다.

`elongation_observed` 같은 것에 이름표를 달지 않는 것은 검사가 못 잡는다 — 그것은
판단이고, `Produced.property_key` 의 docstring 이 그 판단을 적어 둔다.
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from matcore import cards, extensions, processing, registry

BACKEND = Path(__file__).resolve().parents[2]
SEED = BACKEND / "seeds" / "catalog" / "materialtwin.db.gz"


@pytest.fixture(scope="module")
def literature_keys(tmp_path_factory: pytest.TempPathFactory) -> Iterator[set[str]]:
    plain = tmp_path_factory.mktemp("catalog-seed") / "materialtwin.db"
    with gzip.open(SEED, "rb") as packed, plain.open("wb") as out:
        shutil.copyfileobj(packed, out)
    con = sqlite3.connect(plain)
    try:
        yield {row[0] for row in con.execute("select key from property_definition")}
    finally:
        con.close()


def _declared() -> list[tuple[str, str, str]]:
    """`(어디, 값 이름, 문헌 키)` — 처리·묶음 플러그인과 카드 블록 전부."""
    processing.load_builtin()
    cards.load_builtin()
    extensions.load(BACKEND / "extensions")
    found: list[tuple[str, str, str]] = []
    for plugin in registry.list_plugins():
        for made in plugin.makes_values:
            if made.property_key:
                found.append((plugin.id, made.key, made.property_key))
    for block in cards.list_blocks():
        for made in (*block.produces, *block.rows):
            if made.property_key:
                found.append((f"block:{block.key}", made.key, made.property_key))
    return found


def test_이름표는_문헌_정의에_있는_키다(literature_keys: set[str]) -> None:
    assert literature_keys, "씨앗에서 정의를 하나도 못 읽었다 — 대조가 무의미하다"
    declared = _declared()
    assert declared, "이름표가 하나도 없다 — 선언이 사라졌나"
    missing = [
        f"{where}.{key} → {prop}"
        for where, key, prop in declared
        if prop not in literature_keys
    ]
    assert not missing, (
        "문헌에 없는 물성 키를 달았습니다 — 오타이거나 정의가 빠진 것:\n  "
        + "\n  ".join(missing)
    )


def test_핵심_측정값은_이름표를_들고_있다() -> None:
    """인장 셋과 Tg — 이것들이 빠지면 「잰 값까지 찾는다」 가 빈말이 된다."""
    processing.load_builtin()
    for prop, scalar in (
        ("mechanical.yield_strength", "proof_stress"),
        ("mechanical.tensile_strength", "tensile_strength"),
        ("mechanical.youngs_modulus", "youngs_modulus"),
        ("thermal.glass_transition", "glass_transition"),
    ):
        assert scalar in {key for _plugin, key in registry.measured_by(prop)}, prop


def test_같은_값_이름은_한_물성만_가리킨다() -> None:
    """`property_key_of` 가 답하려면 한 이름이 두 물성에 걸리면 안 된다."""
    processing.load_builtin()
    by_scalar: dict[str, set[str]] = {}
    for plugin in registry.list_plugins():
        for made in plugin.makes_values:
            if made.property_key:
                by_scalar.setdefault(made.key, set()).add(made.property_key)
    torn = {key: sorted(props) for key, props in by_scalar.items() if len(props) > 1}
    assert not torn, f"한 값 이름이 두 물성을 가리킵니다: {torn}"
