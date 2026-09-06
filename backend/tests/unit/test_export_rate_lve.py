"""속도 의존 덱과 DMA 선형 탄성 덱 — **블록이 있으면 형식이 열리고, 순서가 맞다.**

지키는 것은 셋이다.

    속도마다 *PLASTIC, RATE= 한 벌      속도 순, 응력이 먼저
    속도가 하나면 이 형식은 안 열린다   그 덱은 `abaqus` 가 낸다
    LVE 덱은 유효 범위를 적는다        한계 변형률·주파수·온도가 주석에 있다
"""

from __future__ import annotations

from typing import Any

import pytest

from matcore import cards, export

cards.load_builtin()

ELASTIC = {"values": {"youngs_modulus": 2.0e9, "poisson_ratio": 0.35, "density": 1200.0}}


def rate_deck(
    rates: tuple[float, ...] = (0.001, 1.0, 100.0), model: str = "none"
) -> export.Deck:
    rows: list[dict[str, Any]] = []
    for rate in rates:
        for strain, stress in ((0.0, 30e6), (0.05, 40e6), (0.2, 48e6)):
            rows.append(
                {
                    "strain_rate": rate,
                    "plastic_strain": strain,
                    "true_stress": stress * (1 + rate / 1000),
                }
            )
    values: dict[str, Any] = {
        "source": "rate_family",
        "rate_count": len(rates),
        "reference_rate": rates[0],
        "model": model,
    }
    if model == "cowper_symonds":
        values.update({"cs_d": 1000.0, "cs_p": 5.0, "model_r_squared": 0.99})
    return export.Deck(
        name="RATE",
        solver_id=1,
        blocks={
            "elastic": ELASTIC,
            "table": {"rows": [row for row in rows if row["strain_rate"] == rates[0]]},
            "rate_table": {"values": values, "rows": rows},
        },
        provenance=("시편 6개 · PA66",),
    )


def lve_deck(**extra: float) -> export.Deck:
    return export.Deck(
        name="LVE",
        solver_id=2,
        blocks={
            "elastic": ELASTIC,
            "lve": {
                "values": {
                    "youngs_modulus": 2.0e9,
                    "lve_strain_limit": 0.004,
                    "sample_count": 3,
                    **extra,
                }
            },
        },
        provenance=("시편 3개 · PA66",),
    )


class Test속도_의존_덱:
    def test_속도마다_PLASTIC_한_벌이_속도_순으로_선다(self) -> None:
        text = export.render("abaqus_rate", rate_deck()).text
        headers = [line for line in text.splitlines() if line.startswith("*PLASTIC")]
        assert len(headers) == 3
        assert [line.split("RATE=")[1] for line in headers] == [
            f"{rate:.12E}" for rate in (0.001, 1.0, 100.0)
        ]
        # **응력이 먼저, 소성변형률이 나중이다.** OpenRadioss 와 반대다.
        body = text.split(headers[0])[1].splitlines()[1]
        stress, strain = (float(one) for one in body.split(","))
        assert stress > 1e6 and strain == 0.0

    def test_속도가_하나면_이_형식은_안_열린다(self) -> None:
        deck = rate_deck(rates=(0.001,))
        assert "abaqus_rate" not in export.available_formats(deck)
        # 그 대신 보통 Abaqus 는 낸다 — 기준 표(`table`)가 있으니.
        assert "abaqus" in export.available_formats(deck)

    def test_둘_이상이면_열리고_보통_Abaqus_도_남는다(self) -> None:
        formats = export.available_formats(rate_deck())
        assert "abaqus_rate" in formats
        assert "abaqus" in formats

    def test_식은_주석으로만_적는다(self) -> None:
        text = export.render("abaqus_rate", rate_deck(model="cowper_symonds")).text
        assert "Cowper-Symonds summary" in text
        assert "*RATE DEPENDENT" not in text

    def test_속도_행에_값이_빠지면_거부한다(self) -> None:
        deck = rate_deck()
        deck.blocks["rate_table"]["rows"][0] = {"strain_rate": 0.001}
        with pytest.raises(export.ExportError):
            export.render("abaqus_rate", deck)


class TestDMA_선형_탄성_덱:
    def test_ELASTIC_만_내고_유효_범위를_적는다(self) -> None:
        text = export.render(
            "abaqus_lve", lve_deck(frequency_hz=1.0, temperature_k=298.15)
        ).text
        assert "*ELASTIC" in text
        assert "*PLASTIC" not in text
        assert "valid up to strain 4.000000000000E-03" in text
        assert "1.000000000000E+00 Hz" in text
        assert "298.15" in text or "2.981500000000E+02 K" in text
        assert "from 3 specimen(s)" in text

    def test_소성_표가_없어도_이_형식은_열리고_보통_Abaqus_는_안_열린다(self) -> None:
        formats = export.available_formats(lve_deck())
        assert "abaqus_lve" in formats
        assert "abaqus" not in formats
        assert "json" in formats

    def test_한계_변형률이_없으면_안_열린다(self) -> None:
        deck = lve_deck()
        del deck.blocks["lve"]["values"]["lve_strain_limit"]
        assert "abaqus_lve" not in export.available_formats(deck)


def test_속도가_하나뿐이면_낼_수_있다고_말하지_않는다() -> None:
    """메뉴가 「가능」 이라 해 놓고 내려받기가 422 였다(2026-09-05 순환 점검)."""
    one = rate_deck(rates=(0.001,))
    assert "abaqus_rate" not in export.available_formats(one)
    assert any(
        "rate_count" in said or "속도" in said
        for said in export.missing_for(one, "abaqus_rate")
    )
    assert "abaqus_rate" in export.available_formats(rate_deck())
