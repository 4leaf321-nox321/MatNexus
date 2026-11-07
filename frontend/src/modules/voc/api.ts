/** VOC API — 게시판이고 절차다. */

import { api, downloadFile, downloadPostFile } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type VocItem = components['schemas']['VocOut']
export type VocDetail = components['schemas']['VocDetailOut']
export type VocEvent = components['schemas']['VocEventOut']
export type VocAttachment = components['schemas']['VocAttachmentOut']
export type VocPage = components['schemas']['Page_VocOut_']
export type VocStatus = components['schemas']['VocStatusOut']
/** 복사할 글 한 건 — 본문 · 이력 · 첨부 이름째(`GET /voc/contents`). */
export type VocContent = components['schemas']['VocContentOut']
export type VocContentPage = components['schemas']['Page_VocContentOut_']
type CreateRequest = components['schemas']['VocCreateRequest']
type UpdateRequest = components['schemas']['VocUpdateRequest']
type EventRequest = components['schemas']['VocEventRequest']

export interface VocListParams {
  status?: string
  q?: string
  mine?: boolean
  limit?: number
  offset?: number
}

/** 내용 복사의 범위 — 목록의 거르기에 번호 범위(양끝 포함)를 더한다. */
export interface VocContentParams extends VocListParams {
  seqFrom?: number
  seqTo?: number
}

/** 고른 건을 한 번에 묻는 수. 주소에 실려 가므로 서버(`MAX_CONTENT_IDS`)가 같은 수로 막는다. */
export const CONTENT_IDS_PER_ASK = 50

function contentQuery(params: VocContentParams & { ids?: string[] }): string {
  const query = new URLSearchParams()
  if (params.status) query.set('status', params.status)
  if (params.q) query.set('q', params.q)
  if (params.mine) query.set('mine', 'true')
  if (params.seqFrom) query.set('seq_from', String(params.seqFrom))
  if (params.seqTo) query.set('seq_to', String(params.seqTo))
  for (const id of params.ids ?? []) query.append('ids', id)
  if (params.limit) query.set('limit', String(params.limit))
  if (params.offset) query.set('offset', String(params.offset))
  const suffix = query.toString()
  return `/voc/contents${suffix ? `?${suffix}` : ''}`
}

/**
 * 상태의 색. **차례와 이름은 서버가 준다**(`vocApi.statuses` · `status_label`) —
 * 여기는 색만 정한다. 모르는 상태는 기본색이다.
 */
export const STATUS_TONES: Record<string, string> = {
  open: 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200',
  accepted:
    'border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-200',
  in_progress:
    'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200',
  resolved:
    'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  closed: 'border-border bg-muted text-muted-foreground',
  rejected:
    'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200',
}

export const vocApi = {
  statuses: () => api.get<VocStatus[]>('/voc/statuses'),
  list: (params: VocListParams = {}) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.q) query.set('q', params.q)
    if (params.mine) query.set('mine', 'true')
    if (params.limit) query.set('limit', String(params.limit))
    if (params.offset) query.set('offset', String(params.offset))
    const suffix = query.toString()
    return api.get<VocPage>(`/voc${suffix ? `?${suffix}` : ''}`)
  },
  /** 범위의 글을 본문 · 이력째로 — 쪽은 `fetchAll` 이 넘긴다. */
  contents: (params: VocContentParams = {}) => api.get<VocContentPage>(contentQuery(params)),
  /** 고른 건들의 글. 주소 길이 때문에 `CONTENT_IDS_PER_ASK` 개씩 나눠 묻고, 게시판 차례(최신이
   *  위)로 모아 준다. 없어진 건은 빠진다 — 몇 건이 빠졌는지는 부른 쪽이 고른 수와 견준다. */
  contentsOf: async (ids: string[]): Promise<VocContent[]> => {
    const found: VocContent[] = []
    for (let at = 0; at < ids.length; at += CONTENT_IDS_PER_ASK) {
      const chunk = ids.slice(at, at + CONTENT_IDS_PER_ASK)
      const page = await api.get<VocContentPage>(contentQuery({ ids: chunk, limit: chunk.length }))
      found.push(...page.items)
    }
    return found.sort((a, b) => b.seq - a.seq)
  },
  get: (id: string) => api.get<VocDetail>(`/voc/${id}`),
  create: (payload: CreateRequest) => api.post<VocDetail>('/voc', payload),
  /** 낸 사람은 남이 말을 남기기 전까지, 관리자는 언제나. 서버가 같은 것을 막는다
   *  (`MNX-VOC-0003`·`0004`) — 화면은 `can_edit` 를 보고 단추를 감출 뿐이다. */
  update: (id: string, payload: UpdateRequest) => api.patch<VocDetail>(`/voc/${id}`, payload),
  remove: (id: string) => api.delete<void>(`/voc/${id}`),
  /** 상태를 옮기거나(`status`) 말만 보탠다(`status` 없이). 갈 수 있는 곳은 상세의
   *  `allowed` 가 말한다 — 화면이 규칙을 외우지 않는다. */
  event: (id: string, payload: EventRequest) => api.post<VocDetail>(`/voc/${id}/events`, payload),
  /** 이력 한 줄을 지운다 — 시스템 관리자만(`can_delete_events`). 상태는 남은 이력에서
   *  다시 정해진다. */
  /** 이력 한 줄의 말을 고친다 — 시스템 관리자만. 상태 이동은 안 바뀐다. */
  updateEvent: (id: string, eventId: string, note: string) =>
    api.patch<VocDetail>(`/voc/${id}/events/${eventId}`, { note }),
  removeEvent: (id: string, eventId: string) =>
    api.delete<VocDetail>(`/voc/${id}/events/${eventId}`),
  /** 파일 하나를 붙인다. 여럿이면 차례로 — 하나가 커서 막혀도 나머지는 붙는다. */
  attach: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return api.postForm<VocDetail>(`/voc/${id}/attachments`, form)
  },
  detach: (id: string, attachmentId: string) =>
    api.delete<VocDetail>(`/voc/${id}/attachments/${attachmentId}`),
  /** 토큰이 있어야 열리므로 `<a href>` 가 아니라 받아서 넘긴다. */
  download: (attachment: VocAttachment) =>
    downloadFile(attachment.url.replace(/^\/api/, ''), attachment.filename),
  /** 고른 건들을 zip 하나로 — 건마다 폴더, `item.json` + `attachments/`. */
  exportZip: (ids: string[]) => {
    const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')
    return downloadPostFile('/voc/export', { ids }, `voc-export-${stamp}.zip`)
  },
}
