"""예제 인장 파일을 만든다 — **점 수 맞추기를 눈으로 보려고.**

    .venv/Scripts/python.exe scripts/make_example_tensile.py
    .venv/Scripts/python.exe scripts/make_example_tensile.py --out C:/tmp/예제

`tests/fixtures/example_tensile_0*.mtet` 를 다시 만든다. **파일을 손으로 고치지 말고
여기를 고친다** — 정답이 코드에 있고 파일은 그 그림자다(`make_example_dma.py` 와 같다).

## 왜 합성인가

실파일은 **정답을 모른다.** 읽히는지는 보이지만 「나온 값이 맞는지」 는 못 본다. 여기
파일은 아래 값으로 만들었으므로 되찾은 값을 정답과 견줄 수 있다.

    E        = 206 GPa   탄성계수
    sigma_y  = 350 MPa   항복(0.2% 오프셋이 여기 근처로 나와야 한다)
    Voce: sigma = sigma_y + q(1 - exp(-b * eps_p)),  q = 260 MPa, b = 12

## 왜 점을 촘촘히 박는가

**항복 무릎을 등간격으로 뜨면 뭉개진다** — 표를 읽는 솔버는 두 점 사이를 직선으로
잇는다. 그래서 이 파일은 탄성 구간을 아주 촘촘히(0.05% 간격), 소성 구간을 성기게
찍는다. 카드 만들 때 「점 수 맞추기」 를 껐다 켜 보면 표가 어떻게 달라지는지 보인다.

    안 켬                1200점 그대로 — 덱이 두꺼워진다
    등간격 30점           무릎이 두세 점으로 뭉개진다
    꺾이는 곳에 촘촘히 30점  무릎에 점이 몰린다
    측정점을 지키고 채우기   1200점을 하나도 안 버린다(요청보다 많으면 그대로)

## 시편 셋을 만든다

한 장으로는 묶음(글로벌 피팅)도 통계도 못 본다. 항복을 2% 안팎으로 흔들어 셋을 만든다 —
이상치로 잡힐 만큼 벌리지는 않는다.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
from pathlib import Path

# **콘솔 인코딩에 걸려 죽지 않게 한다.** Windows 기본 콘솔이 CP949 라, 물결 기호 하나가
# `UnicodeEncodeError` 를 내며 스크립트를 끝낸다 — 파일은 이미 다 썼는데 마지막
# 안내에서 죽으므로 성공한 것인지 아닌지가 안 보인다(실측 2026-09-02).
with contextlib.suppress(AttributeError, OSError):  # 파이프로 넘길 때는 이미 안전하다
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# --- 정답 -------------------------------------------------------------------

YOUNGS_PA = 206e9
YIELD_PA = 350e6
VOCE_Q_PA = 260e6
VOCE_B = 12.0

#: 시편 치수(mm). 힘을 응력으로 되돌리는 데 쓴다.
WIDTH_MM = 12.5
THICKNESS_MM = 1.0
GAUGE_MM = 50.0

#: 시편마다 항복이 이만큼 갈린다. **이상치로 잡힐 만큼 벌리지 않는다.**
SCATTER = (0.98, 1.00, 1.02)


def stress_at(strain: float, scale: float) -> float:
    """진응력. 탄성은 직선, 소성은 Voce."""
    yield_strain = YIELD_PA * scale / YOUNGS_PA
    if strain <= yield_strain:
        return YOUNGS_PA * strain
    plastic = strain - yield_strain
    return YIELD_PA * scale + VOCE_Q_PA * (1.0 - math.exp(-VOCE_B * plastic))


def grid() -> list[float]:
    """변형률 격자 — **무릎 앞뒤를 촘촘히.**

    등간격 하나로 뜨면 무릎이 몇 점 안 되고, 그러면 「점 수 맞추기」 를 걸어도
    원본에 그 모양이 없어서 차이가 안 보인다.
    """
    fine = [i * 0.00005 for i in range(0, 120)]  # 0 ~ 0.6% : 0.005% 간격
    knee = [0.006 + i * 0.0002 for i in range(0, 120)]  # 0.6 ~ 3% : 0.02%
    rest = [0.03 + i * 0.00015 for i in range(0, 960)]  # 3 ~ 17.4% : 0.015%
    return fine + knee + rest


def rows(scale: float) -> tuple[list[str], list[str]]:
    """(변위 mm, 하중 N). **장비가 주는 대로** — 응력·변형률은 처리가 만든다."""
    area = WIDTH_MM * THICKNESS_MM  # mm²
    displacement: list[str] = []
    load: list[str] = []
    for strain in grid():
        true_stress = stress_at(strain, scale)
        # 공칭으로 되돌린다: nom = true / (1 + eps_nom), eps_true = ln(1 + eps_nom)
        nominal_strain = math.exp(strain) - 1.0
        nominal_stress = true_stress / (1.0 + nominal_strain)
        displacement.append(f"{nominal_strain * GAUGE_MM:.5f}")
        load.append(f"{nominal_stress / 1e6 * area:.4f}")
    return displacement, load


def one(index: int, scale: float) -> dict[str, object]:
    displacement, load = rows(scale)
    peak = max(float(one) for one in load) / (WIDTH_MM * THICKNESS_MM)
    return {
        "tensile-test": {
            "": {},
            "Test Condition": {
                "Specimen Number": str(index),
                "Specimen Standard": "KS B 0801 5호",
                "Sensor Type": "makroXtens",
                "Testing Group": "예제 인장",
                "Instrument name": "Zwick Z100-EXAMPLE",
                "Specimen Real Thickness (mm)": f"{THICKNESS_MM:.3f}",
                "Specimen Real Width (mm)": f"{WIDTH_MM:.3f}",
                "rundate": f"2026-09-0{index} 09:0{index}:00",
                "Operator": "예제",
            },
            "Test Result": {
                # **장비가 계산한 값도 함께 준다** — MatNexus 가 낸 값과 나란히 놓고
                # 견주는 것이 이 화면의 쓰임이다.
                "Force maximum (MPa)": f"{peak:.3f}",
                "Force at proof stress 0.2% (MPa)": f"{YIELD_PA * scale / 1e6:.3f}",
                "Yield strain": "Unknown",
                "Specimen thickness a0 (mm)": f"{THICKNESS_MM:.3f}",
                "Specimen width b0 (mm)": f"{WIDTH_MM:.3f}",
                "Tensile Test Raw Data": {
                    "#": [str(one + 1) for one in range(len(displacement))],
                    "Standard extensometer (mm)": displacement,
                    "Standard load cell (N)": load,
                    "Specimen width (mm)": [f"{WIDTH_MM:.3f}"] * len(displacement),
                },
            },
            "Data Information": {
                "Technical Data Record Name": f"EXAMPLE_{index}",
                "Tensile Data ID": f"TensileTest_EXAMPLE_{index}",
            },
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT), help="어디에 쓸까 (기본: tests/fixtures)")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for index, scale in enumerate(SCATTER, start=1):
        path = out / f"example_tensile_0{index}.mtet"
        path.write_text(
            json.dumps(one(index, scale), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{path.name}: {len(grid())}점, 항복 {YIELD_PA * scale / 1e6:.0f} MPa")

    print()
    print("올린 뒤 해 볼 것:")
    print("  1) 시험 셋을 처리하고 채택한다")
    print(
        "  2) 재료 > 물성 탭에서 「경화식 맞춰 보기」 → Voce 가 q 260MPa, b 12 근처로 나온다"
    )
    print("  3) 카드 만들 때 「소성 표의 점 수 맞추기」 를 켜고 방법을 바꿔 본다")
    print("     - 등간격 30점 vs 꺾이는 곳에 촘촘히 30점: 무릎 근처 점 수를 견준다")


if __name__ == "__main__":
    main()
