"""굴절률의 **분산식 맞춤** — 파장별 n 에 Schott 식을 맞춘다(Zemax 유리 카탈로그가 받는 꼴).

광학 설계 프로그램은 굴절률을 점 표가 아니라 **식의 계수**로 받는 일이 많다(Zemax AGF 의
`CD` 줄). 우리에게 있는 것은 잰 점들이라, 그 사이를 식으로 잇는 일이 필요하다.

## 왜 Schott 식인가

    n² = a0 + a1·λ² + a2·λ⁻² + a3·λ⁻⁴ + a4·λ⁻⁶ + a5·λ⁻⁸        (λ 는 µm)

**n² 에 대해 계수가 일차다** — 최소제곱이 닫힌 꼴로 풀린다. Sellmeier 식은 공명 파장이
분모에 들어가 비선형 맞춤이 필요하고, 시작값에 따라 다른 답이 나온다. 같은 점에서 늘 같은
계수가 나와야 덱이 재현된다. 광학 플라스틱 카탈로그(Zeon 등)가 이 식으로 실려 있다.

## 점보다 항을 적게

항은 점 수보다 **하나 적게**(최대 여섯) 쓴다. 점과 항이 같으면 잔차가 늘 0 이라 「식이 점을
얼마나 따르나」 를 말할 수 없고, 점 사이에서 식이 출렁여도 모른다. 그래서 점이 셋 이상이어야
한다. 항을 더하는 차례는 가시광에서 먼저 듣는 것부터다 — 상수, λ⁻²(Cauchy), λ²(적외 흡수 꼬리),
λ⁻⁴ ….

DB 도 HTTP 도 모른다. `tests/architecture` 가 검사한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: (계수 이름, λ 의 지수) — **맞춤에 더하는 차례**다. 계수의 자리(a0…a5)는 이름이 정한다.
TERMS: tuple[tuple[str, int], ...] = (
    ("a0", 0),
    ("a2", -2),
    ("a1", 2),
    ("a3", -4),
    ("a4", -6),
    ("a5", -8),
)

#: Fraunhofer 선(µm) — nd · νd 를 정하는 세 파장(헬륨 d · 수소 F · 수소 C).
LINE_D = 0.5875618
LINE_F = 0.4861327
LINE_C = 0.6562725

#: 맞춤에 필요한 최소 점 수 — 항 둘 + 잔차를 볼 자유도 하나.
MIN_POINTS = 3


class DispersionError(ValueError):
    """식을 맞출 수 없다. 메시지는 사용자가 읽는다."""


@dataclass(frozen=True)
class SchottFit:
    coefficients: tuple[float, float, float, float, float, float]
    """a0 … a5 — 쓰지 않은 항은 0."""
    terms: int
    """실제로 맞춘 항 수."""
    points: int
    max_residual: float
    """잰 점에서 |n_식 - n_잰값| 의 최댓값."""
    wavelength_min_um: float
    wavelength_max_um: float

    def index(self, wavelength_um: float) -> float:
        return schott_index(self.coefficients, wavelength_um)

    @property
    def nd(self) -> float:
        return self.index(LINE_D)

    @property
    def vd(self) -> float:
        """아베수 νd = (nd - 1)/(nF - nC)."""
        return (self.nd - 1) / (self.index(LINE_F) - self.index(LINE_C))

    def covers(self, wavelength_um: float) -> bool:
        return self.wavelength_min_um <= wavelength_um <= self.wavelength_max_um


def schott_index(
    coefficients: tuple[float, float, float, float, float, float], wavelength_um: float
) -> float:
    a0, a1, a2, a3, a4, a5 = coefficients
    lam2 = wavelength_um**2
    square = a0 + a1 * lam2 + a2 / lam2 + a3 / lam2**2 + a4 / lam2**3 + a5 / lam2**4
    if square <= 0:
        raise DispersionError(
            f"맞춘 식이 {wavelength_um:g} µm 에서 n² ≤ 0 을 냅니다 — 잰 범위 밖에서 식이 "
            "무너집니다."
        )
    return math.sqrt(square)


def fit_schott(points: list[tuple[float, float]]) -> SchottFit:
    """`(파장 µm, n)` 점들에 Schott 식을 맞춘다. **점이 셋 이상**이어야 한다."""
    if len(points) < MIN_POINTS:
        raise DispersionError(
            f"분산식을 맞추려면 파장이 다른 굴절률이 {MIN_POINTS}점 이상 있어야 합니다 "
            f"(지금 {len(points)}점)."
        )
    wavelengths = np.array([float(at) for at, _ in points])
    indices = np.array([float(n) for _, n in points])
    if np.any(wavelengths <= 0) or np.any(indices <= 0):
        raise DispersionError("파장과 굴절률은 0 보다 커야 합니다.")
    if len(set(wavelengths.tolist())) != len(points):
        raise DispersionError("같은 파장의 굴절률이 둘 있습니다 — 하나만 남기세요.")
    terms = min(len(TERMS), len(points) - 1)
    design = np.column_stack([wavelengths**power for _, power in TERMS[:terms]])
    # 열마다 크기가 수십 배 다르다(λ⁻⁸) — 열을 맞춰 두고 풀어야 계수가 흔들리지 않는다.
    scale = np.abs(design).max(axis=0)
    solved, *_ = np.linalg.lstsq(design / scale, indices**2, rcond=None)
    found = dict.fromkeys(("a0", "a1", "a2", "a3", "a4", "a5"), 0.0)
    for (name, _), value, size in zip(TERMS[:terms], solved, scale, strict=True):
        found[name] = float(value / size)
    coefficients = (
        found["a0"],
        found["a1"],
        found["a2"],
        found["a3"],
        found["a4"],
        found["a5"],
    )
    residual = max(abs(schott_index(coefficients, float(at)) - float(n)) for at, n in points)
    return SchottFit(
        coefficients=coefficients,
        terms=terms,
        points=len(points),
        max_residual=residual,
        wavelength_min_um=float(wavelengths.min()),
        wavelength_max_um=float(wavelengths.max()),
    )
