/**
 * 물성 핸드북 — 문서·절·초안·검색·그림.
 *
 * **정본은 편집기 문서(JSON)** 다. 이 층은 그 JSON 을 열어 보지 않는다 — 어떻게
 * 그리고 어떻게 고치는지는 편집기(`GuideEditor`)의 일이다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type GuideDocument = components['schemas']['DocumentOut']
export type SectionBrief = components['schemas']['SectionBrief']
export type Section = components['schemas']['SectionOut']
export type Revision = components['schemas']['RevisionOut']
export type SearchHit = components['schemas']['SearchHit']
export type Asset = components['schemas']['AssetOut']

/** 편집기 문서. 서버는 `{type: 'doc'}` 인지만 본다. */
export type Doc = Record<string, unknown>

/** 문서 종류 — **「무엇을 하려고 왔나」 의 입구.** 순서가 곧 화면 순서다. */
export const KINDS = [
  { key: 'specimen', label: '시편 규격', hint: '어떻게 자르나' },
  { key: 'method', label: '시험 방법', hint: '어떻게 재나' },
  { key: 'calculation', label: '물성 계산', hint: '잰 것이 어떻게 물성이 되나' },
  { key: 'instrument', label: '장비 사용', hint: '장비를 어떻게 다루나' },
  { key: 'glossary', label: '용어', hint: '말이 무엇을 뜻하나' },
] as const
export type Kind = (typeof KINDS)[number]['key']

export const EMPTY_DOC: Doc = { type: 'doc', content: [] }

export const guideApi = {
  documents: () => api.get<GuideDocument[]>('/guide/documents'),
  document: (key: string) => api.get<GuideDocument>(`/guide/documents/${key}`),
  createDocument: (body: {
    key: string
    title: string
    kind: string
    topic?: string | null
    summary?: string | null
    position?: number
  }) => api.post<GuideDocument>('/guide/documents', body),
  updateDocument: (
    key: string,
    body: { title?: string; kind?: string; topic?: string | null; summary?: string | null }
  ) => api.patch<GuideDocument>(`/guide/documents/${key}`, body),

  section: (id: string) => api.get<Section>(`/guide/sections/${id}`),
  createSection: (documentKey: string, body: { key: string; title: string; position?: number }) =>
    api.post<Section>(`/guide/documents/${documentKey}/sections`, body),
  updateSection: (id: string, body: { title?: string; position?: number }) =>
    api.patch<Section>(`/guide/sections/${id}`, body),

  /** 초안을 낸다 — 누구나. `publish` 는 검토자만(서버가 거절한다). */
  submit: (sectionId: string, body: { body: Doc; note?: string; publish?: boolean }) =>
    api.post<Revision>(`/guide/sections/${sectionId}/revisions`, body),
  history: (sectionId: string) => api.get<Revision[]>(`/guide/sections/${sectionId}/revisions`),
  pending: () => api.get<Revision[]>('/guide/revisions?status=pending'),
  approve: (id: string, note?: string) =>
    api.post<Revision>(`/guide/revisions/${id}/approve`, { note: note ?? null }),
  reject: (id: string, note?: string) =>
    api.post<Revision>(`/guide/revisions/${id}/reject`, { note: note ?? null }),

  search: (q: string) => api.get<SearchHit[]>(`/guide/search?q=${encodeURIComponent(q)}`),

  /** 그림을 올린다. 본문에는 돌아온 `url` 만 들어간다. */
  upload: (file: File, documentKey?: string) => {
    const form = new FormData()
    form.append('file', file)
    const suffix = documentKey ? `?document_key=${encodeURIComponent(documentKey)}` : ''
    return api.postForm<Asset>(`/guide/assets${suffix}`, form)
  },
}
