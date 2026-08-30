"""`applies_to` 가 **있는 시험종류를 가리키는가.**

실측(2026-08-30): 묶음 Prony 가 `dma_temperature_sweep` 을 가리키고 있었는데 그런
시험종류는 없다 — 실제 key 는 `dma_sweep` 이다.

## 왜 오래 안 드러났나

**아무도 그 값으로 조회한 적이 없었다.** 화면은 `/groups/kinds` 를 필터 없이 불러
방법 전부를 받았고, 사람이 시험을 목록에서 골랐다. 「이 시험종류로 무엇을 할 수
있나」 를 처음 물은 것이 물성 화면을 고치던 그날이었고, 그때 방법이 0개로 나왔다.

**틀린 값이 조용히 앉아 있는 종류의 결함**이다 — 아무것도 안 터지고, 기능이 하나
없어질 뿐이다. 그래서 시험으로 굳힌다.

## 무엇을 막나

    가리키는 종류가 없다     이번에 잡힌 것. 그 플러그인은 어디서도 안 뜬다.
    오타                    `tensil`·`dma_seep` 같은 것.
    이름이 바뀐 뒤          시험종류 key 를 고치면 여기가 따라와야 한다.

**비어 있는 것은 괜찮다** — 「제한 없음」 이라는 뜻이고 레지스트리가 그렇게 읽는다.
"""

from __future__ import annotations

import pytest

from app.modules.tests.definitions import BUILTIN_TEST_TYPES
from matcore import registry


@pytest.fixture(scope="module", autouse=True)
def _loaded() -> None:
    """확장까지 올려 둔다 — 확장이 등록한 플러그인도 같은 규칙을 받는다."""
    from app.main import create_app

    create_app()


def _keys() -> set[str]:
    return {str(one["key"]) for one in BUILTIN_TEST_TYPES}


def test_가리키는_시험종류가_실제로_있다() -> None:
    known = _keys()
    wrong: list[tuple[str, str]] = []
    for plugin in registry.list_plugins():
        for target in plugin.applies_to:
            # 재료군(`metal`·`polymer`)도 이 칸을 쓴다 — 밑줄이 든 것만 시험종류
            # 이름으로 본다.
            if "_" in target and target not in known:
                wrong.append((plugin.id, target))
    assert not wrong, (
        "없는 시험종류를 가리킵니다: "
        + ", ".join(f"{one} → {target}" for one, target in wrong)
        + f". 있는 것: {', '.join(sorted(known))}"
    )


def test_묶음은_적어도_하나가_붙어_있다() -> None:
    """**묶음은 무엇에 쓰는지 반드시 적는다.**

    제한 없는 묶음은 「아무 시험이나 묶는다」 는 뜻이 되는데, 묶는 계산은 데이터
    모양을 가정한다 — Prony 는 주파수·탄성률 열이 있어야 한다. 아무것도 안 적으면
    인장 시험 목록에도 그 방법이 떠서, 눌러 보고서야 안 된다는 것을 안다.

    **키든 채널이든 하나는 적혀 있어야 한다.** 채널 쪽이 더 낫다 — 키는 부서가
    자기 종류를 만드는 순간 안 맞는다.
    """
    loose = [
        plugin.id
        for plugin in registry.list_plugins()
        if plugin.kind == "grouping" and not plugin.applies_to and not plugin.requires_channels
    ]
    assert not loose, f"묶는 대상을 안 적은 묶음: {loose}"


#: 아직 채널로 안 옮긴 계산. **여기 있는 것은 결함이지 예외가 아니다.**
#:
#: 인장 단계 일곱은 조건을 채널로 옮기면 `force`·`displacement` 를 가진 **다른**
#: 종류(압축 등)에도 뜨게 된다. 그것이 맞는지는 인장과 압축을 같은 계산으로 볼
#: 것인가 하는 도메인 판단이고, 물성 개발자가 정할 일이다 — DMA 를 옮기는 김에
#: 조용히 결정해서는 안 된다. 그래서 목록에 적어 두고 새 계산만 막는다.
NOT_YET_CHANNELS = {
    "tensile.engineering",
    "tensile.toe_compensation",
    "tensile.elastic_modulus",
    "tensile.proof_stress",
    "tensile.strength",
    "tensile.necking_candidate",
    "tensile.true_plastic",
}


def test_시험종류를_가리키면_채널도_함께_적는다() -> None:
    """**키만 적힌 계산은 부서가 만든 종류에서 사라진다.**

    실측(2026-08-31): 운영에 `dma_sweep` 이 없을 수 있다는 것을 사람이 먼저 물었다.
    시험 종류는 데이터라서 마이그레이션이 만들어 주지 않는다 — 그때 DMA 단계 다섯과
    Prony 묶음은 **막히는 것이 아니라 목록에서 안 보이고**, 사람은 그것을 「이 기능이
    없구나」 로 읽는다.

    그래서 시험종류 키를 가리키는 계산은 같은 조건을 **채널로도** 적는다.

    **파서는 해당 없다** — 채널을 요구하는 것이 아니라 만드는 쪽이다. 재료군
    (`metal`·`polymer`)만 가리키는 것도 해당 없다: 그것은 데이터 모양이 아니다.
    """
    known = _keys()
    naked = [
        plugin.id
        for plugin in registry.list_plugins()
        if plugin.kind in ("processing", "grouping")
        and plugin.id not in NOT_YET_CHANNELS
        and any(target in known for target in plugin.applies_to)
        and not plugin.requires_channels
    ]
    assert not naked, (
        "시험종류 키만 보고 거릅니다 — `requires_channels` 를 함께 적으세요: "
        + ", ".join(naked)
    )


def test_안_옮긴_목록이_실제로_남아_있다() -> None:
    """**옮기고 나면 목록에서 빼야 한다.**

    다 옮겼는데 이름이 남아 있으면, 그 이름을 근거로 다음 사람이 「예외가 허용되는
    구나」 로 읽는다. 없는 계산을 가리키는 것도 같은 이유로 막는다.
    """
    ids = {plugin.id for plugin in registry.list_plugins()}
    gone = sorted(NOT_YET_CHANNELS - ids)
    assert not gone, f"없는 계산이 목록에 있습니다: {gone}"
    done = sorted(one for one in NOT_YET_CHANNELS if registry.get(one).requires_channels)
    assert not done, f"이미 옮겼습니다 — 목록에서 빼세요: {done}"
