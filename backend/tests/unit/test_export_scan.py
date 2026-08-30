"""예제 덱을 읽어 정의 초안으로 — **빈 폼에서 시작하지 않게.**

무는 자리를 「읽힌다」 가 아니라 넷에 둔다. 넷 다 틀려도 덱은 나오고, 틀린 채로
나온 덱은 솔버가 오류로 알려 주지 않는다:

  1. **우리가 낸 덱을 다시 읽으면 같은 구조가 나온다.** 이보다 정직한 검사가
     없다 — 답을 아는 입력이다.
  2. **표를 표로 본다.** 소성 곡선을 값 줄 스무 개로 읽으면 사람이 스무 번
     지워야 하고, 그 앞에서 이 기능은 없는 것보다 나쁘다.
  3. **칸 폭을 센다.** 사람이 남의 덱을 보고 세는 것은 틀리기 쉽고, 틀려도
     덱은 멀쩡히 나온다.
  4. **짐작을 짐작이라고 말한다.** 맞는 것이 여럿이면 아무것도 제안하지 않는다.
"""

from __future__ import annotations

from matcore import export
from matcore.export import scan

ABAQUS = """** MatNexus
** Consistent units: SI
*MATERIAL, NAME=DP600_MD
*DENSITY
7.850000000000E+03,
*ELASTIC, TYPE=ISOTROPIC
2.000000000000E+11, 3.000000000000E-01
*PLASTIC, HARDENING=ISOTROPIC
2.500000000000E+08, 0.000000000000E+00
3.000000000000E+08, 1.000000000000E-02
3.400000000000E+08, 5.000000000000E-02
"""

#: 고정폭 20칸 둘. OpenRadioss 가 이 모양이다.
FIXED = """#RHO_I
     7.850000000E+03     0.000000000E+00
"""


class Test우리가_낸_덱을_다시_읽는다:
    def test_키워드와_숫자가_갈린다(self) -> None:
        found = scan.scan(ABAQUS)
        kinds = [one.kind for one in found.lines]
        assert kinds[:4] == ["text", "text", "text", "text"]
        assert found.lines[0].text == "** MatNexus"
        assert found.lines[2].text == "*MATERIAL, NAME=DP600_MD"

    def test_밀도_줄은_칸_하나에_쉼표가_붙는다(self) -> None:
        # `*DENSITY` 다음 줄이 `7.85E+03,` 다. **쉼표를 흘리면 덱이 달라진다.**
        found = scan.scan(ABAQUS)
        density = next(one for one in found.lines if len(one.cells) == 1)
        assert density.kind == "fields"
        assert density.cells[0].value == 7850.0
        assert density.suffix == ","

    def test_소성_표를_표로_본다(self) -> None:
        """**스무 줄짜리 곡선을 값 줄 스무 개로 읽으면** 사람이 스무 번 지워야
        하고, 그 앞에서 이 기능은 없는 것보다 나쁘다."""
        found = scan.scan(ABAQUS)
        tables = [one for one in found.lines if one.kind == "rows"]
        assert len(tables) == 1, [one.kind for one in found.lines]
        assert tables[0].rows == 3
        assert len(tables[0].cells) == 2

    def test_탄성_줄은_표가_아니다(self) -> None:
        # 숫자 둘짜리 줄 하나뿐이다. 표로 묶으면 소성 표와 뭉개진다.
        found = scan.scan(ABAQUS)
        pairs = [one for one in found.lines if len(one.cells) == 2 and one.kind == "fields"]
        assert len(pairs) == 1
        assert pairs[0].cells[0].value == 2e11

    def test_실제_렌더러가_낸_덱도_읽힌다(self) -> None:
        """**답을 아는 입력이다.** 손으로 적은 예제가 아니라 지금 코드가 내는 것을
        그대로 먹인다 — 렌더러가 바뀌면 여기가 먼저 깨진다."""
        deck = export.Deck(
            name="DP600",
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
                        {"plastic_strain": 0.0, "true_stress": 250e6},
                        {"plastic_strain": 0.01, "true_stress": 300e6},
                        {"plastic_strain": 0.05, "true_stress": 340e6},
                    ]
                },
            },
            provenance=(),
        )
        found = scan.scan(export.renderer("abaqus").render(deck).text)
        assert any(one.kind == "rows" and one.rows == 3 for one in found.lines)
        assert any(one.text == "*MATERIAL, NAME=DP600" for one in found.lines)


class Test칸_폭:
    def test_고정폭을_센다(self) -> None:
        """**사람이 세면 틀리고, 틀려도 덱은 나온다.** 그 다음이 조용히 틀린
        해석이다."""
        found = scan.scan(FIXED)
        numbers = next(one for one in found.lines if one.cells)
        assert numbers.width == 20
        assert numbers.precision == 9
        assert numbers.join == ""

    def test_폭이_다르면_다르게_센다(self) -> None:
        """**20칸이라고 쳐 두면 안 된다.** OptiStruct 는 8칸, LS-DYNA 는 10칸이다 —
        그 덱을 20칸 정의로 저장하면 모든 값이 다른 필드로 간다."""
        found = scan.scan(" 1.0E+00 2.0E+00\n")  # 8칸 둘
        assert next(one for one in found.lines if one.cells).width == 8

    def test_왼쪽_맞춤도_잰다(self) -> None:
        """**맞춤이 두 가지다.** LS-DYNA·Radioss 는 오른쪽 맞춤이고 Nastran·
        OptiStruct 벌크는 왼쪽 맞춤이다 — 오른쪽만 보면 절반의 솔버에서 폭을
        못 잰다."""
        found = scan.scan("1.0E+00 22.0E+00\n")  # 8칸 왼쪽 맞춤
        assert next(one for one in found.lines if one.cells).width == 8

    def test_간격이_들쭉날쭉하면_고정폭이_아니다(self) -> None:
        # **자유 형식을 고정폭으로 저장하면** 값이 칸을 넘쳐 옆 필드를 밀어낸다.
        found = scan.scan("1.0E+00 22.0E+00 3.0E+00\n")
        assert next(one for one in found.lines if one.cells).width is None

    def test_좁은_폭은_고정폭으로_안_본다(self) -> None:
        # 실제 솔버 폭은 8·10·16·20 이다. 그보다 좁으면 자유 형식이다.
        found = scan.scan("1.0 2.0 3.0\n")
        assert next(one for one in found.lines if one.cells).width is None

    def test_쉼표가_있으면_자유_형식이다(self) -> None:
        # 고정폭 덱은 칸으로만 가른다 — 쉼표를 같이 쓰면 칸 수를 세는 뜻이 없다.
        found = scan.scan(ABAQUS)
        assert all(one.width is None for one in found.lines if one.cells)


class Test표로_묶는_선:
    """**어디까지가 표인가.** 잘못 묶으면 조용히 틀린다 — 표는 줄 정의 하나로
    여러 줄을 내므로, 값 줄 둘을 표로 보면 두 번째 줄의 값이 통째로 사라진다.
    반대(표를 값 줄로 봄)는 화면에 그대로 보여서 사람이 안다.
    """

    def test_같은_모양_둘은_아직_표가_아니다(self) -> None:
        found = scan.scan("1.0, 2.0\n3.0, 4.0\n")
        assert [one.kind for one in found.lines] == ["fields", "fields"]

    def test_셋부터_표다(self) -> None:
        found = scan.scan("1.0, 2.0\n3.0, 4.0\n5.0, 6.0\n")
        assert [one.kind for one in found.lines] == ["rows"]
        assert found.lines[0].rows == 3

    def test_모양이_다르면_안_묶인다(self) -> None:
        # 숫자 개수가 다르면 다른 뜻의 줄이다.
        found = scan.scan("1.0, 2.0\n3.0, 4.0, 5.0\n6.0, 7.0\n")
        assert [one.kind for one in found.lines] == ["fields", "fields", "fields"]


#: 카드에서 뽑은 값. 앱이 이 모양으로 준다.
KNOWN = {
    "elastic.youngs_modulus": 200e9,
    "elastic.poisson_ratio": 0.3,
    "elastic.density": 7850.0,
}


class Test이름_붙이기:
    def test_카드_값과_같은_숫자에_이름을_붙인다(self) -> None:
        """**여기가 「막연하다」 를 실제로 없애는 자리다.** 덱을 올린 사람은 그
        덱이 자기 재료의 것임을 아는데, 화면은 숫자만 본다."""
        found = scan.scan(ABAQUS, KNOWN)
        named = {
            cell.suggested: cell.value
            for one in found.lines
            for cell in one.cells
            if cell.suggested
        }
        assert named["elastic.density"] == 7850.0
        assert named["elastic.youngs_modulus"] == 2e11
        assert named["elastic.poisson_ratio"] == 0.3

    def test_유효숫자가_잘려도_알아본다(self) -> None:
        # 덱은 값을 잘라 적는다. 정확히 같기를 요구하면 아무것도 안 맞는다.
        found = scan.scan("2.0000E+11\n", {"elastic.youngs_modulus": 200000000000.4})
        assert found.lines[0].cells[0].suggested == "elastic.youngs_modulus"

    def test_여럿에_맞으면_아무것도_제안하지_않는다(self) -> None:
        """0 이나 1 같은 값은 여러 자리에 나온다. 그때 하나를 고르는 것은
        **짐작이고, 짐작을 제안으로 내면 사람이 그대로 저장한다.**"""
        found = scan.scan("5.0, 5.0\n", {"a.one": 5.0, "b.two": 5.0})
        assert all(cell.suggested is None for cell in found.lines[0].cells)

    def test_하나도_안_맞으면_그렇다고_말한다(self) -> None:
        found = scan.scan(ABAQUS, {"elastic.density": 1234.5})
        assert any("같은 것이 없습니다" in said for said in found.notes)

    def test_짐작이라고_적는다(self) -> None:
        found = scan.scan(ABAQUS, KNOWN)
        assert any("짐작" in said for said in found.notes)


class Test빈_것:
    def test_빈_파일도_터지지_않는다(self) -> None:
        assert scan.scan("").lines == []

    def test_주석만_있어도_읽는다(self) -> None:
        found = scan.scan("** 아무 숫자도 없다\n")
        assert [one.kind for one in found.lines] == ["text"]


#: HyperMesh 가 낸 OptiStruct 덱. **실제로 겪는 모양이다** — 머리에 주석이 여럿
#: 붙고, 벌크 데이터는 `$` 로 시작하지 않으며 키워드 이름에 숫자가 있다.
HYPERMESH = """$$--------------------------------$
$$   HyperMesh name and version information
$$--------------------------------$
$$  Template: optistruct
$HMNAME MAT                     1"steel"
$HWCOLOR MAT                    1       5
MAT1           1 2.0E+05     0.3 7.85E-9
$
TABLES1        2
"""

#: HyperMesh 가 낸 Abaqus 덱의 머리. 주석이 `**` 다.
HM_ABAQUS = """**HM_ADD_COMMENTS
**  Abaqus Input Deck Generated by HyperMesh Version : 2021
**
*MATERIAL, NAME=steel
"""

#: LS-DYNA. 열 이름을 `$#` 주석으로 적어 준다 — 그 줄에 숫자가 없다.
LSDYNA = """$# LS-DYNA Keyword file created by LS-PrePost
*MAT_PIECEWISE_LINEAR_PLASTICITY
$#     mid        ro         e        pr
         1 7.850E-09 2.100E+05     0.300
"""


class Test전처리기가_낸_덱:
    """**HyperMesh 로 뽑은 덱이 흔하다.** 머리에 주석이 여럿 붙고, 카드마다
    이름·색 주석이 낀다. 그것을 값으로 읽으면 초안이 통째로 못 쓰게 된다.
    """

    def test_주석은_전부_글자_줄이다(self) -> None:
        found = scan.scan(HYPERMESH)
        head = [one for one in found.lines[:6]]
        assert all(one.kind == "text" for one in head), [one.kind for one in head]
        # 주석 안의 숫자(`1"steel"`·색 번호)가 값이 되면 안 된다.
        assert all(not one.cells for one in head)

    def test_키워드_이름_속_숫자를_값으로_안_읽는다(self) -> None:
        """**`MAT1` 의 `1` 이 값으로 잡혔었다**(2026-08-30). Nastran 벌크 데이터는
        키워드 이름에 숫자가 있고 `$` 로 시작하지도 않는다 — 칸이 하나 늘면 그
        덱은 모든 값이 한 칸씩 밀린다."""
        found = scan.scan(HYPERMESH)
        mat1 = next(one for one in found.lines if len(one.cells) == 4)
        assert [cell.text for cell in mat1.cells] == ["1", "2.0E+05", "0.3", "7.85E-9"]

        tables = found.lines[-1]
        assert [cell.text for cell in tables.cells] == ["2"], "TABLES1 의 1 이 값이 됐습니다"

    def test_뒤에_글자가_붙은_숫자도_값이_아니다(self) -> None:
        """앞만 보면 모자란다. **지수가 잘린 표기**가 실제로 나온다 — 포트란
        `1.0D+05` 는 통째로 숫자지만 `1.0D` 는 아니고, 단위가 붙은 `100mm` 도
        값이 아니다. 값으로 읽으면 칸이 하나 늘어 모든 값이 밀린다."""
        found = scan.scan("3ea 5.0\n")
        assert [cell.text for cell in found.lines[0].cells] == ["5.0"]

        cut = scan.scan("1.0D 2.0\n")
        assert [cell.text for cell in cut.lines[0].cells] == ["2.0"]

    def test_abaqus_머리_주석도_글자_줄이다(self) -> None:
        found = scan.scan(HM_ABAQUS)
        assert [one.kind for one in found.lines] == ["text"] * 4
        # 버전 번호 2021 이 값이 되면 안 된다.
        assert all(not one.cells for one in found.lines)

    def test_lsdyna_열이름_주석도_글자_줄이다(self) -> None:
        found = scan.scan(LSDYNA)
        kinds = [one.kind for one in found.lines]
        assert kinds == ["text", "text", "text", "fields"]
        assert len(found.lines[-1].cells) == 4


class Test주석이_표를_가를_때:
    """**주석을 건너뛰고 잇지 않는다.** 그 주석은 덱에 있던 것이라 정의에도 남아야
    하고, 무엇보다 거기가 진짜 경계일 수 있다 — 다른 재료의 표가 이어지는 자리.
    대신 그런 자리가 있으면 말한다.
    """

    SPLIT = "1.0, 2.0\n3.0, 4.0\n$ HyperMesh 주석\n5.0, 6.0\n7.0, 8.0\n"

    def test_묶지_않는다(self) -> None:
        found = scan.scan(self.SPLIT)
        assert [one.kind for one in found.lines] == [
            "fields",
            "fields",
            "text",
            "fields",
            "fields",
        ]

    def test_그러나_말해_준다(self) -> None:
        # 말 안 하면 사람은 값 줄 네 개를 손으로 지우고 표를 다시 만든다.
        found = scan.scan(self.SPLIT)
        assert any("표로 묶지" in said for said in found.notes), found.notes

    def test_흩어진_것이_없으면_말하지_않는다(self) -> None:
        # **없는 문제를 말하면 다음부터 안 읽는다.**
        found = scan.scan(ABAQUS)
        assert not any("표로 묶지" in said for said in found.notes)
