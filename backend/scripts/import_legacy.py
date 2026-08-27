"""옛 JSON 을 **형식 프로파일로** 읽어 운영과 같은 길로 넣는다.

    .venv/Scripts/python.exe scripts/import_legacy.py --dir <폴더> --email <계정>
    .venv/Scripts/python.exe scripts/import_legacy.py --dir <폴더> --email <계정> --apply

## 코드를 안 고친다

옛 JSON 은 파서를 새로 만들 필요가 없다. 리더가 이미 JSON 을 읽고
(`matcore/readers/json_tables.py`), 그 위에 **형식 프로파일**을 씌우면 어느 열이
변위이고 하중인지 정해진다. 프로파일은 데이터라서 관리 화면에서 만든다 —
**배포 없이 새 형식이 들어온다.** 그게 프로파일이 있는 이유다.

그래서 이 스크립트가 하는 일은 파일을 읽는 것이 아니라 **줄을 세우는 것**이다.
재료·시료·시편을 찾거나 만들고, 올리고, 처리해서 채택한다.

## 미리 보기가 기본이다

`--apply` 를 안 주면 **아무것도 안 만든다.** 무엇이 생기고 무엇을 다시 쓰는지만
보여 준다. 옛 데이터는 이름 규칙이 어긋난 자리가 꼭 있는데, 재료 200개를 넣고
나서 그것을 알면 되돌릴 방법이 없다 — 처리 결과는 불변이고, 지우는 스크립트는
언젠가 잘못된 것을 지운다.

## 식별자는 **프로파일이** 안다

파일의 열 이름을 이 스크립트가 또 알면, 형식이 조금 달라질 때마다 **두 군데**를
고쳐야 하고 한쪽만 고쳐지는 날이 온다. 그래서 프로파일의 `identity` 선언을
먼저 본다 — 편집 화면의 ⑤ 에서 「어느 재료·시료·시편인지」 로 정하는 그것이다.

찾는 순서는 넷이고, 앞엣것이 이긴다.

    ① 프로파일의 `identity` 선언
    ② `--material-key` 따위로 준 메타 키   ← 막다른 곳에서 빠져나올 문
    ③ 흔한 이름(`material_code`·`lot_no`·`specimen_no`·`orientation`)
    ④ `--name-pattern` 으로 파일 이름에서

## 파일 안에 없으면 파일 **이름**에서 뽑는다

옛 앱의 `.mtet` 에는 재료 코드도 로트도 방향도 없다 — 그것들은 파일 이름과 폴더
구조에 들어 있다. 그래서 `--name-pattern` 으로 이름에서 뽑는다. 이름 붙인 그룹
`material`·`lot`·`orientation`·`seq` 를 쓴다.

    --name-pattern "(?P<material>[^_]+)_(?P<lot>[^_]+)_(?P<orientation>MD|TD)_(?P<seq>[0-9]+)"

**메타가 이긴다.** 이름은 메타가 안 준 것만 채운다 — 파일 안의 값이 이름보다
믿을 만하고, 이름은 사람이 손으로 바꾼 적이 있다.

## 다시 돌려도 된다

있으면 쓰고 없으면 만든다. 지우고 다시 만들지 않는다 — **남의 데이터가 같은
이름일 수 있다.**

**같은 파일은 두 번 안 올린다.** 판단은 내용 해시(`source_sha256`)로 한다 —
이름이 아니다. 이관은 한 번에 끝나지 않는다(이름 규칙을 고쳐 다시 돌린다).
그때마다 곡선이 한 벌씩 더 붙으면 통계가 **조용히 두 번 센다** — 대표 곡선은
그럴듯하게 나오고 n 만 두 배가 되므로 화면 어디에도 티가 안 난다.

## S-S 곡선은 안 받는다

옛 파일에 S-S 곡선이 함께 있어도 **F-D 만 올린다.** 응력·변형률은 시편 치수와
함께 이 시스템이 계산한다(`tensile.engineering`). 남이 계산한 곡선을 원본으로
들이면, 어떤 게이지 길이와 단면적으로 나눈 것인지 모르는 값이 원본 자리에
앉는다 — 그 뒤로는 어느 것이 측정이고 어느 것이 계산인지 못 가른다.

장비가 계산해 준 곡선을 **버리지 않고** 갖고 오려면 프로파일의 `tables.derived`
에 그 표를 적는다(`readers/profile.py`). 그러면 처리가 그것을 원본으로 착각하지
않으면서 나란히 남는다.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))  # `python scripts/import_legacy.py` 로도 돌게

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.all_models  # noqa: E402, F401  (외래키가 가리키는 표를 전부 등록시킨다)
from app.database import SessionLocal  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.accounts.models import User  # noqa: E402
from app.modules.tests import services as test_services  # noqa: E402
from app.modules.tests.models import FormatProfile, TestRun  # noqa: E402
from app.shared.auth import current_user  # noqa: E402
from matcore.parsers import ParseError  # noqa: E402
from matcore.readers import profile as profiles  # noqa: E402
from matcore.readers import sniff  # noqa: E402

#: 처리 단계. 화면에서 고르는 것과 같은 순서이고, 이유는
#: `frontend/src/modules/processing/standard.ts` 의 머리말에 있다.
#:
#: **재샘플의 끝 값만 여기서 채운다.** 화면의 표준은 그 칸을 비워 둔다 — 묶음의
#: 모든 시편이 같은 값이어야 하는데 그 값은 가장 짧은 곡선이 정하고, 화면은
#: 무엇이 함께 묶일지 모르기 때문이다. 이관은 폴더 하나가 곧 묶음이라 알 수 있다.
STEPS: list[dict[str, Any]] = [
    {
        "plugin": "tensile.engineering",
        # 시편 치수는 곡선에 없다. `@` 가 그 다리를 놓는다.
        "options": {"gauge_length": "@specimen_gauge_length", "area": "@specimen_area"},
    },
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    {
        "plugin": "curve.resample",
        "options": {"x": "strain_engineering", "count": 400, "start": 0.0},
    },
    {"plugin": "tensile.strength", "options": {}},
    {"plugin": "tensile.elastic_modulus", "options": {"method": "linear_regression"}},
    {
        "plugin": "tensile.proof_stress",
        "options": {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
    },
    {"plugin": "tensile.necking_candidate", "options": {}},
    {
        "plugin": "curve.crop",
        "options": {"x": "strain_engineering", "end": "@necking_candidate_strain"},
    },
    {"plugin": "tensile.true_plastic", "options": {"youngs_modulus": "@youngs_modulus"}},
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_true_plastic", "duplicate_policy": "mean"},
    },
    {
        "plugin": "curve.resample",
        "options": {"x": "strain_true_plastic", "count": 300, "start": 0.0},
    },
]


#: 이 칸들은 **단위를 선언해야** 받는다. 안 그러면 API 기본값(mm · tonne/mm3)
#: 으로 조용히 읽히는데, m 로 적어 온 파일에서 그것은 1000배다.
#:
#: `poisson_ratio` 는 없다 — 비율이라 단위가 없다.
NEEDS_UNIT = {"spec_thickness", "density"}


def _numeric_problem(where: str, values: dict[str, str], units: dict[str, str]) -> str | None:
    """단위를 안 적은 숫자 칸이 있으면 그 사연. 없으면 `None`."""
    naked = sorted(key for key in values if key in NEEDS_UNIT and not units.get(key))
    if not naked:
        return None
    return (
        f"{where}의 {', '.join(naked)} 에 단위가 없습니다. "
        f"프로파일에서 그 칸의 단위를 적으세요 — 안 적으면 mm · tonne/mm3 로 "
        f"읽힙니다."
    )


class Row:
    """파일 하나에서 읽어 낸 것. **아직 아무것도 안 만들었다.**"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.grade: str = ""
        self.lot: str = ""
        self.orientation: str = ""
        self.seq: int | None = None
        self.dimensions: dict[str, float] = {}
        #: 파일이 **재료·시료에 대해** 적어 온 값과 그 단위. 프로파일의 `material`·
        #: `sample` 선언이 낸다. 업로드 경로는 이것을 안 읽는다 — 시험 하나가
        #: 재료를 고치면 그 아래 시험 100건이 저마다 한 번씩 덮어쓴다.
        self.material: dict[str, str] = {}
        self.material_units: dict[str, str] = {}
        self.sample: dict[str, str] = {}
        self.sample_units: dict[str, str] = {}
        #: 시편의 **성질**(규격·메모). 치수와 다르다 — 그쪽은 잰 값이다.
        self.specimen_props: dict[str, str] = {}
        self.points: int = 0
        self.problem: str | None = None
        #: 막지는 않지만 말해야 하는 것. **치수가 파일에 없는 것이 그렇다** —
        #: 시편 규격이 치수를 갖고 있으면 그것으로 돌기 때문이다(v1.119.0).
        self.notes: list[str] = []

    @property
    def ok(self) -> bool:
        return self.problem is None

    @property
    def where(self) -> str:
        # 로트가 비어 있으면 그렇게 보인다 — `SECC /  / MD1` 은 읽을 수 없다.
        return f"{self.grade} / {self.lot or '(로트 없음)'} / {self.orientation}{self.seq}"


def _as(app: Any, email: str) -> uuid.UUID:
    """이 사람으로 부른다. 이유는 `demo_load.py` 의 같은 함수에 적었다."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            found = [row.email for row in db.query(User).limit(10)]
            raise SystemExit(f"그 계정이 없습니다: {email} / 있는 계정: {found}")
        if user.home_workspace_id is None:
            raise SystemExit(f"{email} 에 소속 부서가 없습니다. 재료를 만들 수 없습니다.")
        found_id = user.id

    def _current() -> User:
        db = SessionLocal()
        got = db.get(User, found_id)
        assert got is not None
        return got

    app.dependency_overrides[current_user] = _current
    return found_id


def _profile(key: str) -> dict[str, Any]:
    with SessionLocal() as db:
        found = db.scalar(select(FormatProfile).where(FormatProfile.key == key))
        if found is None:
            have = [row.key for row in db.scalars(select(FormatProfile)).all()]
            raise SystemExit(f"그 형식이 없습니다: {key} / 있는 형식: {have}")
        return dict(found.definition)


def _read(
    path: Path,
    definition: dict[str, Any],
    keys: dict[str, str],
    pattern: re.Pattern[str] | None = None,
) -> Row:
    """파일 하나를 프로파일로 읽어 식별자와 치수를 뽑는다. **여기서 안 만든다.**"""
    from app.shared.curvedata import DIMENSION_ALIASES, instrument_dimensions

    row = Row(path)
    data = path.read_bytes()
    try:
        structure = sniff(data)
    except Exception as error:  # 리더가 못 읽는 파일
        row.problem = f"읽을 수 없습니다: {error}"
        return row

    if not profiles.matches(definition, filename=path.name, structure=structure):
        # **지문이 안 맞는다.** 확장자나 열 이름이 다르다 — 프로파일을 고칠 자리다.
        row.problem = "이 형식의 지문에 안 맞습니다(확장자·열 이름을 보세요)."
        return row

    try:
        parsed = profiles.apply(definition, data)
    except (ParseError, ValueError) as error:
        row.problem = str(error)
        return row

    meta = parsed.metadata
    told = parsed.identity  # 프로파일이 선언한 것. 이것이 먼저다.

    def pick(field: str, given: str | None, fallback: str) -> str:
        # ① 사람이 준 키가 이긴다 — 프로파일이 틀렸을 때 빠져나올 문이다.
        if given:
            return str(meta.get(given, "")).strip()
        # ② 프로파일이 선언한 것.
        if told.get(field):
            return str(told[field]).strip()
        # ③ 흔한 이름.
        return str(meta.get(fallback, "")).strip()

    row.grade = pick("material_grade", keys["material"], "material_code")
    row.lot = pick("sample_lot_no", keys["lot"], "lot_no")
    row.orientation = pick("specimen_orientation", keys["orientation"], "orientation").upper()
    raw_seq = pick("specimen_seq_no", keys["seq"], "specimen_no")
    row.seq = int(raw_seq) if raw_seq.isdigit() else None
    row.dimensions = instrument_dimensions(meta)
    row.material, row.material_units = dict(parsed.material), dict(parsed.material_units)
    row.sample, row.sample_units = dict(parsed.sample), dict(parsed.sample_units)
    row.specimen_props = dict(parsed.specimen_props)
    row.points = len(parsed.curves[0].channels[0].values) if parsed.curves else 0

    if pattern is not None:
        # **메타가 이긴다.** 이름은 메타가 안 준 것만 채운다 — 파일 안의 값이
        # 이름보다 믿을 만하고, 이름은 사람이 손으로 바꾼 적이 있다.
        found = pattern.search(path.name)
        if found is None:
            row.problem = f"이름 규칙에 안 맞습니다: {pattern.pattern}"
            return row
        parts = found.groupdict()
        row.grade = row.grade or (parts.get("material") or "").strip()
        row.lot = row.lot or (parts.get("lot") or "").strip()
        row.orientation = row.orientation or (parts.get("orientation") or "").strip().upper()
        if row.seq is None and (parts.get("seq") or "").strip().isdigit():
            row.seq = int(parts["seq"])

    # **비어도 되는 것과 없으면 안 되는 것을 가른다.**
    #
    # 옛 DB 에는 원래 빈 칸이 있다 — 로트를 안 적은 시료, 방향을 안 적은 시편.
    # 그것을 「어디서 읽을지 모릅니다」 로 막으면 이관이 통째로 서고, 사람은
    # **없는 값을 지어내서 채우게 된다.** 그게 훨씬 나쁘다.
    #
    #   로트   `Sample.lot_no` 가 NULL 을 받는다. 시료는 **번호로 식별**된다
    #          (`재료__01`) — 로트는 이름표이지 열쇠가 아니다.
    #   방향   `NA` 가 그러라고 있는 값이다(`ORIENTATIONS`). 화면의 일괄 등록도
    #          빈 방향을 `NA` 로 읽는다(`bulkRows.specimenNode`) — 두 길이 같은
    #          규칙을 써야 한다.
    if not row.orientation:
        row.orientation = "NA"

    missing = [name for name, value in (("재료 코드", row.grade),) if not value]
    if row.seq is None:
        missing.append("시편 번호")
    if missing and pattern is None:
        missing.append("— 파일 이름에서 뽑으려면 --name-pattern 을 주세요")
    if missing:
        # **지어내지 않는다.** 시편 번호를 파일 순서로 매기면, 폴더에 파일이
        # 하나 더 들어온 날 번호가 통째로 밀린다. 재료 코드는 이름을 만드는
        # 값이라 없으면 재료를 찾을 수도 만들 수도 없다.
        row.problem = (
            f"어디서 읽을지 모릅니다: {', '.join(missing)}. "
            f"프로파일 ⑤ 에서 「어느 재료·시료·시편인지」 로 정하거나 "
            f"--material-key 따위로 주세요. 있는 키: {sorted(meta)[:12]}"
        )
    elif said := (
        _numeric_problem("재료", row.material, row.material_units)
        or _numeric_problem("시료", row.sample, row.sample_units)
    ):
        row.problem = said
    if not row.dimensions:
        # **막지 않는다.** 치수는 세 곳에서 올 수 있다(v1.119.0) — 이 파일이 잰
        # 값 · 시편에 적힌 값 · **시편 규격이 정한 공칭**. 파일에 없다고 이관을
        # 세우면, 규격만 붙이면 될 일에 사람이 없는 값을 찾아 헤매게 된다.
        #
        # 그렇다고 조용히 넘어가지도 않는다. 규격에도 없으면 처리 1단계가
        # `@specimen_area` 에서 멈춘다 — 그때 원인을 여기서 찾게 하면 늦다.
        row.notes.append(_dimension_note(definition, sorted(DIMENSION_ALIASES)))
    return row


def _dimension_note(definition: dict[str, Any], looked: list[str]) -> str:
    """치수를 왜 못 읽었는지. **단위 탓만 하지 않는다.**

    전에는 「프로파일의 시편 규칙에 단위를 적었는지 보세요」 한 줄이었다. 그런데
    단위를 제대로 적어도 안 읽히는 자리가 있다 — **이관이 찾는 이름이 셋뿐**이다
    (`thickness`·`width`·`gauge_length`, 별칭 포함). 시편이 아직 없어서 그
    규격이 어떤 칸을 갖는지 알 수 없기 때문이다.

    그래서 규칙이 **무슨 키를 만들었는지**와 **무엇을 찾는지**를 나란히 적는다.
    어긋난 것이 눈에 보이면 고칠 수 있다.
    """
    made = sorted(
        {
            _specimen_key(label, rule)
            for label, rule in (definition.get("specimen") or {}).items()
        }
    )
    return (
        "파일에서 시편 치수를 못 읽었습니다. "
        f"프로파일의 시편 규칙이 만드는 키: {made or '(없음)'} · "
        f"이관이 찾는 이름: {looked}(별칭 포함). "
        "이름이 다르면 단위를 적어도 못 찾습니다. "
        "시편 규격이 치수를 갖고 있으면 그것으로 돕니다 — 둘 다 없으면 처리 "
        "1단계가 '@specimen_area' 에서 멈춥니다."
    )


def _specimen_key(label: str, rule: Any) -> str:
    """시편 규칙 하나가 만드는 키. 글자면 그것이고, dict 면 `key` 다."""
    if isinstance(rule, dict):
        return str(rule.get("key") or label)
    return str(rule)


def _said(values: dict[str, str], units: dict[str, str]) -> str:
    """`spec_thickness 1.2 mm · density 7.85e-9 tonne/mm3` — 사람이 읽을 한 줄."""
    return " · ".join(
        f"{key} {raw}" + (f" {units[key]}" if units.get(key) else "")
        for key, raw in sorted(values.items())
    )


def _preview(
    rows: list[Row], material: str | None, category: str | None, thickness: float | None
) -> int:
    good = [row for row in rows if row.ok]
    bad = [row for row in rows if not row.ok]

    print(f"\n파일 {len(rows)}개 — 읽힘 {len(good)} · 문제 {len(bad)}\n")

    if good:
        grades = sorted({row.grade for row in good})
        lots = sorted({(row.grade, row.lot) for row in good})
        told = " / ".join(
            part
            for part in (material, category, f"{thickness}mm" if thickness else None)
            if part
        )
        print(
            f"만들거나 다시 쓸 재료 {len(grades)}개"
            + (f"  (사람이 정한 것: {told} — 파일보다 먼저다)" if told else "")
        )
        # **파일이 무엇을 갖고 왔는지 보여 준다.** 이관 당일에 알면 늦다.
        for grade in grades:
            first = next(row for row in good if row.grade == grade)
            said = _said(first.material, first.material_units)
            print(f"  {grade}" + (f"\n      파일: {said}" if said else ""))

        print(f"\n시료(로트) {len(lots)}개")
        for grade, lot in lots:
            kin = [row for row in good if row.grade == grade and row.lot == lot]
            said = _said(kin[0].sample, kin[0].sample_units)
            print(
                f"  {grade} / {lot} — 시편 {len(kin)}개"
                + (f"\n      파일: {said}" if said else "")
            )

        # **재료 하나에 파일이 서로 다른 값을 적어 오면 말한다.** 먼저 만나는
        # 파일이 이기는데, 그건 폴더의 파일 순서가 정하는 것이지 사람이 정한
        # 것이 아니다. 그리고 이관은 되돌릴 수 없다.
        for grade in grades:
            seen = {
                _said(row.material, row.material_units) for row in good if row.grade == grade
            } - {""}
            if len(seen) > 1:
                print(f"\n재료 {grade} 에 파일마다 다른 값이 적혀 있습니다 ({len(seen)}가지)")
                for one in sorted(seen)[:4]:
                    print(f"  {one}")
                print("  → 먼저 만나는 파일이 이깁니다. --family 따위로 못 박으세요.")

        # **겹치는 자리를 먼저 말한다.** 같은 시편에 파일이 둘이면 시험이 둘
        # 붙는다. 그게 맞을 때도 있지만(재시험), 대개는 번호가 틀린 것이다.
        #
        # **어느 파일들이 뭉쳤는지 적는다.** 자리 이름만 적으면 사람은 "번호는
        # 다를 텐데 왜?" 에서 멈춘다 — 파일 이름을 나란히 놓아야 무엇이 같은
        # 번호로 읽혔는지 보인다(실사용에서 그렇게 막혔다).
        by_place: dict[str, list[Row]] = {}
        for row in good:
            by_place.setdefault(row.where, []).append(row)
        double = {key: kin for key, kin in by_place.items() if len(kin) > 1}
        if double:
            print(f"\n같은 시편에 파일이 둘 이상 ({len(double)}자리) — 재시험이 맞습니까?")
            for key, kin in list(double.items())[:5]:
                print(f"  {key}  ← 파일 {len(kin)}개")
                for row in kin[:4]:
                    print(f"      {row.path.name}")
                if len(kin) > 4:
                    print(f"      … {len(kin) - 4}개 더")
            if len(double) > 5:
                print(f"  … {len(double) - 5}자리 더")
            # **어디서 읽은 번호인지 짚는다.** 프로파일 ⑤ 의 「시편 번호」 가
            # 시험 회차나 늘 같은 값을 가리키면 전부 한 자리로 뭉친다.
            print(
                "  → 번호가 다를 텐데 뭉쳤다면, 프로파일 ⑤ 의 「시편 번호」 가 "
                "가리키는 키를 보세요. 그 키의 값이 파일마다 같으면 이렇게 됩니다."
            )

        thin = [row for row in good if "gauge_length" not in row.dimensions]
        if thin:
            # **막지 않는다.** 게이지 길이는 시험기 설정값이라 파일에 안 적히는
            # 것이 보통이고, 시편 규격이 갖고 있으면 그것으로 돈다(v1.119.0).
            print(
                f"\n게이지 길이가 파일에 없는 것 {len(thin)}개 — 규격에 있으면 그것을 씁니다."
            )
            for row in thin[:5]:
                print(f"  {row.path.name}")

        # **참고를 묻어 두지 않는다.** 막지는 않지만 나중에 처리에서 걸릴 것들이다.
        noted = [row for row in good if row.notes]
        if noted:
            print(f"\n참고 {len(noted)}개 — 넣기는 합니다")
            # 같은 사연이 수백 번 반복된다. 한 번만 적고 몇 개인지 센다.
            for said in dict.fromkeys(note for row in noted for note in row.notes):
                count = sum(1 for row in noted if said in row.notes)
                print(f"  ({count}개) {said}")

    if bad:
        print(f"\n문제 {len(bad)}개")
        for row in bad:
            print(f"  {row.path.name}\n    {row.problem}")

    print("\n--apply 를 주면 실제로 넣습니다. 지금은 아무것도 안 만들었습니다.")
    if bad:
        # **읽힌 것이 훨씬 많을 때 이 말이 필요하다.** 514개 중 96개가 막는데
        # 기본이 전부-아니면-전무라, 그것을 모르면 사람은 96개를 다 고칠 때까지
        # 아무것도 못 넣는 줄 안다.
        print(
            f"기본은 **하나라도 문제면 아무것도 안 넣습니다.** "
            f"읽힌 {len(good)}개만 넣으려면 --skip-bad 를 함께 주세요."
        )
    return 0 if good else 1


#: 값과 짝이 되는 단위 칸의 이름. API 가 `<칸>_unit` 으로 받는다.
UNIT_FIELD = {"spec_thickness": "spec_thickness_unit", "density": "density_unit"}

#: 파일이 준 것을 숫자로 읽어야 하는 칸.
AS_NUMBER = {"spec_thickness", "density", "poisson_ratio"}

#: **목록으로 보내야 하는 칸.** 옛 DB 는 「적용 제품」 을 한 칸에 하나만 갖고
#: 있는 경우가 흔하다. API 는 목록을 받으므로 한 개짜리 목록으로 감싼다.
AS_LIST = {"applied_products", "applied_parts"}


def _body(
    values: dict[str, str], units: dict[str, str], given: dict[str, Any], note: str
) -> dict[str, Any]:
    """파일이 준 것 + 사람이 준 것 → API 몸통. **사람이 준 것이 먼저다.**

    파일이 이기게 하면 프로파일이 틀렸을 때 빠져나올 문이 없다. `--material-key`
    를 기본값 없이 둔 것과 같은 판단이다 — 값이 있으면 "사람이 일부러 정했다" 는
    뜻이고, 그때만 파일보다 먼저다.

    **단위는 값과 함께 간다.** 값만 보내고 단위를 안 보내면 API 가 기본값(mm ·
    tonne/mm3)으로 읽는다 — 그래서 `_numeric_problem` 이 먼저 막는다.
    """
    body: dict[str, Any] = {"note": note}
    for key, raw in values.items():
        text = raw.strip()
        if not text:
            continue
        if key in AS_LIST:
            body[key] = [text]
            continue
        if key in AS_NUMBER:
            try:
                body[key] = float(text)
            except ValueError:
                # **지어내지 않는다.** 숫자가 아니면 그 칸만 빼고 나머지는 넣는다.
                continue
        else:
            body[key] = text
        if key in UNIT_FIELD and units.get(key):
            body[UNIT_FIELD[key]] = units[key]
    # 사람이 준 것으로 덮는다. `None` 은 "안 줬다" 이므로 파일 것을 살린다.
    body.update({key: value for key, value in given.items() if value is not None})
    return body


def _fill_specimen(
    client: TestClient, specimen: dict[str, Any], props: dict[str, str]
) -> None:
    """있던 시편의 **빈 칸만** 파일 값으로 채운다.

    ## 왜 필요한가 — 다시 돌려도 안 붙었다

    시편은 「있으면 쓰고 없으면 만든다」 인데, **규격은 만들 때만** 붙고 있었다.
    그래서 프로파일이 규격을 안 보내던 동안 들어간 시편들은 규격이 빈 채로 남고,
    프로파일을 고쳐 **다시 돌려도 그 시편은 `hit` 으로 걸려 그대로**였다
    (실사용 2026-08-28).

    고칠 길이 화면밖에 없었는데, 시편이 수백 장이면 그것은 길이 아니다.

    ## 빈 칸만 채운다

    사람이 이미 골라 넣은 규격을 파일이 조용히 바꾸면 어느 것이 맞는지 알 수
    없다. 장비 치수를 시편에 채울 때와 같은 규칙이다
    (`apply_instrument_dimensions` 의 `overwrite`).

    **덮어쓰기는 안 연다.** 이관은 되돌릴 수 없고, 규격을 덮어쓰면 그 시편의
    치수 칸이 통째로 바뀐다(ADR 0010) — 되돌릴 수 없는 것에 자동 덮어쓰기를
    붙이지 않는다.
    """
    fill = {
        key: value.strip()
        for key, value in props.items()
        if value.strip() and not specimen.get(key)
    }
    if not fill:
        return
    name = specimen.get("record_name") or specimen["id"]
    done = client.patch(f"/api/specimens/{specimen['id']}", json=fill)
    if done.status_code != 200:
        # **막지 않는다.** 곡선은 멀쩡히 들어가야 한다 — 규격은 나중에도 붙일
        # 수 있지만, 여기서 멈추면 그 시험이 통째로 안 들어간다.
        print(f"  시편 채우기 실패 {name}: {done.text[:160]}")
        return
    said = ", ".join(f"{key}={value}" for key, value in fill.items())
    print(f"  시편 {name} 빈 칸 채움 — {said}")


def _parse(client: TestClient, run_id: str) -> str:
    """이 시험을 읽는다. **워커가 먼저 집어 갔으면 그것을 기다린다.**

    스크립트는 일부러 제 손으로 읽는다 — 실패가 그 자리에서 보여야 하고, 다음
    단계(치수·처리·채택)가 읽힌 뒤에 와야 하기 때문이다. 그런데 올리기는 큐에도
    넣으므로, **워커가 떠 있으면 둘이 같은 시험을 동시에 읽는다.**

    실측(2026-08-27): 셋을 넣다가 둘째에서 터졌다.

        PermissionError: [WinError 32] 다른 프로세스가 파일을 사용 중 ...
        .../curves/raw.parquet.part

    이관은 되돌릴 수 없다. 중간에 터지면 재료 하나는 만들어졌고 시험은 반만
    들어간 상태로 남는다. 그래서 **진 쪽이 이긴 쪽을 기다린다** — 누가 읽었든
    끝 상태는 같다.

    미리 기다리지 않고 먼저 해 보는 이유는, 워커가 없는 것이 보통이기 때문이다.
    파일이 수백 개일 때 매번 대기 시간을 먹으면 그것만으로 이관이 하루가 된다.
    """
    try:
        with SessionLocal() as db:
            return test_services.parse_run(db, uuid.UUID(run_id))
    except Exception as caught:  # 워커가 같은 파일을 쥐고 있다
        print(f"  워커가 먼저 읽고 있습니다 — 기다립니다 ({type(caught).__name__})")

    for _ in range(60):
        state = str(client.get(f"/api/test-runs/{run_id}").json().get("status") or "")
        if state in ("parsed", "failed"):
            return state
        time.sleep(1)
    return "timeout"


def _load(
    client: TestClient,
    rows: list[Row],
    *,
    family: str | None,
    category: str | None,
    details: str,
    thickness: float | None,
    division: str,
    profile_key: str,
    note: str,
) -> int:
    materials: dict[str, str] = {}
    samples: dict[tuple[str, str], str] = {}
    specimens: dict[str, str] = {}
    done = 0
    skipped = 0

    for row in rows:
        # ── 재료 ──────────────────────────────────────────────────────
        if row.grade not in materials:
            found = client.get("/api/materials", params={"q": row.grade}).json()["items"]
            hit = [one for one in found if one["grade"] == row.grade]
            if hit:
                materials[row.grade] = hit[0]["id"]
                print(f"재료: {hit[0]['record_name']} (있던 것)")
            else:
                body = _body(
                    row.material,
                    row.material_units,
                    {
                        "family": family,
                        "category": category,
                        "details": details or None,
                        "spec_thickness": thickness,
                    },
                    note,
                )
                body["grade"] = row.grade  # 열쇠다. 파일도 사람도 못 덮는다.
                # **계열·분류는 필수다.** 파일에도 없고 사람도 안 줬으면 여기서
                # 정한다 — 값을 안 넣고 보내면 422 로 막히고, 그 사연은 이관
                # 당일에 파일 수백 개를 앞에 두고 읽게 된다.
                body.setdefault("family", "Metal")
                body.setdefault("category", "Steel")
                made = client.post("/api/materials", json=body)
                if made.status_code != 201:
                    print(f"  재료 실패 {row.grade}: {made.text[:200]}")
                    continue
                materials[row.grade] = made.json()["id"]
                print(f"재료: {made.json()['record_name']} (새로)")
        material_id = materials[row.grade]

        # ── 시료 ──────────────────────────────────────────────────────
        #
        # **빈 로트는 `None` 이다.** 옛 DB 에는 로트를 안 적은 시료가 있고, 그때
        # 서버는 `lot_no = NULL` 로 담는다. 여기서 `""` 로 견주면 다음에 다시
        # 돌릴 때 못 찾아서 **같은 시료가 또 생긴다** — 그러면 시편이 갈라지고
        # 통계가 두 묶음으로 센다.
        lot = row.lot or None
        lot_key = (row.grade, lot or "")
        if lot_key not in samples:
            pool = client.get(f"/api/materials/{material_id}/samples").json()
            hit = [one for one in pool if (one["lot_no"] or None) == lot]
            if hit:
                samples[lot_key] = hit[0]["id"]
            else:
                body = _body(row.sample, row.sample_units, {}, note)
                body["lot_no"] = lot  # 열쇠다.
                made = client.post(f"/api/materials/{material_id}/samples", json=body)
                if made.status_code != 201:
                    print(f"  시료 실패 {lot or '(로트 없음)'}: {made.text[:200]}")
                    continue
                samples[lot_key] = made.json()["id"]
        sample_id = samples[lot_key]

        # ── 시편 ──────────────────────────────────────────────────────
        if row.where not in specimens:
            pool = client.get(f"/api/samples/{sample_id}/specimens").json()
            hit = [
                one
                for one in pool
                if one["seq_no"] == row.seq and one["orientation"] == row.orientation
            ]
            if hit:
                specimens[row.where] = hit[0]["id"]
                _fill_specimen(client, hit[0], row.specimen_props)
            else:
                # **규격을 붙인다.** 규격이 치수 칸을 정하므로(ADR 0010), 안
                # 붙이면 그 시편은 치수를 받을 자리조차 없다.
                body = _body(row.specimen_props, {}, {}, note)
                body["orientation"] = row.orientation  # 열쇠다.
                body["seq_no"] = row.seq
                made = client.post(f"/api/samples/{sample_id}/specimens", json=body)
                if made.status_code != 201:
                    print(f"  시편 실패 {row.where}: {made.text[:200]}")
                    continue
                specimens[row.where] = made.json()["id"]
        specimen_id = specimens[row.where]

        # ── 같은 파일이 이미 올라와 있나 ───────────────────────────────
        digest = hashlib.sha256(row.path.read_bytes()).hexdigest()
        with SessionLocal() as db:
            already = db.scalar(
                select(TestRun).where(
                    TestRun.specimen_id == uuid.UUID(specimen_id),
                    TestRun.source_sha256 == digest,
                    TestRun.deleted_at.is_(None),
                )
            )
            if already is not None:
                print(f"  {row.path.name} → {already.record_name} (이미 있음, 건너뜀)")
                skipped += 1
                continue

        # ── 올리기 · 파싱 · 처리 · 채택 ────────────────────────────────
        run = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen_id,
                "test_type": "tensile",
                "conditions": "{}",
                "division": division,
                "note": note,
            },
            files={"file": (row.path.name, row.path.read_bytes())},
        )
        if run.status_code != 202:
            print(f"  올리기 실패 {row.path.name}: {run.text[:200]}")
            continue
        run_id = run.json()["id"]

        # **읽을 형식을 고정한다.** 자동 선택은 지문이 겹치면 엉뚱한 것을 고른다 —
        # 이관은 무엇으로 읽을지 이미 정해 놓고 시작하는 일이다.
        client.post(f"/api/test-runs/{run_id}/reparse", json={"profile_key": profile_key})
        state = _parse(client, run_id)
        if state != "parsed":
            detail = client.get(f"/api/test-runs/{run_id}").json()
            print(f"  파싱 실패 {row.path.name}: {detail.get('parse_error', state)}")
            continue

        client.post(f"/api/test-runs/{run_id}/apply-instrument-dimensions")
        stored = client.post(
            "/api/processing/results", json={"test_run_id": run_id, "steps": STEPS}
        )
        if stored.status_code != 201:
            print(f"  처리 실패 {row.path.name}: {stored.text[:250]}")
            continue
        adopted = client.post(f"/api/processing/results/{stored.json()['id']}/adopt")
        if adopted.status_code not in (200, 201):
            print(f"  채택 실패 {row.path.name}: {adopted.text[:200]}")
            continue

        done += 1
        print(f"  {row.path.name} → {run.json()['record_name']} 채택")

    print(f"\n{done}/{len(rows)}건이 채택까지 끝났습니다.")
    for grade, material_id in materials.items():
        print(f"재료 화면: /materials/{material_id}  ({grade})")
    return 0 if done or skipped else 1


def _gate(rows: list[Row], *, skip_bad: bool) -> list[Row]:
    """문제 있는 줄을 만났을 때 **멈출 것인가 거를 것인가.**

    기본은 멈춘다. 절반만 들어간 이관은 무엇이 들어갔는지 사람이 손으로 세어야
    하고, 그 세는 일이 또 틀린다.

    다만 **514개짜리 실데이터에서는 이것이 시작을 막는다.** 옛 DB 에는 영영 못
    고칠 줄이 섞여 있다(재료 코드가 아예 없는 행). 그때 100%를 요구하면
    아무것도 못 넣는다.

    그래서 빠져나갈 문을 낸다 — 다만 **기본은 아니다.** 그리고 건너뛴 파일을
    전부 적는다: 「손으로 세지 않게」 하려고 막았던 것이므로, 문을 열려면 그
    목록이 함께 나와야 한다.
    """
    bad = [row for row in rows if not row.ok]
    if not bad:
        return rows
    if not skip_bad:
        raise SystemExit(
            f"문제가 {len(bad)}개 있습니다. 미리 보기로 먼저 보세요 "
            f"(--apply 없이). 첫 번째: {bad[0].path.name} — {bad[0].problem}"
            f"\n읽힌 것만 넣으려면 --skip-bad 를 함께 주세요 "
            f"(건너뛴 {len(bad)}개를 이름으로 적어 줍니다)."
        )
    print(f"\n건너뜁니다 — {len(bad)}개")
    for row in bad:
        print(f"  {row.path.name}")
        print(f"      {row.problem}")
    print(
        f"\n**이 {len(bad)}개는 안 들어갑니다.** 고친 뒤 다시 돌리면 됩니다 — "
        f"이미 들어간 것은 내용 해시로 걸러집니다."
    )
    return [row for row in rows if row.ok]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True, help="옛 파일이 있는 폴더")
    parser.add_argument("--email", required=True, help="이 사람 이름으로 등록한다")
    parser.add_argument("--profile", default="legacy_mtet", help="읽을 형식의 key")
    parser.add_argument("--glob", default="*", help="폴더에서 고를 파일")
    parser.add_argument("--apply", action="store_true", help="실제로 넣는다")
    parser.add_argument(
        "--skip-bad",
        action="store_true",
        help="읽힌 것만 넣고 문제 있는 줄은 건너뛴다 (건너뛴 파일 이름을 전부 적는다)",
    )
    # **기본을 비워 둔다.** 값이 있으면 "사람이 일부러 정했다" 는 뜻이고, 그때만
    # 파일보다 먼저다. 기본값을 박아 두면 그 구별이 사라져 **파일이 절대 못
    # 이긴다** — 프로파일에 `material` 을 적어 놔도 아무 일이 안 일어난다.
    # 둘 다 없으면 `_load` 가 Metal/Steel 로 만든다(전과 같다).
    parser.add_argument("--family", default=None, help="파일보다 먼저다. 기본 Metal")
    parser.add_argument("--category", default=None, help="파일보다 먼저다. 기본 Steel")
    parser.add_argument("--details", default="", help="재료 이름에 붙는 세부(예: LEGACY)")
    parser.add_argument("--thickness", type=float, default=None, help="공칭 두께(mm)")
    parser.add_argument("--division", default="", help="사업부")
    parser.add_argument("--note", default="옛 데이터 이관", help="재료·시험 메모")
    # **기본을 비워 둔다.** 값이 있으면 "사람이 일부러 정했다" 는 뜻이고, 그때만
    # 프로파일보다 먼저 이긴다. 기본값을 박아 두면 그 구별이 사라진다.
    parser.add_argument("--material-key", default=None, help="프로파일 선언을 덮어쓴다")
    parser.add_argument("--lot-key", default=None)
    parser.add_argument("--seq-key", default=None)
    parser.add_argument("--orientation-key", default=None)
    parser.add_argument(
        "--name-pattern",
        default=None,
        help="파일 이름에서 뽑을 정규식. 이름 붙인 그룹 material·lot·orientation·seq 를 쓴다",
    )
    args = parser.parse_args()

    files = sorted(path for path in args.dir.glob(args.glob) if path.is_file())
    if not files:
        raise SystemExit(f"파일이 없습니다: {args.dir}/{args.glob}")

    definition = _profile(args.profile)
    keys = {
        "material": args.material_key,
        "lot": args.lot_key,
        "seq": args.seq_key,
        "orientation": args.orientation_key,
    }
    pattern = re.compile(args.name_pattern) if args.name_pattern else None
    rows = [_read(path, definition, keys, pattern) for path in files]

    if not args.apply:
        raise SystemExit(_preview(rows, args.family, args.category, args.thickness))

    rows = _gate(rows, skip_bad=args.skip_bad)

    app = create_app()
    _as(app, args.email)
    client = TestClient(app)
    raise SystemExit(
        _load(
            client,
            rows,
            family=args.family,
            category=args.category,
            details=args.details,
            thickness=args.thickness,
            division=args.division,
            profile_key=args.profile,
            note=args.note,
        )
    )


if __name__ == "__main__":
    main()
