"""계약 baseline — 커밋된 openapi.json이 코드와 어긋나면 실패한다.

D13이 프론트 타입을 이 파일에서 생성하므로, 파일이 낡으면 프론트가 존재하지
않는 응답 형태를 믿게 된다. 65는 계약 baseline 호환성 검사를 갖고 있었고
(비교표 '65 → RA 도입 권장'), 여기서는 그 역할을 가장 싼 형태로 가져온다.

스키마가 바뀌면 diff가 남는다 — 그것이 곧 "API가 바뀌었다"는 신호다.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import version
from app.main import create_app

BASELINE = Path(__file__).resolve().parents[2] / "openapi.json"


def test_openapi_baseline_is_current() -> None:
    # **버전은 빼고 본다.** 계약이 바뀐 것과 릴리스를 낸 것은 다른 일이다
    # (v0.1.16 에서 버전만 올렸는데 이 검사가 실패했다).
    current = json.loads(
        json.dumps(
            version.as_baseline(create_app().openapi()),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    assert BASELINE.exists(), (
        f"{BASELINE.name} 이 없습니다. `python scripts/export_openapi.py` 를 실행하세요."
    )
    committed = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert current == committed, (
        "openapi.json 이 코드와 다릅니다. "
        "`python scripts/export_openapi.py` 로 갱신하고, "
        "프론트에서 `npm run api:types` 를 실행해 타입도 함께 갱신하세요."
    )
