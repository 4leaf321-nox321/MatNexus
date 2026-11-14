"""운영 점검 보고서 — **읽기만 한다**. 배포가 돌리고 결과를 로그 폴더에 남긴다(2026-11-15).

## 왜

VOC 41~61 을 고치며 「운영에서 한 번 볼 것」 이 VOC 마다 하나씩 쌓였다 — 옛 데이터는
코드가 바뀌어도 그대로라(처리 결과 · 카드는 불변), 무엇이 옛 규칙으로 남았는지 세어 보고
사람이 다시 처리할지 정해야 한다. 스크립트 일곱을 사람이 기억해 돌리면 언젠가 아무도 안
돌린다(핸드북 씨앗이 그랬다). 그래서 **한 번에 돌려 한 파일로** 남긴다.

## 무엇을 보나

    1 다시 처리할 후보      채택 결과가 쓴 시편 치수 · 단면적이 지금 값과 다른 시험(VOC 56)
    2 채택된 탄성률        재료군 범위 · 적어 둔 값과 어긋나는 것 — 단위 · 시편 치수 ·
                         붙인 재료를 확인할 것(VOC 43)
    3 처리 경고 빈도        탄성률 · 직선성 경고가 결과의 몇 건에 붙나 — 기준값(잠정) 확인용
    4 옛 카드             묶음 E 출처가 재료 선언값인 카드 · 옛 τ 규칙의 응력완화 카드 ·
                         어느 카드에도 안 뜨는 사람이 만든 덱 정의(VOC 49 · 52 · 47)
    5 조건 이중 환산 의심    `find_double_converted_conditions.py`
    6 곡선 하강 분포        `measure_curve_drops.py`(VOC 57 기준값)
    7 옛 규칙 기울기 결과    `count_slope_results.py`(ADR 0088)

**고치지 않는다.** 다시 처리는 `reprocess_adopted.py`(미리보기 먼저)가 한다.

사용:
    python scripts/ops_report.py                       # 화면에
    python scripts/ops_report.py --out 보고서.txt        # 파일에도(배포가 이렇게 부른다)
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

# **모델을 전부 등록시킨다** — 손대는 모델만 import 하면 외래키가 가리키는 테이블이
# 메타데이터에 없어 매핑을 못 푼다.
import app.all_models  # noqa: E402,F401
from _console import survive_cp949  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.modules.fitting.models import ExportProfile, PropertyCard  # noqa: E402
from app.modules.processing.models import ProcessingResult  # noqa: E402
from app.modules.tests.models import TestRun, TestType  # noqa: E402
from app.shared import curvedata, modulus_sanity  # noqa: E402
from matcore import extensions, processing  # noqa: E402
from matcore.export import template  # noqa: E402

survive_cp949()

#: 한 절에 이름을 적는 건수 — 나머지는 센다.
LIST_LIMIT = 30
#: 이만큼 넘게 다르면 「치수가 바뀌었다」 고 본다(상대).
AREA_TOLERANCE = 1e-6
#: 처리 경고의 갈래 — 문장의 표지로 센다(`modulus_sanity` · `slopes.concerns`).
WARNING_KINDS = {
    "재료군 범위 밖": "재료군",
    "적어 둔 값과 3배 넘게": "적어 둔 탄성률",
    "어느 재료에도 없는 값": "어느 재료에도",
    "기울기 흔들림": "흔들립니다",
    "구간이 휨": "휘었습니다",
    "현 구간에 신호 없음": "늦게 걸렸거나",
}


def _listed(lines: list[str]) -> list[str]:
    shown = lines[:LIST_LIMIT]
    if len(lines) > LIST_LIMIT:
        shown.append(f"  … 외 {len(lines) - LIST_LIMIT}건")
    return shown


def _adopted(db: object) -> list[tuple[TestRun, ProcessingResult]]:
    runs = list(
        db.scalars(  # type: ignore[attr-defined]
            select(TestRun).where(
                TestRun.adopted_result_id.is_not(None), TestRun.deleted_at.is_(None)
            )
        )
    )
    found: list[tuple[TestRun, ProcessingResult]] = []
    for run in runs:
        result = db.get(ProcessingResult, run.adopted_result_id)  # type: ignore[attr-defined]
        if result is not None:
            found.append((run, result))
    return found


def reprocess_candidates(db: object) -> tuple[str, list[str]]:
    """채택 결과의 단계가 `@specimen_…` 으로 받은 값이 **지금 이 시험에 주어질 값**과 다른 것.

    파일 실측 치수를 채운 시험(`backfill_run_dimensions`) · 시편 치수를 고친 시험이 여기 선다 —
    채택된 응력 · 탄성률은 옛 치수로 낸 값이다.
    """
    lines: list[str] = []
    for run, result in _adopted(db):
        now = {one.key: float(one.value) for one in curvedata.specimen_scalars(db, run)}  # type: ignore[arg-type]
        changed: list[str] = []
        for step, stage in zip(result.steps_snapshot or [], result.stages or [], strict=False):
            for name, given in (step.get("options") or {}).items():
                if not isinstance(given, str) or not given.startswith(
                    processing.REFERENCE_PREFIX
                ):
                    continue
                key = given.removeprefix(processing.OPTIONAL_PREFIX).removeprefix(
                    processing.REFERENCE_PREFIX
                )
                used = (stage.get("options") or {}).get(name)
                if not key.startswith("specimen_") or not isinstance(used, int | float):
                    continue
                if key not in now:
                    continue
                if abs(now[key] - float(used)) > AREA_TOLERANCE * max(abs(float(used)), 1e-30):
                    change = (now[key] / float(used) - 1) * 100 if used else float("inf")
                    changed.append(
                        f"{key} {float(used):.5g} → {now[key]:.5g}({change:+.2f} %)"
                    )
        if changed:
            lines.append(f"  {run.record_name}: {', '.join(dict.fromkeys(changed))}")
    head = (
        f"채택 결과가 쓴 시편 치수가 지금 값과 다른 시험 {len(lines)}건 — "
        "`python scripts/reprocess_adopted.py` 로 무엇이 바뀌는지 본 뒤 `--apply`."
        if lines
        else "채택 결과가 쓴 시편 치수는 모두 지금 값과 같습니다."
    )
    return head, _listed(lines)


def adopted_moduli(db: object) -> tuple[str, list[str]]:
    """채택된 탄성률을 재료군 범위 · 적어 둔 값과 견준다 — 처리할 때의 경고와 같은 판정."""
    lines: list[str] = []
    looked = 0
    for run, result in _adopted(db):
        keys = {
            key
            for stage in result.stages or []
            for key in modulus_sanity.modulus_keys(str(stage.get("plugin")))
        }
        values = [
            one
            for one in result.scalars or []
            if isinstance(one, dict)
            and one.get("key") in keys
            and isinstance(one.get("value"), int | float)
        ]
        if not values:
            continue
        looked += 1
        context = modulus_sanity.context_of(db, run)  # type: ignore[arg-type]
        if context is None:
            continue
        for one in values:
            for message in modulus_sanity.judge(
                float(one["value"]),
                str(one.get("label") or one["key"]),
                family=context.family,
                attributes=context.attributes,
                declared=context.declared,
            ):
                lines.append(f"  {run.record_name}: {message}")
    head = (
        f"채택된 탄성률 {looked}건 중 재료군 범위 · 적어 둔 값과 어긋나는 것 {len(lines)}건 — "
        "단위 · 시편 치수 · 시험을 붙인 재료를 확인하세요(범위 숫자는 잠정값)."
    )
    return head, _listed(lines)


def warning_rates(db: object) -> tuple[str, list[str]]:
    """처리 결과에 붙은 탄성률 · 직선성 경고의 갈래별 건수 — 기준값이 잦게 걸리는지 본다."""
    counts: Counter[str] = Counter()
    total = 0
    for warnings in db.scalars(select(ProcessingResult.warnings)):  # type: ignore[attr-defined]
        total += 1
        texts = [
            str(one.get("message", "")) for one in warnings or [] if isinstance(one, dict)
        ]
        for name, mark in WARNING_KINDS.items():
            if any(mark in text for text in texts):
                counts[name] += 1
    lines = [f"  {name}: {counts[name]}건" for name in WARNING_KINDS]
    head = (
        f"처리 결과 {total}건(경고 기능 전의 결과도 포함 — 그것들은 0 으로 센다). "
        "한 갈래가 결과의 큰 몫이면 기준값을 다시 볼 자리다."
    )
    return head, lines


def old_cards(db: object) -> tuple[str, list[str]]:
    """옛 규칙으로 만들어진 채 남은 카드 · 정의."""
    lines: list[str] = []
    relaxation = {
        one.id
        for one in db.scalars(select(TestType).where(TestType.key == "stress_relaxation"))  # type: ignore[attr-defined]
    }
    for card in db.scalars(select(PropertyCard)):  # type: ignore[attr-defined]
        source = card.source or {}
        blocks = card.blocks or {}
        if not source.get("group_result_id"):
            continue
        elastic = (blocks.get("elastic") or {}).get("values") or {}
        if str(elastic.get("youngs_modulus_source", "")).startswith("declared:"):
            lines.append(
                f"  [묶음 E 출처] {card.label}: 묶음이 낸 탄성계수인데 출처가 재료에 적은 "
                "값으로 찍혀 있습니다(v1.317 전) — 같은 묶음으로 카드를 다시 만드세요."
            )
        visco = (blocks.get("viscoelastic") or {}).get("values") or {}
        if card.test_type_id in relaxation and visco and "instantaneous_ratio" not in visco:
            lines.append(
                f"  [응력완화 τ] {card.label}: 옛 완화시간 규칙(v1.317 전)으로 만든 응력완화 "
                "카드 — 순간 탄성률이 첫 측정 시각에 따라 크게 뛰었을 수 있습니다. 다시 묶어 "
                "만드세요."
            )
    for profile in db.scalars(  # type: ignore[attr-defined]
        select(ExportProfile).where(
            ExportProfile.deleted_at.is_(None),
            ExportProfile.is_active.is_(True),
            ExportProfile.seed_digest.is_(None),
        )
    ):
        definition = profile.definition or {}
        if not definition.get("needs") and not template.reads(definition):
            lines.append(
                f"  [덱 정의] {profile.label}({profile.key}): 필요한 블록도 읽는 블록도 없어 "
                "어느 카드의 형식 목록에도 안 뜹니다(v1.318 규칙) — 정의에 `needs` 를 "
                "적으세요."
            )
    head = f"옛 규칙으로 남은 카드 · 정의 {len(lines)}건."
    return head, _listed(lines)


def _script(name: str, *arguments: str) -> Callable[[object], tuple[str, list[str]]]:
    """다른 읽기 전용 스크립트를 그대로 돌려 출력을 싣는다 — 판정을 두 벌로 두지 않는다."""

    def run(_db: object) -> tuple[str, list[str]]:
        done = subprocess.run(
            [sys.executable, str(BACKEND_DIR / "scripts" / name), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=BACKEND_DIR,
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
        output = [f"  {line}" for line in done.stdout.splitlines() if line.strip()]
        if done.returncode != 0:
            tail = (done.stderr.strip().splitlines() or ["(출력 없음)"])[-1]
            return f"{name} 이 실패했습니다(종료 코드 {done.returncode}): {tail}", output
        last = output[-1].strip() if output else "(출력 없음)"
        return last, _listed(output)

    return run


SECTIONS: list[tuple[str, Callable[[object], tuple[str, list[str]]]]] = [
    ("1. 다시 처리할 후보(시편 치수가 바뀐 채택 결과)", reprocess_candidates),
    ("2. 채택된 탄성률 — 단위 · 시편 치수 · 붙인 재료를 확인할 것", adopted_moduli),
    ("3. 처리 경고 빈도(탄성률 · 직선성)", warning_rates),
    ("4. 옛 규칙으로 남은 카드 · 덱 정의", old_cards),
    ("5. 조건 이중 환산 의심", _script("find_double_converted_conditions.py")),
    ("6. 인장 곡선의 최대 응력 앞 하강 분포", _script("measure_curve_drops.py")),
    ("7. 옛 규칙의 접선 · 응력 띠 탄성률", _script("count_slope_results.py")),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="보고서를 이 파일에도 쓴다")
    args = parser.parse_args()

    # **처리 단계 · 확장을 불러온다** — 안 부르면 레지스트리가 비어 탄성률 단계를 못 알아보고
    # 「채택된 탄성률 0건」 이 된다(처음 짠 판이 그랬다).
    processing.load_builtin()
    extensions.load(get_settings().extensions_dir)
    report: list[str] = ["MatNexus 운영 점검 보고서 — 읽기만 했습니다(고친 것 없음).", ""]
    summary: list[str] = []
    with SessionLocal() as db:
        for title, section in SECTIONS:
            try:
                # 섹션이 찍는 것(다른 모듈의 print)이 보고서를 흐리지 않게 받아 둔다.
                with redirect_stdout(io.StringIO()):
                    head, lines = section(db)
            except Exception as exc:  # 한 절이 터져도 나머지는 보인다
                db.rollback()
                head, lines = f"이 절을 못 봤습니다: {type(exc).__name__}: {exc}", []
            report += [f"## {title}", head, *lines, ""]
            summary.append(f"{title}: {head}")
    text = "\n".join(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(text.encode("utf-8"))
        print("\n".join(summary))
        print(f"보고서: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
