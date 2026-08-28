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

#: 업로드한 시험 원본 파싱 → Parquet 정규화 — payload: test_run_id
#:
#: 업로드 요청 안에서 파싱하지 않는 이유: 큰 파일은 수 초가 걸리고, 그동안 요청이
#: 물려 있으면 브라우저가 먼저 끊는다. 그러면 사용자는 실패한 줄 아는데 서버는
#: 계속 처리하고 있다. 업로드는 파일만 받고 끝내고, 파싱은 워커가 한다.
TESTS_PARSE_UPLOAD = "tests.parse_upload"

#: 저장소 정리 — payload: dry_run(bool, 기본 true) · retention_days(int, 선택)
#:
#: 치울 것이 세 종류다. 오펀(DB 에 행 없음) · 미완성(.part) · 보존기간 지난 소프트
#: 삭제. **세 번째가 가장 크다** — 소프트 삭제는 행을 남기므로 오펀 탐색으로는
#: 영원히 안 잡힌다. 실측(2026-08-15): 지운 시험 2건의 파일이 그대로 남아 있었다.
TESTS_CLEANUP_STORAGE = "tests.cleanup_storage"

#: 어긋남 점검 — payload 없음
#:
#: 문자열 컬럼과 기준정보가 같은 말을 하는지 본다(ADR 0010 Contract). **주기 작업이다**
#: — 사람이 누를 때만 도는 점검으로는 "한 릴리스 동안 0" 을 답할 수 없다.
VOCABULARY_CHECK_DRIFT = "vocabulary.check_drift"

#: 장비 커넥터가 넣은 파일 읽기 — payload: item_id
#:
#: 반입 요청은 파일만 받고 끝낸다(업로드와 같은 이유). 워커가 종류를 감지하고
#: 읽어서 시편 후보를 찾고, 하나면 시험을 만들고 아니면 사람을 기다린다.
PIPELINES_PARSE_INBOX = "pipelines.parse_inbox"
