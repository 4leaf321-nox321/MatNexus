"""덱의 탄성 대체 판정 · 받은 덱의 ro · e · pr (2026-11-17, HWAX 연결).

대체 판정        서버가 고른 탄성 형식 · 선택 소성 표가 빈 형식 · 항복 없이 지은 표 —
                 사람이 고른 탄성 형식 · 점탄성은 대체가 아니다
받은 덱 읽기     고정폭 · 쉼표 · _TITLE · 긴 칸(+) · 칸 차례를 모르는 키워드는 안 읽는다
값 넣기          덱 단위 → SI, 출처 줄을 바꾼다
"""

from __future__ import annotations

import pytest

from matcore import synth
from matcore.export import Deck, Need, Rendered, Renderer, dyna_base, fallback
from matcore.export.systems import MM_N_TONNE


def _renderer(key: str, *needs: Need) -> Renderer:
    return Renderer(
        key=key,
        label=key,
        extension="k",
        describe="",
        render=lambda deck: Rendered(text=""),
        needs=needs,
    )


ELASTIC = _renderer("dyna_elastic", Need("elastic", values=("youngs_modulus",)))
PLASTIC = _renderer(
    "dyna", Need("elastic", values=("youngs_modulus",)), Need("table", rows_min=2)
)
OPTIONAL_PLASTIC = _renderer(
    "deck_custom", Need("elastic", values=("youngs_modulus",)), Need("table", optional=True)
)
VISCO = _renderer(
    "dyna_viscoelastic", Need("elastic", values=("youngs_modulus",)), Need("viscoelastic")
)
THERMAL = _renderer("dyna_thermal", Need("thermal"), Need("elastic", optional=True))

TABLE = {
    "rows": [
        {"plastic_strain": 0.0, "true_stress": 1e8},
        {"plastic_strain": 0.1, "true_stress": 2e8},
    ]
}


def _deck(**blocks: object) -> Deck:
    return Deck(
        name="M",
        solver_id=1,
        blocks={"elastic": {"values": {"youngs_modulus": 2e11}}, **blocks},
    )


class Test대체_판정:
    def test_서버가_고른_탄성_형식은_대체다(self) -> None:
        assert fallback.kind(ELASTIC, _deck(), server_chose=True) == "elastic"

    def test_사람이_고른_탄성_형식은_대체가_아니다(self) -> None:
        assert fallback.kind(ELASTIC, _deck(), server_chose=False) is None

    def test_선택_소성_표가_비면_고른_형식이어도_대체다(self) -> None:
        assert fallback.kind(OPTIONAL_PLASTIC, _deck(), server_chose=False) == "elastic"
        assert fallback.kind(OPTIONAL_PLASTIC, _deck(table=TABLE), server_chose=False) is None

    def test_소성_표가_있으면_대체가_아니다(self) -> None:
        assert fallback.kind(PLASTIC, _deck(table=TABLE), server_chose=True) is None

    def test_항복_없이_지은_표는_대체다(self) -> None:
        deck = Deck(
            name="M",
            solver_id=1,
            blocks={"table": TABLE},
            provenance=(f"합성 소성 표 — 실측이 아니다. 모델: {synth.YIELD_FROM_UTS_MODEL}",),
        )
        assert fallback.kind(PLASTIC, deck, server_chose=True) == "yield_from_uts"

    def test_점탄성_열_형식은_대체가_아니다(self) -> None:
        assert fallback.kind(VISCO, _deck(), server_chose=True) is None
        assert fallback.kind(THERMAL, _deck(), server_chose=True) is None


class Test받은_덱_읽기:
    def test_고정폭(self) -> None:
        text = (
            "*KEYWORD\n*MAT_PIECEWISE_LINEAR_PLASTICITY\n"
            "$      mid        ro         e        pr\n"
            "        12   7.80E-9  200000.0      0.30\n*END\n"
        )
        got = dyna_base.read(text).materials[12]
        assert got.values == {"ro": pytest.approx(7.8e-9), "e": 200000.0, "pr": 0.3}
        assert got.keyword == "*MAT_PIECEWISE_LINEAR_PLASTICITY"

    def test_쉼표_TITLE_번호_키워드(self) -> None:
        text = "*MAT_024_TITLE\nsteel part\n3,7.85e-9,210000,0.29,250\n"
        got = dyna_base.read(text).materials[3]
        assert got.values == {"ro": pytest.approx(7.85e-9), "e": 210000.0, "pr": 0.29}

    def test_긴_칸(self) -> None:
        cells = ["5", "2.7e-9", "70000.", "0.33"]
        text = "*MAT_ELASTIC+\n" + "".join(f"{one:>20}" for one in cells) + "\n"
        assert dyna_base.read(text).materials[5].values["e"] == 70000.0

    def test_칸_차례를_모르는_키워드는_안_읽는다(self) -> None:
        """*MAT_GENERAL_VISCOELASTIC 의 셋째 칸은 BULK 다 — 읽으면 체적탄성률이 탄성계수다."""
        text = "*MAT_GENERAL_VISCOELASTIC\n         9   1.1e-9    3000.0\n"
        found = dyna_base.read(text)
        assert 9 not in found.materials
        assert found.skipped == ("*MAT_GENERAL_VISCOELASTIC (MID 9)",)

    def test_숫자가_아닌_칸은_그_칸만_못_읽는다(self) -> None:
        got = dyna_base.read("*MAT_ELASTIC\n4,&ro,200000.,\n").materials[4]
        assert got.values == {"e": 200000.0}
        assert "ro(「&ro」)" in got.unread and "pr(빈 칸)" in got.unread


class Test값_넣기:
    def test_덱_단위를_SI_로_넣고_출처_줄을_바꾼다(self) -> None:
        deck = Deck(
            name="M",
            solver_id=7,
            blocks={
                "elastic": {
                    "values": {
                        "youngs_modulus": 2.05e11,
                        "poisson_ratio": 0.29,
                        "density": 7850.0,
                    },
                    "rows": [{"temperature": 300.0, "youngs_modulus": 2.05e11}],
                }
            },
            provenance=(
                "탄성계수: 이 시험들에서 잰 값",
                "밀도: 재료에 적힌 공칭값",
                "그 밖의 줄",
            ),
        )
        base = dyna_base.BaseMaterial(
            mid=7, keyword="*MAT_024", values={"ro": 7.8e-9, "e": 200000.0, "pr": 0.3}
        )
        made = dyna_base.keep(deck, base, MM_N_TONNE)
        values = made.deck.values("elastic")
        assert values["youngs_modulus"] == pytest.approx(2.0e11)
        assert values["density"] == pytest.approx(7800.0)
        assert values["poisson_ratio"] == pytest.approx(0.3)
        assert made.values == {"ro": 7.8e-9, "e": 200000.0, "pr": 0.3}
        # 지킨 값의 출처는 받은 덱 — MatNexus 의 출처 줄이 남으면 거짓 출처다.
        assert not any(
            line.startswith(("탄성계수:", "밀도:")) for line in made.deck.provenance
        )
        assert "그 밖의 줄" in made.deck.provenance
        assert any(
            line.startswith("받은 덱의 값으로 둠(MID 7") for line in made.deck.provenance
        )
        # 온도별 표는 뺀다 — 덱 값 하나와 갈린다.
        assert made.deck.rows("elastic") == []
        assert any("온도별 탄성 표" in one for one in made.notes)
