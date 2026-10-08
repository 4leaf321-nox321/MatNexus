"""유변 확장 — **Cross·Carreau 가 확장 폴더 하나로 붙고, 답을 아는 곡선을 되돌린다.**

fixture(`rheometer_flow_sweep.csv`)는 Carreau η₀=12·η∞=0.05·λ=0.5·n=0.35 로 만든
합성 TRIOS 파일이다. 로그 잔차로 맞추는 이유가 여기서 보인다 — 점도가 12 에서 0.26
까지 40배 내려가는데, 선형 잔차면 0.3 근처는 두 배 틀려도 RMSE 에 안 잡힌다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.modules.tests.legacy_profiles import TA_HR_FLOW_DEFINITION
from matcore import export, fitting
from matcore.readers import profile as profiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FLOW = FIXTURES / "rheometer_flow_sweep.csv"


def _curve() -> tuple[np.ndarray, np.ndarray]:
    out = profiles.apply(TA_HR_FLOW_DEFINITION, FLOW.read_bytes())
    by_key = {channel.key: np.asarray(channel.values) for channel in out.curves[0].channels}
    return by_key["shear_rate"], by_key["viscosity"]


class Test등록:
    def test_레지스트리에_내장과_나란히_서고_축과_블록을_안다(self) -> None:
        for key in ("cross", "carreau"):
            family = fitting.FAMILIES[key]
            assert (family.x_column, family.y_column) == ("shear_rate", "viscosity")
            assert family.block == "rheology"
            assert family.residual == "log"
        # 재료군이 고분자면 유변 식이 목록에 있고, 금속이면 없다.
        assert {"cross", "carreau"} <= {f.key for f in fitting.families_for("Polymer")}
        assert not {"cross", "carreau"} & {f.key for f in fitting.families_for("Metal")}


class Test적합:
    def test_Carreau_가_답을_그대로_되돌린다(self) -> None:
        rate, viscosity = _curve()
        x, y, _ = fitting.FAMILIES["carreau"].prepare(rate, viscosity)
        result = fitting.fit("carreau", x, y)
        got = {p.name: p.value for p in result.parameters}
        assert got["eta_0"] == pytest.approx(12.0, rel=1e-3)
        assert got["eta_inf"] == pytest.approx(0.05, rel=1e-2)
        assert got["lambda"] == pytest.approx(0.5, rel=1e-3)
        assert got["n"] == pytest.approx(0.35, rel=1e-3)
        assert result.r_squared == pytest.approx(1.0, abs=1e-6)
        assert [p.si_unit for p in result.parameters] == ["Pa.s", "Pa.s", "s", "1"]

    def test_Cross_도_같은_곡선을_거의_따라가고_영전단_점도가_견줄_만하다(self) -> None:
        rate, viscosity = _curve()
        x, y, _ = fitting.FAMILIES["cross"].prepare(rate, viscosity)
        result = fitting.fit("cross", x, y)
        assert result.r_squared > 0.99
        extras = fitting.FAMILIES["cross"].extras(
            np.asarray([p.value for p in result.parameters])
        )
        assert extras["zero_shear_viscosity"] == pytest.approx(12.0, rel=0.15)

    def test_로그_잔차라서_낮은_점도_구간도_맞는다(self) -> None:
        """선형 잔차였다면 큰 점도 몇 점이 적합을 지배해 박화 구간이 틀린다."""
        rate, viscosity = _curve()
        x, y, _ = fitting.FAMILIES["carreau"].prepare(rate, viscosity)
        result = fitting.fit("carreau", x, y)
        tail = x > 100.0
        predicted = result.evaluate(x[tail])
        assert np.max(np.abs(predicted / y[tail] - 1.0)) < 0.01

    def test_전단율_0_과_점도_0_이하는_빼고_말한다(self) -> None:
        rate, viscosity = _curve()
        x, _y, notes = fitting.FAMILIES["carreau"].prepare(
            np.concatenate([[0.0], rate]), np.concatenate([[12.0], viscosity])
        )
        assert x.size == rate.size
        assert any("0 이하" in one for one in notes)


class Test덱:
    def _deck(self, key: str) -> export.Deck:
        rate, viscosity = _curve()
        x, y, _ = fitting.FAMILIES[key].prepare(rate, viscosity)
        result = fitting.fit(key, x, y)
        blocks = {
            "elastic": {"values": {"density": 900.0}},
            "rheology": {
                "values": {
                    "family": key,
                    "label": result.label,
                    "r_squared": result.r_squared,
                },
                "rows": [
                    {"name": p.name, "value": p.value, "si_unit": p.si_unit}
                    for p in result.parameters
                ],
            },
        }
        return export.Deck(name="PP_MELT", solver_id=1, blocks=blocks)

    def test_Carreau_는_CARREAU_YASUDA_a_2_로_나간다(self) -> None:
        text = export.render("abaqus_viscosity", self._deck("carreau")).text
        assert "*VISCOSITY, DEFINITION=CARREAU-YASUDA" in text
        line = next(one for one in text.splitlines() if one.endswith(", 2.0"))
        eta0, _eta_inf, lam, n, _a = (float(v) for v in line.split(","))
        assert (eta0, lam, n) == pytest.approx((12.0, 0.5, 0.35), rel=1e-2)
        assert "*DENSITY" in text

    def test_Cross_는_지수를_Abaqus_규약_1_n_으로_돌려_적는다(self) -> None:
        """그대로 적으면 박화가 반대로 간다 — 조용히 틀리는 자리라 시험이 지킨다."""
        deck = self._deck("cross")
        m = next(row["value"] for row in deck.rows("rheology") if row["name"] == "m")
        text = export.render("abaqus_viscosity", deck).text
        assert "*VISCOSITY, DEFINITION=CROSS" in text
        data = next(
            one
            for one in text.splitlines()
            if one and not one.startswith("*") and one.count(",") == 3
        )
        n = float(data.split(",")[3])
        assert n == pytest.approx(1.0 - m, rel=1e-6)

    def test_mm_N_tonne_계로_내면_점도가_1e_6_배가_된다(self) -> None:
        """1 Pa·s = 1e-6 N·s/mm². `MPa.s` 기호를 썼다면 단위표가 `mPa.s` 로 읽어 1e9 배
        틀렸을 것이다 — 이 시험이 그 자리를 지킨다."""
        deck = export.to_system(self._deck("carreau"), export.systems.MM_N_TONNE)
        eta0 = next(row["value"] for row in deck.rows("rheology") if row["name"] == "eta_0")
        assert eta0 == pytest.approx(12.0e-6, rel=1e-3)


def _tens(line: str) -> list[str]:
    """LS-DYNA 10칸 줄을 칸으로 — 솔버가 읽는 그대로."""
    return [line[start : start + 10].strip() for start in range(0, 80, 10)]


class TestICFD:
    """LS-DYNA ICFD `*ICFD_MODEL_NONNEWT` — R16 매뉴얼 Vol III 의 식과 칸(2026-10-08)."""

    def _deck(self, key: str) -> export.Deck:
        return Test덱()._deck(key)

    def _after(self, text: str, label: str) -> list[str]:
        lines = text.splitlines()
        at = next(i for i, line in enumerate(lines) if line.startswith(label))
        return _tens(lines[at + 1])

    def test_Cross_는_Cross_II_이고_지수를_돌리지_않는다(self) -> None:
        """Cross II 는 (λγ̇)^n — 우리 m 그대로다. Abaqus 처럼 1-m 으로 돌리면 박화가 반대로
        간다. NNID=3(Cross)은 μ∞ 가 없어 쓰지 않는다."""
        deck = self._deck("cross")
        rows = {row["name"]: row["value"] for row in deck.rows("rheology")}
        text = export.render("dyna_viscosity", deck).text
        assert self._after(text, "$   nnmoid      nnid")[:2] == ["1", "5"]
        k, n, mumin, lam = (float(v) for v in self._after(text, "$        k")[:4])
        assert (k, n, mumin, lam) == pytest.approx(
            (rows["eta_0"], rows["m"], rows["eta_inf"], rows["lambda"]), rel=1e-6
        )

    def test_Carreau_는_NNID_2_이고_온도_항을_끈다(self) -> None:
        deck = self._deck("carreau")
        text = export.render("dyna_viscosity", deck).text
        assert self._after(text, "$   nnmoid      nnid")[:2] == ["1", "2"]
        fields = self._after(text, "$        k")
        assert float(fields[1]) == pytest.approx(0.35, rel=1e-2)  # N = n
        assert float(fields[3]) == pytest.approx(0.5, rel=1e-2)  # LAMBDA — 기본 1e30
        assert float(fields[4]) == 0.0  # ALPHA = 0 → H(T) = 1

    def test_ICFD_MAT_은_빈_열_카드_뒤에_NNMOID_를_가리킨다(self) -> None:
        """둘째 카드(열)를 0 으로 채우면 PRT 기본 0.85 가 0 이 된다 — 매뉴얼대로 빈 카드."""
        text = export.render("dyna_viscosity", self._deck("cross")).text
        lines = text.splitlines()
        at = lines.index("*ICFD_MAT")
        cards = [line for line in lines[at + 1 :] if not line.startswith("$")]
        assert _tens(cards[0])[:3] == ["1", "1", "900.0"]  # MID · FLG=1(비압축) · RO
        assert cards[1] == ""
        assert _tens(cards[2])[0] == "1"  # NNMOID

    def test_밀도가_없으면_목록에서_막힌다(self) -> None:
        deck = self._deck("cross")
        bare = export.Deck(
            name=deck.name, solver_id=1, blocks={"rheology": deck.blocks["rheology"]}
        )
        assert "dyna_viscosity" not in export.available_formats(bare)
        assert "abaqus_viscosity" in export.available_formats(bare)
