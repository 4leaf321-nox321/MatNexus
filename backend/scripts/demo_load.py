"""예시 곡선을 **운영과 같은 길로** 개발 서버에 넣는다.

재료 → 시료 → 시편 → 시험 올리기 → 파싱 → 처리 → 채택까지 API 로 한다.
DB 에 직접 꽂으면 빠르지만, 그렇게 넣은 데이터는 **실제 흐름을 한 번도 안 지나서**
화면에서 어디가 비는지 알 수 없다. 파일 이름 규칙·채번·기준정보 연결이 전부
그 길 위에 있다.

## 반드시 표시한다

만든 곡선은 측정값이 아니다(`demo_curves.py`). 이 시스템은 값이 어디서 왔는지를
지키려고 만든 것이라, 이름표 없이 섞이면 전제가 무너진다 — 재료 이름·별칭·메모와
시험 메모에 모두 적는다.

## 다시 돌려도 된다

이미 있으면 그 재료를 쓴다. 지우고 다시 만들지 않는다 — **남의 데이터가 같은
이름일 수 있고**, 지우는 스크립트는 언젠가 잘못된 것을 지운다.

    .venv/Scripts/python.exe scripts/demo_load.py --dir <곡선 폴더>
        --email <계정>
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))  # `python scripts/demo_load.py` 로도 돌게

from fastapi.testclient import TestClient  # noqa: E402

import app.all_models  # noqa: E402, F401  (외래키가 가리키는 표를 전부 등록시킨다)
from app.database import SessionLocal  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.accounts.models import User  # noqa: E402
from app.modules.tests import services as test_services  # noqa: E402
from app.shared.auth import current_user  # noqa: E402

#: 예시 재료. **이름에 DEMO 를 넣는다** — 목록에서 한눈에 갈린다.
MATERIAL = {
    "family": "Metal",
    "category": "Steel",
    "grade": "DEMO-DP590",
    "details": "예시",
    "spec_thickness": 1.0,
    "alias": "예시 데이터 (합성 곡선)",
    "poisson_ratio": 0.3,
    "density": 7.85e-9,
    "note": (
        "MatNexus 예시 데이터입니다. 측정값이 아니라 공개된 DP590(DP590T/340Y) "
        "물성 범위(항복 330~430 MPa · 인장 590~700 MPa)를 목표로 만든 합성 "
        "곡선입니다. 기능을 눈으로 확인하는 용도이고, 해석 근거로 쓰면 안 됩니다."
    ),
}

RUN_NOTE = "예시(합성) 곡선입니다 — 측정값이 아닙니다."

#: 게이지 길이(mm). `demo_curves.py` 가 이 길이로 신율을 만들었다 — **둘이
#: 어긋나면 변형률이 통째로 틀린다.**
GAUGE_MM = 50.0

#: 처리 단계. 화면에서 고르는 것과 같은 순서다.
STEPS: list[dict[str, Any]] = [
    # **시편 치수는 곡선에 없다.** 게이지 길이와 단면적은 `Specimen` 에 있고,
    # 레시피는 `@` 로 그것을 가리킨다(`processing/routes.py` 머리말).
    {
        "plugin": "tensile.engineering",
        "options": {
            "gauge_length": "@specimen_gauge_length",
            "area": "@specimen_area",
        },
    },
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_engineering", "duplicate_policy": "mean"},
    },
    # **격자를 맞춘다.** 시편마다 x 가 달라서, 안 맞추면 통계가 대표 곡선을
    # 아예 안 낸다("통계는 정렬을 대신 하지 않습니다"). 구간은 가장 짧은 곡선
    # 안쪽으로 고정한다 — 끝을 관측 최댓값으로 두면 시편마다 또 달라진다.
    {
        "plugin": "curve.resample",
        "options": {"x": "strain_engineering", "count": 400, "start": 0.0, "end": 0.20},
    },
    {"plugin": "tensile.strength", "options": {}},
    # **카드에 들어갈 값들이다.** 탄성계수가 없으면 덱의 `*ELASTIC` 자리가 비고,
    # 항복강도가 없으면 통계에서 견줄 것이 인장강도 하나뿐이다.
    {"plugin": "tensile.elastic_modulus", "options": {"method": "linear_regression"}},
    {
        "plugin": "tensile.proof_stress",
        # `@` 는 **앞 단계가 낸 값**도 가리킨다 — 4단계가 잰 탄성계수를 그대로 쓴다.
        "options": {"offset_strain": 0.002, "youngs_modulus": "@youngs_modulus"},
    },
    # 네킹 뒤를 자를 자리를 짚어 준다 — 자동으로 자르지는 않는다.
    {"plugin": "tensile.necking_candidate", "options": {}},
    # **네킹 뒤를 자른다.** 최대하중을 지나면 하중이 떨어지고, 그러면 진소성
    # 변형률이 되돌아온다 — 그 상태로는 재샘플도 적합도 안 된다(단조 증가가
    # 아니다). 앞 단계가 짚어 준 자리를 그대로 쓴다.
    {
        "plugin": "curve.crop",
        "options": {"x": "strain_engineering", "end": "@necking_candidate_strain"},
    },
    # 진응력·진소성변형률. **경화식이 쓰는 축이다.**
    {"plugin": "tensile.true_plastic", "options": {"youngs_modulus": "@youngs_modulus"}},
    # 자른 뒤에도 한 번 더 정렬한다 — 진소성 축은 공칭 축과 순서가 다를 수 있다.
    {
        "plugin": "curve.sort_unique",
        "options": {"x": "strain_true_plastic", "duplicate_policy": "mean"},
    },
    # 진소성 축도 시편마다 다르다 — 경화식이 쓰는 축이라 여기도 맞춰야 한다.
    {
        "plugin": "curve.resample",
        "options": {"x": "strain_true_plastic", "count": 300, "start": 0.0, "end": 0.14},
    },
]


def _as(app: Any, email: str) -> None:
    """이 사람으로 부른다.

    **서버의 인증을 우회하는 것이 아니다.** 이 스크립트는 앱을 자기 프로세스
    안에서 띄우고 그 함수들을 직접 부른다 — 이미 DB 에 붙어야 돌아가므로,
    돌릴 수 있는 사람은 어차피 DB 를 통째로 만질 수 있다. 비밀번호를 받아
    적어 두게 하는 편이 오히려 나쁘다(명령 이력에 남는다).

    **아무도 아닌 사람으로 넣지 않는다.** 등록한 사람이 비면 그 데이터는
    나중에 물어볼 데가 없어진다 — 그래서 계정을 반드시 받는다.
    """
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            found = [row.email for row in db.query(User).limit(10)]
            raise SystemExit(f"그 계정이 없습니다: {email} / 있는 계정: {found}")
        if user.home_workspace_id is None:
            raise SystemExit(f"{email} 에 소속 부서가 없습니다. 재료를 만들 수 없습니다.")
        found_id = user.id

    def _current() -> User:
        # 요청마다 그 요청의 세션에서 다시 읽는다 — 다른 세션의 객체를 물고
        # 있으면 `DetachedInstanceError` 가 난다.
        db = SessionLocal()
        got = db.get(User, found_id)
        assert got is not None
        return got

    app.dependency_overrides[current_user] = _current


def _material(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    """있으면 쓰고 없으면 만든다."""
    found = client.get("/api/materials", params={"q": "DEMO-DP590"}, headers=headers).json()
    for item in found["items"]:
        if item["grade"] == MATERIAL["grade"]:
            print(f"재료가 이미 있습니다: {item['record_name']}")
            return item
    made = client.post("/api/materials", json=MATERIAL, headers=headers)
    if made.status_code != 201:
        raise SystemExit(f"재료를 못 만들었습니다: {made.text}")
    print(f"재료를 만들었습니다: {made.json()['record_name']}")
    return made.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True, help="`.tra` 가 있는 폴더")
    parser.add_argument("--email", required=True, help="이 사람 이름으로 등록한다")
    parser.add_argument("--division", default="예시", help="사업부")
    args = parser.parse_args()

    files = sorted(args.dir.glob("*.tra"))
    if not files:
        raise SystemExit(f"`.tra` 가 없습니다: {args.dir}")

    app = create_app()
    _as(app, args.email)
    client = TestClient(app)
    # 인증은 위에서 갈아 끼웠다 — 머리글은 비워 둔다.
    headers: dict[str, str] = {}
    material = _material(client, headers)

    # 로트 하나에 시편 열. **실제로도 그렇게 온다** — 한 판을 잘라 여러 개를 뜬다.
    sample = client.post(
        f"/api/materials/{material['id']}/samples",
        json={"lot_no": "DEMO-LOT-A", "note": RUN_NOTE},
        headers=headers,
    )
    if sample.status_code != 201:
        raise SystemExit(f"시료를 못 만들었습니다: {sample.text}")
    print(f"시료: {sample.json()['record_name']}")

    made = 0
    for path in files:
        specimen = client.post(
            f"/api/samples/{sample.json()['id']}/specimens",
            json={
                "orientation": "MD",
                "standard": "KS B 0801 5호",
                # **게이지 길이는 장비 파일에 없다.** `.tra` 는 두께 a0 와 폭 b0
                # 만 적는다 — 사람이 안 넣으면 처리 1단계가 그 자리에서 멈춘다.
                "gauge_length": GAUGE_MM,
                "note": RUN_NOTE,
            },
            headers=headers,
        )
        if specimen.status_code != 201:
            print(f"  시편 실패: {specimen.text}")
            continue

        run = client.post(
            "/api/test-runs",
            data={
                "specimen_id": specimen.json()["id"],
                "test_type": "tensile",
                "conditions": "{}",
                "division": args.division,
                "note": RUN_NOTE,
            },
            files={"file": (path.name, path.read_bytes())},
            headers=headers,
        )
        if run.status_code != 202:
            print(f"  올리기 실패 {path.name}: {run.text}")
            continue

        # **워커를 기다리지 않는다.** 워커가 안 떠 있어도 이 스크립트는 끝나야
        # 한다 — 같은 함수를 그대로 부른다.
        with SessionLocal() as db:
            state = test_services.parse_run(db, uuid.UUID(run.json()["id"]))
        if state != "parsed":
            print(f"  파싱 실패 {path.name}: {state}")
            continue

        # 시편 치수를 장비 파일에서 채운다 — 처리에 면적이 필요하다.
        client.post(
            f"/api/test-runs/{run.json()['id']}/apply-instrument-dimensions",
            headers=headers,
        )

        stored = client.post(
            "/api/processing/results",
            json={"test_run_id": run.json()["id"], "steps": STEPS},
            headers=headers,
        )
        if stored.status_code != 201:
            print(f"  처리 실패 {path.name}: {stored.text}")
            continue
        adopted = client.post(
            f"/api/processing/results/{stored.json()['id']}/adopt", headers=headers
        )
        if adopted.status_code not in (200, 201):
            print(f"  채택 실패 {path.name}: {adopted.text}")
            continue

        made += 1
        print(f"  {path.name} → {run.json()['record_name']} 채택")

    print(f"\n{made}/{len(files)}건이 채택까지 끝났습니다.")
    if made:
        print(f"재료 화면: /materials/{material['id']}  (물성 탭에서 카드를 만들어 보세요)")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
