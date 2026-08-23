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

export const auditApi = {
  /** 최근 것부터. 서버가 상한을 강제한다 — `limit` 을 크게 줘도 잘린다. */
  list: (params: { action?: string; workspace_id?: string; limit?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.action) query.set('action', params.action)
    if (params.workspace_id) query.set('workspace_id', params.workspace_id)
    if (params.limit) query.set('limit', String(params.limit))
    const suffix = query.toString()
    return api.get<AuditEntry[]>(`/audit${suffix ? `?${suffix}` : ''}`)
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
  'account.deleted': '계정 삭제',
  'vocabulary.renamed': '기준정보 이름 변경',
  'test_type.changed': '시험 종류 변경',
}
