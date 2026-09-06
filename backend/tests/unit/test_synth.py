"""합성 곡선 — **지어낸 곡선은 지어냈다고 말해야 한다** (이식 5단계).

모델 분기(MT 원본의 판단)와, 원본에 없던 한 층 — *MAT_024 소성 표 규약
(첫 점이 (0, 진항복), 진응력·소성변형률 단조 증가)을 문다.
"""

from __future__ import annotations

import pytest

from matcore import synth


class Test모델_분기:
    def test_완전_정보면_Hollomon_경화다(self) -> None:
        made = synth.synthesize(200e9, 300e6, 450e6, 0.25)
        assert made is not None
        assert "Hollomon" in made.model
        assert "실측이 아니다" in made.note
        # 공칭 곡선이 항복에서 시작해 UTS 근처까지 오른다.
        assert made.stress_pa[-1] == pytest.approx(450e6, rel=0.01)

    def test_항복만_있으면_완전소성이다(self) -> None:
        made = synth.synthesize(200e9, 300e6)
        assert made is not None
        assert made.model == "elastic-perfectly plastic"
        assert made.table_rows  # 소성 표는 나온다 — 진응력은 평탄부에서도 오른다

    def test_항복_미공표_연성은_UTS_평탄부다(self) -> None:
        """동박·솔더 — 항복을 공표하지 않는 연성 금속. 취성 취급하면 통째로 틀린다."""
        made = synth.synthesize(70e9, None, 220e6, 0.15)
        assert made is not None
        assert "yield unknown" in made.model
        assert "과대평가" in made.note  # 보수적 근사임을 말한다

    def test_취성은_소성_표가_없다(self) -> None:
        made = synth.synthesize(300e9, None, 400e6, 0.005)
        assert made is not None
        assert made.model == "linear-elastic (brittle)"
        assert made.table_rows == ()

    def test_근거가_없으면_지어내지_않는다(self) -> None:
        assert synth.synthesize(None) is None
        assert synth.synthesize(200e9) is None  # E 뿐 — 항복도 UTS 도 없다
        assert synth.synthesize(0, 300e6) is None

    def test_항복이_인장보다_크면_모순을_말한다(self) -> None:
        made = synth.synthesize(200e9, 500e6, 400e6, 0.2)
        assert made is not None
        assert made.inconsistent is True
        assert "출처·조건이 다르다" in made.note


class Test소성_표_규약:
    """*MAT_024 가 읽는 규약 — 어기면 덱은 멀쩡히 돌고 답만 틀린다."""

    def test_첫_점은_영_소성변형률의_진항복이다(self) -> None:
        made = synth.synthesize(200e9, 300e6, 450e6, 0.25)
        assert made is not None and made.table_rows
        first = made.table_rows[0]
        assert first["plastic_strain"] == 0.0
        ey = 300e6 / 200e9
        assert first["true_stress"] == pytest.approx(300e6 * (1 + ey))

    def test_표는_단조_증가다(self) -> None:
        for args in ((200e9, 300e6, 450e6, 0.25), (200e9, 300e6, None, None)):
            made = synth.synthesize(*args)
            assert made is not None and len(made.table_rows) >= 2
            plastic = [row["plastic_strain"] for row in made.table_rows]
            stress = [row["true_stress"] for row in made.table_rows]
            assert plastic == sorted(plastic) and len(set(plastic)) == len(plastic)
            assert stress == sorted(stress) and len(set(stress)) == len(stress)
