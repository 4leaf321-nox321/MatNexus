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
import uuid
from collections import Counter
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


class Row:
    """파일 하나에서 읽어 낸 것. **아직 아무것도 안 만들었다.**"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.grade: str = ""
        self.lot: str = ""
        self.orientation: str = ""
        self.seq: int | None = None
        self.dimensions: dict[str, float] = {}
        self.points: int = 0
        self.problem: str | None = None

    @property
    def ok(self) -> bool:
        return self.problem is None

    @property
    def where(self) -> str:
        return f"{self.grade} / {self.lot} / {self.orientation}{self.seq}"


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
    from app.shared.curvedata import instrument_dimensions

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

    missing = [
        name
        for name, value in (
            ("재료 코드", row.grade),
            ("로트", row.lot),
            ("방향", row.orientation),
        )
        if not value
    ]
    if row.seq is None:
        missing.append("시편 번호")
    if missing and pattern is None:
        missing.append("— 파일 이름에서 뽑으려면 --name-pattern 을 주세요")
    if missing:
        # **지어내지 않는다.** 시편 번호를 파일 순서로 매기면, 폴더에 파일이
        # 하나 더 들어온 날 번호가 통째로 밀린다.
        row.problem = (
            f"어디서 읽을지 모릅니다: {', '.join(missing)}. "
            f"프로파일 ⑤ 에서 「어느 재료·시료·시편인지」 로 정하거나 "
            f"--material-key 따위로 주세요. 있는 키: {sorted(meta)[:12]}"
        )
    elif not row.dimensions:
        # 오류는 아니지만 처리 1단계가 여기서 멈춘다. 미리 말한다.
        row.problem = (
            "시편 치수를 못 읽었습니다. 프로파일의 시편 규칙에 **단위**를 적었는지 "
            "보세요 — 값에 단위가 안 붙어 오는 파일은 단위를 선언해야 합니다."
        )
    return row


def _preview(rows: list[Row], material: str, category: str, thickness: float | None) -> int:
    good = [row for row in rows if row.ok]
    bad = [row for row in rows if not row.ok]

    print(f"\n파일 {len(rows)}개 — 읽힘 {len(good)} · 문제 {len(bad)}\n")

    if good:
        grades = sorted({row.grade for row in good})
        lots = sorted({(row.grade, row.lot) for row in good})
        print(
            f"만들거나 다시 쓸 재료 {len(grades)}개  ({material} / {category}"
            + (f" / {thickness}mm" if thickness else "")
            + ")"
        )
        for grade in grades:
            print(f"  {grade}")
        print(f"\n시료(로트) {len(lots)}개")
        for grade, lot in lots:
            count = sum(1 for row in good if row.grade == grade and row.lot == lot)
            print(f"  {grade} / {lot} — 시편 {count}개")

        # **겹치는 자리를 먼저 말한다.** 같은 시편에 파일이 둘이면 시험이 둘
        # 붙는다. 그게 맞을 때도 있지만(재시험), 대개는 번호가 틀린 것이다.
        double = [key for key, n in Counter(row.where for row in good).items() if n > 1]
        if double:
            print(f"\n같은 시편에 파일이 둘 이상 ({len(double)}자리) — 재시험이 맞습니까?")
            for key in double[:10]:
                print(f"  {key}")

        thin = [row for row in good if "gauge_length" not in row.dimensions]
        if thin:
            print(f"\n게이지 길이가 없는 파일 {len(thin)}개 — 처리가 여기서 멈춥니다.")
            for row in thin[:5]:
                print(f"  {row.path.name}")

    if bad:
        print(f"\n문제 {len(bad)}개")
        for row in bad:
            print(f"  {row.path.name}\n    {row.problem}")

    print("\n--apply 를 주면 실제로 넣습니다. 지금은 아무것도 안 만들었습니다.")
    return 0 if good else 1


def _load(
    client: TestClient,
    rows: list[Row],
    *,
    family: str,
    category: str,
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
                made = client.post(
                    "/api/materials",
                    json={
                        "family": family,
                        "category": category,
                        "grade": row.grade,
                        **({"details": details} if details else {}),
                        **({"spec_thickness": thickness} if thickness else {}),
                        "note": note,
                    },
                )
                if made.status_code != 201:
                    print(f"  재료 실패 {row.grade}: {made.text[:200]}")
                    continue
                materials[row.grade] = made.json()["id"]
                print(f"재료: {made.json()['record_name']} (새로)")
        material_id = materials[row.grade]

        # ── 시료 ──────────────────────────────────────────────────────
        lot_key = (row.grade, row.lot)
        if lot_key not in samples:
            pool = client.get(f"/api/materials/{material_id}/samples").json()
            hit = [one for one in pool if one["lot_no"] == row.lot]
            if hit:
                samples[lot_key] = hit[0]["id"]
            else:
                made = client.post(
                    f"/api/materials/{material_id}/samples",
                    json={"lot_no": row.lot, "note": note},
                )
                if made.status_code != 201:
                    print(f"  시료 실패 {row.lot}: {made.text[:200]}")
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
            else:
                made = client.post(
                    f"/api/samples/{sample_id}/specimens",
                    json={
                        "orientation": row.orientation,
                        "seq_no": row.seq,
                        "note": note,
                    },
                )
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
        with SessionLocal() as db:
            state = test_services.parse_run(db, uuid.UUID(run_id))
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True, help="옛 파일이 있는 폴더")
    parser.add_argument("--email", required=True, help="이 사람 이름으로 등록한다")
    parser.add_argument("--profile", default="legacy_mtet", help="읽을 형식의 key")
    parser.add_argument("--glob", default="*", help="폴더에서 고를 파일")
    parser.add_argument("--apply", action="store_true", help="실제로 넣는다")
    parser.add_argument("--family", default="Metal")
    parser.add_argument("--category", default="Steel")
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

    bad = [row for row in rows if not row.ok]
    if bad:
        # **하나라도 틀리면 시작하지 않는다.** 절반만 들어간 이관은 무엇이
        # 들어갔는지 사람이 손으로 세어야 하고, 그 세는 일이 또 틀린다.
        raise SystemExit(
            f"문제가 {len(bad)}개 있습니다. 미리 보기로 먼저 보세요 "
            f"(--apply 없이). 첫 번째: {bad[0].path.name} — {bad[0].problem}"
        )

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
