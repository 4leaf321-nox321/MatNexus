"""처리 순서도 — **선언한 의존이 실제 동작과 같은가.**

화면은 이제 "지금 고를 수 있는 열" 과 "이 단계를 쓰려면 무엇이 먼저 필요한가"
를 플러그인이 선언한 `makes_columns`·`makes_values`·`order` 로 계산한다.

선언은 **틀려도 조용하다.** `makes_columns` 에 없는 열을 실제로는 만들고 있어도
계산은 잘 돌고, 화면만 그 열을 목록에 안 낸다 — 사람은 "왜 이 열이 없지" 를
겪고 우리는 아무 오류도 못 본다. 그래서 여기서 **돌려 보고 대조한다.**

실측으로 드러난 함정이 이 파일의 이유다: 장비가 준 것은 변위·하중·폭뿐이라
인장강도 단계의 '변형률 열' 목록이 비어 있었다. 그 열은 앞 단계가 만드는
것이라, **돌려 보려면 골라야 하고 고르려면 돌려 봐야 하는** 자리였다.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from matcore import processing, registry
from matcore.processing import Frame, Step

#: 장비가 실제로 주는 것. Zwick 은 응력-변형률을 주지 않는다.
SOURCE = ("displacement", "force", "width")


@pytest.fixture(autouse=True)
def _plugins() -> None:
    processing.load_builtin()


def source_frame() -> Frame:
    """게이지 50 mm 기준으로 변형률 0~1% 를 200점.

    **값이 아니라 열 이름을 보는 시험**이지만, 토우 보정처럼 구간 안의 점 수를
    요구하는 단계가 있어 성기게 만들면 계산 쪽에서 먼저 막힌다.
    """
    displacement = np.linspace(0.0, 0.0005, 200)
    force = displacement * 2.0e6  # 대충 탄성
    return Frame(
        {
            "displacement": displacement,
            "force": force,
            "width": np.full(200, 0.0125),
        },
        {"displacement": "m", "force": "N", "width": "m"},
    )


def resolve(template: str, options: dict[str, object]) -> str:
    """`{column}_smoothed` 같은 틀을 그 단계 옵션으로 채운다."""
    filled = template
    for name, value in options.items():
        filled = filled.replace("{" + name + "}", str(value))
    return filled


def defaults(plugin: registry.Plugin) -> dict[str, object]:
    return {spec.name: spec.default for spec in plugin.params if spec.default is not None}


class TestDeclaredOrder:
    def test_인장_순서도가_공칭부터_시작한다(self) -> None:
        """`order` 는 화면의 사정이 아니라 계산의 성질이다.

        공칭 변환 없이는 변형률 열 자체가 없다. 목록이 알파벳순이면
        `curve.crop` 이 맨 앞에 오고 시작점이 가운데 묻힌다.
        """
        steps = registry.list_plugins("processing", applies_to="tensile")
        assert steps[0].id == "tensile.engineering"
        # **재샘플은 맨 뒤다.** 앞에 두면 탄성계수·항복강도가 잰 점이 아니라
        # 우리가 보간해 만든 점으로 계산된다.
        assert steps[-1].id == "curve.resample"
        assert [item.order for item in steps] == sorted(item.order for item in steps)

    def test_값을_쓰는_단계가_만드는_단계보다_뒤에_있다(self) -> None:
        """오프셋 항복강도는 탄성계수가 있어야 한다 — 순서도가 그 순서여야 한다."""
        by_id = {item.id: item for item in registry.list_plugins("processing")}
        maker = by_id["tensile.elastic_modulus"]
        assert "youngs_modulus" in {item.key for item in maker.makes_values}
        for user in ("tensile.proof_stress", "tensile.true_plastic"):
            assert by_id[user].order > maker.order


class TestDeclaredColumns:
    """**선언과 실제를 대조한다.** 선언만 고치고 계산을 안 고치면 여기서 걸린다."""

    def test_공칭_변환이_선언한_열을_실제로_만든다(self) -> None:
        plugin = registry.get("tensile.engineering")
        before = source_frame()
        result = processing.apply(
            [Step("tensile.engineering", {"gauge_length": 0.05, "area": 12.12e-6})],
            before,
        )
        added = set(result.frame.columns) - set(before.columns)
        assert added == {item.key for item in plugin.makes_columns}
        # **단위도 선언한다.** 화면이 실무 단위로 바꿔 보여 주는 근거다.
        for item in plugin.makes_columns:
            assert result.frame.units[item.key] == item.si_unit

    def test_진응력_단계가_선언한_열을_실제로_만든다(self) -> None:
        plugin = registry.get("tensile.true_plastic")
        steps = [
            Step("tensile.engineering", {"gauge_length": 0.05, "area": 12.12e-6}),
        ]
        before = processing.apply(steps, source_frame()).frame
        result = processing.apply(
            [Step("tensile.true_plastic", {"youngs_modulus": 200e9})], before
        )
        added = set(result.frame.columns) - set(before.columns)
        assert added == {item.key for item in plugin.makes_columns}
        for item in plugin.makes_columns:
            assert result.frame.units[item.key] == item.si_unit

    def test_평활은_고른_열에_따라_이름이_달라진다(self) -> None:
        """`{column}_smoothed` 는 틀이다. 화면이 옵션 값으로 채운다."""
        plugin = registry.get("curve.smooth")
        assert [item.key for item in plugin.makes_columns] == ["{column}_smoothed"]

        options = {"column": "force", "window": 5}
        before = source_frame()
        result = processing.apply([Step("curve.smooth", options)], before)
        added = set(result.frame.columns) - set(before.columns)
        assert added == {resolve(plugin.makes_columns[0].key, options)}

    def test_열을_안_만든다고_한_단계는_정말_안_만든다(self) -> None:
        """토우 보정은 **고른 열을 그 자리에서 민다** — 새 열을 더하지 않는다.

        새 열을 만드는 것으로 착각하면 화면이 없는 열을 목록에 낸다.
        """
        steps = [Step("tensile.engineering", {"gauge_length": 0.05, "area": 12.12e-6})]
        before = processing.apply(steps, source_frame()).frame
        result = processing.apply(
            [Step("tensile.toe_compensation", {})],
            before,
        )
        assert set(result.frame.columns) == set(before.columns)
        assert registry.get("tensile.toe_compensation").makes_columns == ()


class TestWalkable:
    def test_순서대로_다_고르면_열이_늘_있다(self) -> None:
        """**이 파일의 핵심.**

        순서도를 위에서 아래로 다 고르면, 각 단계의 열 파라미터 기본값이 그
        시점에 **이미 존재하는 열**이어야 한다. 하나라도 아니면 사람은 "고를
        것이 없는 칸" 을 만난다.
        """
        available = set(SOURCE)
        missing: list[str] = []
        for plugin in registry.list_plugins("processing", applies_to="tensile"):
            options = defaults(plugin)
            for spec in plugin.params:
                if spec.role != "column":
                    continue
                wanted = options.get(spec.name)
                # 기본값이 없는 칸(`curve.*` 의 '기준 열')은 사람이 고른다 —
                # 그때 고를 목록이 비어 있지만 않으면 된다.
                if wanted is None:
                    assert available, f"{plugin.id}.{spec.name}: 고를 열이 하나도 없습니다"
                    continue
                if str(wanted) not in available:
                    missing.append(f"{plugin.id}.{spec.name} → {wanted}")
            available |= {resolve(item.key, options) for item in plugin.makes_columns}

        assert missing == [], (
            "순서도를 순서대로 따라가는데 아직 없는 열을 기본값으로 갖고 있습니다:\n  "
            + "\n  ".join(missing)
        )

    def test_값_참조도_순서대로_채워진다(self) -> None:
        """`@youngs_modulus` 를 쓰는 단계 앞에 그 값을 내는 단계가 있는가."""
        made: set[str] = set()
        for plugin in registry.list_plugins("processing", applies_to="tensile"):
            for spec in plugin.params:
                default = spec.default
                if isinstance(default, str) and default.startswith("@"):
                    assert default[1:] in made, (
                        f"{plugin.id}: {default} 를 만드는 앞 단계가 없습니다"
                    )
            made |= {item.key for item in plugin.makes_values}


class TestDocumented:
    """**이름만 적으면 화면이 `strain_true_plastic` 을 그대로 보여 준다.**

    그것이 무엇인지는 코드를 읽어야 알게 되고, 그러면 아무도 안 읽는다. 이름을
    정하는 자리에서 뜻도 같이 적게 한다 — 화면의 변수 목록이 이 선언을 그대로
    보여 준다.
    """

    def test_만들어_내는_것에는_이름이_있다(self) -> None:
        nameless: list[str] = []
        for plugin in registry.list_plugins("processing"):
            for item in (*plugin.makes_columns, *plugin.makes_values):
                if not item.label.strip():
                    nameless.append(f"{plugin.id}: {item.key}")
        assert nameless == []

    def test_열_이름이_겹치지_않는다(self) -> None:
        """두 계산이 같은 열을 만들면 뒤가 앞을 덮는다 — 조용히."""
        seen: dict[str, str] = {}
        clashes: list[str] = []
        for plugin in registry.list_plugins("processing"):
            for item in plugin.makes_columns:
                if item.key in seen:
                    clashes.append(f"{item.key}: {seen[item.key]} 와 {plugin.id}")
                seen[item.key] = plugin.id
        assert clashes == []


class TestRequired:
    """**필수 표시가 실제와 같은가.**

    화면이 "켠 단계 중 덜 채운 것" 을 붉게 짚으려면 어느 칸이 필수인지 알아야
    한다. 그걸 화면이 추측하면 틀린다 — 빈 칸이 정상인 칸도 많다(`curve.resample`
    의 시작·끝은 비우면 관측 범위).

    선언은 **틀려도 조용하다.** 필수인데 안 적으면 화면이 안 짚고, 필수가
    아닌데 적으면 멀쩡한 구성을 붉게 칠한다. 그래서 **빼고 돌려 본다.**
    """

    def _run(self, plugin_id: str, options: dict[str, object]) -> None:
        frame = source_frame()
        if plugin_id != "tensile.engineering":
            frame = processing.apply(
                [Step("tensile.engineering", {"gauge_length": 0.05, "area": 12.12e-6})],
                frame,
            ).frame
        processing.apply([Step(plugin_id, options)], frame)

    #: 필수 칸을 채운 최소 구성. 여기서 하나씩 빼 본다.
    FULL: ClassVar[dict[str, dict[str, object]]] = {
        "tensile.engineering": {"gauge_length": 0.05, "area": 12.12e-6},
        "tensile.elastic_modulus": {"method": "manual", "manual_modulus": 200e9},
        "tensile.proof_stress": {"youngs_modulus": 200e9},
        "tensile.true_plastic": {
            "youngs_modulus": 200e9,
            "necking_policy": "manual_index",
            "manual_index": 100,
        },
    }

    def test_필수라고_적은_칸은_빼면_실제로_실패한다(self) -> None:
        for plugin_id, options in self.FULL.items():
            plugin = registry.get(plugin_id)
            for spec in plugin.params:
                if not spec.required or spec.name not in options:
                    continue
                without = {k: v for k, v in options.items() if k != spec.name}
                with pytest.raises(processing.ProcessingError):
                    self._run(plugin_id, without)

    def test_필수가_아니라고_한_칸은_빼도_돈다(self) -> None:
        """멀쩡한 구성을 붉게 칠하지 않기 위한 반대쪽 검사."""
        for plugin_id, options in self.FULL.items():
            plugin = registry.get(plugin_id)
            optional = [
                spec.name
                for spec in plugin.params
                if not spec.required and spec.name in options and spec.default is None
            ]
            for name in optional:
                without = {k: v for k, v in options.items() if k != name}
                self._run(plugin_id, without)

    def test_열을_받는_칸은_필수로_적지_않는다(self) -> None:
        """열 칸은 **기본값이 있거나 사람이 고른다** — 빈 칸 검사와 길이 다르다.

        `blockersAt` 이 열 칸은 따로 본다(그 시점에 그 열이 있는가). 여기에도
        `required` 를 붙이면 같은 것을 두 번 짚는다.
        """
        for plugin in registry.list_plugins("processing"):
            for spec in plugin.params:
                if spec.role == "column":
                    assert not spec.required, f"{plugin.id}.{spec.name}"
