"""처리 결과가 **낡았나** — 그 결과를 낸 입력(원본 · 시편 치수)이 지금과 같은가(2026-11-15).

## 왜

처리 결과는 불변이다. 시편 치수 · 시험 치수 · 규격 공칭 · 재료 스펙 두께를 고치거나 원본을
바꿔도 이미 채택한 결과는 옛 입력으로 낸 응력 · 탄성률을 그대로 든다 — 그 값이 통계 · 카드로
간다. 전에는 운영 점검 보고서(`scripts/ops_report.py` 1절)만 「시편 치수가 바뀐 채택 결과」 를
셌고, 화면 · 카드 · 채택은 몰랐다. 판정을 여기 하나로 두고 넷이 함께 쓴다:

    통계 노트            `statistics._group_out` — 묶음에 낡은 채택 결과가 몇 건인지
    카드 근거 경고        `fitting._card_warnings` → `source.warnings`
    채택 확인            `processing.adopt` · `adopt-many` — 낡은 결과는 확인
                         (`confirm_warnings`)을 받는다
    운영 점검 보고서      `scripts/ops_report.py` 1절

## 무엇을 견주나

    원본 교체   결과를 만든 뒤 원본 파일을 바꿨다(`run.source_replaced_at`) — 옛 곡선의 결과
    치수        단계 옵션이 `@specimen_…` 으로 받은 값(결과의 `stages[].options`)과 **지금 이
                시험에 주어질 값**(`curvedata.specimen_scalars` — 시험 → 시편 → 규격 공칭 →
                재료 스펙 두께 순)이 다르다

**고치지 않는다.** 다시 처리는 사람이 한다(`scripts/reprocess_adopted.py`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun
from app.shared import curvedata, display
from matcore import processing

#: 이만큼 넘게 다르면 「치수가 바뀌었다」 고 본다(상대). 저장 · 환산의 반올림은 못 넘는다.
TOLERANCE = 1e-6

#: 경고 줄의 이름 — 결과 · 카드 근거의 다른 경고(시험 점검 · 단계 경고)와 갈라 읽힌다.
LABEL = "낡은 결과"

#: 치수 값을 사람이 읽는 단위로 — 저장은 SI(m · m²)다.
_SHOWN = {"m": "mm", "m2": "mm2"}


@dataclass(frozen=True)
class Current:
    """지금 이 시험에 주어질 치수 — `key → (값, 이름, 단위)`. 시험 하나에 한 번 읽는다."""

    values: Mapping[str, tuple[float, str, str]]


@dataclass(frozen=True)
class Change:
    """바뀐 치수 하나 — 결과가 쓴 값과 지금 값(SI)."""

    key: str
    used: float
    now: float
    label: str
    si_unit: str

    @property
    def percent(self) -> float:
        return (self.now / self.used - 1) * 100 if self.used else float("inf")

    def text(self) -> str:
        """사람이 읽는 한 조각 — 「시편 두께 1 mm → 1.2 mm(+20.00 %)」."""
        shown = _SHOWN.get(self.si_unit)
        if shown:
            used = display.quantity(self.used, shown, digits=5)
            now = display.quantity(self.now, shown, digits=5)
        else:
            used, now = f"{self.used:.5g}", f"{self.now:.5g}"
        return f"{self.label} {used} → {now}({self.percent:+.2f} %)"


def current(db: Session, run: TestRun) -> Current:
    """지금 이 시험의 처리에 `@specimen_…` 으로 넘어갈 값들."""
    return Current(
        {
            one.key: (float(one.value), str(one.label), str(one.si_unit))
            for one in curvedata.specimen_scalars(db, run)
        }
    )


def dimension_changes(result: ProcessingResult, now: Current) -> list[Change]:
    """결과의 단계가 `@specimen_…` 으로 받은 값 중 **지금 값과 다른 것.** 같은 키는 한 번만.

    받은 값이 숫자가 아니거나(옛 결과) 지금 그 치수가 없으면 견주지 않는다 — 없어진 치수는
    처리 자체가 「그 값이 없습니다」 로 멈출 자리다.
    """
    found: dict[str, Change] = {}
    for step, stage in zip(result.steps_snapshot or [], result.stages or [], strict=False):
        for name, given in (step.get("options") or {}).items():
            if not isinstance(given, str) or not given.startswith(processing.REFERENCE_PREFIX):
                continue
            key = given.removeprefix(processing.OPTIONAL_PREFIX).removeprefix(
                processing.REFERENCE_PREFIX
            )
            used = (stage.get("options") or {}).get(name)
            if not key.startswith("specimen_") or isinstance(used, bool):
                continue
            if not isinstance(used, int | float) or key not in now.values or key in found:
                continue
            value, label, unit = now.values[key]
            if abs(value - float(used)) > TOLERANCE * max(abs(float(used)), 1e-30):
                found[key] = Change(key, float(used), value, label, unit)
    return list(found.values())


def replaced(result: ProcessingResult, run: TestRun) -> bool:
    """원본을 바꾼 뒤에 만든 결과가 아니면 옛 곡선의 것이다."""
    return run.source_replaced_at is not None and result.created_at < run.source_replaced_at


def reasons(
    db: Session, run: TestRun, result: ProcessingResult, *, now: Current | None = None
) -> list[str]:
    """이 결과가 낡은 까닭 — 없으면 빈 목록. 사람이 읽는 문장이다."""
    found: list[str] = []
    if replaced(result, run):
        found.append(
            "이 결과를 만든 뒤 원본 파일이 바뀌었습니다 — 옛 곡선으로 낸 값입니다. 새 "
            "원본으로 다시 처리하세요."
        )
    changes = dimension_changes(result, now if now is not None else current(db, run))
    if changes:
        found.append(
            "처리할 때 쓴 시편 치수가 지금 값과 다릅니다 — "
            + ", ".join(one.text() for one in changes)
            + ". 응력 · 탄성률이 옛 치수로 낸 값입니다. 같은 레시피로 다시 처리하세요."
        )
    return found


def warnings(
    db: Session, run: TestRun, result: ProcessingResult, *, now: Current | None = None
) -> list[dict[str, str]]:
    """경고 줄 모양으로 — 결과의 경고(`ProcessingResult.warnings`)와 같은 꼴(`source` 는
    `test`: 시험 쪽 입력이 결과와 달라졌다는 점검이다)."""
    return [
        {"source": "test", "label": LABEL, "message": message}
        for message in reasons(db, run, result, now=now)
    ]
