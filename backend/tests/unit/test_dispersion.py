"""분산식 맞춤(`matcore.dispersion`) — **잰 점을 따르나, 그리고 nd · νd 가 맞나.**

Zemax AGF 는 굴절률을 식의 계수로 받는다. 맞춘 식이 점을 못 따르면 그 유리로 한 설계가 통째로
어긋나는데, 덱은 오류 없이 읽힌다 — 그래서 잔차를 늘 잰다.
"""

from __future__ import annotations

import math

import pytest

from matcore import dispersion

#: Zeon 330R(Zemax 플라스틱 카탈로그의 Schott 식 계수) — 공개 카탈로그 값.
ZEON_330R = (
    2.24171666,
    -1.74741324e-3,
    1.11523310e-2,
    7.82763713e-4,
    -7.94137410e-5,
    3.93670794e-6,
)


def _points(
    coefficients: tuple[float, ...], wavelengths: list[float]
) -> list[tuple[float, float]]:
    return [(at, dispersion.schott_index(coefficients, at)) for at in wavelengths]  # type: ignore[arg-type]


def test_Schott_식에서_나온_점이면_계수를_되찾는다() -> None:
    wavelengths = [0.40, 0.44, 0.48, 0.55, 0.60, 0.70, 0.90, 1.20, 1.60]
    fit = dispersion.fit_schott(_points(ZEON_330R, wavelengths))

    assert fit.terms == 6
    assert fit.max_residual < 1e-9
    for found, expected in zip(fit.coefficients, ZEON_330R, strict=True):
        assert found == pytest.approx(expected, rel=1e-5, abs=1e-12)

    # νd 는 정의대로 — 같은 식에서 셈한 값과 같아야 한다.
    def n(at: float) -> float:
        return dispersion.schott_index(ZEON_330R, at)

    expected = (n(dispersion.LINE_D) - 1) / (n(dispersion.LINE_F) - n(dispersion.LINE_C))
    assert fit.vd == pytest.approx(expected, abs=1e-6)
    # 카탈로그의 NM 줄(nd 1.509420 · νd 56.0)은 제조사의 공칭값이라 자기 식과도 조금 다르다
    # (nd 5e-6 · νd 0.13). 그 차이 안에서 맞으면 된다.
    assert fit.nd == pytest.approx(1.50942, abs=1e-5)
    assert fit.vd == pytest.approx(56.0, abs=0.2)


def test_항은_점보다_하나_적다_잔차를_볼_자유도를_남긴다() -> None:
    """점과 항이 같으면 잔차가 늘 0 이라 「식이 점을 따르나」 를 말할 수 없다."""
    fit = dispersion.fit_schott(_points(ZEON_330R, [0.45, 0.55, 0.65]))
    assert fit.terms == 2
    assert fit.max_residual > 0


def test_점이_셋보다_적으면_거절한다() -> None:
    with pytest.raises(dispersion.DispersionError, match="3점 이상"):
        dispersion.fit_schott([(0.5876, 1.49), (0.6563, 1.488)])


def test_같은_파장이_둘이면_거절한다() -> None:
    with pytest.raises(dispersion.DispersionError, match="같은 파장"):
        dispersion.fit_schott([(0.5876, 1.49), (0.5876, 1.491), (0.6563, 1.488)])


def test_잔차는_점에서의_굴절률_차이다() -> None:
    """잘못 적힌 점 하나가 있으면 잔차가 그만큼 드러난다 — 렌더러가 1e-4 를 넘으면 짚는다."""
    points = _points(ZEON_330R, [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80])
    at, n = points[3]
    points[3] = (at, n + 0.002)
    fit = dispersion.fit_schott(points)
    assert fit.max_residual > 1e-4
    assert math.isfinite(fit.vd)
