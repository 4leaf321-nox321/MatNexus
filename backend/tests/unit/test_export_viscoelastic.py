"""점탄성 솔버 카드 — **DMA 에서 해석까지의 마지막 한 걸음.**

여기서 나온 텍스트가 그대로 Abaqus 덱에 들어간다. 틀려도 솔버는 대개 오류 없이
돌고 **다른 재료로 계산한다** — 그게 이 파일이 지키는 것들이다.

## OpenRadioss 는 없다

`/MAT/LAW62` 는 고무 초탄성(Ogden)+Prony 경로라 선형 점탄성과 다른 모형이다.
65 도 같은 이유로 Abaqus 만 낸다(소스에 그렇게 적혀 있다). **검증 못 하는 솔버
문법을 지어내는 것이 이 도메인에서 가장 비싼 결함이다.**
"""

from __future__ import annotations

import pytest

from matcore.export import Deck, ExportError, list_renderers, render
from matcore.prony import PronySeries, PronyTerm

SERIES = PronySeries(
    equilibrium_pa=5.0e6,
    terms=(
        PronyTerm(modulus_pa=2.0e8, relaxation_time_s=1.0e-2),
        PronyTerm(modulus_pa=8.0e8, relaxation_time_s=1.0e0),
        PronyTerm(modulus_pa=3.0e8, relaxation_time_s=1.0e2),
    ),
    normalized_rmse=0.001,
    bic=-100.0,
)


def card(
    *,
    youngs_modulus: float | None = None,
    poisson_ratio: float | None = 0.45,
    density: float | None = 1100.0,
    prony: bool = True,
    reference: float | None = 293.15,
) -> Deck:
    """점탄성 덱 하나. **블록으로 담는다.**

    `*ELASTIC` 에 들어갈 E₀ 는 **탄성 블록**이 든다. 평형 탄성률이 실리면 재료가
    통째로 무르게 계산되는데 덱은 멀쩡히 돌고 결과도 그럴듯하다.
    """
    elastic = {
        key: value
        for key, value in (
            (
                "youngs_modulus",
                SERIES.instantaneous_pa if youngs_modulus is None else youngs_modulus,
            ),
            ("poisson_ratio", poisson_ratio),
            ("density", density),
        )
        if value is not None
    }
    blocks: dict[str, object] = {"elastic": {"values": elastic}}
    if prony:
        blocks["viscoelastic"] = {
            "values": {"reference_temperature_k": reference},
            "rows": [
                {
                    "relative_modulus": ratio,
                    "relaxation_time_s": term.relaxation_time_s,
                    "modulus_pa": term.modulus_pa,
                }
                for ratio, term in zip(SERIES.relative_moduli, SERIES.terms, strict=True)
            ],
        }
    return Deck(
        name="EPDM_60",
        solver_id=42,
        blocks=blocks,
        provenance=("DMA 스윕 6단 · WLF 겹침 · Prony 3항",),
    )


class Test카드:
    def test_키워드가_전부_들어간다(self) -> None:
        text = render("abaqus_viscoelastic", card()).text
        for keyword in ("*MATERIAL", "*ELASTIC", "*VISCOELASTIC, TIME=PRONY"):
            assert keyword in text, keyword

    def test_Prony_행이_g_k_tau_순서다(self) -> None:
        """**순서가 뒤바뀌면 솔버가 오류 없이 다른 재료를 만든다.**"""
        text = render("abaqus_viscoelastic", card()).text
        rows = [
            line
            for line in text.splitlines()
            if line and not line.startswith("*") and not line.startswith("**")
        ]
        prony_rows = rows[-3:]
        assert len(prony_rows) == 3
        for row, term in zip(prony_rows, SERIES.terms, strict=True):
            g_text, k_text, tau_text = (part.strip() for part in row.split(","))
            assert float(k_text) == 0.0
            assert float(tau_text) == pytest.approx(term.relaxation_time_s, rel=1e-6)
            assert 0 < float(g_text) < 1

    def test_완화시간이_커지는_순서로_나간다(self) -> None:
        text = render("abaqus_viscoelastic", card()).text
        taus = [
            float(line.split(",")[2])
            for line in text.splitlines()
            if line.count(",") == 2 and not line.startswith("*")
        ]
        assert taus == sorted(taus)


class Test적어야하는것:
    def test_순간_탄성률임을_덱에_적는다(self) -> None:
        """Abaqus 는 `*VISCOELASTIC` 이 있으면 `*ELASTIC` 을 순간 탄성률로 읽는다.
        평형 탄성률을 넣으면 재료가 통째로 무르게 계산되는데 덱은 멀쩡히 돈다."""
        text = render("abaqus_viscoelastic", card()).text
        assert "instantaneous" in text

    def test_체적을_안_쟀다고_적는다(self) -> None:
        """`k` 를 0 으로 두는 것은 **가정**이다. 가정은 덱에 남아야 한다."""
        text = render("abaqus_viscoelastic", card()).text
        assert "Bulk relaxation" in text and "not measured" in text

    def test_전단_비율을_E_에서_가져왔다고_적는다(self) -> None:
        """푸아송비가 시간에 안 변한다는 가정이다."""
        text = render("abaqus_viscoelastic", card()).text
        assert "constant Poisson" in text

    def test_유효_온도를_적는다(self) -> None:
        """**마스터커브는 기준 온도 하나에서만 유효하다.** 다른 온도로 쓰려면
        `*TRS` 가 따로 필요하다는 사실이 덱에 있어야 한다."""
        text = render("abaqus_viscoelastic", card()).text
        assert "293.15 K" in text and "20.00 C" in text
        assert "*TRS" in text

    def test_온도가_없으면_없다고_말한다(self) -> None:
        """조용히 빼면 이 카드가 어느 온도의 것인지 덱만으로는 알 수 없다."""
        result = render("abaqus_viscoelastic", card(reference=None))
        assert any("기준 온도가 카드에 없어" in note for note in result.notes)

    def test_한_일을_노트로_남긴다(self) -> None:
        result = render("abaqus_viscoelastic", card())
        assert any("Prony 3항" in note for note in result.notes)


class Test거절:
    def test_Prony_가_없으면_거절한다(self) -> None:
        """**빈 블록은 없는 것과 같다.** 전에는 빈 튜플이 기본값이라 `None`
        검사를 빠져나갔는데, 지금은 렌더러가 "점탄성 블록에 표 1줄 이상" 을
        선언하고 그 검사가 한 곳에 있다."""
        with pytest.raises(ExportError, match="점탄성"):
            render("abaqus_viscoelastic", card(prony=False))

    def test_푸아송비가_없으면_거절한다(self) -> None:
        """0.3 을 넣으면 그것이 측정값인지 덱만 봐서는 알 수 없다."""
        with pytest.raises(ExportError, match="푸아송비"):
            render("abaqus_viscoelastic", card(poisson_ratio=None))

    def test_상대_탄성률_합이_1_이상이면_거절한다(self) -> None:
        """평형 탄성률이 0 이하라는 뜻이라 Abaqus 가 거부한다. 여기서 막는 편이
        낫다 — 솔버가 뱉는 오류는 우리 계수 이야기를 안 해 준다."""
        over = card()
        blocks = dict(over.blocks)
        blocks["viscoelastic"] = {
            "values": {"reference_temperature_k": 293.15},
            "rows": [
                {"relative_modulus": 0.6, "relaxation_time_s": 1e-2},
                {"relative_modulus": 0.5, "relaxation_time_s": 1.0},
            ],
        }
        with pytest.raises(ExportError, match="1 이상"):
            render(
                "abaqus_viscoelastic",
                Deck(name=over.name, solver_id=over.solver_id, blocks=blocks),
            )

    def test_밀도는_없어도_된다(self) -> None:
        """`*DENSITY` 는 Abaqus 에서 선택이다. 빼되 **왜 뺐는지 적는다.**"""
        result = render("abaqus_viscoelastic", card(density=None))
        assert "*DENSITY" not in result.text
        assert any("밀도가 카드에 없어" in note for note in result.notes)


class Test형식목록:
    def test_점탄성이_목록에_있다(self) -> None:
        assert "abaqus_viscoelastic" in {item.key for item in list_renderers()}

    def test_OpenRadioss_점탄성은_없다(self) -> None:
        """**LAW62 는 고무 초탄성 경로다.** 검증 못 하는 솔버 문법을 지어내지
        않는다 — 65 도 같은 이유로 Abaqus 만 낸다."""
        keys = {item.key for item in list_renderers()}
        assert not any("radioss" in key and "visco" in key for key in keys)

    def test_탄소성_카드는_그대로다(self) -> None:
        """점탄성을 붙이면서 기존 경로가 안 깨져야 한다."""
        plastic = Deck(
            name="SECC",
            solver_id=1,
            blocks={
                "elastic": {
                    "values": {
                        "youngs_modulus": 200e9,
                        "poisson_ratio": 0.3,
                        "density": 7850.0,
                    }
                },
                "table": {
                    "rows": [
                        {"plastic_strain": 0.0, "true_stress": 300e6},
                        {"plastic_strain": 0.05, "true_stress": 350e6},
                    ]
                },
            },
        )
        assert "*PLASTIC" in render("abaqus", plastic).text
