"""ANSYS 흡습 스니펫(`ansys_moisture`, 2026-10-08) — `MP,DXX` · `CSAT` · `BETX`.

여기서 무는 것은 **읽히기는 하는데 값이 다른** 종류다:

    단위    mm·N·tonne 에서 확산계수는 10⁶ 배, CSAT 은 10⁻¹² 배, β 는 10¹² 배 — β·CSAT
            (팽윤 변형의 크기)은 계와 상관없이 같아야 한다
    환경    CSAT 이 없는데 「이 습도의 포화 농도」 라고 적으면 덱이 없는 값을 말한다
"""

from __future__ import annotations

from typing import Any

from matcore import cards, export
from matcore.export import ansys  # noqa: F401  (렌더러 등록)
from matcore.export.systems import MM_N_TONNE, SI

cards.load_builtin()

#: EMC 85 °C/85 %RH — 포화 농도는 220.2 mol/m³ 를 kg/m³ 로 옮긴 값.
EMC: dict[str, Any] = {
    "moisture": {
        "values": {
            "moisture_diffusivity": 2.5e-13,
            "moisture_saturation": 3.966903,
            "hygroscopic_expansion": 1.7e-4,
            "temperature": 358.15,
            "humidity": 0.85,
        }
    }
}


def deck(blocks: dict[str, Any]) -> export.Deck:
    return export.Deck(name="EMC", solver_id=7, blocks=blocks, provenance=("EMC",))


def mp(text: str) -> dict[str, float]:
    """`MP,<이름>,MNX_MAT,<값>` 줄 → {이름: 값}."""
    found: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("MP,"):
            _, label, _, value = line.split(",")
            found[label] = float(value)
    return found


def without(key: str) -> dict[str, Any]:
    values = {k: v for k, v in EMC["moisture"]["values"].items() if k != key}
    return {"moisture": {"values": values}}


class Test흡습_스니펫:
    def test_세_방향과_CSAT_을_적고_환경을_머리에_말한다(self) -> None:
        result = export.render("ansys_moisture", deck(EMC), SI)
        found = mp(result.text)
        assert found == {
            "DXX": 2.5e-13,
            "DYY": 2.5e-13,
            "DZZ": 2.5e-13,
            "CSAT": 3.966903,
            "BETX": 1.7e-4,
            "BETY": 1.7e-4,
            "BETZ": 1.7e-4,
        }
        assert "! Values measured at 358.15 K" in result.text
        assert "! CSAT is the saturation at RH 85 %" in result.text
        # CREF 는 안 적는다 — 기본 0(마른 상태)이 흡습 팽창 계수의 기준이다.
        assert "MP,CREF" not in result.text
        assert result.notes == ()

    def test_mm_계에서도_팽윤의_크기는_같다(self) -> None:
        """β 와 CSAT 을 한쪽만 옮기면 팽윤 변형이 10¹² 배 틀린다 — 덱은 멀쩡히 돈다."""
        si, mm = (
            mp(export.render("ansys_moisture", deck(EMC), SI).text),
            mp(export.render("ansys_moisture", deck(EMC), MM_N_TONNE).text),
        )
        assert mm["DXX"] == 2.5e-13 * 1e6  # m²/s → mm²/s
        assert mm["CSAT"] == 3.966903e-12  # kg/m³ → tonne/mm³
        assert abs(mm["BETX"] * mm["CSAT"] - si["BETX"] * si["CSAT"]) < 1e-15

    def test_CSAT_이_없으면_실제_농도라고_말하고_습도도_안_말한다(self) -> None:
        result = export.render("ansys_moisture", deck(without("moisture_saturation")), SI)
        assert "CSAT" not in mp(result.text)
        assert "! CSAT not on the card" in result.text
        assert "saturation at RH" not in result.text
        assert any("정규화 농도" in note for note in result.notes)

    def test_흡습_팽창_계수가_없으면_팽윤이_없다고_말한다(self) -> None:
        result = export.render("ansys_moisture", deck(without("hygroscopic_expansion")), SI)
        assert not {"BETX", "BETY", "BETZ"} & set(mp(result.text))
        assert any("팽윤 변형이 생기지 않습니다" in note for note in result.notes)

    def test_확산계수가_없으면_낼_수_없다(self) -> None:
        missing = export.missing_for(
            deck(without("moisture_diffusivity")), export.renderer("ansys_moisture")
        )
        assert missing and "수분 확산계수" in missing[0]
