/** 시험 API — 정의 조회, 업로드, 곡선. */

import { api, downloadFile } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type TestType = components['schemas']['TestTypeOut']
export type TestChannel = components['schemas']['TestChannelOut']
export type TestConditionField = components['schemas']['TestConditionFieldOut']
export type TestRun = components['schemas']['TestRunOut']
export type TestRunDetail = components['schemas']['TestRunDetailOut']
export type TestRunPage = components['schemas']['Page_TestRunOut_']
export type CurvePoints = components['schemas']['CurvePointsOut']
export type StorageReport = components['schemas']['StorageReportOut']
export type Parser = components['schemas']['ParserOut']
type TestTypeSave = components['schemas']['TestTypeSaveRequest']
type TestTypeCreate = components['schemas']['TestTypeCreateRequest']
type CleanupRequest = components['schemas']['CleanupRequest']

export interface RunQuery extends Record<string, unknown> {
  /** 부서 slug. 좁히기만 한다 — 권한을 넓히지 않는다. */
  workspace?: string
  specimen_id?: string
  material_id?: string
  status?: 'uploaded' | 'parsing' | 'parsed' | 'failed'
  limit?: number
  offset?: number
}

function search(query: Record<string, unknown>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `?${text}` : ''
}

export interface UploadInput {
  specimenId: string
  testType: string
  file: File
  conditions?: Record<string, unknown>
  /** 조건 키 → 화면이 받은 단위. 값과 함께 보내야 서버가 올바로 환산한다. */
  conditionUnits?: Record<string, string>
  operator?: string
  instrument?: string
  note?: string
}

export const testsApi = {
  types: () => api.get<TestType[]>('/test-types'),

  /** 등록된 파서. **파서는 정의로 만들 수 없다 — 코드다.** */
  parsers: () => api.get<Parser[]>('/test-types/parsers'),
  createType: (payload: TestTypeCreate) => api.post<TestType>('/test-types', payload),
  /** 정의 한 벌을 갈아 끼운다. 데이터가 있으면 서버가 key·단위 변경을 거절한다. */
  updateType: (key: string, payload: TestTypeSave) =>
    api.put<TestType>(`/test-types/${key}`, payload),
  removeType: (key: string) => api.delete<void>(`/test-types/${key}`),

  /** 저장소 현황. 폴더를 훑는 정도라 요청 안에서 끝난다. */
  storage: () => api.get<StorageReport>('/maintenance/storage'),
  /** 정리는 워커가 한다 — 파일이 많으면 오래 걸린다. */
  cleanup: (payload: CleanupRequest) =>
    api.post<{ status: string; message: string; dry_run: boolean }>(
      '/maintenance/cleanup',
      payload
    ),

  runs: (query: RunQuery = {}) => api.get<TestRunPage>(`/test-runs${search(query)}`),
  run: (id: string) => api.get<TestRunDetail>(`/test-runs/${id}`),
  remove: (id: string) => api.delete<void>(`/test-runs/${id}`),
  reparse: (id: string) => api.post<{ status: string; message: string }>(`/test-runs/${id}/reparse`),

  /** 축약된 점들. 서버가 LTTB 로 줄여 주므로 전부 받지 않는다. */
  curve: (id: string, options: { x?: string; y?: string; maxPoints?: number } = {}) =>
    api.get<CurvePoints>(
      `/test-runs/${id}/curve${search({
        x: options.x,
        y: options.y,
        max_points: options.maxPoints,
      })}`
    ),

  /** 원본 내려받기. 파서가 못 읽었을 때 사람이 열어 봐야 한다.
   *  평범한 링크로는 토큰이 안 실려 401 이 난다 — `downloadFile` 이 붙여 준다. */
  downloadSource: (id: string, filename: string) =>
    downloadFile(`/test-runs/${id}/source`, filename),

  upload: ({
    specimenId,
    testType,
    file,
    conditions,
    conditionUnits,
    operator,
    instrument,
    note,
  }: UploadInput) => {
    const form = new FormData()
    form.set('specimen_id', specimenId)
    form.set('test_type', testType)
    form.set('conditions', JSON.stringify(conditions ?? {}))
    form.set('condition_units', JSON.stringify(conditionUnits ?? {}))
    if (operator) form.set('operator', operator)
    if (instrument) form.set('instrument', instrument)
    if (note) form.set('note', note)
    form.set('file', file)
    return api.postForm<TestRun>('/test-runs', form)
  },
}

/** 상태 → 사람이 읽는 말. 화면마다 다르게 부르면 같은 상태가 달라 보인다. */
export const RUN_STATUS_LABEL: Record<string, string> = {
  uploaded: '대기',
  parsing: '읽는 중',
  parsed: '완료',
  failed: '실패',
}

/** 아직 끝나지 않은 상태. 목록이 스스로 갱신할지 판단하는 데 쓴다. */
export function isPending(status: string): boolean {
  return status === 'uploaded' || status === 'parsing'
}
