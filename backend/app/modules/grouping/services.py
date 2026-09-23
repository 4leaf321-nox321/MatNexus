"""묶음을 만든다 — **저장소와 계산 커널 사이.**

`matcore.groups` 는 숫자만 안다. "어느 시험들이 한 묶음인가", "그 시험에서
무엇을 꺼내는가" 는 여기서 정한다 — 통계가 이미 같은 모양으로 갈려 있다.

## 무엇을 꺼내는지는 플러그인마다 다르다

Prony 묶음은 마스터커브가 필요하고, 나중에 올 S-N 묶음은 채택된 결과의 스칼라가
필요하다. 그 지식을 여기 `if` 로 쌓으면 **중심이 물성을 알게 된다** — 그것이
일반화하려던 바로 그 문제다.

그래서 **구성원을 모으는 법도 플러그인 곁에 둔다**(`_COLLECTORS`). 새 묶음이
오면 여기 한 줄, 그 물성 쪽에 함수 하나다. 완전한 확장은 아니다 — 그 한 줄이
남아 있는 한 이 파일은 물성 이름을 안다. **다음 물성을 붙일 때 그 한 줄이
거슬리면, 그때가 이것을 레지스트리로 옮길 때다.**
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import Any, Literal

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.grouping.models import GroupResult
from app.modules.materials.models import Material, Sample, Specimen
from app.modules.processing.models import ProcessingResult
from app.modules.tests.models import TestRun, TestSummary
from app.modules.viscoelastic.models import MasterCurve, PronyFit
from app.shared import filestore, permissions, specimen_size
from app.shared.errors import AppError, NotFound
from matcore import curves as curvekit
from matcore import groups, registry
from matcore import prony as pronykit
from matcore.groups import prony as _prony_group  # noqa: F401  (등록시킨다)
from matcore.groups import rate as rate_group
from matcore.processing.tensile import PLASTIC_STRAIN, TRUE_STRESS

#: 구성원을 모으는 법. 플러그인 id → 함수.
_COLLECTORS: dict[str, Callable[[Session, list[TestRun]], list[groups.Member]]] = {}

#: 구성원이 시험에서 **무엇을 갖고 있어야** 하는가. 플러그인 id → 이름.
#:
#: 화면이 후보를 거르는 근거다. Prony 는 마스터커브가 있는 시험만, 속도별 묶음은
#: 채택된 처리 결과가 있는 시험만 받는데, 화면이 그것을 플러그인 id 로 알아맞히면
#: 새 묶음이 생길 때마다 화면을 고쳐야 한다(D7). 여기서 선언하고 API 가 준다.
Needs = Literal["master_curve", "adopted_result", "summary"]
_NEEDS: dict[str, Needs] = {}


def collector(
    plugin_id: str, *, needs: Needs
) -> Callable[
    [Callable[[Session, list[TestRun]], list[groups.Member]]],
    Callable[[Session, list[TestRun]], list[groups.Member]],
]:
    def wrap(
        fn: Callable[[Session, list[TestRun]], list[groups.Member]],
    ) -> Callable[[Session, list[TestRun]], list[groups.Member]]:
        _COLLECTORS[plugin_id] = fn
        _NEEDS[plugin_id] = needs
        return fn

    return wrap


#: 확장이 선언하는 구성원 규칙의 자리 — `Plugin.meta["members"]`.
#:
#: **확장은 이 파일을 못 고친다**(app 을 모른다 — AGENTS). 그런데 「채택된 결과에서
#: 어느 열과 어느 조건을 꺼내는가」 는 파이썬이 아니라 선언으로 충분하다. 속도 가족의
#: 수집기를 보면 변형률 속도 하나만 계산이고 나머지는 「열 꺼내기·조건 꺼내기」 다.
#: 그래서 플러그인이 이렇게 적으면 여기가 모은다(2026-09-13):
#:
#:     meta={"members": {
#:         "from": "adopted_result",
#:         "columns": ["strain_true_plastic", "stress_true"],   # 채택된 결과의 곡선 열
#:         "conditions": ["temperature"],                       # 시험 조건 → values (SI)
#:         "values": ["youngs_modulus"],                        # 채택된 결과의 스칼라 → values
#:         "specimen": ["orientation"],                         # 시편의 칸 → meta
#:     }}
#:
#: `"specimen"` 은 **조건도 결과도 아닌 것**을 위한 자리다 — 이방성 묶음은 어느 시편이
#: MD 였는지 모르면 아무 말도 못 하는데, 방향은 시편의 성질이라 그 둘 어디에도 없다.
#:
#: `"from": "summary"` 면 곡선이 없는 시험이다 — 피로처럼 시편마다 점 하나. `conditions`
#: 는 같고 `values` 는 요약값(`TestSummary`, 표로 넣은 것)에서 꺼낸다. 글자 요약값은
#: 예/아니오로 읽어 1/0 이 된다(런아웃).
#:
#: 파이썬 수집기(`@collector`)가 있으면 그것이 먼저다 — 계산이 필요한 것(변형률 속도)은
#: 그 길로. `matcore/groups/__init__.py` 가 "다음 물성을 붙일 때 그 한 줄이 거슬리면
#: 레지스트리로 옮길 때" 라고 적어 둔 것의 절반이다 — 선언으로 되는 것은 옮겼다.
MEMBERS_META = "members"


def _declared_rule(plugin_id: str) -> dict[str, Any] | None:
    try:
        plugin = registry.get(plugin_id)
    except KeyError:
        return None
    rule = plugin.meta.get(MEMBERS_META)
    return rule if isinstance(rule, dict) else None


def member_needs(plugin_id: str) -> Needs:
    """이 묶음의 구성원이 갖고 있어야 하는 것. 모르는 묶음은 마스터커브로 본다 —
    그쪽이 더 좁아서, 틀려도 후보가 덜 뜰 뿐 잘못된 시험이 뜨지는 않는다."""
    found = _NEEDS.get(plugin_id)
    if found is not None:
        return found
    rule = _declared_rule(plugin_id)
    if rule is not None and rule.get("from") == "adopted_result":
        return "adopted_result"
    # **둘 중 하나면 되는 묶음은 안 거른다.** 채택된 결과가 없어도 사람이 표로
    # 적었을 수 있다 — 화면에서 미리 빼 버리면 그 시험을 고를 길이 없어진다.
    # 정말 아무 데도 값이 없으면 묶을 때 서버가 이름을 대고 막는다.
    if rule is not None and rule.get("from") in ("summary", MEASURED_OR_STATED):
        return "summary"
    return "master_curve"


_YES = {"yes", "y", "true", "1", "o", "예", "런아웃", "runout", "run-out"}
_NO = {"no", "n", "false", "0", "x", "아니오", "파단", "failure", "failed"}


#: 채택된 결과에 없으면 **사람이 표로 적은 요약값**에서 읽는 구성원 규칙.
#:
#: 같은 물성을 장비가 내기도 하고 사람이 적기도 하는 자리가 실제로 있다 —
#: r값이 그렇다(폭 신율계가 수동 시험기에만 달려 있다, 2026-09-22). 둘을 가리지
#: 않고 받되 **어느 쪽인지 기억한다**: 구성원의 `meta["source"]` 가 `measured`
#: 또는 `stated` 이고, 카드가 그것을 값의 출처로 옮겨 등급이 따라 내려간다.
MEASURED_OR_STATED = "measured_or_stated"

#: 값의 출처를 적는 자리 — 구성원 `meta` 의 키.
SOURCE_META = "source"

#: **있으면 싣고 없으면 비우는 값.** `values` 는 없으면 막지만 이쪽은 안 막는다.
#:
#: 한 묶음이 여러 물성을 함께 보는 자리가 있다 — 이방성이 그렇다. r값은 세 방향이
#: 다 있어야 r̄ 가 나오므로 필수지만, 방향별 항복응력은 있으면 카드에 더 싣고 없으면
#: 그만이다(Yld2000 을 맞추려면 필요하고, r̄·Δr 만 볼 때는 필요 없다). 이것을
#: `values` 에 넣으면 **항복응력을 안 적은 옛 시험이 통째로 안 묶인다.**
OPTIONAL_VALUES = "optional"

#: 그 구성원에서 **사람이 표로 적은** 값들의 이름 — 구성원 `meta` 의 키.
#:
#: `SOURCE_META` 하나로는 모자란 자리가 생겼다. 한 시험이 r값은 곡선에서 나오고
#: 항복응력은 사람이 적은 것일 수 있는데, 그때 「이 구성원은 stated」 라고만 적으면
#: **잰 r값까지 적은 값으로 내려간다.** 어느 값이 적힌 것인지 이름으로 남긴다.
STATED_KEYS_META = "stated_keys"


def _wanted_values(rule: dict[str, Any]) -> tuple[list[str], list[str]]:
    """규칙이 바라는 값 이름 — `(있어야 하는 것, 있으면 좋은 것)`.

    둘을 한 번에 찾되 **막는 것은 앞쪽뿐이다**(`OPTIONAL_VALUES`).
    """
    required = [str(one) for one in rule.get("values") or []]
    optional = [
        str(one) for one in rule.get(OPTIONAL_VALUES) or [] if str(one) not in required
    ]
    return required, optional


def _stated_values(
    db: Session, runs: list[TestRun], wanted: list[str]
) -> dict[uuid.UUID, dict[str, float]]:
    """시험마다 **사람이 표로 적은** 요약값. 글자는 예/아니오로 읽어 1/0 이 된다."""
    out: dict[uuid.UUID, dict[str, float]] = {}
    if not wanted:
        return out
    for row in db.scalars(
        select(TestSummary).where(TestSummary.test_run_id.in_([run.id for run in runs]))
    ):
        if row.key not in wanted:
            continue
        value: float | None = None
        if row.value_num is not None:
            value = float(row.value_num)
        elif row.value_text is not None:
            text = row.value_text.strip().casefold()
            value = 1.0 if text in _YES else 0.0 if text in _NO else None
        if value is not None:
            out.setdefault(row.test_run_id, {})[row.key] = value
    return out


def _specimen_meta(
    db: Session, runs: list[TestRun], wanted: list[str]
) -> dict[uuid.UUID, dict[str, Any]]:
    """시편에서 읽어 구성원에 실을 칸 — 방향이 대표다.

    **조건이 아니라 시편의 성질이다.** 이방성 묶음은 어느 시편이 MD 였는지 모르면
    아무 말도 못 하는데, 그 값은 시험 조건에도 결과 스칼라에도 없다.
    """
    if not wanted:
        return {}
    ids = {run.specimen_id for run in runs if run.specimen_id}
    found = {one.id: one for one in db.scalars(select(Specimen).where(Specimen.id.in_(ids)))}
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for run in runs:
        specimen = found.get(run.specimen_id) if run.specimen_id else None
        if specimen is None:
            continue
        out[run.id] = {key: getattr(specimen, key) for key in wanted if hasattr(specimen, key)}
    return out


def _summary_members(
    db: Session, runs: list[TestRun], rule: dict[str, Any], plugin_id: str
) -> list[groups.Member]:
    """곡선 없는 시험 — 조건과 요약값만 든 구성원. 없는 값은 **어느 시험이 무엇이 없는지**
    말한다."""
    wanted_conditions = [str(one) for one in rule.get("conditions") or []]
    wanted_values, optional_values = _wanted_values(rule)
    if rule.get("columns"):
        raise AppError(
            "MNX-GROUPING-0001",
            f"{plugin_id}: 요약값 구성원에는 곡선 열이 없습니다 — `columns` 를 비우세요.",
            status=422,
        )
    by_run = _stated_values(db, runs, wanted_values + optional_values)
    extra = _specimen_meta(db, runs, [str(one) for one in rule.get("specimen") or []])
    members: list[groups.Member] = []
    for run in runs:
        values: dict[str, float] = {}
        conditions = run.conditions or {}
        for key in wanted_conditions:
            found = conditions.get(key)
            if isinstance(found, int | float):
                values[key] = float(found)
        written = by_run.get(run.id, {})
        values.update(written)
        members.append(
            groups.Member(
                label=run.record_name,
                columns={},
                values=values,
                meta={
                    **extra.get(run.id, {}),
                    SOURCE_META: "stated",
                    STATED_KEYS_META: sorted(written),
                },
            )
        )
    return members


def _mixed_members(
    db: Session, runs: list[TestRun], rule: dict[str, Any], plugin_id: str
) -> list[groups.Member]:
    """**잰 값이 있으면 그것, 없으면 적은 값.** 어느 쪽인지 구성원에 남긴다.

    장비가 갈리는 물성이 있다 — 폭 신율계가 달린 시험기는 r값을 곡선에서 내고,
    없는 시험기의 시험은 사람이 표로 적는다. 여기서 둘을 가르면 같은 재료의 세
    방향을 한 묶음에 못 넣는다.
    """
    if rule.get("columns"):
        raise AppError(
            "MNX-GROUPING-0001",
            f"{plugin_id}: '{MEASURED_OR_STATED}' 구성원에는 곡선 열이 없습니다 — "
            "`columns` 를 비우세요.",
            status=422,
        )
    wanted_conditions = [str(one) for one in rule.get("conditions") or []]
    wanted_values, optional_values = _wanted_values(rule)
    stated = _stated_values(db, runs, wanted_values + optional_values)
    extra = _specimen_meta(db, runs, [str(one) for one in rule.get("specimen") or []])
    results = {
        one.id: one
        for one in db.scalars(
            select(ProcessingResult).where(
                ProcessingResult.id.in_(
                    {run.adopted_result_id for run in runs if run.adopted_result_id}
                )
            )
        )
    }

    members: list[groups.Member] = []
    for run in runs:
        values: dict[str, float] = {}
        conditions = run.conditions or {}
        for key in wanted_conditions:
            found = conditions.get(key)
            if isinstance(found, int | float):
                values[key] = float(found)
        result = results.get(run.adopted_result_id) if run.adopted_result_id else None
        scalars = {
            str(one.get("key")): one.get("value")
            for one in ((result.scalars if result else None) or [])
            if isinstance(one, dict)
        }
        for key in wanted_values + optional_values:
            found = scalars.get(key)
            if isinstance(found, int | float):
                values[key] = float(found)
        # 채택된 결과가 없거나 그 값을 안 냈다 — 사람이 적은 것을 본다.
        written = stated.get(run.id, {})
        written_keys = [
            key
            for key in wanted_values + optional_values
            if key not in values and key in written
        ]
        for key in written_keys:
            values[key] = written[key]
        # **하나라도 적은 값이면 구성원은 stated 다.** 어느 값이 그랬는지는
        # `STATED_KEYS_META` 가 이름으로 말하므로, 묶음은 값마다 따로 볼 수 있다.
        source = "stated" if written_keys else "measured"
        still = [key for key in wanted_values if key not in values]
        if still:
            raise AppError(
                "MNX-GROUPING-0009",
                f"{run.record_name} 에 {', '.join(still)} 이(가) 없습니다 — "
                f"그 값을 내는 처리를 채택하거나, 「표로 시험 입력」 에서 적으세요.",
                status=422,
            )
        members.append(
            groups.Member(
                label=run.record_name,
                columns={},
                values=values,
                meta={
                    **extra.get(run.id, {}),
                    SOURCE_META: source,
                    STATED_KEYS_META: written_keys,
                },
            )
        )
    return members


def _declared_members(
    db: Session, runs: list[TestRun], rule: dict[str, Any], plugin_id: str
) -> list[groups.Member]:
    """선언대로 채택된 결과에서 열·조건·스칼라를 꺼낸다. 없으면 **어느 시험이 무엇이
    없는지** 말한다 — 속도 가족 수집기와 같은 문장이다."""
    if rule.get("from") == "summary":
        return _summary_members(db, runs, rule, plugin_id)
    if rule.get("from") == MEASURED_OR_STATED:
        return _mixed_members(db, runs, rule, plugin_id)
    if rule.get("from") != "adopted_result":
        raise AppError(
            "MNX-GROUPING-0001",
            f"{plugin_id}: 구성원 규칙의 `from` 은 'adopted_result'·'summary'·"
            f"'{MEASURED_OR_STATED}' 만 됩니다.",
            status=422,
        )
    wanted_columns = [str(one) for one in rule.get("columns") or []]
    wanted_conditions = [str(one) for one in rule.get("conditions") or []]
    required, optional = _wanted_values(rule)
    wanted_values = required + optional
    extra = _specimen_meta(db, runs, [str(one) for one in rule.get("specimen") or []])
    results = {
        one.id: one
        for one in db.scalars(
            select(ProcessingResult).where(
                ProcessingResult.id.in_(
                    {run.adopted_result_id for run in runs if run.adopted_result_id}
                )
            )
        )
    }
    members: list[groups.Member] = []
    for run in runs:
        result = results.get(run.adopted_result_id) if run.adopted_result_id else None
        if result is None:
            raise AppError(
                "MNX-GROUPING-0009",
                f"{run.record_name} 에 채택된 처리 결과가 없습니다. 먼저 처리하고 "
                f"「결과」 탭에서 채택하세요.",
                status=422,
            )
        columns = _read_points(result.storage_path) if wanted_columns else {}
        missing = [one for one in wanted_columns if one not in columns]
        if missing:
            raise AppError(
                "MNX-GROUPING-0010",
                f"{run.record_name} 의 채택된 결과에 {', '.join(missing)} 열이 없습니다. "
                f"그 열을 만드는 단계를 거친 결과를 채택하세요.",
                status=422,
            )
        values: dict[str, float] = {}
        conditions = run.conditions or {}
        for key in wanted_conditions:
            found = conditions.get(key)
            if isinstance(found, int | float):
                values[key] = float(found)
        # 채택된 결과의 스칼라는 `[{"key": …, "value": …}, …]` 로 남는다.
        scalars = {
            str(one.get("key")): one.get("value")
            for one in (result.scalars or [])
            if isinstance(one, dict)
        }
        for key in wanted_values:
            found = scalars.get(key)
            if isinstance(found, int | float):
                values[key] = float(found)
        members.append(
            groups.Member(
                label=run.record_name,
                columns={one: columns[one] for one in wanted_columns},
                values=values,
                meta={
                    **extra.get(run.id, {}),
                    SOURCE_META: "measured",
                    STATED_KEYS_META: [],
                },
            )
        )
    return members


def _read_points(relative: str) -> dict[str, np.ndarray]:
    """저장된 곡선 한 벌. **NaN 을 살려 둔다** — 비운 자리와 0 은 다르다."""
    raw = curvekit.read_columns(filestore.read_bytes(relative))
    return {
        name: np.asarray(
            [np.nan if value is None else float(value) for value in values], dtype=np.float64
        )
        for name, values in raw.items()
    }


#: 마스터커브가 저장하는 열 이름 → 묶음 계산이 기대하는 이름.
#:
#: **두 이름이 다른 것이 실수가 아니다.** 저장 쪽은 화면에 그릴 채널이라
#: `frequency`·`storage_modulus` 로 사람이 읽기 좋게 두고, 계산 쪽은 단위를
#: 이름에 박아(`_hz`·`_pa`) 무엇이 들어오는지 못 헷갈리게 한다.
#:
#: 그 다리를 여기 둔다 — 어느 한쪽을 상대에 맞추면 그 이름이 그 층의 사정이
#: 아니라 남의 사정으로 정해진다.
_PRONY_COLUMNS = {
    "frequency": "frequency_hz",
    "storage_modulus": "storage_pa",
    "loss_modulus": "loss_pa",
}


def _prony_columns(raw: dict[str, np.ndarray], label: str) -> dict[str, np.ndarray]:
    found = {want: raw[have] for have, want in _PRONY_COLUMNS.items() if have in raw}
    missing = set(_PRONY_COLUMNS.values()) - set(found)
    if missing:
        raise AppError(
            "MNX-GROUPING-0006",
            f"{label} 의 마스터커브에 손실 탄성률이 없습니다. "
            f"저장·손실을 함께 맞춰야 계수가 나옵니다.",
            status=422,
        )
    return found


@collector("viscoelastic.prony_group", needs="master_curve")
def _prony_members(db: Session, runs: list[TestRun]) -> list[groups.Member]:
    """마스터커브와 (있으면) 맞춰 둔 Prony 를 꺼낸다.

    **시험마다 마스터커브가 여럿일 수 있다**(기준 온도를 바꿔 가며 만든다).
    그중 **대표로 지정한 것**을 쓴다.

    전에는 「가장 최근 것」 을 썼다. 편의 같지만 조용히 틀리는 자리였다 — 20 °C 로
    만들어 쓰다가 30 °C 로 하나 더 만들면, 그 순간부터 이 계산이 30 °C 것으로
    바뀌는데 화면 어디에도 그 전환이 안 보인다. 처리 결과를 **채택**하는 것과 같은
    문법으로 맞췄다.

    정렬에 `created_at` 을 남겨 둔다 — 대표가 없는 옛 데이터(마이그레이션 전에
    만들어진 것)에서도 무언가는 나와야 한다.
    """
    members: list[groups.Member] = []
    for run in runs:
        curve = db.scalar(
            select(MasterCurve)
            .where(MasterCurve.test_run_id == run.id)
            .order_by(MasterCurve.is_primary.desc(), MasterCurve.created_at.desc())
            .limit(1)
        )
        if curve is None:
            raise AppError(
                "MNX-GROUPING-0002",
                f"{run.record_name} 에 마스터커브가 없습니다. 먼저 겹치세요.",
                status=422,
            )
        # **다른 모듈의 `services` 를 부르지 않는다**(경계 검사). 파케이를
        # 읽는 것은 그 모듈의 로직이 아니라 저장소 인프라다 — `shared` 를 쓴다.
        columns = _prony_columns(_read_points(curve.storage_path), run.record_name)
        meta: dict[str, Any] = {}
        fit = db.scalar(
            select(PronyFit)
            .where(PronyFit.master_curve_id == curve.id)
            .order_by(PronyFit.created_at.desc())
            .limit(1)
        )
        if fit is not None:
            meta["prony"] = pronykit.PronySeries(
                equilibrium_pa=fit.equilibrium_pa,
                terms=tuple(
                    pronykit.PronyTerm(
                        float(term["modulus_pa"]), float(term["relaxation_time_s"])
                    )
                    for term in fit.terms
                ),
                normalized_rmse=fit.normalized_rmse,
                bic=fit.bic,
            )
        members.append(
            groups.Member(
                label=run.record_name,
                columns=columns,
                values={"reference_temperature_k": curve.reference_temperature_k},
                meta=meta,
            )
        )
    return members


def _strain_rate_of(db: Session, run: TestRun, specimen: Specimen) -> float:
    """이 시험의 변형률 속도(1/s).

    **조건에 `strain_rate` 가 있으면 그것**, 없으면 소성역 속도(`speed_plastic`, m/s)를
    게이지 길이로 나눈다. 게이지 길이는 시편 → 규격 공칭 순으로 온다(치수 3층,
    `specimen_size`). 둘 다 없으면 묶을 수 없다 — 속도를 모르는 시편을 「느린 쪽」
    에 조용히 넣으면 그 묶음이 거짓말이 된다.
    """
    conditions = run.conditions or {}
    direct = conditions.get("strain_rate")
    if isinstance(direct, int | float) and direct > 0:
        return float(direct)
    speed = conditions.get("speed_plastic")
    if not isinstance(speed, int | float) or speed <= 0:
        raise AppError(
            "MNX-GROUPING-0007",
            f"{run.record_name} 의 시험 조건에 소성역 속도(speed_plastic)가 없습니다. "
            f"속도로 묶으려면 조건에 속도가 적혀 있어야 합니다 — 시험 수정에서 넣으세요.",
            status=422,
        )
    gauge = specimen_size.sizes_of(db, specimen, run_measured=run.dimensions or None).get(
        "gauge_length"
    )
    if gauge is None or gauge <= 0:
        raise AppError(
            "MNX-GROUPING-0008",
            f"{run.record_name} 의 게이지 길이를 모릅니다 — 시편에도 규격에도 없습니다. "
            f"속도(m/s)를 변형률 속도(1/s)로 바꾸려면 게이지 길이가 필요합니다.",
            status=422,
        )
    return float(speed) / float(gauge)


@collector("tensile.rate_family", needs="adopted_result")
def _rate_members(db: Session, runs: list[TestRun]) -> list[groups.Member]:
    """채택된 결과의 진응력·진소성변형률 곡선과 변형률 속도를 꺼낸다.

    **채택된 것만 본다.** 처리 결과가 여럿이면 어느 것이 이 시험의 답인지는
    채택이 말한다 — 「가장 최근 것」 을 쓰면 다시 처리만 하고 채택을 안 옮긴 시험이
    조용히 바뀐다(Prony 묶음이 대표 마스터커브를 읽는 것과 같은 판단).
    """
    # **한 번에 읽는다**(N+1). 시편·결과를 시험마다 따로 부르지 않는다.
    specimens = {
        one.id: one
        for one in db.scalars(
            select(Specimen).where(Specimen.id.in_({run.specimen_id for run in runs}))
        )
    }
    results = {
        one.id: one
        for one in db.scalars(
            select(ProcessingResult).where(
                ProcessingResult.id.in_(
                    {run.adopted_result_id for run in runs if run.adopted_result_id}
                )
            )
        )
    }
    members: list[groups.Member] = []
    for run in runs:
        result = results.get(run.adopted_result_id) if run.adopted_result_id else None
        if result is None:
            raise AppError(
                "MNX-GROUPING-0009",
                f"{run.record_name} 에 채택된 처리 결과가 없습니다. 먼저 처리하고 "
                f"「결과」 탭에서 채택하세요.",
                status=422,
            )
        specimen = specimens.get(run.specimen_id)
        if specimen is None:
            raise NotFound(
                "MNX-GROUPING-0003", f"{run.record_name} 의 시편을 찾을 수 없습니다."
            )
        columns = _read_points(result.storage_path)
        if PLASTIC_STRAIN not in columns or TRUE_STRESS not in columns:
            raise AppError(
                "MNX-GROUPING-0010",
                f"{run.record_name} 의 채택된 결과에 진응력·진소성변형률이 없습니다. "
                f"「진응력·진소성변형률」 단계를 거친 결과를 채택하세요.",
                status=422,
            )
        values: dict[str, float] = {rate_group.RATE: _strain_rate_of(db, run, specimen)}
        temperature = (run.conditions or {}).get("temperature")
        if isinstance(temperature, int | float):
            values[rate_group.TEMPERATURE] = float(temperature)
        members.append(
            groups.Member(
                label=run.record_name,
                columns={
                    PLASTIC_STRAIN: columns[PLASTIC_STRAIN],
                    TRUE_STRESS: columns[TRUE_STRESS],
                },
                values=values,
            )
        )
    return members


def _material_of(db: Session, runs: Sequence[TestRun]) -> Material:
    """묶은 시험들의 재료. **하나여야 한다.**

    다른 재료의 시편을 묶으면 그 계수가 어느 재료의 것인지 말할 수 없다 —
    카드는 재료에 붙는다.
    """
    # **한 번에 읽는다**(AGENTS.md: N+1 은 명시적 join 으로 막는다). 시편마다
    # 두 번씩 부르면 여덟 시편을 묶을 때 열여섯 번을 왕복한다.
    owners = {
        specimen_id: material_id
        for specimen_id, material_id in db.execute(
            select(Specimen.id, Sample.material_id)
            .join(Sample, Sample.id == Specimen.sample_id)
            .where(Specimen.id.in_([run.specimen_id for run in runs]))
        )
    }
    materials: set[uuid.UUID] = set()
    for run in runs:
        material_id = owners.get(run.specimen_id)
        if material_id is None:
            raise NotFound(
                "MNX-GROUPING-0003", f"{run.record_name} 의 시료를 찾을 수 없습니다."
            )
        materials.add(material_id)
    if len(materials) != 1:
        raise AppError(
            "MNX-GROUPING-0004",
            f"재료가 {len(materials)}가지 섞여 있습니다. 묶음은 한 재료 안에서만 만듭니다.",
            status=422,
        )
    material = db.get(Material, materials.pop())
    if material is None:
        raise NotFound("MNX-GROUPING-0003", "재료를 찾을 수 없습니다.")
    return material


def create(
    db: Session,
    user: User,
    *,
    plugin_id: str,
    run_ids: Sequence[uuid.UUID],
    options: dict[str, Any] | None = None,
    note: str | None = None,
) -> GroupResult:
    """묶어서 **행으로 남긴다.** 커밋은 부르는 쪽이 한다."""
    collect = _COLLECTORS.get(plugin_id)
    rule = _declared_rule(plugin_id) if collect is None else None
    if collect is None and rule is None:
        raise AppError(
            "MNX-GROUPING-0001",
            f"구성원을 모으는 법을 모르는 묶음입니다: {plugin_id}",
            status=422,
        )

    runs = [permissions.get_run(db, user, run_id) for run_id in run_ids]
    material = _material_of(db, runs)
    members = (
        collect(db, runs)
        if collect is not None
        else _declared_members(db, runs, rule or {}, plugin_id)
    )

    try:
        outcome = groups.run_group(plugin_id, members, options or {})
    except groups.GroupError as exc:
        # **계산이 「못 한다」 고 한 것은 사용자 잘못이 아니라 조건 문제다.**
        # 500 으로 흘리면 이유가 안 보인다.
        raise AppError("MNX-GROUPING-0005", str(exc), status=422) from exc

    plugin = groups.groupings()
    version = next((one.version for one in plugin if one.id == plugin_id), "1")
    row = GroupResult(
        workspace_id=runs[0].workspace_id,
        material_id=material.id,
        plugin_id=plugin_id,
        plugin_version=version,
        options=dict(options or {}),
        members=[{"test_run_id": str(run.id), "label": run.record_name} for run in runs],
        used=list(outcome.used),
        values={key: float(value) for key, value in outcome.values.items()},
        detail=dict(outcome.detail),
        warnings=list(outcome.warnings),
        note=note,
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    return row


def of_material(db: Session, material_id: uuid.UUID) -> list[GroupResult]:
    """그 재료의 묶음. **최근 것부터** — 방법을 바꿔 다시 묶으면 새 행이 쌓인다."""
    return list(
        db.scalars(
            select(GroupResult)
            .where(GroupResult.material_id == material_id)
            .order_by(GroupResult.created_at.desc())
        )
    )
