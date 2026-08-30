"""덱을 파일 정의로 — **ADR 0023 1단계의 산출물은 「된다/안 된다」 는 답이다.**

지금 Abaqus 덱은 파이썬 함수가 만든다. 쓰는 솔버가 Abaqus·OptiStruct·Radioss·
ANSYS Mechanical·LS-DYNA… 로 늘면 새 솔버마다 요청 → 개발 → 배포가 돈다. 그것을
데이터로 옮길 수 있는지 **먼저 확인하고** 나머지를 만든다.

확인하는 방법은 하나뿐이다: **같은 덱을 두 길로 만들어 바이트로 견준다.** 눈으로
비슷해 보이는 것은 답이 아니다 — 덱은 솔버가 읽는 파일이고, 쉼표 하나·칸 하나가
다르면 다른 값이 된다.

이 시험이 통과하면 그때부터 **회귀 시험**이 된다: 코드 렌더러를 고치면 템플릿도
같이 고쳐야 한다는 것을 여기서 알려 준다.
"""

from __future__ import annotations

from typing import Any

import pytest

from matcore import export
from matcore.export import template


def deck(
    *,
    density: float | None = 7850.0,
    points: tuple[tuple[float, float], ...] = (
        (0.0, 250e6),
        (0.01, 300e6),
        (0.05, 340e6),
    ),
) -> export.Deck:
    """탄소성 덱 하나.

    `test_export.py` 에 같은 모양이 있지만 **빌려 오지 않는다** — 시험 파일끼리
    import 하는 선례가 이 저장소에 없고(패키지가 아니라 mypy 가 못 찾는다), 이
    시험은 온도 표까지 자기가 손봐야 해서 통제권이 여기 있어야 한다.
    """
    values: dict[str, float] = {"youngs_modulus": 200e9, "poisson_ratio": 0.3}
    if density is not None:
        values["density"] = density
    blocks: dict[str, Any] = {"elastic": {"values": values}}
    if points:
        blocks["table"] = {
            "rows": [{"plastic_strain": x, "true_stress": y} for x, y in points]
        }
    return export.Deck(
        name="DP600_MD",
        solver_id=42,
        blocks=blocks,
        provenance=("시편 3개 · SECC_MDOI_1.0",),
    )


def _both(one: export.Deck) -> tuple[export.Rendered, export.Rendered]:
    return export.renderer("abaqus").render(one), template.render(export.ABAQUS_TEMPLATE, one)


class Test바이트가_같은가:
    def test_평범한_덱(self) -> None:
        code, made = _both(deck())
        assert made.text == code.text

    def test_밀도가_없을_때(self) -> None:
        """**빠진 값이 줄 하나를 지우고 말을 하나 남긴다.** 조판 중 가장 까다로운
        자리고, 여기가 되면 「있으면 넣고 없으면 빼기」 가 표현된다는 뜻이다."""
        code, made = _both(deck(density=None))
        assert made.text == code.text
        assert made.notes == code.notes
        assert any("*DENSITY" in said for said in made.notes)

    def test_표를_정리하면서_남긴_말까지_같다(self) -> None:
        """`prepare` 가 남기는 말(중복을 묶었다·거꾸로 간 점을 버렸다)이 줄에서 나온
        말보다 **앞선다.** 차례가 곧 「무엇을 먼저 알아야 하나」 다."""
        messy = deck(
            density=None,
            points=((0.0, 250e6), (0.0, 260e6), (0.01, 300e6)),
        )
        code, made = _both(messy)
        assert made.text == code.text
        assert made.notes == code.notes

    def test_온도별_탄성표도_같다(self) -> None:
        """온도 표는 **코드가 만든다**(빈 칸 검사가 있다). 템플릿이 그 묶음을 제자리에
        꽂기만 하는지 본다 — 조판과 계산의 경계가 실제로 서는지가 여기서 드러난다."""
        one = deck()
        one.blocks["elastic"]["rows"] = [
            {"temperature": 293.15, "youngs_modulus": 200e9, "poisson_ratio": 0.3},
            {"temperature": 473.15, "youngs_modulus": 180e9, "poisson_ratio": 0.31},
        ]
        code, made = _both(one)
        assert made.text == code.text


class Test칸_폭:
    """자유 형식만 되면 절반의 솔버에서 다시 코드로 돌아가야 한다.

    OpenRadioss 20칸 · OptiStruct 8칸 · LS-DYNA 10칸. **칸이 어긋나면 다른 필드로
    읽히고**, 덱을 읽는 솔버는 그것을 오류로 알려 주지 않는다.
    """

    def test_고정폭을_표현한다(self) -> None:
        spec: dict[str, Any] = {
            "lines": [
                {
                    "fields": [
                        {"value": "elastic.youngs_modulus", "format": ["fixed", 20, 9]},
                        {"value": "elastic.poisson_ratio", "format": ["fixed", 20, 9]},
                    ],
                    "join": "",
                }
            ]
        }
        made = template.render(spec, deck())
        line = made.text.splitlines()[0]
        assert len(line) == 40, f"20칸 둘이어야 하는데 {len(line)}칸입니다: {line!r}"
        assert line == f"{200e9:>20.9E}{0.3:>20.9E}"

    def test_모르는_형식은_거절한다(self) -> None:
        """**조용히 자유 형식으로 떨어지면 안 된다** — 고정폭 솔버가 말없이 틀린
        덱을 받는다."""
        spec: dict[str, Any] = {
            "lines": [{"fields": [{"value": "elastic.density", "format": "nastran"}]}]
        }
        with pytest.raises(export.ExportError) as caught:
            template.render(spec, deck())
        assert "nastran" in str(caught.value)


class Test막는_자리:
    def test_모르는_묶음은_거절한다(self) -> None:
        with pytest.raises(export.ExportError):
            template.render({"lines": [{"block": "없는것"}]}, deck())

    def test_없는_값을_꽂으라고_하면_어디를_고칠지_말한다(self) -> None:
        # 「값이 없습니다」 만으로는 템플릿의 어느 줄인지 모른다.
        spec: dict[str, Any] = {
            "lines": [{"fields": [{"value": "elastic.density", "format": "free"}]}]
        }
        with pytest.raises(export.ExportError) as caught:
            template.render(spec, deck(density=None))
        assert "elastic.density" in str(caught.value)
        assert "when" in str(caught.value)


ABAQUS_DEFINITION: dict[str, Any] = {
    "key": "abaqus_from_definition",
    "label": "Abaqus 탄소성 (정의)",
    "extension": "inp",
    "describe": "정의로 만든 것. 코드 렌더러와 바이트가 같아야 한다.",
    "keywords": ["*MATERIAL"],
    "needs": [
        {"block": "elastic", "values": ["youngs_modulus", "poisson_ratio"]},
        {"block": "elastic", "values": ["density"], "optional": True},
        {"block": "table", "rows_min": 2},
    ],
    "lines": export.ABAQUS_TEMPLATE["lines"],
}


class Test정의를_렌더러로:
    """**2단계가 서는 자리.** DB 행 하나가 렌더러가 되고, 그 렌더러가 내는 덱이
    코드 렌더러와 같아야 「배포 없이 새 솔버」 가 성립한다."""

    def test_정의로_만든_렌더러도_바이트가_같다(self) -> None:
        made = template.renderer_from_definition(ABAQUS_DEFINITION)
        one = deck()
        assert made.render(one).text == export.renderer("abaqus").render(one).text

    def test_needs_가_그대로_따라온다(self) -> None:
        # **화면이 「이 형식은 아직 못 낸다」 를 미리 말하는 근거다.** 안 따라오면
        # 덱을 만들다 터지고, 그때는 사람이 이유를 모른다.
        made = template.renderer_from_definition(ABAQUS_DEFINITION)
        assert [(need.block, need.optional) for need in made.needs] == [
            ("elastic", False),
            ("elastic", True),
            ("table", False),
        ]
        assert made.needs[2].rows_min == 2
        assert made.needs[0].values == ("youngs_modulus", "poisson_ratio")

    def test_빠진_것을_이름으로_말한다(self) -> None:
        """**저장하는 쪽이 이 함수를 그대로 부른다.** 여기서 안 막으면 「저장은
        됐는데 내려받을 때 터지는」 정의가 생기고, 그때는 화면에서 고칠 사람이
        그 자리에 없다."""
        for drop in ("key", "label", "extension", "describe", "lines"):
            broken = {k: v for k, v in ABAQUS_DEFINITION.items() if k != drop}
            with pytest.raises(export.ExportError) as caught:
                template.renderer_from_definition(broken)
            assert drop in str(caught.value)

    def test_기본값이_있는_것은_없어도_된다(self) -> None:
        bare = {
            key: ABAQUS_DEFINITION[key]
            for key in ("key", "label", "extension", "describe", "lines")
        }
        made = template.renderer_from_definition(bare)
        assert made.suffix == ""
        assert made.needs == ()
        assert made.media_type == "text/plain; charset=utf-8"

    def test_덱을_내는_자리는_하나다(self) -> None:
        # 같은 모양의 `Rendered` 를 둘 두면 라우트가 어느 쪽을 받는지 흐려진다.
        made = template.renderer_from_definition(ABAQUS_DEFINITION)
        assert isinstance(made.render(deck()), export.Rendered)


def viscoelastic_deck() -> export.Deck:
    """Prony 항을 가진 덱. **τ 가 일부러 뒤죽박죽이다** — 정리해 버리면 다른
    재료가 되는 것을 보이려면 순서가 흐트러져 있어야 한다."""
    return export.Deck(
        name="PP_TALC20",
        solver_id=7,
        blocks={
            "elastic": {"values": {"youngs_modulus": 1.8e9, "poisson_ratio": 0.4}},
            "viscoelastic": {
                "values": {"reference_temperature_k": 296.15},
                "rows": [
                    {"relative_modulus": 0.31, "relaxation_time_s": 1.0e-2},
                    {"relative_modulus": 0.22, "relaxation_time_s": 1.0e-4},
                    {"relative_modulus": 0.17, "relaxation_time_s": 1.0e1},
                ],
            },
        },
        provenance=("DMA 3점 · PP_TALC20",),
    )


#: Prony 표 세 줄. `g, k, τ` 이고 **`k` 는 상수 0.0** — DMA 가 체적을 재지 않아
#: 코드가 지어내지 않고 0 을 적는다.
PRONY_ROWS: dict[str, Any] = {
    "rows": "viscoelastic",
    "fields": [
        {"value": "relative_modulus", "format": "free"},
        {"const": "0.0"},
        {"value": "relaxation_time_s", "format": "free"},
    ],
}


class Test곡선이_들어가는_물성:
    """**선형만 되면 이 창구는 반쪽이다.** 실제로 늘어날 것은 점탄성·초탄성처럼
    표를 실은 물성이고, 그것이 안 되면 결국 코드로 돌아간다."""

    def test_prony_표가_코드와_바이트가_같다(self) -> None:
        one = viscoelastic_deck()
        code = export.renderer("abaqus_viscoelastic").render(one)
        mine = template.render({"lines": [PRONY_ROWS]}, one)
        # 코드 덱에서 Prony 줄만 뽑는다 — 나머지(주석·헤더)는 이 시험의 주제가 아니다.
        start = code.text.splitlines().index("*VISCOELASTIC, TIME=PRONY, TYPE=ISOTROPIC")
        theirs = code.text.splitlines()[start + 1 : start + 4]
        assert mine.text.splitlines() == theirs

    def test_표를_정리하지_않는다(self) -> None:
        """**Prony 는 점이 아니다.** `(g, τ)` 를 τ 로 정렬하거나 중복을 묶으면
        다른 재료가 되는데, 덱은 멀쩡히 돌고 결과도 그럴듯하다."""
        made = template.render({"lines": [PRONY_ROWS]}, viscoelastic_deck())
        first = [line.split(",")[2].strip() for line in made.text.splitlines()]
        assert first == [f"{1.0e-2:.12E}", f"{1.0e-4:.12E}", f"{1.0e1:.12E}"], (
            "τ 순서가 바뀌었습니다 — 표를 정리해 버렸습니다"
        )

    def test_상수_칸이_있다(self) -> None:
        # 체적 완화 `k` 자리. 이것을 정의로 못 적으면 곡선 물성은 코드로 남는다.
        made = template.render({"lines": [PRONY_ROWS]}, viscoelastic_deck())
        # **글자 그대로** 다. 코드가 `0.0` 을 적으므로 포맷을 거치면 어긋난다.
        assert all(line.split(",")[1].strip() == "0.0" for line in made.text.splitlines())

    def test_점_표는_여전히_정리한다(self) -> None:
        """넓혔다고 소성 곡선의 정리가 없어지면 안 된다 — `x`/`y` 가 그 스위치다."""
        messy = deck(points=((0.05, 340e6), (0.0, 250e6), (0.0, 260e6), (0.01, 300e6)))
        code = export.renderer("abaqus").render(messy)
        mine = template.render(export.ABAQUS_TEMPLATE, messy)
        assert mine.text == code.text
        assert mine.notes == code.notes

    def test_없는_열은_이름으로_말한다(self) -> None:
        spec: dict[str, Any] = {
            "lines": [{"rows": "viscoelastic", "fields": [{"value": "없는열"}]}]
        }
        with pytest.raises(export.ExportError) as caught:
            template.render(spec, viscoelastic_deck())
        assert "없는열" in str(caught.value)
        assert "relative_modulus" in str(caught.value)
