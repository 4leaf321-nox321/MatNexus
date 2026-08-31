"""장비가 겹쳐 준 표를 **읽자마자 마스터커브로 등록한다**(ADR 0023 의 B).

## 왜 자동인가

TA DMA850 은 시간-온도 중첩을 제 소프트웨어에서 하고 그 결과를 파일에 함께 낸다.
프로파일이 그 표를 `derived` 로 읽어 두지만, `MasterCurve` 행이 되기 전에는 Prony
도 글로벌 피팅도 못 쓴다. 사람이 화면에서 한 건씩 가져오는 길은 있는데(A), **파일
100개면 100번 한다.**

## 짐작하지 않는다 — 규칙이 있을 때만

막히는 것은 곡선이 아니라 **기준 온도**다. 틀린 온도로 등록해도 곡선은 멀쩡하고
계산도 돌고 덱도 나간다 — 20 °C 곡선이 30 °C 라고 적힌 채 해석에 들어가면 아무
데서도 안 걸린다. 그래서 프로파일에 **어디서 읽을지 적어 둔 경우에만** 등록한다.

    "tables": {
      "derived": "^TTS",
      "master_curve": { "from": "name", "pattern": "\\\\(([\\\\d.]+)\\\\s*°?\\\\s*C\\\\)",
                        "unit": "degC" }
    }

실측(TA DMA850): 표 이름이 `TTS - master curve (20.0 °C)` 다. 파일 머리에는 기준
온도가 없으므로 **이름이 유일한 근거**다. 같은 파일에 20 °C 와 30 °C 두 벌이 들어
있는 것도 봤다 — 그래서 맞는 표를 전부 등록한다.

## 못 읽으면 등록하지 않는다

규칙이 안 맞으면 **경고를 남기고 넘어간다.** 조용히 틀린 온도보다 「등록 안 됨 +
이유」 가 낫다 — 후자는 화면에 뜨고, 전자는 덱까지 간다.

## 두 번 등록하지 않는다

다시 읽으면 곡선은 새로 쓰이지만 마스터커브는 남아 있다. 같은 곡선 키로 이미
등록된 것이 있으면 건너뛴다 — 안 그러면 재파싱마다 같은 곡선이 하나씩 늘고, 그중
어느 것이 대표인지가 흔들린다.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tests.models import FormatProfile, TestRun
from app.modules.viscoelastic import services
from app.modules.viscoelastic.models import MasterCurve
from app.shared import parse_hooks
from matcore import units


def _profile_of(db: Session, run: TestRun) -> dict[str, Any] | None:
    """이 시험을 읽은 프로파일의 정의.

    사람이 고정한 것(`parse_profile_id`)이 먼저다. 자동으로 골라 읽은 경우에는
    `parser_version` 에 `profile:<key>` 로 남아 있다 — 그것으로 되찾는다.
    """
    if run.parse_profile_id is not None:
        pinned = db.get(FormatProfile, run.parse_profile_id)
        return dict(pinned.definition) if pinned else None

    version = run.parser_version or ""
    if not version.startswith("profile:"):
        return None
    key = version.split(":", 1)[1]
    found = db.scalar(select(FormatProfile).where(FormatProfile.key == key))
    return dict(found.definition) if found else None


def _rule(definition: dict[str, Any]) -> dict[str, Any] | None:
    """`tables.master_curve` 규칙. 없으면 `None` — 그러면 아무것도 안 한다."""
    tables = definition.get("tables")
    if not isinstance(tables, dict):
        return None
    rule = tables.get("master_curve")
    return rule if isinstance(rule, dict) and rule.get("pattern") else None


def temperature_from(label: str, rule: dict[str, Any]) -> tuple[float | None, str]:
    """표 이름에서 기준 온도를 읽는다. `(켈빈, 사람에게 할 말)`.

    **단위는 규칙이 적는다.** 이름에 `°C` 가 보인다고 섭씨로 단정하지 않는다 —
    `(20.0 °C reference)` 처럼 다른 뜻의 온도가 이름에 들어간 파일이 나오면 그때
    구분할 방법이 없다. 사람이 프로파일에서 정한다.
    """
    try:
        found = re.search(str(rule["pattern"]), label)
    except re.error as exc:
        return None, f"기준 온도 규칙의 정규식이 잘못됐습니다: {exc}"
    if found is None or not found.groups():
        return None, ""
    try:
        value = float(found.group(1))
    except (TypeError, ValueError):
        return None, f"'{found.group(0)}' 에서 숫자를 읽지 못했습니다."

    symbol = str(rule.get("unit") or "K")
    try:
        kelvin = units.to_si(value, symbol)
    except Exception:
        return None, f"단위 '{symbol}' 를 모릅니다. 프로파일에서 고쳐 주세요."
    return kelvin, ""


def register_from_profile(db: Session, run: TestRun) -> list[str]:
    """읽은 시험에서 마스터커브를 등록한다. 남길 말을 돌려준다."""
    definition = _profile_of(db, run)
    if definition is None:
        return []
    rule = _rule(definition)
    if rule is None:
        return []

    already = {
        key
        for row in db.scalars(select(MasterCurve).where(MasterCurve.test_run_id == run.id))
        for key in row.source_curve_keys
    }

    notes: list[str] = []
    for curve in services.importable_curves(db, run.id):
        key = str(curve["curve_key"])
        label = str(curve["label"] or key)
        if key in already:
            continue
        kelvin, said = temperature_from(label, rule)
        if said:
            notes.append(f"'{label}': {said}")
            continue
        if kelvin is None:
            # 규칙이 안 맞는 표다. 이동인자 표처럼 애초에 대상이 아닌 것도 여기
            # 걸리므로 **못 쓰는 표만** 말한다 — 아니면 파일마다 경고가 뜬다.
            if curve["usable"]:
                notes.append(f"'{label}' 에서 기준 온도를 못 읽어 등록하지 않았습니다.")
            continue
        if not curve["usable"]:
            notes.append(f"'{label}': {curve['note']}")
            continue

        made = services.import_master_curve(
            db, run, curve_key=key, reference_temperature_k=kelvin
        )
        # **어디서 읽은 온도인지 카드까지 따라가야 한다.** 사람이 적은 값과
        # 규칙이 읽은 값은 나중에 되짚을 때 뜻이 다르다.
        made.notes = [
            *made.notes,
            f"기준 온도를 표 이름에서 읽었습니다: '{label}' (프로파일 규칙)",
        ]
        notes.append(f"'{label}' 을 마스터커브로 등록했습니다.")
    return notes


parse_hooks.on_parsed("마스터커브 자동 등록", register_from_profile)
