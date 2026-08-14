"""작업 종류 이름.

**모듈 사이의 유일한 접점이다.** 계정 모듈이 알림 모듈의 함수를 직접 부르면 둘이
묶이고, 경계 테스트도 막는다(모듈끼리는 models 만 import 한다). 대신 계정 모듈은
큐에 이름과 payload 를 넣기만 하고, 그 이름을 처리하는 쪽은 알림 모듈이 스스로
등록한다.

이름을 문자열 리터럴로 흩뿌리지 않고 여기 모으는 이유는, 오타가 나면 작업이
조용히 `failed` 로만 쌓이기 때문이다.
"""

from __future__ import annotations

#: 알림 발송 — payload: event_kind·key·title·body·link·to_user_id
NOTIFY_DELIVER = "notifications.deliver"

#: 기본 알림 규칙 보장 — payload: user_id
NOTIFY_ENSURE_RULES = "notifications.ensure_rules"
