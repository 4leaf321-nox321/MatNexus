"""예제 DMA 파일을 만든다 — 온도 스윕과 변형률 스윕.

    .venv/Scripts/python.exe scripts/make_example_dma.py

`tests/fixtures/example_dma_*.csv` 를 다시 만든다. **파일을 손으로 고치지 말고
여기를 고친다** — 정답이 코드에 있고 파일은 그 그림자다.

## 왜 합성인가

`dma_freq_temp.csv` 는 실파일이라 **정답을 모른다.** 읽히는지·안 터지는지는
보이지만 「나온 값이 맞는지」 는 못 본다. 여기 파일은 3항 일반화 Maxwell 로
만들었으므로 **되찾은 계수를 정답과 견줄 수 있다** — 실제로 그 견주기가 묶음
평균의 결함을 잡았다(τ 격자를 주파수 창에서 뽑아 E∞ 가 0 이 됐다, v1.135.0).

    E∞ = 5.0e6 Pa
    (Eᵢ, τᵢ) = (2.0e8, 1e-2) · (8.0e8, 1e0) · (3.0e8, 1e2)
    E₀ = E∞ + ΣEᵢ = 1.305e9 Pa

## 두 갈래를 다 만든다

    온도 스윕   온도마다 좁은 주파수 창 → 겹쳐야 넓어진다 → Prony
    변형률 스윕 한 온도·한 주파수, 변형률을 훑는다 → 평탄부 높이가 E

TA TRIOS 내보내기 모양을 그대로 흉내낸다: 머리말 키-값, `[step]` 마다 표 하나,
단위 줄이 열 이름 아래.
"""

from __future__ import annotations

import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# --- 정답 -------------------------------------------------------------------

#: 3항 Maxwell. (탄성률 Pa, 완화시간 s)
TERMS = ((2.0e8, 1.0e-2), (8.0e8, 1.0e0), (3.0e8, 1.0e2))
EQUILIBRIUM_PA = 5.0e6

#: WLF. 기준 온도 20 °C.
#:
#: **17.44/51.6 은 Tg 기준의 「보편」 값이라 여기 쓰면 안 된다.** 기준을 20 °C 로
#: 두고 -40 °C 를 재면 `C2 + ΔT` 가 음수가 되어 식이 성립 범위를 벗어나고,
#: 이동인자가 10^-124 같은 값이 된다 — 곡선이 평형 탄성률로 뭉갠다(실측).
#: 기준 온도에 맞는 계수를 쓰고, 온도 범위도 그 안에서 고른다.
REFERENCE_C = 20.0
C1, C2 = 8.0, 100.0


def shift(celsius: float) -> float:
    """log10(a_T). 기준 온도에서 0."""
    return -C1 * (celsius - REFERENCE_C) / (C2 + (celsius - REFERENCE_C))


def moduli(frequency_hz: float, scatter: float = 0.0) -> tuple[float, float]:
    """저장·손실(MPa). `scatter` 는 시편 사이의 차이."""
    omega = 2.0 * math.pi * frequency_hz
    storage = EQUILIBRIUM_PA
    loss = 0.0
    for modulus, tau in TERMS:
        wt = omega * tau
        storage += modulus * wt * wt / (1.0 + wt * wt)
        loss += modulus * wt / (1.0 + wt * wt)
    factor = 1.0 + scatter
    return storage * factor / 1e6, loss * factor / 1e6


HEADER = """rundate,2026-08-28
Instrument name,DMA850-EXAMPLE
Instrument location,MatNexus
Operator,예제
Sample name,{sample}
Geometry name,3 Point Bending Clamp
Procedure name,{procedure}
proceduresegments,{procedure}
Length,50.0 mm
Width,5.000 mm
Thickness,1.000 mm
"""

COLUMNS = (
    "Angular frequency,Step time,Temperature,Oscillation strain,"
    "Oscillation stress,Tan(delta),Storage modulus,Loss modulus,Frequency"
)
UNITS = "rad/s,s,°C,%,MPa,,MPa,MPa,Hz"


def temperature_sweep(path: Path, sample: str, scatter: float = 0.0) -> None:
    """온도 스윕 — **한 파일 안에 온도별 스윕이 여럿.**

    각 온도에서 좁은 주파수 창(0.1~20 Hz)만 훑는다. 실제 DMA 가 그렇고, 그래서
    겹쳐야 넓은 곡선이 나온다.
    """
    lines = [HEADER.format(sample=sample, procedure="DMA Oscillatory Temperature Sweep")]
    clock = 0.0
    # `C2 + ΔT > 0` 안에서 고른다. 0~80 °C 면 이동이 +2 ~ -3 데케이드라,
    # 좁은 창(0.1~20 Hz)을 겹쳐 7 데케이드짜리 마스터커브가 나온다.
    for celsius in (0.0, 20.0, 40.0, 60.0, 80.0):
        lines.append("[step]")
        lines.append(f"Temperature Sweep (Multifrequency) - {celsius:.0f}C")
        lines.append(COLUMNS)
        lines.append(UNITS)
        # 잰 주파수는 좁지만, **환산 주파수**는 온도만큼 밀린다.
        for decade in range(9):
            measured_hz = 0.1 * (20.0 / 0.1) ** (decade / 8.0)
            reduced_hz = measured_hz * (10.0 ** shift(celsius))
            storage, loss = moduli(reduced_hz, scatter)
            clock += 13.0
            lines.append(
                f"{2 * math.pi * measured_hz:.6g},{clock:.4f},{celsius:.2f},"
                f"5.00000e-3,{storage * 0.005:.6g},{loss / storage:.6g},"
                f"{storage:.6g},{loss:.6g},{measured_hz:.6g}"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def strain_sweep(path: Path, sample: str, plateau_pa: float = 1.2e9) -> None:
    """변형률 스윕 — **E 를 뽑는 것이 목적.**

    낮은 변형률에서 평탄(선형점탄성)하다가 어느 지점부터 떨어진다. 그 평탄
    구간의 높이가 저장 탄성률이다 — 인장의 「직선 구간의 기울기」와 같은 자리.
    """
    lines = [HEADER.format(sample=sample, procedure="DMA Oscillatory Strain Sweep")]
    lines.append("[step]")
    lines.append("Strain Sweep - 1")
    lines.append(COLUMNS)
    lines.append(UNITS)
    clock = 0.0
    for index in range(24):
        strain_pct = 1.0e-3 * (10.0 / 1.0e-3) ** (index / 23.0)
        # 임계 변형률 0.1 % 부터 무너진다.
        softening = 1.0 / (1.0 + (strain_pct / 0.1) ** 1.8)
        storage = plateau_pa * (0.02 + 0.98 * softening) / 1e6
        loss = storage * (0.02 + 0.30 * (1.0 - softening))
        clock += 13.0
        lines.append(
            f"{2 * math.pi * 1.0:.6g},{clock:.4f},25.00,{strain_pct:.6g},"
            f"{storage * strain_pct / 100:.6g},{loss / storage:.6g},"
            f"{storage:.6g},{loss:.6g},1.00000"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


#: 변형률 스윕의 평탄부. 시험이 이 값을 되찾는지 본다.
STRAIN_PLATEAU_PA = 1.20e9

if __name__ == "__main__":
    # 온도 스윕은 시편 셋 — **묶음을 시험하려면 여럿이어야 하고, 흩어져 있어야
    # 세 방법이 갈린다.** 똑같으면 어느 방법을 써도 같은 답이 나온다.
    for index, scatter in enumerate((0.0, 0.06, -0.05), start=1):
        temperature_sweep(
            OUT / f"example_dma_temp_sweep_{index:02d}.csv",
            sample=f"EPDM-EX temperature sweep {index}",
            scatter=scatter,
        )
    strain_sweep(
        OUT / "example_dma_strain_sweep.csv",
        sample="EPDM-EX strain sweep",
        plateau_pa=STRAIN_PLATEAU_PA,
    )
    print(f"만들었습니다 ({OUT}):")
    for path in sorted(OUT.glob("example_dma_*.csv")):
        print(f"  {path.name}  {path.stat().st_size:,} bytes")
