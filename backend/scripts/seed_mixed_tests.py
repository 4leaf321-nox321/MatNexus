"""한 재료에 **여러 시험종류**가 함께 있는 예제를 만든다 — 화면을 볼 수 있게.

    .venv/Scripts/python.exe scripts/seed_mixed_tests.py --email <계정>

물성 화면(재료 → 물성 탭)은 **시험종류와 방향**으로 묶어 보여 준다. 그런데 개발
DB 에는 인장 하나만 있는 재료뿐이라, 묶음이 여럿일 때 그 화면이 어떻게 보이는지를
아무도 못 봤다 — 배치를 고치려면 먼저 그 그림이 있어야 한다.

    인장 MD   3건    ← 방향이 갈린다
    인장 TD   3건
    DMA       3건    ← 시험종류가 갈린다(스칼라도 곡선도 성격이 다르다)

**다시 돌리면 시험이 늘어난다.** 재료와 시료는 찾아 쓰지만 시편·시험은 새로 만든다 —
실제로도 시험은 쌓이는 것이라, 「한 번 더 돌려 n 을 늘린다」 가 자연스러운 쓰임이다.

## 값을 흔든다

같은 파일을 세 번 올리면 표준편차가 0 이 되어 **산포가 있는 화면**을 못 본다.
`Example.tra` 의 하중을 ±2% 안에서 흔들어 세 벌을 만든다. DMA 는 픽스처가 이미
세 벌이라 그대로 쓴다.

## 왜 API 로 부르나

`demo_load.py` 와 같은 이유다 — 채번·기준정보 연결·처리 규칙이 전부 라우트에
있다. DB 에 직접 꽂으면 **실제 흐름을 한 번도 안 지난 데이터**가 생겨, 화면에서
어디가 비는지 알 수 없다.

**서버는 안 떠 있어도 된다.** `TestClient` 로 앱을 직접 부른다.

## 운영에서 돌리지 않는다

지어낸 값이다. 재료 이름·메모에 그렇게 적는다 — 이 시스템은 값이 어디서 왔는지를
지키려고 만든 것이라, 이름표 없이 섞이면 전제가 무너진다.
"""

from __future__ import annotations

import argparse
import random
import sys
import uuid
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.accounts.models import User  # noqa: E402
from app.modules.tests import services as test_services  # noqa: E402
from app.shared.auth import current_user  # noqa: E402

FIXTURES = BACKEND_DIR / "tests" / "fixtures"
TENSILE = FIXTURES / "Example.tra"
DMA = [FIXTURES / f"example_dma_temp_sweep_{n:02d}.csv" for n in (1, 2, 3)]

LOT = "EX-MIX-A"
NOTE = "합성 예제입니다 — 측정값이 아닙니다(scripts/seed_mixed_tests.py)."
#: 재료 하나. **이름이 아니라 `grade` 로 찾는다** — `record_name` 은 채번 규칙이
#: 만드는 것이라 여기서 지어낼 수 없다.
MATERIAL = {
    "family": "Polymer",
    "category": "Thermoplastic",
    "grade": "EXAMPLE-MIX",
    "details": "예제",
    "alias": "여러 시험종류 예제 (합성)",
}

#: 인장 처리. `demo_load.py` 와 같은 차례다 — **진값까지 간다**(솔버가 받는 것이
#: 그쪽이고, 공칭으로 맞춘 파라미터를 넣으면 조용히 틀린 해석이 된다).
TENSILE_STEPS: list[dict[str, Any]] = [
    {
        # **시편 치수는 곡선에 없다.** `@` 로 시편을 가리킨다 — 값을 여기 적으면
        # 시편마다 다른 단면적이 하나로 뭉개진다.
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
    {"plugin": "tensile.strength", "options": {}},
    # **탄성계수는 안 낸다.** `Example.tra` 는 18점짜리 발췌본이라 탄성 창에 점이
    # 한둘밖에 안 들어가고, 그러면 회귀를 막는 가드에 걸린다(v1.159.0) — 그 가드가
    # 옳으므로 여기서 우회하지 않는다. 이 예제가 보여 주려는 것은 **묶음이 여럿일
    # 때의 화면**이지 탄성계수 적합이 아니다.
]

#: DMA 처리. **온도 스윕이므로 유리전이온도다** — `dma.lve_modulus` 는 변형률
#: 스윕용이고, 온도 스윕에 걸면 「선형 구간이 0점」 이라며 멈춘다(실측).
DMA_STEPS: list[dict[str, Any]] = [
    {"plugin": "dma.derived", "options": {}},
    {"plugin": "dma.glass_transition", "options": {}},
]

GAUGE_MM = 50.0


def _as(app: Any, email: str) -> None:
    """이 사람으로 로그인한 셈 친다. `demo_load.py` 와 같은 수법이다."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit(f"계정을 못 찾았습니다: {email}")
        user_id = user.id

    def _current() -> User:
        with SessionLocal() as db:
            found = db.get(User, user_id)
            if found is None:
                raise SystemExit("계정이 사라졌습니다.")
            db.expunge(found)
            return found

    app.dependency_overrides[current_user] = _current


def _shaken(source: bytes, scale: float) -> bytes:
    """하중을 `scale` 배로 흔든 `.tra`.

    **값이 다 같으면 산포가 0 이다** — 그러면 CV·이상치·신뢰구간이 전부 0 이나
    빈칸으로 나와, 그것을 보여 주려고 만든 화면을 못 본다.

    숫자 열만 건드린다. 머리말과 열 이름은 그대로 둬야 프로파일이 읽는다.
    """
    out: list[str] = []
    for line in source.decode("cp949", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and all(_number(one) is not None for one in parts[:2]):
            # 첫 열은 변위·시간이라 그대로, 둘째 열(하중)만 흔든다.
            second = _number(parts[1])
            assert second is not None
            parts[1] = f"{second * scale:.6f}"
            out.append("\t".join(parts))
        else:
            out.append(line)
    return "\n".join(out).encode("cp949", errors="replace")


def _number(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", ""))
    except ValueError:
        return None


def _material(client: TestClient) -> dict[str, Any]:
    """있으면 쓰고 없으면 만든다. **지우고 다시 만들지 않는다** — 남의 데이터가
    같은 이름일 수 있고, 지우는 스크립트는 언젠가 잘못된 것을 지운다."""
    found = client.get("/api/materials", params={"q": MATERIAL["grade"]}).json()
    for item in found.get("items", []):
        if item.get("grade") == MATERIAL["grade"]:
            print(f"재료: {item['record_name']} (이미 있음)")
            return dict(item)
    made = client.post("/api/materials", json={**MATERIAL, "note": NOTE})
    if made.status_code != 201:
        raise SystemExit(f"재료를 못 만들었습니다: {made.text}")
    print(f"재료: {made.json()['record_name']}")
    return dict(made.json())


def _run(
    client: TestClient,
    sample_id: str,
    *,
    orientation: str,
    test_type: str,
    filename: str,
    payload: bytes,
    steps: list[dict[str, Any]],
    gauge: float | None,
) -> bool:
    """시편 하나 → 시험 하나 → 처리 → 채택. **한 건이라도 실패하면 왜인지 적는다.**"""
    body: dict[str, Any] = {"orientation": orientation, "note": NOTE}
    if gauge is not None:
        body["gauge_length"] = gauge
    specimen = client.post(f"/api/samples/{sample_id}/specimens", json=body)
    if specimen.status_code != 201:
        print(f"  시편 실패: {specimen.text[:200]}")
        return False

    created = client.post(
        "/api/test-runs",
        data={
            "specimen_id": specimen.json()["id"],
            "test_type": test_type,
            "conditions": "{}",
            "note": NOTE,
        },
        files={"file": (filename, payload)},
    )
    if created.status_code != 202:
        print(f"  올리기 실패 {filename}: {created.text[:200]}")
        return False

    # **워커를 기다리지 않는다.** 같은 함수를 그대로 부른다.
    with SessionLocal() as db:
        state = test_services.parse_run(db, uuid.UUID(created.json()["id"]))
    if state != "parsed":
        print(f"  파싱 실패 {filename}: {state}")
        return False

    if test_type == "tensile":
        # 처리에 단면적이 필요하다 — 장비 파일이 든 치수를 시편에 옮긴다.
        client.post(f"/api/test-runs/{created.json()['id']}/apply-instrument-dimensions")

    stored = client.post(
        "/api/processing/results",
        json={"test_run_id": created.json()["id"], "steps": steps},
    )
    if stored.status_code != 201:
        print(f"  처리 실패 {filename}: {stored.text[:200]}")
        return False
    adopted = client.post(f"/api/processing/results/{stored.json()['id']}/adopt")
    if adopted.status_code not in (200, 201):
        print(f"  채택 실패 {filename}: {adopted.text[:200]}")
        return False
    print(f"  {test_type} {orientation} ← {filename}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="이 사람 이름으로 등록한다")
    parser.add_argument("--each", type=int, default=3, help="묶음마다 몇 건")
    args = parser.parse_args()

    if not TENSILE.exists():
        raise SystemExit(f"인장 픽스처가 없습니다: {TENSILE}")
    missing = [one for one in DMA if not one.exists()]
    if missing:
        raise SystemExit(
            f"DMA 픽스처가 없습니다: {missing} — "
            "`scripts/make_example_dma.py` 를 먼저 돌리세요."
        )

    application = create_app()
    _as(application, args.email)
    client = TestClient(application)
    material = _material(client)

    # **다시 돌려도 시료가 안 쌓인다.** 로트로 찾아 있으면 그것을 쓴다 — 스크립트를
    # 두 번 돌렸다고 같은 로트가 둘이 되면, 그 자체가 화면을 헷갈리게 만든다.
    existing = client.get(f"/api/materials/{material['id']}/samples").json()
    found = [one for one in existing if one.get("lot_no") == LOT]
    if found:
        sample_id = found[0]["id"]
        print(f"시료: {found[0]['record_name']} (이미 있음)")
    else:
        sample = client.post(
            f"/api/materials/{material['id']}/samples",
            json={"lot_no": LOT, "manufacturer": "예제", "note": NOTE},
        )
        if sample.status_code != 201:
            raise SystemExit(f"시료를 못 만들었습니다: {sample.text[:300]}")
        sample_id = sample.json()["id"]
        print(f"시료: {sample.json()['record_name']}")

    source = TENSILE.read_bytes()
    shake = random.Random(20260830)
    made = 0

    # 인장 — 방향 둘. **방향을 섞으면 그것은 산포가 아니라 다른 것을 섞은 것이다.**
    for orientation in ("MD", "TD"):
        for index in range(args.each):
            # TD 를 조금 세게 둔다 — **방향 차이가 보여야** 그 화면을 볼 수 있다.
            drift = 0.03 if orientation == "TD" else 0.0
            scale = 1.0 + shake.uniform(-0.02, 0.02) + drift
            made += _run(
                client,
                sample_id,
                orientation=orientation,
                test_type="tensile",
                filename=f"Example_{orientation}_{index + 1}.tra",
                payload=_shaken(source, scale),
                steps=TENSILE_STEPS,
                gauge=GAUGE_MM,
            )

    # DMA — 픽스처 셋이 이미 서로 다르다.
    for path in DMA[: args.each]:
        made += _run(
            client,
            sample_id,
            orientation="NA",
            test_type="dma_sweep",
            filename=path.name,
            payload=path.read_bytes(),
            steps=DMA_STEPS,
            gauge=None,
        )

    print(f"\n{made}건이 채택까지 끝났습니다.")
    print(f"물성 화면: /materials/{material['id']}  (물성 탭)")
    if made == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
