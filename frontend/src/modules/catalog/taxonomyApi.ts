/**
 * 물성 분류 — **분야 ⊃ 물성군 ⊃ 물성** (ADR 0054).
 *
 * 물성(허브 키)은 문헌 + 사내(`local.`) 전부다. 물성 하나는 물성군 하나에, 물성군 하나는 분야
 * 하나에 든다. 바깥(Standard Platform)이 이 분류 그대로 물성 목록을 읽어 간다
 * (`/api/catalog/feed/*`) — 그래서 **키는 처음 정한 그대로**이고, 지우지 않고 폐기한다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type Taxonomy = components['schemas']['TaxonomyOut']
export type TaxonomyField = components['schemas']['PropertyFieldOut']
export type TaxonomyGroup = components['schemas']['PropertyGroupOut']
export type TaxonomyProperty = components['schemas']['TaxonomyPropertyOut']
export type TaxonomyImportRow = components['schemas']['TaxonomyImportRow']
export type TaxonomyImportResult = components['schemas']['TaxonomyImportOut']
export type FieldCreate = components['schemas']['PropertyFieldCreate']
export type FieldUpdate = components['schemas']['PropertyFieldUpdate']
export type GroupCreate = components['schemas']['PropertyGroupCreate']
export type GroupUpdate = components['schemas']['PropertyGroupUpdate']
export type AssignResult = components['schemas']['TaxonomyAssignOut']

/** 밀어 넣기 계획의 일 — 화면에 쓰는 말. */
export const ACTION_LABELS: Record<string, string> = {
  create: '새로',
  update: '고침',
  move: '옮김',
  restore: '되살림',
  assign: '넣음',
  unchanged: '그대로',
}

export const taxonomyApi = {
  tree: () => api.get<Taxonomy>('/catalog/taxonomy'),
  createField: (body: FieldCreate) => api.post<TaxonomyField>('/catalog/taxonomy/fields', body),
  updateField: (key: string, body: FieldUpdate) =>
    api.patch<TaxonomyField>(`/catalog/taxonomy/fields/${encodeURIComponent(key)}`, body),
  createGroup: (body: GroupCreate) => api.post<TaxonomyGroup>('/catalog/taxonomy/groups', body),
  updateGroup: (key: string, body: GroupUpdate) =>
    api.patch<TaxonomyGroup>(`/catalog/taxonomy/groups/${encodeURIComponent(key)}`, body),
  /** 물성 여럿을 한 군에. `groupKey` 가 `null` 이면 군에서 뺀다. */
  assign: (groupKey: string | null, propertyKeys: string[]) =>
    api.put<AssignResult>('/catalog/taxonomy/members', {
      group_key: groupKey,
      property_keys: propertyKeys,
    }),
  /** 기본이 미리 보기 — `dryRun: false` 일 때만 넣는다. 오류가 있으면 서버가 422 로 막는다. */
  importRows: (rows: TaxonomyImportRow[], dryRun: boolean) =>
    api.post<TaxonomyImportResult>('/catalog/taxonomy/import', { rows, dry_run: dryRun }),
}
