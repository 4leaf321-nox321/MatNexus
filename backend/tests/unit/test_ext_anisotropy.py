"""이방성 확장 — r값과 세 방향 묶음.

**운영과 같은 길로 읽는다**(확장 로더). 폴더를 직접 import 하면 로더가 쓰는 이름과
달라 등록이 두 번 돌고, 그러면 여기서만 나는 오류를 쫓게 된다.

여기서 지키는 것:

    못 믿을 값은 안 낸다         점이 모자라거나 직선이 아니면 r 을 비운다
    세 방향이 다 있어야 한다     빠진 방향을 옆 것으로 대신하면 숫자 안에 숨는다
    어디서 온 값인지 남는다      사람이 적은 값이 섞이면 카드의 출처가 바뀐다
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from matcore import cards, extensions, groups, processing, registry
from matcore.groups import GroupError, Member
from matcore.processing import Frame

EXTENSIONS = Path(__file__).resolve().parents[2] / "extensions"
extensions.load(EXTENSIONS)
processing.load_builtin()
cards.load_builtin()

STEP = "anisotropy.r_value"
GROUP = "anisotropy.r_family"


#: 시편 초기 폭(m). 장비가 주는 것은 **폭 그 자체**이고 변형률은 단계가 만든다.
WIDTH_0 = 0.0125


def _frame(slope: float, *, points: int = 40, wobble: float = 0.0) -> Frame:
    """길이 변형률 5~20% 구간에서 폭이 `slope` 만큼 따라 줄어드는 곡선.

    `slope` 는 dε_w/dε_l 이고 음수가 정상이다 — 늘면 폭이 준다.
    """
    length = np.linspace(0.05, 0.20, points)
    strain_width = slope * length
    if wobble:
        strain_width = strain_width + wobble * np.sin(np.linspace(0, 20, points))
    return Frame(
        {"strain_true": length, "specimen_width": WIDTH_0 * np.exp(strain_width)},
        {"strain_true": "1", "specimen_width": "m"},
    )


def _run(frame: Frame, **options: Any) -> Any:
    return processing.apply([processing.Step(STEP, options)], frame).stages[-1]


def _member(label: str, orientation: str, r: float, source: str = "measured") -> Member:
    return Member(
        label=label,
        columns={},
        values={"r_value": r},
        meta={"orientation": orientation, "source": source},
    )


class Test곡선에서_재기:
    def test_기울기에서_r_이_나온다(self) -> None:
        """r = -m/(1+m). m=-0.4 면 r=0.667 — 부피 일정 가정에서 나온다."""
        stage = _run(_frame(-0.4))
        values = {one.key: one.value for one in stage.scalars}
        assert values["r_value"] == pytest.approx(0.4 / 0.6, rel=1e-6)
        assert values["r_value_r_squared"] == pytest.approx(1.0)

    def test_점이_모자라면_안_낸다(self) -> None:
        """**값을 안 내되 왜 없는지는 남긴다** — 점 수가 그 자리에 있다."""
        stage = _run(_frame(-0.4, points=6), minimum_strain=0.14, maximum_strain=0.15)
        values = {one.key: one.value for one in stage.scalars}
        assert "r_value" not in values
        assert values["r_value_point_count"] < 5
        assert any("내지 않았습니다" in note for note in stage.notes)

    def test_직선이_아니면_안_낸다(self) -> None:
        """넥킹에 들어갔거나 구간을 잘못 잡은 것이다 — 그 기울기는 r 이 아니다."""
        stage = _run(_frame(-0.4, wobble=0.02))
        assert "r_value" not in {one.key for one in stage.scalars}
        assert any("직선이 아닙니다" in note for note in stage.notes)

    def test_폭이_늘면_채널을_의심한다(self) -> None:
        stage = _run(_frame(0.4))
        assert "r_value" not in {one.key for one in stage.scalars}
        assert any("폭 채널" in note for note in stage.notes)

    def test_폭_채널이_없으면_그_사실을_말한다(self) -> None:
        """자동 시험기에는 폭 신율계가 없다 — 그 시험은 표로 적는 길로 가야 하고,
        그 사실이 오류 문장에 있어야 사람이 다음 수를 안다."""
        bare = Frame({"strain_true": np.linspace(0.05, 0.2, 40)}, {"strain_true": "1"})
        with pytest.raises(processing.ProcessingError) as failed:
            _run(bare)
        assert "specimen_width" in str(failed.value)


class Test세_방향_묶음:
    def _group(self, members: list[Member], **options: Any) -> Any:
        return groups.run_group(GROUP, members, options)

    def test_평균_이방성과_면내_이방성(self) -> None:
        got = self._group(
            [
                _member("MD_01", "MD", 1.8),
                _member("DD_01", "DD", 1.4),
                _member("TD_01", "TD", 2.1),
            ]
        )
        assert got.values["r_bar"] == pytest.approx((1.8 + 2 * 1.4 + 2.1) / 4)
        assert got.values["delta_r"] == pytest.approx((1.8 - 2 * 1.4 + 2.1) / 2)
        # Hill48 도 셋에서 나온다 — G = 1/(1+r₀).
        assert got.values["hill_g"] == pytest.approx(1 / (1 + 1.8))

    def test_같은_방향이_여럿이면_평균한다(self) -> None:
        got = self._group(
            [
                _member("MD_01", "MD", 1.7),
                _member("MD_02", "MD", 1.9),
                _member("DD_01", "DD", 1.4),
                _member("TD_01", "TD", 2.1),
            ]
        )
        assert got.values["r_0"] == pytest.approx(1.8)
        assert got.values["specimen_count"] == 4

    def test_방향이_빠지면_막는다(self) -> None:
        """**옆 방향으로 대신하지 않는다.** 그렇게 나온 r̄ 에는 그 사실이 어디에도 없다."""
        with pytest.raises(GroupError) as failed:
            self._group([_member("MD_01", "MD", 1.8), _member("TD_01", "TD", 2.1)])
        assert "45" in str(failed.value)

    def test_방향이_NA_면_빼고_막는다(self) -> None:
        with pytest.raises(GroupError):
            self._group(
                [
                    _member("NA_01", "NA", 1.8),
                    _member("DD_01", "DD", 1.4),
                    _member("TD_01", "TD", 2.1),
                ]
            )

    def test_사람이_적은_값이_섞이면_카드의_출처가_바뀐다(self) -> None:
        """폭 채널이 없는 장비의 시험은 사람이 적는다. 그 값은 우리 곡선으로 되짚을
        수 없으므로 **가장 약한 쪽을 따른다** — 등급이 그만큼 내려간다."""
        got = self._group(
            [
                _member("MD_01", "MD", 1.8),
                _member("DD_01", "DD", 1.4, source="stated"),
                _member("TD_01", "TD", 2.1),
            ]
        )
        assert got.values["stated_count"] == 1
        assert any("적은 값" in line for line in got.warnings)

        blocks = registry.get(GROUP).meta["card"](got.values, got.detail, got.warnings)
        assert blocks["anisotropy"]["values"]["r_bar_source"] == "manual"

    def test_전부_잰_값이면_measured(self) -> None:
        got = self._group(
            [
                _member("MD_01", "MD", 1.8),
                _member("DD_01", "DD", 1.4),
                _member("TD_01", "TD", 2.1),
            ]
        )
        blocks = registry.get(GROUP).meta["card"](got.values, got.detail, got.warnings)
        assert blocks["anisotropy"]["values"]["r_bar_source"] == "measured"


class Test로더로_읽힌다:
    def test_처리_단계와_묶음이_나란히_선다(self) -> None:
        ids = {plugin.id for plugin in registry.list_plugins()}
        assert {STEP, GROUP} <= ids
        assert GROUP in {one.id for one in groups.groupings(applies_to="tensile")}

    def test_카드_블록이_방향을_가로지른다고_선언한다(self) -> None:
        """이 선언 하나가 「카드 한 장 = 방향 하나」 규칙의 예외를 켠다."""
        spec = cards.block("anisotropy")
        assert spec.meta.get("cross_orientation") is True
        assert {one.key for one in spec.produces} >= {"r_bar", "delta_r", "hill_n"}

    def test_묶음이_두_길에서_값을_받는다고_선언한다(self) -> None:
        """폭 채널이 있는 장비와 없는 장비가 한 묶음에 들어온다."""
        rule = registry.get(GROUP).meta["members"]
        assert rule["from"] == "measured_or_stated"
        assert rule["specimen"] == ["orientation"]
