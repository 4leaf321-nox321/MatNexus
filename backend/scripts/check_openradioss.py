"""앱이 내는 Radioss 덱을 **OpenRadioss 로 실제로 돌려** 본다 — Starter(입력 검사)와 Engine.

    python scripts/check_openradioss.py --openradioss <OpenRadioss 폴더> [--work <작업 폴더>]

OpenRadioss 는 무료다 — https://github.com/OpenRadioss/OpenRadioss/releases 의
`OpenRadioss_win64.zip` 을 풀면 `OpenRadioss/exec/starter_win64.exe` 가 있다. 그 `OpenRadioss`
폴더를 준다. 시험 스위트는 이것을 안 돈다(바이너리가 없는 자리가 많다) — 렌더러의 칸이나
규약을 고쳤으면 손으로 한 번 돈다.

## 무엇을 하나

예제 덱(`시뮬레이션 인풋 덱/예제/*-radioss_0000.rad`)의 재료·함수 블록을 빼고, 앱의 렌더러가
낸 조각(`/UNIT/1` + `/MAT` + `/FUNCT`)을 넣어 돌린다. 모델·하중·출력은 예제 그대로라 결과를
README 의 기대값이나 손계산과 견줄 수 있다.

## 왜 있나 (2026-09-27)

**Starter 가 오류 없이 받는데 재료가 다른 덱**이 실제로 둘 있었다.

    LAW36 의 fct_IDp 값 줄 없음   곡선 번호를 압력 의존 함수로 읽어 **재료가 끝내 항복하지
                                않았다**(σx 84,071 MPa, 소성변형률 0 — 맞게 내면 700.27 ·
                                0.4018)
    LAW43 의 Iyield0 기본값(0)    곡선을 「평균 항복응력」 으로 읽어 압연 방향 응력이 1.3%
                                높았다(r 은 맞게 나왔다) — Iyield0 = 1 이 압연 방향 곡선이다

칸을 눈으로 대조하는 것만으로는 둘 다 못 본다 — 돌려서 숫자를 봐야 한다.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from _console import survive_cp949  # noqa: E402
from matcore import cards, export, extensions  # noqa: E402
from matcore.export import radioss  # noqa: E402,F401  (렌더러 등록)
from matcore.export.systems import MM_N_TONNE  # noqa: E402

# 한국어를 찍는다 — 운영 서버의 콘솔(cp949)에서 멈추지 않게 먼저 푼다.
survive_cp949()

EXAMPLES = BACKEND.parent / "시뮬레이션 인풋 덱" / "예제"

CURVE = [(0.0, 350e6), (0.02, 455e6), (0.1, 560e6), (0.4, 700e6), (1.0, 790e6)]
STEEL = {"values": {"youngs_modulus": 210e9, "poisson_ratio": 0.3, "density": 7850.0}}
TABLE = {"rows": [{"plastic_strain": x, "true_stress": y} for x, y in CURVE]}
RATES = {
    "values": {"rate_count": 2, "reference_rate": 0.001},
    "rows": [
        *({"strain_rate": 0.001, "plastic_strain": x, "true_stress": y} for x, y in CURVE),
        *(
            {"strain_rate": 100.0, "plastic_strain": x, "true_stress": y * 1.1}
            for x, y in CURVE
        ),
    ],
}
RUBBER = {"values": {"poisson_ratio": 0.4995, "density": 1100.0}}
TEMPERATURES = {
    "values": {"temperature_count": 2, "reference_temperature": 293.15},
    "rows": [
        *({"temperature": 293.15, "plastic_strain": x, "true_stress": y} for x, y in CURVE),
        *(
            {"temperature": 473.15, "plastic_strain": x, "true_stress": y * 0.86}
            for x, y in CURVE
        ),
    ],
}
JOHNSON_COOK = {
    "values": {"label": "Johnson-Cook (준정적 항)"},
    "rows": [
        {"name": "a", "value": 350e6, "si_unit": "Pa"},
        {"name": "b", "value": 600e6, "si_unit": "Pa"},
        {"name": "n", "value": 0.4, "si_unit": "1"},
    ],
}
ANISOTROPY = {"values": {"r_0": 1.8, "r_45": 1.4, "r_90": 2.1}}

#: 쉘 속성 — 직교 방향 1(Vx)을 x(당기는 방향 = 압연 방향)로. CFG `prop_p9_sh_orth.cfg`(2021).
PROP_SHELL = "\n".join(
    [
        "/PROP/TYPE9/1",
        "Hill shell",
        "#   Ishell    Ismstr     Ish3n    Idrill                            P_Thick_Fail",
        "        24         2         0         0",
        "#" + "".join(f"{name:>20}" for name in ("Hm", "Hf", "Hr", "Dm", "Dn"))[1:],
        "".join(f"{0:>20}" for _ in range(5)),
        "#        N   ISTRAIN               Thick              Ashear"
        "     Iskew    ITHICK     IPLAS",
        f"{5:>10}{1:>10}{0.5:>20}{0:>20}{0:>10}{1:>10}{1:>10}",
        "#" + "".join(f"{name:>20}" for name in ("Vx", "Vy", "Vz", "Phi"))[1:],
        f"{1.0:>20}{0.0:>20}{0.0:>20}{0.0:>20}",
    ]
)


def _hyper(family: str, **params: float) -> dict[str, Any]:
    return {
        "values": {"family": family},
        "rows": [
            {"name": key, "value": value, "si_unit": "1" if key == "alpha" else "Pa"}
            for key, value in params.items()
        ],
    }


def _curve_at(plas: float) -> float:
    """DP600 곡선(MPa)을 소성변형률에서 선형으로 읽는다."""
    points = [(x, y / 1e6) for x, y in CURVE]
    for (x0, y0), (x1, y1) in pairwise(points):
        if x0 <= plas <= x1:
            return y0 + (y1 - y0) * (plas - x0) / (x1 - x0)
    return points[-1][1]


def _at_473(text: str) -> str:
    """T0 칸(61~80열)에 473.15 K — 열해석 없이 그 온도에서 등온으로 돈다."""
    tref = f"{'':>20}{'':>20}{293.15:>20.9E}\n"
    return text.replace(tref, tref.rstrip("\n") + f"{473.15:>20.9E}\n")


def _laminate_pull(text: str) -> str:
    """laminate 모델을 10% 까지 당기고(원래 0.5%) 옆 절점 3 의 이력을 더한다 — r 을 잰다."""
    pulled = "         2                    pulled\n"
    return text.replace(
        f"{0:>20}{0:>20}{0:>20}{0:>20}\n#---1", f"{0:>20}{20:>20}{0:>20}{0:>20}\n#---1", 1
    ).replace(pulled, pulled + "         3                    side\n")


def _no_shell_anim(text: str) -> str:
    """예제 Engine 파일의 `/ANIM/SHELL/TENS/…` 는 이 판이 모르는 줄이다(예제 덱의 결함)."""
    return "".join(
        line for line in text.splitlines(keepends=True) if not line.startswith("/ANIM/SHELL/")
    )


@dataclass(frozen=True)
class Case:
    key: str
    blocks: dict[str, Any]
    example: str
    drop: tuple[str, ...]
    """예제에서 뺄 블록 머리 — 앱의 조각이 그 자리를 채운다."""
    sx: float | Callable[[float], float] | None = None
    """끝의 σx(MPa). 기대값이거나, 끝의 소성변형률로 계산하는 식(곡선·경화식에서 읽는 값)."""
    engine: bool = True
    fragment_edit: Callable[[str], str] | None = None
    """앱이 낸 조각을 고친다 — 해석 조건(T0 등)을 덱에 적는 사람의 일을 흉내 낸다."""
    base_edit: Callable[[str], str] | None = None
    engine_edit: Callable[[str], str] | None = None
    shell: bool = False
    """쉘 모델(/TH/SHEL) — 응력·소성변형률 칸 자리가 다르다."""
    r: float | None = None
    """기대하는 소성 변형비 — 옆 절점의 폭 변위와 두께(부피 보존)에서 잰다."""


CASES: dict[str, Case] = {
    # README: 700.32 MPa(해석해). 예제 덱을 그대로 돌리면 700.27.
    "탄소성 LAW36": Case(
        "openradioss",
        {"elastic": STEEL, "table": TABLE},
        "dp600",
        ("/MAT/", "/FUNCT/100"),
        700.3,
    ),
    "선형 LAW1": Case(
        "openradioss_elastic", {"elastic": STEEL}, "dp600", ("/MAT/", "/FUNCT/100")
    ),
    # README: 770.30(해석해, 1.10 배). 예제 덱을 그대로 돌리면 772.37 — 명시 해석의 속도 필터.
    "속도 의존 LAW36": Case(
        "openradioss_rate",
        {"elastic": STEEL, "table": TABLE, "rate_table": RATES},
        "rate",
        ("/MAT/", "/FUNCT/100", "/FUNCT/101"),
        772.4,
    ),
    # README: 4.7162(K/G=1000). 예제 덱을 그대로 돌리면 4.7108.
    "초탄성 Mooney": Case(
        "openradioss_hyperelastic",
        {"elastic": RUBBER, "hyperelastic": _hyper("mooney_rivlin", c10=0.6e6, c01=0.15e6)},
        "rubber",
        ("/MAT/",),
        4.711,
    ),
    # Ogden α=3 — 규약이 갈리는 자리. 비압축 해석해 (2μ/α)(λ^α - λ^(-α/2)) = 7.646(λ=2).
    # 옮기지 않으면(μ_R = μ) 1.5 배가 나온다.
    "초탄성 Ogden α=3": Case(
        "openradioss_hyperelastic",
        {"elastic": RUBBER, "hyperelastic": _hyper("ogden_1", mu=1.5e6, alpha=3.0)},
        "rubber",
        ("/MAT/",),
        7.646,
    ),
    "점탄성 LAW42+Prony": Case(
        "openradioss_viscoelastic",
        {
            "elastic": {
                "values": {
                    "youngs_modulus": 4.4985e6,
                    "poisson_ratio": 0.4995,
                    "density": 1100.0,
                }
            },
            "viscoelastic": {
                "values": {"reference_temperature_k": 296.15},
                "rows": [
                    {"relative_modulus": 0.3, "relaxation_time_s": 0.001},
                    {"relative_modulus": 0.25, "relaxation_time_s": 0.01},
                ],
            },
        },
        "rubber",
        ("/MAT/",),
    ),
    "열물성 /HEAT/MAT": Case(
        "openradioss_thermal",
        {
            "elastic": STEEL,
            "thermal": {
                "values": {
                    "specific_heat": 460.0,
                    "thermal_conductivity": 45.0,
                    "reference_temperature": 293.15,
                }
            },
        },
        "dp600",
        (),
        engine=False,
    ),
    # --- 확장 블록 ----------------------------------------------------------------
    # 온도 의존 LAW109: T0 를 비우면 기준 온도 곡선, 473.15 를 적으면 그 온도의 곡선(0.86 배).
    "온도 의존 LAW109 Tref": Case(
        "openradioss_temperature",
        {"elastic": STEEL, "table": TABLE, "temperature_table": TEMPERATURES},
        "dp600",
        ("/MAT/", "/FUNCT/100"),
        700.3,
    ),
    "온도 의존 LAW109 473K": Case(
        "openradioss_temperature",
        {"elastic": STEEL, "table": TABLE, "temperature_table": TEMPERATURES},
        "dp600",
        ("/MAT/", "/FUNCT/100"),
        0.86 * 700.27,
        fragment_edit=_at_473,
    ),
    # Johnson-Cook LAW2: c=0 → σ = a + b·εp^n 를 끝의 소성변형률로 계산해 견준다.
    "Johnson-Cook LAW2": Case(
        "openradioss_johnson_cook",
        {"elastic": STEEL, "table": TABLE, "hardening": JOHNSON_COOK},
        "dp600",
        ("/MAT/", "/FUNCT/100"),
        lambda plas: 350.0 + 600.0 * plas**0.4,
    ),
    # Hill48 LAW43(쉘): 압연 방향으로 당기면 σx 가 곡선 그대로이고 폭/두께 소성변형비가 r0.
    "Hill48 LAW43 쉘": Case(
        "openradioss_hill",
        {"elastic": STEEL, "table": TABLE, "anisotropy": ANISOTROPY},
        "laminate",
        ("/MAT/", "/PROP/"),
        _curve_at,
        fragment_edit=lambda text: text.replace("/END", PROP_SHELL + "\n/END"),
        base_edit=_laminate_pull,
        engine_edit=_no_shell_anim,
        shell=True,
        r=1.8,
    ),
}

#: 기대값과의 허용 오차(상대). 명시 해석이라 해석해와 1% 안쪽에서 어긋난다.
TOLERANCE = 0.01


def _env(root: pathlib.Path) -> dict[str, str]:
    out = dict(os.environ)
    out["RAD_CFG_PATH"] = str(root / "hm_cfg_files")
    out["RAD_H3D_PATH"] = str(root / "extlib" / "h3d" / "lib" / "win64")
    out["PATH"] = os.pathsep.join(
        [
            str(root / "extlib" / "hm_reader" / "win64"),
            str(root / "extlib" / "intelOneAPI_runtime" / "win64"),
            out.get("PATH", ""),
        ]
    )
    out["KMP_STACKSIZE"] = "400m"
    out["OMP_NUM_THREADS"] = "1"
    return out


def _splice(base: str, drop: tuple[str, ...], fragment: str) -> str:
    """예제에서 `drop` 블록을 빼고 조각을 끝 `/END` 앞에 넣는다.

    조각의 끝 줄바꿈을 떼고 넣는다 — Radioss 는 **빈 줄도 한 줄로 읽는다**(곡선 뒤의 빈 줄은
    (0, 0) 점이 되어 「6번째 가로축이 5번째보다 작다」 로 멈춘다).
    """
    out: list[str] = []
    skipping = False
    for line in base.replace("\r\n", "\n").split("\n"):
        if line.startswith("/"):
            skipping = any(line.startswith(head) for head in drop)
        if not skipping:
            out.append(line)
    body = [
        line
        for line in fragment.rstrip("\n").split("\n")
        if line not in ("#RADIOSS STARTER", "/END")
    ]
    end = len(out) - 1 - out[::-1].index("/END")
    return "\n".join([*out[:end], *body, *out[end:]]) + "\n"


def _run(root: pathlib.Path, case: pathlib.Path, runname: str, engine: bool) -> dict[str, Any]:
    exe = root / "exec"
    subprocess.run(
        [str(exe / "starter_win64.exe"), "-i", f"{runname}_0000.rad", "-np", "1"],
        cwd=case, env=_env(root), capture_output=True, timeout=600, check=False,
    )  # fmt: skip
    listing = (case / f"{runname}_0000.out").read_text(errors="replace")
    found = re.search(r"(\d+)\s+ERROR\(S\)", listing)
    result: dict[str, Any] = {
        "errors": int(found.group(1)) if found else None,
        "messages": [
            " ".join(one.split())[:200]
            for one in re.findall(
                r"ERROR ID\s*:\s*\d+.*?DESCRIPTION.*?(?=\n\s*\n)", listing, re.S
            )
        ],
    }
    if result["errors"] != 0 or not engine:
        return result
    subprocess.run(
        [str(exe / "engine_win64.exe"), "-i", f"{runname}_0001.rad"],
        cwd=case, env=_env(root), capture_output=True, timeout=1800, check=False,
    )  # fmt: skip
    engine_out = case / f"{runname}_0001.out"
    listing = engine_out.read_text(errors="replace") if engine_out.exists() else ""
    result["normal"] = "NORMAL TERMINATION" in listing
    subprocess.run(
        [str(exe / "th_to_csv_win64.exe"), f"{runname}T01"],
        cwd=case, env=_env(root), capture_output=True, timeout=300, check=False,
    )  # fmt: skip
    table = case / f"{runname}T01.csv"
    if table.exists():
        rows = list(csv.reader(table.open(errors="replace")))
        result["header"] = [cell.strip() for cell in rows[0]]
        result["last"] = [float(cell) for cell in rows[-1]]
    return result


def _measure(got: dict[str, Any], shell: bool) -> dict[str, float]:
    """끝 줄에서 σx · 소성변형률(쉘이면 r 까지)을 읽는다.

    솔리드 /TH/BRIC DEF: OFF SX SY SZ SXY SYZ SXZ IE DENS PLAS TEMP — 전역 23칸 뒤에 선다.
    쉘 /TH/SHEL DEF: 첫 칸이 σx, 열째가 소성변형률. 절점(/TH/NODE DEF)은 절점마다 7칸
    (DX DY DZ VX VY VZ REACX) — 2번(당기는 끝)과 3번(옆 끝). r 은 소성 부분만 본다.
    """
    header, last = got.get("header"), got.get("last")
    if not header or not last:
        return {}
    if not shell:
        return {"sx": last[24], "plas": last[32]}
    node = [value for name, value in zip(header, last, strict=True) if "pulled node" in name]
    shells = [
        value for name, value in zip(header, last, strict=True) if "shell history" in name
    ]
    sx, plas = shells[0], shells[9]
    youngs, poisson = 210000.0, 0.3
    length = math.log(1.0 + node[0]) - sx / youngs
    width = math.log(1.0 + node[8]) + poisson * sx / youngs
    return {"sx": sx, "plas": plas, "r": width / -(length + width)}


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--openradioss", required=True, type=pathlib.Path)
    parser.add_argument("--work", type=pathlib.Path, default=None)
    args = parser.parse_args()
    root: pathlib.Path = args.openradioss
    if not (root / "exec" / "starter_win64.exe").exists():
        print(f"OpenRadioss 가 아닙니다: {root} (exec/starter_win64.exe 가 없습니다)")
        return 2
    work = args.work or pathlib.Path(tempfile.mkdtemp(prefix="mnx_radioss_"))
    extensions.load(BACKEND / "extensions")
    cards.load_builtin()
    failed = 0
    for index, (name, spec) in enumerate(CASES.items(), start=1):
        deck = export.Deck(
            name="MNX_CASE", solver_id=1, blocks=spec.blocks, provenance=(name,)
        )
        fragment = export.render(spec.key, deck, MM_N_TONNE).text
        if spec.fragment_edit:
            fragment = spec.fragment_edit(fragment)
        runname = f"{spec.example}-1elem-radioss"
        case = work / f"case{index}"
        shutil.rmtree(case, ignore_errors=True)
        case.mkdir(parents=True)
        base = (EXAMPLES / f"{runname}_0000.rad").read_text(encoding="utf-8")
        text = _splice(base, spec.drop, fragment)
        if spec.base_edit:
            text = spec.base_edit(text)
        (case / f"{runname}_0000.rad").write_bytes(text.encode("utf-8"))
        if spec.engine:
            engine = (EXAMPLES / f"{runname}_0001.rad").read_text(encoding="utf-8")
            if spec.engine_edit:
                engine = spec.engine_edit(engine)
            (case / f"{runname}_0001.rad").write_bytes(engine.encode("utf-8"))
        got = _run(root, case, runname, spec.engine)
        got.update(_measure(got, spec.shell))
        ok = got["errors"] == 0 and (not spec.engine or bool(got.get("normal")))
        said = f"Starter 오류 {got['errors']}"
        if spec.engine:
            said += f" · Engine {'정상 종료' if got.get('normal') else '비정상'}"
        if "sx" in got:
            said += f" · σx {got['sx']:.4g} MPa · 소성변형률 {got['plas']:.4g}"
            if spec.sx is not None:
                expected = spec.sx(got["plas"]) if callable(spec.sx) else spec.sx
                ok = ok and abs(got["sx"] - expected) <= TOLERANCE * expected
                said += f" (기대 {expected:.4g})"
        if "r" in got and spec.r is not None:
            ok = ok and abs(got["r"] - spec.r) <= 2 * TOLERANCE * spec.r
            said += f" · r {got['r']:.3g} (기대 {spec.r:g})"
        failed += 0 if ok else 1
        print(f"{'통과' if ok else '실패'}  {name:22s} {spec.key:26s} {said}")
        for message in got["messages"][:3]:
            print(f"        {message}")
    print(f"작업 폴더: {work}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
