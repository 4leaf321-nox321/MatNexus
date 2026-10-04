"""시험 상태 → 사람이 읽는 말 — **한 벌이다.**

화면의 `RUN_STATUS_LABEL`(`frontend/src/modules/tests/api.ts`)과 같아야 한다 — 거르개(서버
라벨)와 배지(화면 라벨)가 다른 말을 하면 같은 상태가 둘로 보인다
(`tests/architecture/test_frontend_record_fields.py` 가 대 본다).

`shared` 에 둔 이유: 시험 목록의 거르개와 워크벤치의 담긴 줄이 같은 말을 해야 하는데,
워크벤치는 시험 모듈을 부를 수 없다(모듈끼리 직접 부르지 않는다). 워크벤치가 따로 적었다가
「읽힘」 과 「완료」 로 갈렸다(2026-10-04).
"""

from __future__ import annotations

RUN_STATUS_LABELS: dict[str, str] = {
    "uploaded": "대기",
    "parsing": "읽는 중",
    "parsed": "완료",
    "failed": "실패",
    "imported": "표로 입력",
}
