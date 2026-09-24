/**
 * 감사 로그 — **읽기만 있다.**
 *
 * 만드는 함수가 없는 것이 실수가 아니다. 감사 기록은 **변경이 일어난 그
 * 트랜잭션 안에서만** 생긴다(`app/shared/audit.py`) — API 로 만들 수 있으면
 * 그것은 감사가 아니다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type AuditEntry = components['schemas']['AuditEntryOut']
export type AuditPage = components['schemas']['Page_AuditEntryOut_']

export const auditApi = {
  /**
   * 최근 것부터. 서버가 상한을 강제한다 — `limit` 을 크게 줘도 잘린다.
   *
   * `client` 는 **들어온 길**이다: `mcp` 면 AI 를 거친 것만, `web` 이면 화면에서
   * 한 것만. 서버가 빈 문자열을 `web` 이라는 말로 받는다(질의 인자로 빈 값은
   * 넘기기 나쁘다).
   */
  list: (
    params: { action?: string; client?: string; workspace_id?: string; limit?: number } = {},
  ) => {
    const query = new URLSearchParams()
    if (params.action) query.set('action', params.action)
    if (params.client) query.set('client', params.client)
    if (params.workspace_id) query.set('workspace_id', params.workspace_id)
    if (params.limit) query.set('limit', String(params.limit))
    const suffix = query.toString()
    return api.get<AuditEntry[]>(`/audit${suffix ? `?${suffix}` : ''}`)
  },
  /**
   * **내 자료에 일어난 일** — 등록자가 묻는 자리(ADR 0035 남은 것). 누구나 부르되 제 자료의
   * 기록만 온다. 내가 손으로 한 일은 빠지고, 내 이름으로 AI 가 한 일은 선다.
   */
  mine: (params: { limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.limit) query.set('limit', String(params.limit))
    if (params.offset) query.set('offset', String(params.offset))
    const suffix = query.toString()
    return api.get<AuditPage>(`/audit/mine${suffix ? `?${suffix}` : ''}`)
  },
}

/**
 * 행위 코드 → 사람이 읽는 말.
 *
 * **서버가 주는 것은 `card.published` 같은 코드다.** 화면이 그것을 그대로 보이면
 * 읽는 사람이 매번 해석해야 한다. 다만 여기 없는 코드도 **감추지 않고** 코드
 * 그대로 보인다 — 모르는 일이 일어났다는 것 자체가 알아야 할 일이다.
 */
export const ACTION_LABELS: Record<string, string> = {
  'card.published': '물성 카드 확정',
  'card.deprecated': '물성 카드 내림',
  'card.deleted': '물성 카드 삭제',
  'material.deleted': '재료 삭제',
  'test_run.deleted': '시험 삭제',
  'account.decided': '가입 결정',
  'account.suspended': '계정 정지',
  'account.home_changed': '대표 소속 변경',
  'account.admin_changed': '시스템 관리자 권한 변경',
  'account.deleted': '계정 삭제',
  'vocabulary.renamed': '기준정보 이름 변경',
  'test_type.changed': '시험 종류 변경',
  // 아래 다섯은 **사람이 아닌 길로 들어온 것만** 남는다(`shared/audit.py`).
  // 화면에서 같은 일을 해도 안 남는다 — 남길 이유가 「누가 했나」 하나뿐이라.
  'values.changed_by_client': 'AI 가 값 수정',
  'card.created_by_client': 'AI 가 물성 카드 생성',
  'processing.run_by_client': 'AI 가 처리 실행',
  'recipe.saved_by_client': 'AI 가 레시피 저장',
  'format.saved_by_client': 'AI 가 형식 저장',
  // 그러고도 샜던 자리(2026-09-25) — 등록·문헌 카탈로그·의뢰. MCP 쓰기 도구마다 감사 흔적이
  // 있는지 `tests/architecture/test_mcp_writes_audited.py` 가 본다.
  'material.created_by_client': 'AI 가 재료 등록',
  'sample.created_by_client': 'AI 가 시료 등록',
  'specimen.created_by_client': 'AI 가 시편 등록',
  'catalog_property.created_by_client': 'AI 가 문헌 물성 정의 추가',
  'catalog_property.deprecated_by_client': 'AI 가 문헌 물성 정의 폐기',
  'catalog_material.created_by_client': 'AI 가 문헌 재료 추가',
  'catalog_value.added_by_client': 'AI 가 문헌 값 추가',
  'commission.created_by_client': 'AI 가 측정 의뢰 작성',
  // 이 둘은 **사람이 해도 남는다** — 되돌릴 수 없다.
  'catalog_value.deleted': '문헌 값 삭제',
  'catalog_property.migrated': '문헌 물성 키 이관',
  // **이름이 없으면 코드 그대로 뜨고 「행위로 필터」 에서 고를 수도 없다.** 아래는 이름표가
  // 없던 것들이다(2026-09-24, 36가지 중 18가지) — 배포 뒤 「열람 제한이 켜져 있던 부서」 를
  // 찾으려는데 필터에 없었다. 새 행위를 남기면 여기도 적는다(`tests/architecture/
  // test_audit_labels.py` 가 백엔드와 대조한다).
  'card.restored': '물성 카드 되살림(초안으로)',
  'test_run.updated': '시험 정보 변경',
  'processing_result.deleted': '처리 결과 삭제',
  'group_result.deleted': '글로벌 피팅 결과 삭제',
  'equipment.deleted': '장비 삭제',
  'trash.restored': '휴지통 복원',
  'trash.purged': '휴지통 영구 삭제',
  'data.exported': '데이터 내보내기',
  'guide.revision.approve': '핸드북 수정안 승인',
  'pipelines.connector.create': '장비 커넥터 생성',
  'pipelines.inbox.register': '수신함 파일 등록',
  'pipelines.inbox.discard': '수신함 파일 버림',
  'workspace.merged': '부서 병합',
  'auth.login_throttled': '로그인 지연(연속 실패)',
  // ADR 0035 — 보기는 모두에게, 고치기는 사람에게.
  'account.data_manager_changed': '자료 관리자 권한 변경',
  'ownership.changed': '등록자·편집 부서 변경',
  // 등록자가 아닌 사람이 고친 일 — 판정 자리가 남긴다(2026-09-25). 등록자는 「내 자료
  // 변경 이력」 에서 본다.
  'data.edited_by_other': '남의 자료 고침',
  // 아래 둘은 배포(마이그레이션)가 한 번 남긴다 — 배포 뒤 확인할 목록이다.
  'workspace.restriction_removed': '부서 열람 제한 해제',
  'definition.key_renamed': '정의 키 변경(겹침 정리)',
}
