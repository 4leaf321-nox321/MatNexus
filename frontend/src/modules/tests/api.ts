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
export type Detected = components['schemas']['DetectOut']
type TestTypeSave = components['schemas']['TestTypeSaveRequest']
type TestTypeCreate = components['schemas']['TestTypeCreateRequest']
export type TestChannelSave = TestTypeSave['channels'][number]
type CleanupRequest = components['schemas']['CleanupRequest']

export type FormatProfile = components['schemas']['FormatProfileOut']
export type StructurePreview = components['schemas']['StructurePreviewOut']
export type TablePreview = components['schemas']['TablePreviewOut']
export type ProfileTry = components['schemas']['ProfileTryOut']
type FormatSave = components['schemas']['FormatProfileSaveRequest']

/** 프로파일 규칙(v1). 서버는 `dict` 로 받으므로 생성 타입이 안 나온다 —
 *  `matcore/readers/profile.py` 의 문서화된 모양과 짝이다. */
export interface ProfileDefinition {
  reader?: {
    encoding?: string | null
    delimiter?: string | null
    /** 헤더가 몇 줄인가. 기계가 알 수 없어 사람이 정한다 — 그룹 머리와 나뉜
     *  이름은 생김새가 같다. */
    header_rows?: number
  }
  /** 지문. 이게 없으면 서버가 저장을 거절한다 — 모든 파일에 맞아 버린다. */
  match: { extensions?: string[]; header_any?: string[]; meta_any?: string[] }
  tables?: {
    mode?: 'first' | 'all'
    /** 측정으로 읽을 표. 비우면 전부 측정. */
    include?: string
    /** **장비가 계산해 준 표**(TTS 마스터 곡선 등). 버리지도 섞지도 않는다. */
    derived?: string
  }
  columns: Record<string, { channel: string; unit?: string }>
  summary?: Record<string, { key: string; unit?: string }>
  specimen?: Record<string, string>
  metadata?: string[]
}

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

  /**
   * 이 파일이 어느 시험 종류인가. 프로파일 지문 → 확장자 순으로 본다.
   *
   * **머리 조각만 보낸다.** 지문은 파일 앞쪽(메타·헤더)에 있고, 20개짜리 배치를
   * 통째로 두 번 올릴 이유가 없다. 앞이 잘려 못 알아보면 그냥 '못 정함' 이
   * 나오고 사람이 고르면 된다 — 틀리게 정하는 것보다 낫다.
   */
  detectType: (file: File, headBytes = 64 * 1024) => {
    const form = new FormData()
    form.set('file', file.slice(0, headBytes), file.name)
    return api.postForm<Detected>('/test-types/detect', form)
  },
  createType: (payload: TestTypeCreate) => api.post<TestType>('/test-types', payload),
  /** 정의 한 벌을 갈아 끼운다. 데이터가 있으면 서버가 key·단위 변경을 거절한다. */
  updateType: (key: string, payload: TestTypeSave) =>
    api.put<TestType>(`/test-types/${key}`, payload),
  removeType: (key: string) => api.delete<void>(`/test-types/${key}`),

  /** 형식 프로파일 — **장비마다 파서를 짜지 않으려고 만든 길**(ADR 0005). */
  formats: (testType?: string) => api.get<FormatProfile[]>(`/formats${search({ test_type: testType })}`),

  /** 파일을 **저장하지 않고** 구조만 읽는다. 아직 어느 시편의 것인지도 모른다. */
  previewFormat: (file: File, headerRows = 1) => {
    const form = new FormData()
    form.set('file', file)
    form.set('header_rows', String(headerRows))
    return api.postForm<StructurePreview>('/formats/preview', form)
  },

  /** 저장하기 **전에** 적용해 본다. 저장하고 나서 틀린 것을 아는 것과는 다르다. */
  tryFormat: (file: File, definition: ProfileDefinition) => {
    const form = new FormData()
    form.set('definition', JSON.stringify(definition))
    form.set('file', file)
    return api.postForm<ProfileTry>('/formats/try', form)
  },

  createFormat: (payload: FormatSave & { key: string }) =>
    api.post<FormatProfile>('/formats', payload),
  updateFormat: (key: string, payload: FormatSave) =>
    api.put<FormatProfile>(`/formats/${key}`, payload),
  removeFormat: (key: string) => api.delete<void>(`/formats/${key}`),

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
  curve: (
    id: string,
    options: { x?: string; y?: string; curve?: string; maxPoints?: number } = {}
  ) =>
    api.get<CurvePoints>(
      `/test-runs/${id}/curve${search({
        x: options.x,
        y: options.y,
        // 한 시험이 곡선을 여럿 가질 수 있다(DMA 의 `[step]`). 안 주면 첫 곡선.
        curve: options.curve,
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
