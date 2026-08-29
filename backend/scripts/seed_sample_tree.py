"""개발 DB 에 **시료·시편 계층 예제**를 하나 만든다 — 화면을 볼 수 있게.

    python scripts/seed_sample_tree.py                  # 시료 5 · 시편 3 씩
    python scripts/seed_sample_tree.py --samples 3 --specimens 4
    python scripts/seed_sample_tree.py --material SECC_1.0   # 기존 재료에 붙인다

## 왜 API 로 부르나

`db.add(Sample(...))` 로 직접 넣으면 **채번과 기준정보 카운트가 어긋난다.**
시료 번호는 `next_sample_seq` 가 주고, 시편 번호는 **방향마다 따로** 매겨지며,
제조사·거래처는 기준정보의 「쓰는 곳」 을 올린다. 그 규칙이 라우트에 있으므로
여기서 다시 쓰면 두 벌이 되고, 갈라진 쪽이 이 스크립트면 **화면에서만 이상한
데이터**가 생긴다.

그래서 **개발 서버가 떠 있어야 한다.** 화면이 누르는 것과 같은 요청을 보낸다.

## 운영에서 돌리지 않는다

지어낸 로트 번호와 생산일이다. 카드의 근거가 되면 안 된다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.modules.accounts.models import User  # noqa: E402
from app.modules.auth.security import create_access_token  # noqa: E402

#: 방향은 돌려 가며 준다. **같은 시료의 MD/TD/DD 를 묶어 r값·이방성을 낸다**
#: (ADR 0004) — 한 방향만 만들면 그 화면에서 볼 것이 없다.
ORIENTATIONS = ("MD", "TD", "DD")

MAKERS = ("포스코", "현대제철", "동국제강", "JFE", "Nippon Steel")


def _token() -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.is_system_admin.is_(True)))
        if user is None:
            raise SystemExit("시스템 관리자 계정이 없습니다.")
        return create_access_token(user.id)[0]


def _material(client: httpx.Client, wanted: str | None) -> dict[str, Any]:
    """붙일 재료. 이름을 주면 그것을, 안 주면 새로 만든다."""
    if wanted:
        found = client.get("/api/materials", params={"q": wanted, "limit": 5}).json()
        for one in found["items"]:
            if one["record_name"] == wanted:
                return one
        raise SystemExit(f"그 이름의 재료를 못 찾았습니다: {wanted}")

    made = client.post(
        "/api/materials",
        json={
            "family": "Metal",
            "category": "Steel",
            "grade": "TREE-DEMO",
            "spec_thickness": 1.2,
        },
    )
    if made.status_code != 201:
        raise SystemExit(f"재료를 못 만들었습니다: {made.text}")
    body: dict[str, Any] = made.json()
    return body


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--specimens", type=int, default=3)
    parser.add_argument("--material", help="기존 재료의 record_name. 없으면 새로 만든다")
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {_token()}"}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=30) as client:
        try:
            material = _material(client, args.material)
        except httpx.ConnectError:
            raise SystemExit(
                f"개발 서버에 못 붙었습니다({args.base_url}). "
                f"채번 규칙이 라우트에 있어 서버 없이는 만들 수 없습니다."
            ) from None

        print(f"재료: {material['record_name']}")
        made_specimens = 0
        for index in range(args.samples):
            sample = client.post(
                f"/api/materials/{material['id']}/samples",
                json={
                    "lot_no": f"L{24 + index // 12}-{(index % 12) + 1:02d}17",
                    "manufacturer": MAKERS[index % len(MAKERS)],
                    # 로트마다 날짜를 벌려 둔다 — 목록이 날짜순으로 설 때 뜻이 있다.
                    "production_date": (
                        date(2026, 1, 15) + timedelta(days=45 * index)
                    ).isoformat(),
                },
            )
            if sample.status_code != 201:
                raise SystemExit(f"시료를 못 만들었습니다: {sample.text}")
            row = sample.json()
            print(f"  시료 {row['record_name']}")

            for which in range(args.specimens):
                specimen = client.post(
                    f"/api/samples/{row['id']}/specimens",
                    json={
                        "orientation": ORIENTATIONS[which % len(ORIENTATIONS)],
                        "standard": "ASTM E8",
                        "thickness": 1.2,
                        "width": 12.5,
                        "gauge_length": 50.0,
                    },
                )
                if specimen.status_code != 201:
                    raise SystemExit(f"시편을 못 만들었습니다: {specimen.text}")
                made_specimens += 1
                print(f"    시편 {specimen.json()['record_name']}")

    print(f"\n시료 {args.samples} · 시편 {made_specimens} 을 만들었습니다.")


if __name__ == "__main__":
    main()
