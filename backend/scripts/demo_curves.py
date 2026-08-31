"""예시 인장 곡선 열 벌을 만든다 — **합성이고, 그렇게 표시한다.**

## 왜 만드는가

개발 서버의 시험 데이터가 한 종류뿐이라, 대표 곡선 뒤에 원곡선을 깔아도
흩어짐이 안 보이고 이상치 후보도 안 뜬다. **기능이 도는지 눈으로 볼 표본이
없다.** 카드를 만들어 보려면 그럴듯한 묶음이 하나 있어야 한다.

## 무엇을 근거로 하는가

공개된 DP590(DP590T/340Y) 물성 범위를 목표로 삼는다 — 항복 330~430 MPa,
인장 590~700 MPa, n 값 0.16~0.21, 총연신 20~26%. **측정 곡선을 받아 온 것이
아니다.** 공개·기계판독 가능한 원곡선 데이터셋을 찾지 못했고, 대신 그 범위를
맞추는 Swift 경화식으로 곡선을 만든다.

    진응력  σ = K (ε0 + εp)^n
    탄성    σ = E ε            (E = 206 GPa)
    네킹 후 하중이 떨어지는 구간을 붙인다 — 그 구간을 자르는 기능이 있어서다.

## 반드시 표시한다

이 시스템은 **값이 어디서 왔는지**를 지키려고 만든 것이다. 합성 곡선이 측정값
사이에 이름표 없이 섞이면 그 전제가 무너진다. 그래서 재료 이름·별칭·메모와
시험 메모 모두에 예시라고 적고, 파일 머리에도 적는다.

## 흩어짐을 일부러 넣는다

열 벌이 겹쳐 보이면 「대표 곡선이 적절한가」를 볼 수 없다. 시편마다 K·n·치수를
조금씩 흔들고, **둘은 일부러 멀리 보낸다** — 이상치 후보 표시가 실제로 뜨는지
보려면 후보가 있어야 한다.
"""

from __future__ import annotations

import argparse
import contextlib
import math
import random
import sys
from pathlib import Path

#: 목표 물성. 공개 자료의 DP590 범위 안에서 고른 값이다.
E_PA = 206e9
K_PA = 1010e6
"""Swift 계수. 이 K·n·ε0 이 항복 약 350 MPa · 인장 약 620 MPa 를 준다."""
N_EXP = 0.185
EPS0 = 0.0042

#: 시편 치수(mm). 두께는 1.0t 판재, 폭은 JIS 5호에 가깝게.
THICKNESS_MM = 1.0
WIDTH_MM = 12.5
GAUGE_MM = 50.0

#: 네킹 뒤 하중이 얼마나 떨어지고 어디서 끊기는가.
NECK_DROP = 0.22
BREAK_EXTRA = 0.09

#: 한 곡선의 점 수. 실제 장비 파일도 이 언저리다.
POINTS = 900


def true_stress(plastic: float, k: float, n: float) -> float:
    """Swift. 소성변형률에서 진응력."""
    return k * (EPS0 + plastic) ** n


def curve(
    k: float, n: float, thickness: float, width: float
) -> list[tuple[float, float, float]]:
    """한 시편의 (신율 mm, 하중 N, 폭 mm).

    **장비가 내는 것과 같은 축이다** — 파서가 이 셋을 읽는다. 진응력·진변형률로
    바꾸는 것은 처리 단계의 일이고, 여기서 미리 해 두면 파이프라인을 건너뛰는
    셈이 된다.
    """
    area0 = thickness * width * 1e-6  # m²
    uniform = n - EPS0  # Considère: 진소성변형률이 n 에 닿으면 네킹
    rows: list[tuple[float, float, float]] = []

    # ── 탄성 ─────────────────────────────────────────────────────────
    yield_stress = true_stress(0.002, k, n)
    elastic_strain = yield_stress / E_PA
    elastic_points = max(int(POINTS * 0.12), 12)
    for at in range(elastic_points):
        engineering = elastic_strain * (at / (elastic_points - 1))
        stress = E_PA * engineering
        rows.append(_row(engineering, stress, area0, width, thickness))

    # ── 균일 소성 ────────────────────────────────────────────────────
    plastic_points = int(POINTS * 0.68)
    for at in range(1, plastic_points + 1):
        plastic = uniform * (at / plastic_points)
        true = true_stress(plastic, k, n)
        # 진 → 공칭. 소성은 부피가 보존된다.
        engineering_strain = math.exp(plastic + true / E_PA) - 1.0
        engineering_stress = true / (1.0 + engineering_strain)
        rows.append(_row(engineering_strain, engineering_stress, area0, width, thickness))

    # ── 네킹 뒤 ──────────────────────────────────────────────────────
    #
    # **이 구간이 있어야 한다.** 처리 화면에 「네킹 뒤를 자르고 외삽」이 있는데,
    # 자를 것이 없으면 그 기능을 눌러 볼 수 없다.
    peak_strain = rows[-1][0]
    peak_stress = rows[-1][1]
    tail_points = POINTS - len(rows)
    for at in range(1, tail_points + 1):
        share = at / tail_points
        engineering_strain = peak_strain + BREAK_EXTRA * share
        # 매끈하게 떨어뜨린다 — 꺾인 선은 장비 파일에서 안 나온다.
        engineering_stress = peak_stress * (1.0 - NECK_DROP * share**1.6)
        rows.append(_row(engineering_strain, engineering_stress, area0, width, thickness))

    return rows


def _row(
    strain: float, stress: float, area0: float, width: float, thickness: float
) -> tuple[float, float, float]:
    """공칭 변형률·응력을 장비가 적는 세 값으로."""
    del thickness
    extension = strain * GAUGE_MM
    force = stress * area0
    # 폭도 함께 줄어든다(장비가 실제로 재는 값이다). 부피 보존에서 온다.
    shrunk = width / math.sqrt(1.0 + strain) if strain > 0 else width
    return (extension, force, shrunk)


def write_tra(
    path: Path,
    index: int,
    rows: list[tuple[float, float, float]],
    *,
    thickness: float,
    width: float,
) -> None:
    """장비 파일과 같은 모양으로 적는다(`zwick_tra` 가 읽는 형식).

    머리에 **예시라는 것을 적는다** — 파일만 따로 돌아다녀도 무엇인지 알아야 한다.
    """
    peak = max(force for _, force, _ in rows)
    area0 = thickness * width  # mm²
    lines = [
        '"MatNexus 예시 데이터 - 합성 곡선입니다(측정값이 아닙니다)","",""',
        '"근거","공개 DP590 물성 범위를 목표로 만든 Swift 곡선",""',
        f'"Specimen number",{index}," "',
        f'"Specimen thickness a0",{thickness:.3f},"mm"',
        f'"Specimen width b0",{width:.3f},"mm"',
        f'"Force maximum",{peak / area0:.4f},"MPa"',
        '"Standard extensometer ","Standard load cell ","Specimen width"',
        '"mm","N","mm"',
    ]
    lines += [f"{a:.6g},{b:.6g},{c:.6g}" for a, b, c in rows]
    # **UTF-8 로 적는다.** 전에는 CP949 였다 — 「장비가 그렇게 적는다」 는 이유
    # 였는데, 파서는 UTF-8 이 아니면 CP1252 로 읽으므로(`zwick_tra._decode`) 이
    # 파일의 한글 라벨이 화면에서 깨져 보였다(실측 2026-08-31). 예시 파일이
    # 파서의 인코딩 폴백을 시험하는 자리는 아니다.
    #
    # 줄 끝은 장비대로 CRLF 다. **바이트로 적는다** — `write_text`
    # 는 줄 끝을 플랫폼에 맞춰 바꿔서, 실제 파일과 다른 것이 나온다.
    body = "\r\n".join(lines) + "\r\n"
    path.write_bytes(body.encode("utf-8"))


# **콘솔 인코딩에 걸려 죽지 않게 한다.** 운영·개발 모두 Windows 이고 기본 콘솔이
# CP949 라, 요약에 쓰는 `≈` 하나가 `UnicodeEncodeError` 를 내며 스크립트를 끝낸다
# — 파일은 이미 다 만들어 놓고 마지막 줄에서 죽는다(실측 2026-08-31).
with contextlib.suppress(AttributeError, OSError):  # 파이프로 넘길 때는 이미 안전하다
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("demo_curves"))
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    #: 몇 번째를 멀리 보낼까. **후보가 있어야 이상치 표시를 볼 수 있다.**
    far = {3: 1.075, 7: 0.935}

    for index in range(1, args.count + 1):
        # 시편끼리의 흩어짐. 실제 인장에서 강도는 2% 안쪽으로 흔들린다.
        nudge = far.get(index, 1.0)
        k = K_PA * nudge * rng.gauss(1.0, 0.012)
        n = N_EXP * rng.gauss(1.0, 0.020)
        thickness = THICKNESS_MM * rng.gauss(1.0, 0.008)
        width = WIDTH_MM * rng.gauss(1.0, 0.004)

        rows = curve(k, n, thickness, width)
        path = args.out / f"DEMO_DP590_MD_{index:02d}.tra"
        write_tra(path, index, rows, thickness=thickness, width=width)

        area0 = thickness * width
        peak = max(force for _, force, _ in rows) / area0
        print(f"{path.name}  UTS≈{peak:.0f} MPa  t={thickness:.3f}  b={width:.3f}  n={n:.3f}")


if __name__ == "__main__":
    main()
