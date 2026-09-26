"""처리 파이프라인 — **답을 아는 곡선으로 검산한다.**

수치 코드는 "돌아간다" 로는 아무것도 증명되지 않는다. 틀린 탄성계수도 실수로
나오고, 틀린 항복강도도 MPa 단위로 그럴듯하게 나온다. 그래서 여기서는 **답을
미리 아는 곡선**을 만들어 그 값이 나오는지 본다.

합성 곡선: E=200 GPa 의 탄성 구간 + 항복 400 MPa 뒤 선형 경화. 이 곡선의
0.2% 오프셋 항복강도와 탄성계수는 손으로 계산할 수 있다.

그리고 **실제 Zwick 파일**로 한 번 더 돌린다. 합성 데이터만 쓰면 "장비가 실제로
주는 모양" 에서 깨지는 것을 못 잡는다 — 실제로 그 종류의 결함을 여러 번 냈다.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from matcore import parsers, processing, registry
from matcore.parsers import zwick_tra
from matcore.processing import Frame, ProcessingError, Step
from matcore.processing.tensile import AUTO_YIELD_PROFILES, _first_drop

TRA = Path(__file__).resolve().parents[1] / "fixtures" / "Example.tra"
OXFORD_PC_TEST2 = (
    Path(__file__).resolve().parents[1] / "fixtures" / "oxford_pc_fig5_50mm_min_test2.csv"
)

#: 합성 곡선의 정답.
E_TRUE = 200e9
YIELD_TRUE = 400e6
HARDENING = 2e9

#: 이 미만이면 탄성계수를 안 낸다(`matcore.processing.tensile`).
MIN_POINTS_FOR_TRUST = 5


@pytest.fixture(autouse=True)
def _plugins() -> None:
    processing.load_builtin()


def synthetic() -> Frame:
    """E=200 GPa, 항복 400 MPa, 그 뒤 기울기 2 GPa 인 이상적 곡선."""
    yield_strain = YIELD_TRUE / E_TRUE  # 0.002
    elastic = np.linspace(0.0, yield_strain, 40)
    plastic = np.linspace(yield_strain, 0.10, 200)[1:]
    strain = np.concatenate([elastic, plastic])
    stress = np.where(
        strain <= yield_strain,
        E_TRUE * strain,
        YIELD_TRUE + HARDENING * (strain - yield_strain),
    )
    return Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )


S355_PROOF_EXCERPT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "s355_proof_point_excerpt.csv"
)


def s355_toe_corrected_excerpt() -> Frame:
    """Actual BAM-S355-Zy4 rows 438-468 and 521-527, after toe correction.

    Values are derived from displacement/gauge length (50 mm), the measured
    120.582838 mm² area, and the recorded zero-stress shift. Source row and
    physical-line columns retain provenance for the interpolated proof point.
    """
    with S355_PROOF_EXCERPT.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return Frame(
        {
            "strain_engineering": np.asarray(
                [float(row["strain_engineering"]) for row in rows]
            ),
            "stress_engineering": np.asarray(
                [float(row["stress_engineering_pa"]) for row in rows]
            ),
            "source_data_row": np.asarray([float(row["source_data_row"]) for row in rows]),
            "source_physical_line": np.asarray(
                [float(row["source_physical_line"]) for row in rows]
            ),
        },
        {
            "strain_engineering": "1",
            "stress_engineering": "Pa",
            "source_data_row": "1",
            "source_physical_line": "1",
        },
    )


def scalar(result: processing.PipelineResult, key: str) -> float:
    for item in result.scalars:
        if item.key == key:
            return item.value
    raise AssertionError(f"{key} 가 결과에 없습니다: {[s.key for s in result.scalars]}")


class Test탄성계수:
    def test_아는_답이_나온다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {
                        "method": "linear_regression",
                        "minimum_strain": 0.0002,
                        "maximum_strain": 0.0015,
                    },
                )
            ],
            synthetic(),
        )
        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE, rel=1e-6)
        assert scalar(result, "elastic_r_squared") == pytest.approx(1.0, abs=1e-9)

    def test_방법마다_값이_다르고_그_사실이_남는다(self) -> None:
        # 이상적 탄성 구간에서는 세 방법이 같아야 한다. 달라지면 구현이 틀린 것이다.
        frame = synthetic()
        values = {}
        for method in ("linear_regression", "chord", "secant"):
            result = processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"method": method, "minimum_strain": 0.0, "maximum_strain": 0.0015},
                    )
                ],
                frame,
            )
            values[method] = scalar(result, "youngs_modulus")
            # **무엇으로 쟀는지가 값과 함께 남아야** 나중에 비교가 성립한다.
            assert method in result.notes[0]
        for value in values.values():
            assert value == pytest.approx(E_TRUE, rel=1e-6)

    def test_항복_뒤까지_잡으면_R제곱이_떨어진다(self) -> None:
        # 값 자체는 나온다 — 그게 위험한 점이다. 그 사실은 R² 에만 보인다.
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0, "maximum_strain": 0.05},
                )
            ],
            synthetic(),
        )
        assert scalar(result, "elastic_r_squared") < 0.99
        assert any("R²" in note for note in result.notes)

    def test_구간을_변위로_적을_수_있다(self) -> None:
        """**사람이 보는 그래프로 적게 한다.**

        원본 화면은 하중-변위인데 구간은 변형률로만 적을 수 있었다 — 눈으로 고른
        직선 구간을 게이지 길이로 나눠 옮겨 적어야 하고, 그 자리에서 틀린다
        (2026-09-02: 「몇으로 해야 할지 모르겠다」).

        게이지 길이를 다시 받지 않는다 — **곡선에 남은 변위 열**로 옮긴다. 앞
        단계가 무엇으로 나눴든 그것과 어긋나지 않는다.
        """
        gauge = 0.05
        displacement = np.linspace(0.0, 0.005, 201)  # 0 ~ 5 mm
        strain = displacement / gauge
        frame = Frame(
            {
                "displacement": displacement,
                "strain_engineering": strain,
                "stress_engineering": strain * E_TRUE,
            },
            {"displacement": "m", "strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {
                        "method": "linear_regression",
                        "window_basis": "displacement",
                        # **SI(m)로 보낸다** — 화면이 mm 를 받아 환산해 보내는 것과
                        # 같다. 변형률 0.0005~0.0025 와 같은 구간이다(게이지 50 mm).
                        "minimum_displacement": 2.5e-5,
                        "maximum_displacement": 1.25e-4,
                    },
                )
            ],
            frame,
        )
        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE, rel=1e-6)
        # **무엇으로 적었는지 남는다.** 결과를 보는 사람은 변형률만 보게 되는데
        # 사람이 적은 것은 mm 였다.
        assert any("mm 로 적은 구간" in note for note in result.notes)

    def test_변위로_적기로_해_놓고_안_주면_거절한다(self) -> None:
        frame = Frame(
            {
                "displacement": np.linspace(0.0, 0.005, 51),
                "strain_engineering": np.linspace(0.0, 0.1, 51),
                "stress_engineering": np.linspace(0.0, 0.1, 51) * E_TRUE,
            },
            {"displacement": "m", "strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"method": "linear_regression", "window_basis": "displacement"},
                    )
                ],
                frame,
            )

    def test_점이_모자라면_탄성계수를_아예_안_낸다(self) -> None:
        """**여기가 진짜 지키는 것이다 — 나쁜 값을 내보내지 않는다.**

        경고만 붙이고 값은 내던 때가 있었다. 그러면 그 값이 채택돼 통계·물성
        카드·해석 덱까지 흘러가고, 경고는 처리 화면에만 남아 아무도 다시 안 본다.

        실측(2026-08-29): 이관 데이터의 18점짜리 곡선에서 탄성계수 중앙값이
        **1.83 GPa** 로 나왔다 — 강판이면 200 GPa 다. 같은 코드가 2000점짜리
        곡선에서는 200.2 GPa 를 낸다. **R² 로는 이것을 못 막는다** — 2점을
        지나는 직선은 언제나 R²=1 이다.
        """
        strain = np.array([0.0, 0.0008, 0.0012, 0.05])
        sparse = Frame(
            {"strain_engineering": strain, "stress_engineering": strain * E_TRUE},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0005, "maximum_strain": 0.0015},
                )
            ],
            sparse,
        )
        keys = {item.key for item in result.scalars}
        assert "youngs_modulus" not in keys
        # 절편·R² 도 함께 사라진다 — 계수를 못 믿으면 그 둘도 못 믿는다.
        assert "elastic_intercept" not in keys and "elastic_r_squared" not in keys
        # **왜 없는지가 값으로 남는다.** 「값이 없다」 만으로는 고칠 데를 모른다.
        assert scalar(result, "elastic_point_count") == pytest.approx(2.0)
        assert any("탄성계수를 내지 않았습니다" in note for note in result.notes)

    def test_점이_모자라도_그_구간의_기울기는_보여_준다(self) -> None:
        """**「일단 거기 기울기는 계산해 줄 수 있지 않나」 — 맞는 말이다**(2026-09-02).

        사람은 그 숫자를 보면 맞는지 대개 안다: 강판인데 1.8 GPa 면 구간이 틀린
        것이고, 190 GPa 면 점이 둘이어도 쓸 만하다. 그러니 **보여는 준다.**

        다만 **다른 이름으로** 낸다. `youngs_modulus` 로 내면 항복강도가 물어 가고
        카드와 덱까지 흘러간다 — 못 믿는다고 판단해 놓고 뒷문으로 내보내는 셈이다.
        """
        strain = np.array([0.0, 0.0008, 0.0012, 0.05])
        sparse = Frame(
            {"strain_engineering": strain, "stress_engineering": strain * E_TRUE},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0005, "maximum_strain": 0.0015},
                )
            ],
            sparse,
        )
        keys = {item.key for item in result.scalars}
        assert "youngs_modulus" not in keys, "믿을 수 없는 값을 그 이름으로 내면 안 된다"
        assert scalar(result, "elastic_slope_reference") == pytest.approx(E_TRUE, rel=1e-6)
        assert any("참고값" in note for note in result.notes)

    def test_참고_기울기는_NaN_이면_안_낸다(self) -> None:
        """**NaN 은 모든 비교를 통과한다.** 빠진 칸이 섞인 곡선에서 `peak <= 0` 이
        False 가 되어 NaN 기울기가 JSON 응답까지 흘러간다 — JSON 에 NaN 은 없다."""
        from matcore.processing import tensile as tensile_kit

        strain = np.array([0.0, 0.001, 0.002, 0.003])
        stress = np.array([0.0, np.nan, 2.0e8, 3.0e8])
        scalars, note = tensile_kit._reference_slope(strain, stress, 0.1, 0.4)
        assert scalars == ()
        assert note == ""

    def test_참고_기울기는_뒤_단계로_안_간다(self) -> None:
        """**뒷문을 만들지 않는다.** 참고값이 `@youngs_modulus` 를 채우면 그 값이
        항복강도로, 카드로, 덱으로 그대로 간다 — 사람이 「쓰겠다」 고 한 적이 없다."""
        strain = np.array([0.0, 0.0008, 0.0012, 0.05])
        sparse = Frame(
            {"strain_engineering": strain, "stress_engineering": strain * E_TRUE},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 0.0005, "maximum_strain": 0.0015},
                    ),
                    Step(
                        "tensile.proof_stress",
                        {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
                    ),
                ],
                sparse,
            )

    def test_그_값을_쓰려던_단계가_이유를_그대로_전한다(self) -> None:
        """**목록만 보여 주면 사람은 단계를 빼 버린다.**

        탄성계수가 없으면 항복강도 단계가 `@youngs_modulus` 를 못 푼다. 그때
        「쓸 수 있는 값: elastic_point_count, …」 만 적으면 무엇을 고쳐야 하는지
        알 수 없다 — 실사용에서 그 물음이 나왔다(2026-09-02). 앞 단계가 이미 적어
        둔 거절 사유를 그 오류에 함께 싣는다.
        """
        strain = np.array([0.0, 0.0008, 0.0012, 0.05])
        sparse = Frame(
            {"strain_engineering": strain, "stress_engineering": strain * E_TRUE},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError) as caught:
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 0.0005, "maximum_strain": 0.0015},
                    ),
                    Step(
                        "tensile.proof_stress",
                        {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
                    ),
                ],
                sparse,
            )
        said = str(caught.value)
        assert "탄성계수를 내지 않았습니다" in said, said
        # 쓸 수 있는 값 목록도 그대로 둔다 — 참조 이름을 잘못 적은 경우엔 그것이 답이다.
        assert "elastic_point_count" in said

    def test_자동은_토우와_항복_사이를_잡는다(self) -> None:
        """**고정 구간이 매 곡선에 안 맞는 것**이 이 방법의 이유다. 곡선마다 토우
        길이와 항복 시점이 달라, 변형률 절대값으로 박아 두면 어떤 곡선에서는
        토우를 물고 어떤 곡선에서는 항복 뒤를 문다.

        띠를 응력 비율로 잡으면 그 곡선을 따라간다.
        """
        # 토우(위로 굽음) → 직선 → 항복 뒤
        toe = np.linspace(0.0, 0.0002, 40)
        toe_stress = E_TRUE * (toe**2) / 0.0002
        straight = np.linspace(0.0002, 0.004, 300)
        straight_stress = toe_stress[-1] + E_TRUE * (straight - 0.0002)
        after = np.linspace(0.004, 0.20, 600)
        after_stress = straight_stress[-1] + 3e8 * np.log1p((after - 0.004) * 60)
        frame = Frame(
            {
                "strain_engineering": np.concatenate([toe, straight[1:], after[1:]]),
                "stress_engineering": np.concatenate(
                    [toe_stress, straight_stress[1:], after_stress[1:]]
                ),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

        result = processing.apply([Step("tensile.elastic_modulus", {"method": "auto"})], frame)

        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE, rel=0.01)
        # **고른 구간이 값으로 남는다.** 사람이 안 고른 값이라 검토할 근거가 있어야 한다.
        assert scalar(result, "elastic_window_start") > 0.0002, "토우를 물었다"
        assert scalar(result, "elastic_window_end") < 0.004, "항복 뒤를 물었다"

    def test_자동이_소성_구역을_고르지_않는다(self) -> None:
        """**처음 두 판이 여기서 걸렸다**(2026-08-31).

        「R² 기준을 만족하는 가장 긴 창」 은 소성 구역을 골라 2.25 GPa 를 냈다 —
        R² 는 전체 분산 대비 잔차라 넓은 구간에서는 완만히 굽은 곡선도 0.98 을
        넘는다. 「가장 가파른 창」 으로 바꿨더니 잡음이 이겼다.
        """
        result = processing.apply(
            [Step("tensile.elastic_modulus", {"method": "auto"})], synthetic()
        )

        got = scalar(result, "youngs_modulus")
        assert got == pytest.approx(E_TRUE, rel=0.01)
        assert got > HARDENING * 10, "소성 구역 기울기가 뽑혔다"

    def test_자동은_파단_뒤를_안_본다(self) -> None:
        """**실제 곡선은 최대응력 뒤에 떨어진다.** 그 하강 구간의 점들이 응력
        띠(최대의 10~40%) 안에 **다시 들어온다** — 변형률은 큰데 응력은 낮은
        점들이라, 그것까지 물면 구간이 곡선 끝까지 벌어지고 기울기가 무너진다.

        사보타주로 드러났다(2026-08-31): 합성 곡선이 전부 단조증가라 최대응력
        자르기를 없애도 시험이 안 물었다.
        """
        rising = synthetic()
        rise = rising.columns["strain_engineering"]
        rise_stress = rising.columns["stress_engineering"]
        # 파단: 최대응력의 5% 까지 떨어진다 — 하강하며 **띠를 다시 가로지른다.**
        fall = np.linspace(rise[-1], rise[-1] * 1.2, 60)[1:]
        fall_stress = np.linspace(rise_stress[-1], rise_stress[-1] * 0.05, 59)
        frame = Frame(
            {
                "strain_engineering": np.concatenate([rise, fall]),
                "stress_engineering": np.concatenate([rise_stress, fall_stress]),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

        result = processing.apply([Step("tensile.elastic_modulus", {"method": "auto"})], frame)

        assert scalar(result, "elastic_window_end") < 0.01, "파단 뒤를 물었다"
        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE, rel=0.05)

    def test_자동도_잡음에_안_흔들린다(self) -> None:
        """짧은 창은 잡음으로 얼마든지 가팔라진다. 띠는 창을 고를 자유가 없다."""
        rng = np.random.default_rng(7)
        strain = np.linspace(0.0, 0.004, 400)
        frame = Frame(
            {
                "strain_engineering": strain,
                "stress_engineering": E_TRUE * strain + rng.normal(0, 2e6, 400),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

        result = processing.apply([Step("tensile.elastic_modulus", {"method": "auto"})], frame)

        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE, rel=0.01)

    def test_항복이_낮으면_기본띠가_안_맞고_그것을_말한다(self) -> None:
        """**기본 띠(10~40%)가 모든 재료에 맞지 않는다.**

        항복이 인장강도의 29% 인 곡선에서는 띠 전체가 항복 뒤에 놓여 2.2 GPa 가
        나온다 — 참값은 200 GPa 다. 다만 그 구간은 직선이 아니라 **거절 검사가
        잡는다.** 조용히 틀린 값이 나가지 않는 것이 요점이다.
        """
        strain = np.concatenate(
            [np.linspace(0.0, 0.001, 40), np.linspace(0.001, 0.40, 400)[1:]]
        )
        low_yield = Frame(
            {
                "strain_engineering": strain,
                "stress_engineering": np.where(
                    strain <= 0.001, E_TRUE * strain, 200e6 + 1.25e9 * (strain - 0.001)
                ),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

        refused = processing.apply(
            [Step("tensile.elastic_modulus", {"method": "auto"})], low_yield
        )
        assert "youngs_modulus" not in {item.key for item in refused.scalars}
        # **고칠 데를 말한다.** 「직선이 아니다」 만으로는 띠가 손잡이인 줄 모른다.
        assert any("띠를 낮춰 보세요" in note for note in refused.notes)

        # 띠를 낮추면 맞는다.
        fixed = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"method": "auto", "auto_stress_low": 0.05, "auto_stress_high": 0.20},
                )
            ],
            low_yield,
        )
        assert scalar(fixed, "youngs_modulus") == pytest.approx(E_TRUE, rel=0.01)

    def test_뒤집힌_띠는_받지_않는다(self) -> None:
        """아래끝이 위끝보다 크면 띠가 비고, 그러면 「점이 모자라다」 로만 보인다 —
        사람은 곡선을 의심하지 설정을 의심하지 않는다."""
        for low, high in ((0.5, 0.2), (0.0, 0.4), (0.1, 1.5)):
            with pytest.raises(processing.ProcessingError, match="자동 띠"):
                processing.apply(
                    [
                        Step(
                            "tensile.elastic_modulus",
                            {
                                "method": "auto",
                                "auto_stress_low": low,
                                "auto_stress_high": high,
                            },
                        )
                    ],
                    synthetic(),
                )

    def test_자동도_성기면_값을_안_낸다(self) -> None:
        """**여기서 지어내면 소성 구역이 뽑힌다.** 고정 구간의 거절과 같은 자리다."""
        strain = np.linspace(0.0, 0.05, 60)
        sparse = Frame(
            {
                "strain_engineering": strain,
                "stress_engineering": np.where(
                    strain < 0.0015,
                    E_TRUE * strain,
                    E_TRUE * 0.0015 + HARDENING * (strain - 0.0015),
                ),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

        result = processing.apply(
            [Step("tensile.elastic_modulus", {"method": "auto"})], sparse
        )

        assert "youngs_modulus" not in {item.key for item in result.scalars}
        assert any("탄성계수를 내지 않았습니다" in note for note in result.notes)
        # **왜 없는지가 값으로 남는다.** 「값이 없다」 만으로는 고칠 데를 모른다 —
        # 실측(2026-08-31): 이 수가 없어서 사람이 18점 곡선을 직접 열어 점을 셌다.
        assert scalar(result, "elastic_point_count") < MIN_POINTS_FOR_TRUST
        # 몇 점이었는지와 곡선 전체가 몇 점인지를 함께 말한다 — 고칠 데가 다르다.
        assert any("상승 구간 전체가" in note for note in result.notes)

    def test_자동도_직선이_아니면_거절한다(self) -> None:
        """띠가 곡선을 따라가도 그 안이 직선이라는 보장은 없다 — 판정은 그대로
        R² 가 한다. **이 함수가 판정까지 하지 않는다.**"""
        strain = np.linspace(0.0, 0.1, 200)
        curved = Frame(
            {"strain_engineering": strain, "stress_engineering": 5e8 * np.sqrt(strain)},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )

        result = processing.apply(
            [Step("tensile.elastic_modulus", {"method": "auto"})], curved
        )

        assert "youngs_modulus" not in {item.key for item in result.scalars}
        assert any("직선이 아닙니다" in note for note in result.notes)

    def test_단계를_실패시키지는_않는다(self) -> None:
        """인장강도·연신율은 멀쩡히 나온 것이다 — 그것까지 잃으면 사람이 「점이
        모자란 것」 을 고치는 대신 이 단계를 빼 버린다."""
        strain = np.array([0.0, 0.0008, 0.0012, 0.05])
        sparse = Frame(
            {"strain_engineering": strain, "stress_engineering": strain * E_TRUE},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0005, "maximum_strain": 0.0015},
                ),
                Step("tensile.strength", {}),
            ],
            sparse,
        )
        assert scalar(result, "tensile_strength") > 0

    def test_직접_입력은_점_수와_무관하다(self) -> None:
        """**빠져나갈 문이 있어야 한다.** 값을 아는 사람이 규격서를 보고 적는
        길까지 막으면, 점이 모자란 곡선은 영영 카드를 못 만든다."""
        strain = np.array([0.0, 0.0008, 0.0012, 0.05])
        sparse = Frame(
            {"strain_engineering": strain, "stress_engineering": strain * E_TRUE},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"method": "manual", "manual_modulus": E_TRUE},
                )
            ],
            sparse,
        )
        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE)

    def test_사실상_한_점인_구간을_막는다(self) -> None:
        """**`polyfit` 은 퇴화한 구간에도 숫자를 돌려준다.**

        점 두 개의 변형률이 부동소수 정밀도 안에서 같으면, 나온 기울기는 유한하고
        양수라 뒤따르는 `isfinite`·`> 0` 검사를 그냥 지나간다. 그 값이 그대로
        탄성계수가 되어 카드를 거쳐 솔버 덱까지 간다 — **조용히 틀리는 자리다.**

        토우 보정에만 있던 방어인데 탄성계수 회귀는 `count < 2` 만 보고 있었다.
        같은 함수를 같은 방식으로 쓰면서 한쪽만 막아 둔 것이었다.
        """
        # 1e-18 은 0.001 옆에서 배정밀도로 구별되지 않는다.
        strain = np.array([0.001, 0.001 + 1e-18, 0.05])
        frame = Frame(
            {"strain_engineering": strain, "stress_engineering": np.array([2e8, 9e8, 5e8])},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="사실상 한 점"):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 0.0005, "maximum_strain": 0.002},
                    )
                ],
                frame,
            )

    def test_반올림_찌꺼기를_탄성계수라고_부르지_않는다(self) -> None:
        """**`modulus > 0` 은 방어가 아니다 — 운이다.**

        400 MPa 근처에서 폭 0.002 인 구간에 직선을 얹으면, 배정밀도의 반올림
        찌꺼기만으로도 기울기가 1e-3 Pa 규모까지 흔들린다. 그 아래에서는 부호가
        데이터가 아니라 **반올림이 정한다** — 여기 쓴 곡선은 실질 상수인데
        `polyfit` 이 9.2e-4 Pa 라는 유한한 양수를 돌려주고, 옛 검사는 그것을
        통과시켰다.

        eps 에 데이터 크기를 곱해 만든 바닥은 그 구간 전체를 거절한다.
        """
        strain = np.linspace(0.0005, 0.0025, 30)
        noise_only = Frame(
            {
                "strain_engineering": strain,
                "stress_engineering": 4e8 + (strain - strain[0]) * 1e-3,
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="탄성계수가 유한한 양수가 아닙니다"):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 0.0005, "maximum_strain": 0.0025},
                    )
                ],
                noise_only,
            )

    def test_구간에_점이_없으면_실제_범위를_알려_준다(self) -> None:
        with pytest.raises(ProcessingError, match="관측 범위는"):
            processing.apply(
                [
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 5.0, "maximum_strain": 6.0},
                    )
                ],
                synthetic(),
            )


class Test항복강도:
    def test_0_2퍼센트_오프셋이_아는_답을_준다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus",
                    {"minimum_strain": 0.0, "maximum_strain": 0.0015},
                ),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
            ],
            synthetic(),
        )
        # 오프셋 선 stress = E*(e-0.002) 와 경화선 stress = 400M + 2G*(e-0.002)
        # 의 교점. 정리하면 (e-0.002) = 400e6 / (200e9-2e9) 이고, 그 지점의
        # 응력은 E * 그 값이다.
        expected = E_TRUE * (YIELD_TRUE / (E_TRUE - HARDENING))
        assert scalar(result, "proof_stress") == pytest.approx(expected, rel=2e-3)

    def test_앞_단계_값을_참조한다(self) -> None:
        # **사람이 E 를 두 번 적지 않아야 한다.** 손으로 옮기면 방법을 바꿔 다시
        # 쟀을 때 항복강도만 옛 값으로 남고, 그 결과는 그럴듯해 보인다.
        result = processing.apply(
            [
                Step("tensile.elastic_modulus", {"method": "manual", "manual_modulus": 150e9}),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
            ],
            synthetic(),
        )
        assert result.stages[1].options["youngs_modulus"] == pytest.approx(150e9)

    def test_참조할_값이_없으면_어느_단계가_필요한지_말한다(self) -> None:
        with pytest.raises(ProcessingError, match="앞 단계가 내지 않았습니다"):
            processing.apply(
                [Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"})],
                synthetic(),
            )

    def test_만나지_않으면_외삽하지_않고_실패한다(self) -> None:
        """**이 테스트가 이 모듈의 태도 전부다.**

        탄성 구간만 측정된 곡선에 0.2% 오프셋을 걸면 교점이 없다. 외삽하면
        그럴듯한 항복강도가 나오고 아무도 의심하지 않는다.
        """
        strain = np.linspace(0.0, 0.001, 50)
        elastic_only = Frame(
            {"strain_engineering": strain, "stress_engineering": E_TRUE * strain},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="외삽해서 값을 만들지 않습니다"):
            processing.apply(
                [Step("tensile.proof_stress", {"youngs_modulus": E_TRUE})], elastic_only
            )


#: 합성 토우가 원점을 미는 양.
TOE_OFFSET = 0.0015


def synthetic_with_toe() -> Frame:
    """앞에 토우가 붙은 곡선. **정답은 `synthetic()` 과 같다.**

    시편이 그립에 물려 자리를 잡는 동안 변위는 늘어나는데 하중은 안 오른다. 그
    구간을 응력 0 으로 둔다 — 실제 토우도 이 이상화에 가깝고, 무엇보다 **정답을
    알 수 있다**: 보정량은 정확히 `TOE_OFFSET` 이어야 한다.
    """
    base = synthetic()
    strain = base.columns["strain_engineering"] + TOE_OFFSET
    stress = base.columns["stress_engineering"]
    # 이음점을 두 번 넣지 않는다 — 변형률이 같은 점이 둘이면 단조 증가가 깨진다.
    toe_strain = np.linspace(0.0, TOE_OFFSET, 30)[:-1]
    return Frame(
        {
            "strain_engineering": np.concatenate([toe_strain, strain]),
            "stress_engineering": np.concatenate([np.zeros_like(toe_strain), stress]),
        },
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )


#: 탄성 구간을 재는 창. **두 시험이 같은 창을 써야** 비교가 성립한다.
#: 보정 뒤에는 [0, 0.002] 가 탄성이므로 이 창이 그 안에 든다.
ELASTIC_WINDOW = {"minimum_strain": 0.001, "maximum_strain": 0.002}


class Test토우보정:
    """**토우가 망치는 것은 탄성계수다.**

    이 클래스가 보이려는 것은 보정이 "돌아간다" 가 아니라 **안 하면 무슨 일이
    나는가** 다.

    처음에는 항복강도가 크게 틀릴 것으로 보고 그렇게 단언했는데, 재 보니
    0.3% 였다 — 경화가 거의 평탄해서(2 GPa) 교점의 응력이 항복 근처에 붙박인다.
    **주장을 실측에 맞췄다.** 대신 탄성계수는 두 배 틀렸다(99.5 GPa, 참값 200).

    **v1.160.0 부터는 그 두 배 틀린 값이 아예 안 나온다.** 토우가 섞인 구간은
    직선이 아니라서(R²=0.797) 거절된다 — 「그럴듯해 보이는 100 GPa」 가 알루미늄
    이라고 하면 넘어가던 자리를, 이제는 멈춰서 토우를 가리킨다.
    """

    def test_보정_안_하면_탄성계수를_아예_못_낸다(self) -> None:
        """먼저 피해를 보인다. 탄성을 재는 창이 토우 안에 걸린다.

        **값이 안 나오는 것이 나은 결과다.** 전에는 99.5 GPa 가 나왔고, 그것은
        알루미늄이라고 하면 넘어가는 수다 — 틀렸다는 신호가 R² 에만 있었다.
        """
        result = processing.apply(
            [Step("tensile.elastic_modulus", dict(ELASTIC_WINDOW))],
            synthetic_with_toe(),
        )
        keys = {item.key for item in result.scalars}
        assert "youngs_modulus" not in keys
        # **거절의 근거가 값으로 남는다.** 직선이 아니라서 막은 것이므로 R² 를 남긴다.
        assert scalar(result, "elastic_r_squared") < 0.98
        note = " ".join(result.notes)
        assert "탄성계수를 내지 않았습니다" in note
        # **무엇을 하라고까지 말한다.** 「값이 없다」 만으로는 고칠 데를 모른다.
        assert "토우" in note

    def test_보정하면_아는_답이_돌아온다(self) -> None:
        result = processing.apply(
            [
                # 토우가 끝난 뒤의 직선 구간을 사람이 잡는다.
                Step(
                    "tensile.toe_compensation",
                    {"minimum_strain": 0.002, "maximum_strain": 0.003},
                ),
                Step("tensile.elastic_modulus", dict(ELASTIC_WINDOW)),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
            ],
            synthetic_with_toe(),
        )
        assert scalar(result, "toe_strain_offset") == pytest.approx(TOE_OFFSET, rel=1e-6)
        assert scalar(result, "youngs_modulus") == pytest.approx(E_TRUE, rel=1e-6)
        expected = E_TRUE * (YIELD_TRUE / (E_TRUE - HARDENING))
        assert scalar(result, "proof_stress") == pytest.approx(expected, rel=2e-3)

    def test_보정_안_하면_뒤_단계가_멈춘다(self) -> None:
        """**조용한 0.3% 오차가 시끄러운 정지로 바뀌었다.**

        전에는 보정 없이도 항복강도가 나왔고 정답과 0.3% 밖에 안 달랐다(경화가
        평탄해서 교점이 항복 근처에 붙박인다). 그럴듯해서 아무도 안 봤다.

        이제 탄성계수가 안 나오므로 `@youngs_modulus` 를 쓰는 뒤 단계가 멈춘다.
        **값이 조금 틀린 것보다 멈추는 편이 낫다** — 멈추면 토우 보정을 넣게 된다.
        """
        with pytest.raises(ProcessingError) as caught:
            processing.apply(
                [
                    Step("tensile.elastic_modulus", dict(ELASTIC_WINDOW)),
                    Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
                ],
                synthetic_with_toe(),
            )
        assert "@youngs_modulus" in str(caught.value)

    def test_보정하고_나면_항복강도가_정답에_붙는다(self) -> None:
        """**재 보고 적는다.** 보정을 넣으면 그 뒤가 다 맞는다 — 위 시험이 「멈춘다」
        만 말하고 끝나면, 멈추는 것이 옳았는지 알 수 없다."""
        result = processing.apply(
            [
                Step(
                    "tensile.toe_compensation",
                    {"minimum_strain": 0.002, "maximum_strain": 0.003},
                ),
                Step("tensile.elastic_modulus", dict(ELASTIC_WINDOW)),
                Step("tensile.proof_stress", {"youngs_modulus": "@youngs_modulus"}),
            ],
            synthetic_with_toe(),
        )
        exact = E_TRUE * (YIELD_TRUE / (E_TRUE - HARDENING))
        assert scalar(result, "proof_stress") == pytest.approx(exact, rel=2e-3)

    def test_응력은_안_건드린다(self) -> None:
        """장비 컴플라이언스를 추정하지 않는다는 뜻이다."""
        before = synthetic_with_toe()
        result = processing.apply(
            [
                Step(
                    "tensile.toe_compensation",
                    {"minimum_strain": 0.002, "maximum_strain": 0.003},
                )
            ],
            before,
        )
        assert np.array_equal(
            result.frame.columns["stress_engineering"],
            before.columns["stress_engineering"],
        )

    def test_자르지_않는다(self) -> None:
        """보정 뒤 앞쪽은 음의 변형률이 된다 — 시편이 물리기 전이라 맞다.

        한 단계가 옮기고 자르기까지 하면 무엇 때문에 값이 바뀌었는지 못 가린다.
        지우려면 `curve.crop` 을 뒤에 둔다.
        """
        before = synthetic_with_toe()
        result = processing.apply(
            [
                Step(
                    "tensile.toe_compensation",
                    {"minimum_strain": 0.002, "maximum_strain": 0.003},
                )
            ],
            before,
        )
        assert result.frame.length() == before.length()
        assert float(result.frame.columns["strain_engineering"].min()) < 0

    def test_점이_모자라면_추측하지_않고_실패한다(self) -> None:
        with pytest.raises(ProcessingError, match="최소 5점"):
            processing.apply(
                [
                    Step(
                        "tensile.toe_compensation",
                        {"minimum_strain": 0.00201, "maximum_strain": 0.00204},
                    )
                ],
                synthetic_with_toe(),
            )

    def test_구간이_직선이_아니면_경고한다(self) -> None:
        """**실패가 아니라 경고다.** 재료에 따라 진짜로 직선이 아닐 수 있다."""
        result = processing.apply(
            [
                # 토우와 탄성 구간에 걸치게 잡으면 꺾인 선이다.
                Step(
                    "tensile.toe_compensation",
                    {"minimum_strain": 0.0005, "maximum_strain": 0.0035},
                )
            ],
            synthetic_with_toe(),
        )
        notes = " ".join(result.stages[0].notes)
        assert "직선이 아닙니다" in notes, notes

    def test_기울기가_양수가_아니면_실패한다(self) -> None:
        """항복 뒤 평탄부에 구간을 잡으면 보정량이 뜻을 잃는다."""
        strain = np.linspace(0.0, 0.05, 100)
        flat = Frame(
            {"strain_engineering": strain, "stress_engineering": np.full_like(strain, 400e6)},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="유한한 양수가 아닙니다"):
            processing.apply(
                [
                    Step(
                        "tensile.toe_compensation",
                        {"minimum_strain": 0.01, "maximum_strain": 0.04},
                    )
                ],
                flat,
            )


#: 식 자체를 보는 시험은 항복에서 안 자른다 — 전 구간에서 식이 맞는지 본다.
WHOLE = {"youngs_modulus": E_TRUE, "yield_policy": "line_crossing"}


class Test진응력:
    def test_변환식이_맞다(self) -> None:
        result = processing.apply([Step("tensile.true_plastic", WHOLE)], synthetic())
        frame = result.frame
        eng_strain = frame.columns["strain_engineering"]
        eng_stress = frame.columns["stress_engineering"]
        assert frame.columns["strain_true"] == pytest.approx(np.log1p(eng_strain))
        assert frame.columns["stress_true"] == pytest.approx(eng_stress * (1 + eng_strain))
        assert frame.units["stress_true"] == "Pa"

    def test_자르지_않으면_네킹_경고가_남는다(self) -> None:
        # 조용히 넘어가면 그 곡선으로 적합한 경화식이 네킹 후 구간까지 맞추려 든다.
        result = processing.apply([Step("tensile.true_plastic", WHOLE)], synthetic())
        assert any("네킹 뒤 구간이 섞여" in note for note in result.notes)
        assert "proof_strain" not in result.stages[0].options
        assert any("옛 방식" in note for note in result.notes)

    def test_음의_소성변형률을_어떻게_다뤘는지_남는다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "tensile.true_plastic",
                    {**WHOLE, "negative_policy": "clip_zero"},
                )
            ],
            synthetic(),
        )
        assert np.all(result.frame.columns["strain_true_plastic"] >= 0)
        assert any("0 으로 잘랐습니다" in note for note in result.notes)


class Test소성은_항복부터:
    """**소성 곡선의 시작은 항복강도가 정한다** — E 직선이 아니라 (2026-09-11 VOC).

    v1 은 `ε - σ/E` 를 첫 점부터 적용하고 음수만 0 으로 눌렀다. 「어디서부터
    소성인가」 를 정하는 자리가 없어서 시작점이 노이즈·토우·컴플라이언스·E 값에
    따라 움직였고, 항복강도 단계의 오프셋은 **아무도 읽지 않아** 아무리 바꿔도
    이 열은 비트 하나 안 바뀌었다. 토우가 있으면 탄성 구간이 통째로 남아 덱 첫
    점이 (0, 0 MPa) 가 됐다.

        첫 점은 (0, Rp)          솔버는 첫 점을 항복점으로 읽는다
        Rp 앞은 없다             탄성 구간의 응력이 소성 곡선에 남지 않는다
        둘째 점은 오프셋 근처     잰 점을 옮기지 않는다 — 항복점까지의 영구 변형은 첫 구간이다
        오프셋이 시작을 정한다    바꾸면 첫 점이 움직인다
        토우가 있어도 같다        E 직선 아래로 처진 초기 구간이 새어 들어오지 않는다
    """

    @staticmethod
    def _run(frame: Frame, offset: float = 0.002) -> processing.PipelineResult:
        return processing.apply(
            [
                Step(
                    "tensile.proof_stress",
                    {"youngs_modulus": E_TRUE, "offset_strain": offset},
                ),
                Step(
                    "tensile.true_plastic",
                    {"youngs_modulus": E_TRUE, "proof_stress": "@proof_stress"},
                ),
            ],
            frame,
        )

    def test_첫_점이_항복점이고_그_앞은_없다(self) -> None:
        result = self._run(synthetic())
        rp = scalar(result, "proof_stress")
        plastic = result.frame.columns["strain_true_plastic"]
        eng_stress = result.frame.columns["stress_engineering"]
        assert plastic[0] == 0.0
        # 첫 줄은 곡선이 Rp 를 지나는 보간 교점 — 공칭응력이 정확히 Rp 다.
        assert eng_stress[0] == pytest.approx(rp, rel=1e-9)
        assert np.all(eng_stress >= rp * (1 - 1e-9))
        assert np.all(plastic[1:] > 0)
        assert any("항복점으로 읽습니다" in note for note in result.notes)

    def test_둘째_점부터는_식_그대로라_오프셋_근처에서_시작한다(self) -> None:
        result = self._run(synthetic(), offset=0.002)
        plastic = result.frame.columns["strain_true_plastic"]
        # 잰 점은 안 옮긴다. 오프셋 정의상 항복점에 이미 0.2% 의 영구 변형이 있다.
        assert 0.0015 < plastic[1] < 0.004

    def test_오프셋이_시작점을_정한다(self) -> None:
        low = self._run(synthetic(), offset=0.001)
        high = self._run(synthetic(), offset=0.005)
        first_low = low.frame.columns["stress_true"][0]
        first_high = high.frame.columns["stress_true"][0]
        assert first_high > first_low
        assert low.frame.length() > high.frame.length()

    def test_토우가_있어도_탄성_구간이_새어_들지_않는다(self) -> None:
        """v1 의 증상 그대로 — 토우 구간은 E 직선 아래에 있어 `ε - σ/E > 0` 이다."""
        frame = synthetic_with_toe()
        result = self._run(frame)
        eng_stress = result.frame.columns["stress_engineering"]
        rp = scalar(result, "proof_stress")
        assert np.all(eng_stress >= rp * (1 - 1e-9))
        # 옛 방식이면 토우의 점들이 양의 소성변형률을 달고 남는다.
        old = processing.apply([Step("tensile.true_plastic", WHOLE)], frame)
        leaked = old.frame.columns["stress_engineering"] < rp
        assert np.any(leaked & (old.frame.columns["strain_true_plastic"] > 0))

    def test_항복강도를_안_이어_붙이면_어디를_고칠지_말한다(self) -> None:
        with pytest.raises(processing.ProcessingError, match="@proof_stress"):
            processing.apply(
                [Step("tensile.true_plastic", {"youngs_modulus": E_TRUE})], synthetic()
            )


class Test항복교점전달:
    E_S355 = 210867263618.31775

    @staticmethod
    def _prefix() -> list[Step]:
        return [
            Step(
                "tensile.elastic_modulus",
                {"method": "manual", "manual_modulus": Test항복교점전달.E_S355},
            ),
            Step(
                "tensile.proof_stress",
                {"youngs_modulus": "@youngs_modulus", "offset_strain": 0.002},
            ),
        ]

    def test_s355_toe보정_후에도_기존레시피가_원교점을_전달한다(self) -> None:
        """원자료의 q=0.00221310 첫 응력 교차 대신 p=0.00390515515를 보존한다."""
        raw_options = {
            "youngs_modulus": "@youngs_modulus",
            "proof_stress": "@proof_stress",
        }
        steps = [
            *self._prefix(),
            Step("tensile.true_plastic", raw_options),
        ]
        source = s355_toe_corrected_excerpt()
        result = processing.apply(steps, source)
        proof = scalar(result, "proof_stress")
        proof_strain = scalar(result, "proof_strain")
        assert proof == pytest.approx(401734853.3933848, abs=1e-6)
        assert proof_strain == pytest.approx(0.0039051551506854507, abs=1e-15)

        first = result.frame
        assert first.columns["strain_engineering"][0] == proof_strain
        assert first.columns["stress_engineering"][0] == proof
        assert "proof_strain" not in raw_options
        assert result.stages[-1].options["proof_strain"] == proof_strain

        stress = source.columns["stress_engineering"]
        crossing_at = int(np.flatnonzero(stress >= proof)[0])
        fraction = (proof - stress[crossing_at - 1]) / (
            stress[crossing_at] - stress[crossing_at - 1]
        )
        old_strain = source.columns["strain_engineering"][crossing_at - 1] + fraction * (
            source.columns["strain_engineering"][crossing_at]
            - source.columns["strain_engineering"][crossing_at - 1]
        )
        assert old_strain == pytest.approx(0.002213103794829775, abs=1e-15)
        assert first.columns["strain_engineering"][0] != pytest.approx(old_strain)

        right = int(np.searchsorted(source.columns["strain_engineering"], proof_strain))
        left = right - 1
        bracket_fraction = (proof_strain - source.columns["strain_engineering"][left]) / (
            source.columns["strain_engineering"][right]
            - source.columns["strain_engineering"][left]
        )
        expected_source_row = source.columns["source_data_row"][left] + bracket_fraction * (
            source.columns["source_data_row"][right] - source.columns["source_data_row"][left]
        )
        assert first.columns["source_data_row"][0] == pytest.approx(expected_source_row)

    def test_중간에_400점_재샘플해도_명시한_원교점을_쓴다(self) -> None:
        result = processing.apply(
            [
                *self._prefix(),
                Step("curve.resample", {"x": "strain_engineering", "count": 400}),
                Step(
                    "tensile.true_plastic",
                    {
                        "youngs_modulus": "@youngs_modulus",
                        "proof_stress": "@proof_stress",
                        "proof_strain": "@proof_strain",
                    },
                ),
            ],
            s355_toe_corrected_excerpt(),
        )
        proof = scalar(result, "proof_stress")
        proof_strain = scalar(result, "proof_strain")
        resampled = result.stages[-2].frame
        assert resampled.length() == 400
        assert result.stages[-1].options["proof_strain"] == proof_strain
        assert result.frame.columns["strain_engineering"][0] == proof_strain
        assert result.frame.columns["stress_engineering"][0] == proof

    def test_교점이_기존_행이면_중복하지_않고_뒤_행만_잇는다(self) -> None:
        frame = Frame(
            {
                "strain_engineering": np.asarray([0.0, 0.01, 0.02, 0.03, 0.04]),
                "stress_engineering": np.asarray(
                    [0, 100_000_000, 200_000_000, 300_000_000, 400_000_000]
                ),
                "marker": np.asarray([10.0, 20.0, 30.0, 40.0, 50.0]),
            },
            {
                "strain_engineering": "1",
                "stress_engineering": "Pa",
                "marker": "1",
            },
        )
        result = processing.apply(
            [
                Step(
                    "tensile.true_plastic",
                    {
                        "youngs_modulus": E_TRUE,
                        "proof_stress": 250_000_000.5,
                        "proof_strain": 0.02,
                    },
                )
            ],
            frame,
        )
        assert result.frame.columns["strain_engineering"] == pytest.approx([0.02, 0.03, 0.04])
        assert result.frame.columns["stress_engineering"][0] == 250_000_000.5
        assert result.frame.columns["marker"] == pytest.approx([30.0, 40.0, 50.0])

    @pytest.mark.parametrize("proof_strain", [-0.001, 0.04])
    def test_관측범위_밖의_교점은_명료하게_실패한다(self, proof_strain: float) -> None:
        frame = Frame(
            {
                "strain_engineering": np.asarray([0.0, 0.01, 0.02, 0.03]),
                "stress_engineering": np.asarray([0.0, 100e6, 200e6, 300e6]),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="관측 변형률 범위"):
            processing.apply(
                [
                    Step(
                        "tensile.true_plastic",
                        {
                            "youngs_modulus": E_TRUE,
                            "proof_stress": 100e6,
                            "proof_strain": proof_strain,
                        },
                    )
                ],
                frame,
            )

    def test_교점_뒤_관측점이_두개_미만이면_실패한다(self) -> None:
        frame = Frame(
            {
                "strain_engineering": np.asarray([0.0, 0.01, 0.02, 0.03]),
                "stress_engineering": np.asarray([0.0, 100e6, 200e6, 300e6]),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="뒤에 관측점이 2점 미만"):
            processing.apply(
                [
                    Step(
                        "tensile.true_plastic",
                        {
                            "youngs_modulus": E_TRUE,
                            "proof_stress": 100e6,
                            "proof_strain": 0.02,
                        },
                    )
                ],
                frame,
            )

    def test_숫자_Rp만_받으면_기존_첫응력교차를_쓰고_근거를_남긴다(self) -> None:
        frame = synthetic()
        proof = 350e6
        stress = frame.columns["stress_engineering"]
        strain = frame.columns["strain_engineering"]
        at = int(np.flatnonzero(stress >= proof)[0])
        fraction = (proof - stress[at - 1]) / (stress[at] - stress[at - 1])
        expected = strain[at - 1] + fraction * (strain[at] - strain[at - 1])
        result = processing.apply(
            [
                Step(
                    "tensile.true_plastic",
                    {"youngs_modulus": E_TRUE, "proof_stress": proof},
                )
            ],
            frame,
        )
        assert result.frame.columns["strain_engineering"][0] == pytest.approx(expected)
        assert "proof_strain" not in result.stages[0].options
        assert any("좌표 없이" in note for note in result.notes)

    def test_준비훅은_옛참조만_보충하고_명시값과_입력을_보존한다(self) -> None:
        plugin = registry.get("tensile.true_plastic")
        assert plugin.prepare_options is not None
        assert "prepare_options" not in plugin.meta
        strain_param = next(one for one in plugin.params if one.name == "proof_strain")
        assert strain_param.default is None
        assert strain_param.dimension == "strain"
        assert strain_param.unit == "1"
        legacy = {"proof_stress": "@proof_stress"}
        assert plugin.prepare_options(dict(legacy)) == {
            "proof_stress": "@proof_stress",
            "proof_strain": "@proof_strain",
        }
        assert legacy == {"proof_stress": "@proof_stress"}
        for options in (
            {"proof_stress": "@proof_stress", "proof_strain": None},
            {"proof_stress": 350e6},
            {"proof_stress": "@lower_yield_strength"},
            {"proof_stress": "@proof_stress", "yield_policy": "line_crossing"},
        ):
            assert plugin.prepare_options(dict(options)) == options


class Test네킹:
    def test_후보만_내고_아무것도_자르지_않는다(self) -> None:
        frame = synthetic()
        before = frame.length()
        result = processing.apply([Step("tensile.necking_candidate", {})], frame)
        assert result.frame.length() == before
        assert any("아무것도 자르지 않았습니다" in note for note in result.notes)


class Test정렬:
    def test_정렬되지_않은_입력을_계산이_거절한다(self) -> None:
        # **np.interp 는 정렬을 검사하지 않는다.** 오류 없이 엉뚱한 값을 낸다.
        shuffled = synthetic()
        order = np.arange(shuffled.length())[::-1]
        reversed_frame = shuffled.select(order)
        with pytest.raises(ProcessingError, match="sort_unique"):
            processing.apply([Step("tensile.elastic_modulus", {})], reversed_frame)

    def test_정렬_단계가_중복을_정리한다(self) -> None:
        frame = Frame(
            {"x": np.array([2.0, 1.0, 1.0, 3.0]), "y": np.array([20.0, 10.0, 12.0, 30.0])},
            {"x": "1", "y": "Pa"},
        )
        result = processing.apply(
            [Step("curve.sort_unique", {"x": "x", "duplicate_policy": "mean"})], frame
        )
        assert result.frame.columns["x"] == pytest.approx([1.0, 2.0, 3.0])
        assert result.frame.columns["y"] == pytest.approx([11.0, 20.0, 30.0])
        assert "중복 1점" in result.notes[0]

    def test_마지막_점만_남기기가_항복점을_지킨다(self) -> None:
        """**진소성변형률 축에서 필요해진 정책이다.**

        `clip_zero` 가 탄성 구간을 전부 x=0 에 쌓아 두는데(실측 120점 중 34점),
        평균을 내면 탄성 구간 응력이 섞여 항복강도가 낮아지고, 첫 점을 남기면
        0 에 가까운 응력을 항복강도로 쓰게 된다. **쌓인 것 중 마지막이 항복점**이다.
        """
        frame = Frame(
            {
                "strain_true_plastic": np.array([0.0, 0.0, 0.0, 0.01]),
                "stress_true": np.array([50e6, 200e6, 341e6, 360e6]),
            },
            {"strain_true_plastic": "1", "stress_true": "Pa"},
        )
        result = processing.apply(
            [
                Step(
                    "curve.sort_unique",
                    {"x": "strain_true_plastic", "duplicate_policy": "last"},
                )
            ],
            frame,
        )
        assert result.frame.columns["strain_true_plastic"] == pytest.approx([0.0, 0.01])
        assert result.frame.columns["stress_true"] == pytest.approx([341e6, 360e6])

    def test_거절_정책은_거절한다(self) -> None:
        frame = Frame({"x": np.array([1.0, 1.0])}, {"x": "1"})
        with pytest.raises(ProcessingError, match="같은 값이 1개"):
            processing.apply(
                [Step("curve.sort_unique", {"x": "x", "duplicate_policy": "reject"})], frame
            )


class Test재샘플:
    def test_관측_밖은_만들어_내지_않는다(self) -> None:
        with pytest.raises(ProcessingError, match="측정하지 않은 구간"):
            processing.apply(
                [Step("curve.resample", {"x": "strain_engineering", "end": 99.0})],
                synthetic(),
            )

    def test_격자_위로_보간한다(self) -> None:
        result = processing.apply(
            [
                Step(
                    "curve.resample",
                    {"x": "strain_engineering", "count": 51, "start": 0.0, "end": 0.05},
                )
            ],
            synthetic(),
        )
        assert result.frame.length() == 51
        assert result.frame.columns["strain_engineering"][0] == pytest.approx(0.0)

    def test_0_에서_시작하는_요청이_반올림에_막히지_않는다(self) -> None:
        """**전체 흐름 점검에서 걸렸다**(2026-08-27).

        화면이 채워 주는 표준 레시피는 `start: 0` 을 적는다 — 「0 부터」 라는
        뜻이고, **모든 시편이 같은 격자를 쓰게** 하려는 것이다. 그런데 실제
        `.tra` 의 첫 변형률은 `2.92968e-09` 이지 정확히 0 이 아니라서, 화면이
        권하는 그 구성이 실파일에서 422 로 막혔다.
        """
        first = 2.92968e-09
        x = np.linspace(first, 0.4, 50)
        frame = Frame(
            {"strain_engineering": x, "stress_engineering": x * 2.0e9},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [Step("curve.resample", {"x": "strain_engineering", "count": 11, "start": 0.0})],
            frame,
        )
        # **격자는 요청한 대로다.** 관측 안으로 당기면 시편마다 시작점이 달라져
        # 통계가 대표 곡선을 못 낸다 — `start: 0` 을 못 박는 이유가 그것이다.
        assert result.frame.columns["strain_engineering"][0] == pytest.approx(0.0)

    def test_봐_준_것을_조용히_넘기지_않는다(self) -> None:
        """조용히 넘어가면 「외삽하지 않는다」 가 언제 지켜졌는지 알 수 없다."""
        x = np.linspace(2.92968e-09, 0.4, 50)
        frame = Frame(
            {"strain_engineering": x, "stress_engineering": x * 2.0e9},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        result = processing.apply(
            [Step("curve.resample", {"x": "strain_engineering", "count": 11, "start": 0.0})],
            frame,
        )
        assert any("끝자락의 반올림" in said for said in result.notes)

    def test_잡음을_넘어서면_그대로_거절한다(self) -> None:
        """봐 주는 폭은 **관측 폭에 견준 잡음 수준**이어야 한다.

        실측된 잡음은 관측 폭의 `7.3e-09` 다. 여기서 쓰는 틈은 그 **세 자릿수
        위인 `1e-5`** 이고, 그래도 막혀야 한다 — 안 막히면 「측정 안 한 구간을
        만들어 내지 않는다」 가 반올림 봐 주기라는 이름으로 헐거워진다.
        """
        x = np.linspace(0.4 * 1e-5, 0.4, 50)
        frame = Frame(
            {"strain_engineering": x, "stress_engineering": x * 2.0e9},
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="측정하지 않은 구간"):
            processing.apply(
                [
                    Step(
                        "curve.resample",
                        {"x": "strain_engineering", "count": 11, "start": 0.0},
                    )
                ],
                frame,
            )


class Test단위:
    def test_변형률이_퍼센트면_거절한다(self) -> None:
        # 저장 단위는 고를 수 있는 것이 아니다. 여기서 안 막으면 100배 어긋난다.
        frame = Frame(
            {
                "strain_engineering": np.linspace(0, 5, 10),
                "stress_engineering": np.linspace(0, 4e8, 10),
            },
            {"strain_engineering": "%", "stress_engineering": "Pa"},
        )
        with pytest.raises(ProcessingError, match="무차원 변형률"):
            processing.apply([Step("tensile.elastic_modulus", {})], frame)

    def test_응력이_MPa면_거절한다(self) -> None:
        frame = Frame(
            {
                "strain_engineering": np.linspace(0, 0.05, 10),
                "stress_engineering": np.linspace(0, 400, 10),
            },
            {"strain_engineering": "1", "stress_engineering": "MPa"},
        )
        with pytest.raises(ProcessingError, match="Pa 여야"):
            processing.apply([Step("tensile.elastic_modulus", {})], frame)


class Test실제장비파일:
    """**합성 데이터만으로는 장비가 주는 모양에서 깨지는 것을 못 잡는다.**"""

    def frame(self) -> Frame:
        parsers.load_builtin()
        parsed = zwick_tra.parse(TRA.read_bytes())
        curve = parsed.all_curves[0]
        columns = {
            channel.key: np.asarray(
                [np.nan if v is None else v for v in channel.values], dtype=np.float64
            )
            for channel in curve.channels
        }
        units = {channel.key: channel.si_unit for channel in curve.channels}
        return Frame(columns, units)

    def test_변위_하중에서_물성까지_이어진다(self) -> None:
        frame = self.frame()
        assert "displacement" in frame.columns, sorted(frame.columns)
        assert "force" in frame.columns

        # 시편 치수는 곡선에 없다 — 시편 기록에서 온다. 여기서는 실측 폭을 쓴다.
        width = float(np.nanmedian(frame.columns["specimen_width"]))
        thickness = 1.0e-3
        result = processing.apply(
            [
                Step("tensile.engineering", {"gauge_length": 0.05, "area": width * thickness}),
                Step(
                    "curve.sort_unique",
                    {"x": "strain_engineering", "duplicate_policy": "mean"},
                ),
                Step("tensile.strength", {}),
                Step("tensile.necking_candidate", {}),
            ],
            frame,
        )
        uts = scalar(result, "tensile_strength")
        # 강판이면 100 MPa ~ 2 GPa 사이다. 자릿수가 틀리면 면적·단위가 어긋난 것이다.
        assert 1e8 < uts < 2e9, f"인장강도가 {uts / 1e6:.4g} MPa 로 물리적이지 않습니다"
        assert result.frame.units["stress_engineering"] == "Pa"

    def test_실패한_단계에서_멈추고_어디서인지_말한다(self) -> None:
        with pytest.raises(ProcessingError, match="2단계"):
            processing.apply(
                [
                    Step("tensile.engineering", {"gauge_length": 0.05, "area": 1e-5}),
                    Step(
                        "tensile.elastic_modulus",
                        {"minimum_strain": 9.0, "maximum_strain": 10.0},
                    ),
                    Step("tensile.strength", {}),
                ],
                self.frame(),
            )


def test_등록되지_않은_단계는_코드라고_말한다() -> None:
    # 프로파일(데이터)과 처리(코드)의 경계를 화면이 분명히 보여 줘야 한다.
    with pytest.raises(ProcessingError, match="정의만으로는 만들 수 없습니다"):
        processing.apply([Step("tensile.made_up", {})], synthetic())


def mild_steel() -> Frame:
    """항복점 현상 — E=200 GPa, ReH 320 · ReL 280 MPa, 뤼더스 평탄부 0.0016~0.02, 뒤는 경화."""
    strain = np.linspace(0.0, 0.10, 1001)
    stress = np.empty_like(strain)
    for at, e in enumerate(strain):
        if e <= 0.0016:
            stress[at] = E_TRUE * e  # 0.0016 → 320 MPa
        elif e <= 0.0026:
            stress[at] = 320e6 - (e - 0.0016) / 0.001 * 40e6  # 뚝 떨어져 280
        elif e <= 0.02:
            stress[at] = 280e6 + 2e6 * np.sin((e - 0.0026) * 3000)  # 평탄부 잔물결 ±2 MPa
        else:
            stress[at] = 280e6 + 1.5e9 * (e - 0.02)  # 다시 경화, 0.0467 에서 320 을 넘는다
    return Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )


def polymer_neck() -> Frame:
    """수지 — 항복 60 MPa(변형률 0.05) 뒤 넥으로 공칭 응력이 45 까지 내려가 평탄."""
    strain = np.linspace(0.0, 0.5, 251)
    stress = np.where(
        strain <= 0.05,
        60e6 * np.sin(strain / 0.05 * np.pi / 2),
        45e6 + 15e6 * np.exp(-(strain - 0.05) / 0.03),
    )
    return Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )


def noisy() -> Frame:
    """경화 곡선에 ±1.5 MPa 잡음 — 국소적으로 내려가지만 연화는 아니다."""
    base = synthetic()
    rng = np.random.default_rng(7)
    stress = base.columns["stress_engineering"] + rng.normal(0, 1.5e6, base.length())
    return Frame({**base.columns, "stress_engineering": stress}, dict(base.units))


def _run(frame: Frame, options: dict[str, object]) -> processing.PipelineResult:
    return processing.apply([Step("tensile.yield_drop", dict(options))], frame)


def oxford_pc_test2() -> Frame:
    """Oxford PC50Test2, in original row order, with engineering channels derived."""
    with OXFORD_PC_TEST2.open(encoding="utf-8", newline="") as handle:
        data = list(csv.reader(handle))
    columns = {name: index for index, name in enumerate(data[0])}
    rows = data[1:]

    def values(name: str) -> np.ndarray:
        return np.asarray([float(row[columns[name]]) for row in rows], dtype=np.float64)

    displacement = values("displacement_mm") / 1000.0
    force = values("force_N")
    return Frame(
        {
            "displacement": displacement,
            "force": force,
            "time": values("time_s"),
            "source_excel_row": values("source_excel_row"),
            "strain_engineering": displacement / 0.08,
            "stress_engineering": force / 40e-6,
        },
        {
            "displacement": "m",
            "force": "N",
            "time": "s",
            "source_excel_row": "1",
            "strain_engineering": "1",
            "stress_engineering": "Pa",
        },
    )


class Test항복_강하_정리:
    """**단조 표를 받는 솔버를 위해 내려가는 구간을 정리하되, 무엇을 버렸는지 남긴다.**"""

    def test_연강은_명시한_구간만_모델_응력으로_평탄화한다(self) -> None:
        frame = mild_steel()
        result = _run(
            frame,
            {
                "method": "lower_yield",
                "plateau_start": 0.0016,
                "plateau_end": 0.02,
                "plateau_stress": 278e6,
            },
        )
        original = frame.columns["stress_engineering"]
        strain = frame.columns["strain_engineering"]
        selected = (strain >= 0.0016) & (strain <= 0.02)
        fixed = result.frame.columns["stress_engineering"]

        np.testing.assert_array_equal(result.frame.columns["strain_engineering"], strain)
        np.testing.assert_array_equal(fixed[~selected], original[~selected])
        assert np.all(fixed[selected] == 278e6)
        assert scalar(result, "yield_drop_points") == np.count_nonzero(
            original[selected] != 278e6
        )
        assert scalar(result, "yield_drop_max") == pytest.approx(42e6, rel=1e-2)
        assert scalar(result, "model_plateau_stress") == 278e6
        assert scalar(result, "model_plateau_start") == pytest.approx(0.0016)
        assert scalar(result, "model_plateau_end") == pytest.approx(0.02)
        assert not {item.key for item in result.scalars} & {
            "upper_yield_strength",
            "lower_yield_strength",
            "luders_strain",
        }
        assert any("실제 관측 구간" in note for note in result.notes)
        assert any("규격 하항복강도" in note for note in result.notes)

    def test_옛_하항복_방법만_지정하면_필요한_설정을_말하고_보류한다(self) -> None:
        with pytest.raises(ProcessingError, match=r"옛 하항복 자동 평탄화.*plateau_start"):
            _run(mild_steel(), {"method": "lower_yield"})

    @pytest.mark.parametrize(
        ("options", "message"),
        (
            (
                {
                    "method": "lower_yield",
                    "plateau_start": 0.02,
                    "plateau_end": 0.01,
                    "plateau_stress": 280e6,
                },
                "작아야",
            ),
            (
                {
                    "method": "lower_yield",
                    "plateau_start": -0.01,
                    "plateau_end": 0.01,
                    "plateau_stress": 280e6,
                },
                "관측 변형률 범위",
            ),
            (
                {
                    "method": "lower_yield",
                    "plateau_start": 0.0016,
                    "plateau_end": 0.00160001,
                    "plateau_stress": 280e6,
                },
                "2점 미만",
            ),
            (
                {
                    "method": "lower_yield",
                    "plateau_start": 0.0016,
                    "plateau_end": 0.002,
                    "plateau_stress": 0.0,
                },
                "0보다 커야",
            ),
            (
                {
                    "method": "lower_yield",
                    "plateau_start": 0.0016,
                    "plateau_end": 0.002,
                    "plateau_stress": float("nan"),
                },
                "유한하지 않습니다",
            ),
        ),
    )
    def test_명시_평탄화_입력의_범위와_유한성을_검증한다(
        self, options: dict[str, object], message: str
    ) -> None:
        with pytest.raises(ProcessingError, match=message):
            _run(mild_steel(), options)

    def test_평탄화_메타데이터는_모델_근사와_실제_선택점을_선언한다(self) -> None:
        plugin = registry.get("tensile.yield_drop")
        assert plugin.label == "공칭 하강 처리"
        assert plugin.version == "6"
        params = {item.name: item for item in plugin.params}
        assert params["scope"].default == "full"
        assert params["method"].default == "envelope"
        auto_method = "lower_envelope_auto_v1"
        assert params["method"].choice_labels[auto_method] == "하측 포락선 — 자동"
        assert len(AUTO_YIELD_PROFILES) == 7
        assert len({profile.id for profile in AUTO_YIELD_PROFILES}) == 7
        for profile in AUTO_YIELD_PROFILES:
            assert profile.id in params["method"].choices
            assert params["method"].choice_labels[profile.id] == profile.label
            assert profile.id in params["method"].choice_help
        for name in ("scope", "threshold", "min_slope"):
            assert all(
                profile.id not in params[name].when["method"]
                for profile in AUTO_YIELD_PROFILES
            )
        for name in ("recovery_threshold", "min_reference_fraction", "terminal_action"):
            assert all(
                profile.id not in params[name].when["method"]
                for profile in AUTO_YIELD_PROFILES
            )
        for profile in AUTO_YIELD_PROFILES:
            assert profile.id not in params["slope_constraint"].when["method"]
        for name in ("range_start", "range_end"):
            assert params[name].when == {
                "scope": ("range", "events"),
                "method": params[name].when["method"],
            }
            assert all(
                profile.id not in params[name].when["method"]
                for profile in AUTO_YIELD_PROFILES
            )
        for name in ("plateau_start", "plateau_end", "plateau_stress"):
            assert params[name].required
            assert params[name].when == {"method": ("lower_yield",)}
            assert all(
                profile.id not in params[name].when["method"]
                for profile in AUTO_YIELD_PROFILES
            )
        assert {item.key for item in plugin.makes_values} >= {
            "yield_drop_max",
            "yield_drop_points",
            "model_plateau_stress",
            "model_plateau_start",
            "model_plateau_end",
            "auto_edit_applied",
            "auto_review_required",
            "auto_terminal_only",
            "open_partial_count",
        }
        assert not {item.key for item in plugin.makes_values} & {
            "upper_yield_strength",
            "lower_yield_strength",
            "luders_strain",
        }

    def test_포락선은_내려가는_점을_직전_최댓값으로_덮는다(self) -> None:
        result = _run(mild_steel(), {"method": "envelope"})
        fixed = result.frame.columns["stress_engineering"]
        assert np.all(np.diff(fixed) >= 0)
        # 봉우리(320)를 그대로 끌고 간다 — 하항복점부터와 다른 점이다.
        strain = result.frame.columns["strain_engineering"]
        assert fixed[np.searchsorted(strain, 0.01)] == pytest.approx(320e6, rel=1e-3)

    def test_단조_회귀는_잡음을_원곡선_가까이_편다(self) -> None:
        frame = noisy()
        result = _run(frame, {"method": "isotonic", "threshold": 0.0})
        fixed = result.frame.columns["stress_engineering"]
        assert np.all(np.diff(fixed) >= 0)
        truth = synthetic().columns["stress_engineering"]
        envelope = np.maximum.accumulate(frame.columns["stress_engineering"])
        # 포락선보다 진짜 곡선에 가깝다 — 포락선은 봉우리 쪽으로 치우친다.
        assert np.mean(np.abs(fixed - truth)) < np.mean(np.abs(envelope - truth))

    def test_자르기는_봉우리_뒤를_버리고_그_수를_적는다(self) -> None:
        frame = polymer_neck()
        result = _run(frame, {"method": "cut"})
        strain = result.frame.columns["strain_engineering"]
        assert strain[-1] == pytest.approx(0.05, abs=0.003)
        assert result.frame.length() < frame.length()
        assert scalar(result, "yield_drop_points") == frame.length() - result.frame.length()
        assert any("잘랐습니다" in note for note in result.notes)
        # 봉우리를 다시 넘지 않는 곡선 — 그 사실을 말한다.
        assert any("다시 넘지 않습니다" in note for note in result.notes)

    def test_그대로_두기는_재기만_한다(self) -> None:
        frame = polymer_neck()
        result = _run(frame, {"method": "keep"})
        assert np.array_equal(
            result.frame.columns["stress_engineering"], frame.columns["stress_engineering"]
        )
        assert scalar(result, "yield_drop_max") == pytest.approx(15e6, rel=0.05)
        assert scalar(result, "yield_drop_points") == 0
        assert not any(
            item.key in {"upper_yield_strength", "lower_yield_strength", "luders_strain"}
            for item in result.scalars
        )

    def test_평탄화와_최소_기울기는_한_단계에서_섞지_않는다(self) -> None:
        with pytest.raises(ProcessingError, match="별도의 단조화 단계"):
            _run(
                mild_steel(),
                {
                    "method": "lower_yield",
                    "min_slope": 1e7,
                    "plateau_start": 0.0016,
                    "plateau_end": 0.02,
                    "plateau_stress": 278e6,
                },
            )

    def test_문턱_미만의_하강은_손대지_않는다(self) -> None:
        # 잡음까지 정리하면 모든 곡선이 조금씩 손대진 채 저장된다 — 「측정 그대로」 가 아니다.
        frame = noisy()
        result = _run(frame, {"method": "envelope", "threshold": 0.05})
        assert np.array_equal(
            result.frame.columns["stress_engineering"], frame.columns["stress_engineering"]
        )
        assert scalar(result, "yield_drop_points") == 0
        assert any("응력 하강으로 보지 않습니다" in note for note in result.notes)

    def test_하강이_없어도_명시한_모델_근사는_처리한다(self) -> None:
        result = _run(
            synthetic(),
            {
                "method": "lower_yield",
                "plateau_start": 0.03,
                "plateau_end": 0.04,
                "plateau_stress": 450e6,
            },
        )
        assert scalar(result, "yield_drop_max") == 0
        assert scalar(result, "yield_drop_points") > 0
        assert scalar(result, "model_plateau_stress") == 450e6
        assert any("선택 구간 평탄화" in note for note in result.notes)

    @pytest.mark.parametrize("method", ("envelope", "isotonic", "lower_yield", "cut", "keep"))
    def test_Oxford_PC50Test2_음수_첫하중을_보존하며_다섯방법이_실행된다(
        self, method: str
    ) -> None:
        frame = oxford_pc_test2()
        stress = frame.columns["stress_engineering"]
        assert stress[0] == pytest.approx(-5_000.0)

        first = _first_drop(stress, 0.005)
        assert first is not None
        assert first > 0

        options: dict[str, object] = {"method": method}
        if method == "lower_yield":
            options.update(
                {"plateau_start": 0.05, "plateau_end": 0.10, "plateau_stress": 55e6}
            )
        result = _run(frame, options)
        output = result.frame
        assert output.length() > 1
        assert np.all(np.isfinite(output.columns["stress_engineering"]))
        assert np.all(np.diff(output.columns["strain_engineering"]) > 0)
        assert np.all(np.diff(output.columns["source_excel_row"]) > 0)

        if method == "keep":
            assert output.length() == frame.length()
            for key, values in frame.columns.items():
                np.testing.assert_array_equal(output.columns[key], values)
            assert scalar(result, "yield_drop_points") == 0

    def test_Oxford_PC50Test2_명시_구간은_말단_급락과_원행을_보존한다(self) -> None:
        frame = oxford_pc_test2()
        options = {
            "method": "lower_yield",
            "plateau_start": 0.05,
            "plateau_end": 0.10,
            "plateau_stress": 55e6,
        }
        for excluded_tail in (0, 1, 2):
            candidate = frame.select(np.arange(frame.length() - excluded_tail))
            result = _run(candidate, options)
            output = result.frame
            selected = (candidate.columns["strain_engineering"] >= 0.05) & (
                candidate.columns["strain_engineering"] <= 0.10
            )
            np.testing.assert_array_equal(
                output.columns["source_excel_row"], candidate.columns["source_excel_row"]
            )
            np.testing.assert_array_equal(
                output.columns["stress_engineering"][~selected],
                candidate.columns["stress_engineering"][~selected],
            )
            assert np.all(output.columns["stress_engineering"][selected] == 55e6)
            assert (
                output.columns["stress_engineering"][-1]
                == candidate.columns["stress_engineering"][-1]
            )
            assert scalar(result, "model_plateau_start") == pytest.approx(
                candidate.columns["strain_engineering"][selected][0]
            )
            assert scalar(result, "model_plateau_end") == pytest.approx(
                candidate.columns["strain_engineering"][selected][-1]
            )

    def test_상대하강은_양수인_선행최댓값만_기준으로_삼는다(self) -> None:
        assert _first_drop(np.asarray([-5000.0, -1.0, 0.0]), 0.005) is None
        assert _first_drop(np.asarray([0.0, 0.0, 0.0]), 0.005) is None
        assert _first_drop(np.asarray([-5000.0, 0.0, 1.0, 0.99]), 0.005) == 3

    @pytest.mark.parametrize("stress", ((-5000.0, -1.0, 0.0), (0.0, 0.0, 0.0)))
    def test_양의_인장응력이_없으면_상대하강을_보류한다(
        self, stress: tuple[float, ...]
    ) -> None:
        frame = Frame(
            {
                "strain_engineering": np.asarray([0.0, 0.01, 0.02]),
                "stress_engineering": np.asarray(stress),
            },
            {"strain_engineering": "1", "stress_engineering": "Pa"},
        )
        with pytest.raises(
            ProcessingError, match="양의 인장응력이 없어 상대 하강을 평가할 수 없음"
        ):
            _run(frame, {"method": "keep"})

    def test_옛_하항복_참조는_값이_없다고_명확히_보류한다(self) -> None:
        with pytest.raises(ProcessingError, match=r"@lower_yield_strength.*내지 않았습니다"):
            processing.apply(
                [
                    Step(
                        "tensile.yield_drop",
                        {
                            "method": "lower_yield",
                            "plateau_start": 0.0016,
                            "plateau_end": 0.02,
                            "plateau_stress": 278e6,
                        },
                    ),
                    Step(
                        "tensile.elastic_modulus",
                        {"method": "manual", "manual_modulus": E_TRUE},
                    ),
                    Step(
                        "tensile.true_plastic",
                        {
                            "youngs_modulus": "@youngs_modulus",
                            "proof_stress": "@lower_yield_strength",
                        },
                    ),
                ],
                mild_steel(),
            )

    def test_외부_하항복강도_참조를_소성_시작에_연결한다(self) -> None:
        # 외부 입력으로 받은 사용자 지정 proof_stress 참조도 호환해 첫 곡선 교점을 쓴다.
        frame = mild_steel()
        strain = frame.columns["strain_engineering"]
        stress = frame.columns["stress_engineering"]
        above = int(np.flatnonzero(stress >= 278e6)[0])
        fraction = (278e6 - stress[above - 1]) / (stress[above] - stress[above - 1])
        expected_strain = strain[above - 1] + fraction * (strain[above] - strain[above - 1])
        result = processing.apply(
            [
                Step(
                    "tensile.elastic_modulus", {"method": "manual", "manual_modulus": E_TRUE}
                ),
                Step(
                    "tensile.true_plastic",
                    {
                        "youngs_modulus": "@youngs_modulus",
                        "proof_stress": "@lower_yield_strength",
                    },
                ),
            ],
            frame,
            given=(processing.Scalar("lower_yield_strength", "외부 하항복강도", 278e6, "Pa"),),
        )
        assert result.frame.columns["strain_engineering"][0] == pytest.approx(expected_strain)
        assert result.frame.columns["stress_engineering"][0] == pytest.approx(278e6)
        assert result.frame.columns["strain_true_plastic"][0] == 0.0
        assert result.frame.columns["stress_true"][0] == pytest.approx(
            278e6 * (1.0 + expected_strain)
        )
        assert "proof_strain" not in result.stages[-1].options
        assert any("좌표 없이" in note for note in result.notes)


def plateau() -> Frame:
    """항복 뒤 응력이 **그대로**인 곡선 — 내려가지는 않는데 접선계수가 0 이다."""
    strain = np.linspace(0.0, 0.10, 201)
    stress = np.minimum(E_TRUE * strain, YIELD_TRUE)
    return Frame(
        {"strain_engineering": strain, "stress_engineering": stress},
        {"strain_engineering": "1", "stress_engineering": "Pa"},
    )


class Test단조_증가_보정:
    """**변형률이 늘어도 응력이 그대로면 솔버가 거부한다**(2026-09-18 요청) — 하강만
    문제가 아니다. 평탄부까지 아주 조금씩 올려 엄격히 증가로 만든다."""

    OPTIONS: ClassVar[dict[str, object]] = {
        "column": "stress_engineering",
        "x": "strain_engineering",
    }

    def test_평탄부를_엄격히_증가로_만든다(self) -> None:
        result = processing.apply([Step("curve.monotone", dict(self.OPTIONS))], plateau())
        fixed = result.frame.columns["stress_engineering"]
        assert np.all(np.diff(fixed) > 0)
        # 올린 폭은 물성으로는 없는 값이다 — 400 MPa 곡선에서 점당 400 Pa.
        assert scalar(result, "monotone_max_lift") < 1e-3 * YIELD_TRUE
        assert scalar(result, "monotone_points") > 0
        assert any("엄격히 증가" in note for note in result.notes)

    def test_최소_기울기를_주면_그만큼_오른다(self) -> None:
        result = processing.apply(
            [Step("curve.monotone", {**self.OPTIONS, "min_slope": 1e7})], plateau()
        )
        fixed = result.frame.columns["stress_engineering"]
        strain = result.frame.columns["strain_engineering"]
        slopes = np.diff(fixed) / np.diff(strain)
        assert np.all(slopes >= 1e7 * (1 - 1e-9))

    def test_엄격을_끄면_평탄부를_둔다(self) -> None:
        result = processing.apply(
            [Step("curve.monotone", {**self.OPTIONS, "strict": False})], plateau()
        )
        fixed = result.frame.columns["stress_engineering"]
        assert np.all(np.diff(fixed) >= 0)
        assert scalar(result, "monotone_points") == 0
        assert any("손대지 않았습니다" in note for note in result.notes)

    def test_내려간_곳은_고른_방법으로_올리고_폭을_말한다(self) -> None:
        result = processing.apply(
            [Step("curve.monotone", {**self.OPTIONS, "method": "isotonic"})], polymer_neck()
        )
        fixed = result.frame.columns["stress_engineering"]
        assert np.all(np.diff(fixed) > 0)
        # 15 MPa 를 내려갔던 곡선 — 최대 폭이 크고, 이유를 가르라는 말이 선다.
        assert scalar(result, "monotone_max_lift") > 1e6
        assert any("tensile.yield_drop" in note for note in result.notes)

    def test_이미_증가하면_손대지_않는다(self) -> None:
        result = processing.apply([Step("curve.monotone", dict(self.OPTIONS))], synthetic())
        assert scalar(result, "monotone_points") == 0
        assert np.array_equal(
            result.frame.columns["stress_engineering"],
            synthetic().columns["stress_engineering"],
        )

    def test_항복_강하_정리도_하강_없이_최소_기울기를_건다(self) -> None:
        # 전에는 「하강이 없다」 로 일찍 돌아가 min_slope 가 무시됐다.
        result = processing.apply(
            [Step("tensile.yield_drop", {"method": "envelope", "min_slope": 1e7})], plateau()
        )
        fixed = result.frame.columns["stress_engineering"]
        assert np.all(np.diff(fixed) > 0)
        assert scalar(result, "yield_drop_points") > 0
