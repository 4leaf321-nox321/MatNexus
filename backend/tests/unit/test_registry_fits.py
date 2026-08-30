"""**어느 시험 종류에서 이 계산을 보여 줄까.**

전에는 `applies_to` 의 **키**만 봤다. 그러면 부서가 자기 DMA 종류를 만드는 순간
(정의는 데이터다 — D7) 키가 `dma_sweep` 이 아니라서 DMA 단계 다섯과 Prony 묶음이
목록에서 사라진다. **막히는 것이 아니라 안 보이는** 것이라, 사람은 그것을 「이
기능이 없구나」 로 읽고 우회한다.

실측(2026-08-31): 운영 서버에 `dma_sweep` 이 없을 수 있다는 것을 사람이 먼저 물었다.
시험 종류는 데이터라서 마이그레이션이 만들어 주지 않고, 설치 시드나 보정 스크립트를
돌려야 생긴다.

그래서 **데이터의 모양**으로도 잡는다. 이름이 무엇이든 저장·손실 탄성률을 재는
시험이면 그 계산은 성립한다.
"""

from __future__ import annotations

import pytest

from matcore.registry import Plugin, fits, missing_channels


def _plugin(**kwargs: object) -> Plugin:
    base: dict[str, object] = {
        "id": "x",
        "kind": "processing",
        "label": "x",
        "fn": lambda: None,
    }
    return Plugin(**{**base, **kwargs})  # type: ignore[arg-type]


class Test아무_제한이_없으면:
    def test_어디서나_보인다(self) -> None:
        assert fits(_plugin(), "tensile", ["force"]) is True
        assert fits(_plugin(), None, None) is True


class Test키로_잡는_경우:
    def test_적힌_종류면_보인다(self) -> None:
        one = _plugin(applies_to=("dma_sweep",))
        assert fits(one, "dma_sweep", []) is True

    def test_다른_종류면_안_보인다(self) -> None:
        one = _plugin(applies_to=("dma_sweep",))
        assert fits(one, "tensile", ["force", "displacement"]) is False


class Test채널로_잡는_경우:
    """**이것이 이 기능의 요점이다.** 키가 달라도 재는 것이 같으면 보여 준다."""

    def test_키가_달라도_채널이_맞으면_보인다(self) -> None:
        one = _plugin(
            applies_to=("dma_sweep",),
            requires_channels=(("storage_modulus",), ("loss_modulus",)),
        )
        # 부서가 만든 DMA 종류 — 키는 다르고 재는 것은 같다.
        assert fits(one, "dma_inhouse_freqtemp", ["storage_modulus", "loss_modulus"]) is True

    def test_채널이_모자라면_안_보인다(self) -> None:
        one = _plugin(requires_channels=(("storage_modulus",), ("loss_modulus",)))
        assert fits(one, "tensile", ["storage_modulus"]) is False

    def test_안쪽_묶음은_그중_하나면_된다(self) -> None:
        # 각주파수만 있는 표가 실재한다 — 실측 파일의 첫 스윕에만 `Frequency` 가
        # 있고 나머지 여섯에는 없었다.
        one = _plugin(requires_channels=(("frequency", "angular_frequency"),))
        assert fits(one, "x", ["angular_frequency"]) is True
        assert fits(one, "x", ["frequency"]) is True
        assert fits(one, "x", ["temperature"]) is False

    def test_채널을_모르면_키로만_판단한다(self) -> None:
        """**「모른다」 를 「없다」 로 읽지 않는다.** 종류를 못 찾았을 때 채널이
        없다고 단정하면, 그 종류에서 계산이 통째로 사라진다."""
        one = _plugin(
            applies_to=("dma_sweep",),
            requires_channels=(("storage_modulus",),),
        )
        assert fits(one, "dma_sweep", None) is True
        assert fits(one, "모르는종류", None) is False


class Test무엇이_빠졌나:
    def test_빠진_것을_묶음째_돌려준다(self) -> None:
        """화면이 그대로 적는다 — 「조건을 만족하지 않습니다」 는 다음에 할 일을
        안 알려 준다."""
        one = _plugin(
            requires_channels=(("storage_modulus",), ("frequency", "angular_frequency"))
        )
        assert missing_channels(one, ["storage_modulus"]) == [
            ("frequency", "angular_frequency")
        ]

    def test_다_있으면_비어_있다(self) -> None:
        one = _plugin(requires_channels=(("storage_modulus",),))
        assert missing_channels(one, ["storage_modulus", "loss_modulus"]) == []


@pytest.mark.parametrize("plugin_id", ["dma.derived", "dma.glass_transition"])
def test_실제_DMA_단계가_채널로_잡힌다(plugin_id: str) -> None:
    """선언이 실제로 붙어 있는지 본다 — 규약만 만들고 안 쓰면 아무것도 안 바뀐다."""
    from matcore import processing, registry

    processing.load_builtin()
    plugin = registry.get(plugin_id)
    assert plugin.requires_channels, f"{plugin_id} 에 requires_channels 가 없습니다"
    assert fits(
        plugin,
        "dma_inhouse_freqtemp",
        ["storage_modulus", "loss_modulus", "temperature", "tan_delta"],
    )
