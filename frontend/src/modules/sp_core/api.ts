/**
 * SP 코어 온톨로지 — **화면은 읽기만 한다**(ADR 0063).
 *
 * 잇기 · 끊기는 운영에서 AI(MCP)가 후보를 보이고 사람이 확인한다. 화면은 이어진 것을
 * 기준정보 · 물성 분류 옆에 「SP」 배지로 보일 뿐이다 — 전에는 이어도 변경 이력 말고는
 * 어디에도 안 보였다(2026-11-02).
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type SpLinked = components['schemas']['SpCoreLinkedOut']
export type SpLinkedPage = components['schemas']['SpCoreLinkedPage']
export type SpObjectDetail = components['schemas']['SpCoreObjectDetailOut']
export type SpRelation = components['schemas']['SpCoreRelationOut']

/** 이을 수 있는 대상 — 기준정보 값 · 물성 · 물성군 · 물성 분야. */
export type SpTarget = 'term' | 'property' | 'property_group' | 'property_field'

export const spCoreApi = {
  /** 한 대상 종류(기준정보는 한 축)에 이어진 SP 전부 — 줄마다 묻지 않는다. */
  linked: (target: SpTarget, vocabulary?: string) => {
    const params = new URLSearchParams({ target })
    if (vocabulary) params.set('vocabulary', vocabulary)
    return api.get<SpLinkedPage>(`/sp-core/linked?${params.toString()}`)
  },
  object: (type: string, key: string) =>
    api.get<SpObjectDetail>(
      `/sp-core/objects/${encodeURIComponent(type)}/${encodeURIComponent(key)}`
    ),
}
