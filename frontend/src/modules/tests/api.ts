/** 시험 API — 정의 조회, 업로드, 곡선. */

import { api, downloadFile } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type TestType = components['schemas']['TestTypeOut']
export type TestChannel = components['schemas']['TestChannelOut']
export type TestConditionField = components['schemas']['TestConditionFieldOut']
export type TestRun = components['schemas']['TestRunOut']
export type RunFacets = components['schemas']['RunFacetsOut']
export type RunDeleteResult = components['schemas']['RunDeleteOut']
/** 표로 넣은 결과. **미리보기와 실제가 같은 모양이다** — 서버가 같은 코드로 답한다. */
export type SummaryImport = components['schemas']['SummaryImportOut']
type SummaryImportRequest = components['schemas']['SummaryImportRequest']
export type TestRunDetail = components['schemas']['TestRunDetailOut']
export type TestRunPage = components['schemas']['Page_TestRunOut_']
export type CurvePoints = components['schemas']['CurvePointsOut']
export type StorageReport = components['schemas']['StorageReportOut']
export type Parser = components['schemas']['ParserOut']
export type Detected = components['schemas']['DetectOut']
export type InstrumentDimensions = components['schemas']['InstrumentDimensionsOut']
export type AppliedDimensions = components['schemas']['AppliedDimensionsOut']
type TestTypeUpdate = components['schemas']['TestTypeUpdateRequest']
type TestTypeCreate = components['schemas']['TestTypeCreateRequest']
export type TestChannelSave = TestTypeCreate['channels'][number]
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
  /** 열 규칙. **셋이 한 벌이다.**
   *
   *  `channel` 은 없을 수 있다 — 저장된 정의에 `{"skip": true}` 만 든 규칙이
   *  있다(옛 앱 파일의 행 번호 열). `string` 이라고 단언해 두었더니 불러오기가
   *  그 `undefined` 를 그대로 읽어 규칙을 통째로 잃었다.
   *
   *  `unit` 은 **파일이 준 단위를 이긴다**(`profile.py`). 그래서 파일에서 본
   *  값을 여기에 미리 굳히지 않는다 — 같은 열이 파일에 따라 단위를 달고도
   *  안 달고도 온다. */
  columns: Record<string, { channel?: string; unit?: string; skip?: boolean }>
  summary?: Record<string, { key: string; unit?: string }>
  /** 시편 치수. 글자면 키만 정한 것이고(값에 단위가 붙어 오는 파일),
   *  dict 면 단위까지 정한 것이다 — **단위가 열 이름 안에만 있는 파일**이 있다
   *  (`Specimen thickness a0 (mm)` 옆의 값은 `0.986` 뿐이다). 단위를 안 적으면
   *  치수가 조용히 안 채워진다. */
  specimen?: Record<string, string | { key: string; unit?: string }>
  /** 이 메타를 **시험 기록의 칸에 채운다.** 빈 칸일 때만 들어간다.
   *  칸 이름의 정본은 서버의 `RECORD_FIELDS` 다. */
  record?: Record<string, { field: string; format?: string }>
  /** 이 메타가 **어느 재료·시료·시편의 것인지** 짚는다. 채우지는 않는다 —
   *  잘못 붙은 곡선은 칸을 고쳐 되돌릴 수 없다.
   *  칸 이름의 정본은 서버의 `IDENTITY_FIELDS` 다. */
  identity?: Record<string, { field: string }>
  /** 이 메타를 **시험 조건**에 채운다. 빈 칸일 때만.
   *
   *  칸 이름은 **시험 종류가 선언한다**(`TestType.conditions`) — 인장은 속도·
   *  예하중이고 DMA 는 진폭이라 고정 목록이 없다.
   *
   *  `unit` 은 **파일에 적힌 단위**다. 안 적으면 값에 붙어 온 것을 쓰고, 그것도
   *  없으면 정의의 SI 로 해석된다 — 정의가 `m/s` 인데 파일이 `mm/min` 이면
   *  6만 배 어긋나므로 적어 두는 편이 안전하다. */
  conditions?: Record<string, { field: string; unit?: string }>
  /** 이 메타를 **이관이 재료를 만들 때** 적는다. 올릴 때는 안 쓴다.
   *
   *  올릴 때도 쓰면 재료 아래 시험 100건이 같은 칸을 저마다 한 번씩 덮어쓰고,
   *  그중 하나만 옛 값이어도 카드와 덱이 조용히 바뀐다. 시편 치수는 시험 하나가
   *  시편 하나를 보므로 「빈 칸만 채운다」 로 막을 수 있었지만 재료는 못 막는다.
   *
   *  `unit` 은 **두께·밀도에 반드시 적는다** — 안 적으면 이관이 mm · tonne/mm3
   *  로 읽고, m 로 적어 온 파일에서 그것은 1000배다.
   *  칸 이름의 정본은 서버의 `MATERIAL_FIELDS` 다. */
  material?: Record<string, { field: string; unit?: string; format?: string }>
  /** 이 메타를 **이관이 시료를 만들 때** 적는다. 쓰이는 자리는 재료와 같다.
   *  칸 이름의 정본은 서버의 `SAMPLE_FIELDS` 다. */
  sample?: Record<string, { field: string; unit?: string; format?: string }>
  /** 이 메타를 **이관이 시편을 만들 때** 적는다 — 규격·메모.
   *
   *  치수(`specimen`)와 다르다. 그쪽은 이 시험이 **잰 값**이고 이쪽은 그 시편의
   *  **성질**이다. 규격이 특히 중요하다 — 규격이 치수 칸을 정한다(ADR 0010). */
  specimen_props?: Record<string, { field: string }>
  metadata?: string[]
}

/** 여럿을 한 번에 고칠 수 있는 칸. **서버의 `EDITABLE_FIELDS` 가 정본이다.** */
export type BulkUpdateField =
  components['schemas']['RunBulkUpdateRequest']['field']
export type BulkUpdateResult = components['schemas']['RunBulkUpdateOut']

export type ReparseResult = components['schemas']['ReparseOut']
export type RetypeResult = components['schemas']['RetypeOut']

export interface RunQuery extends Record<string, unknown> {
  /** 부서 slug. 좁히기만 한다 — 권한을 넓히지 않는다. */
  workspace?: string
  specimen_id?: string
  material_id?: string
  status?: 'uploaded' | 'parsing' | 'parsed' | 'failed'
  /**
   * 채택된 처리 결과가 있는가. **"올렸는데 아직 아무것도 안 한 것"** 을 세려면
   * `false`. 목록을 받아 화면이 세면 상한에 걸린 순간 숫자가 조용히 틀린다.
   */
  adopted?: boolean
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
  /** 어느 사업부가 낸 시험인가. 부서(권한)와 다른 축이다. */
  division?: string
  note?: string
}

export const testsApi = {
  /**
   * 표로 시험을 넣는다. **한 줄이 시험 하나이고 곡선은 없다.**
   *
   * `dry` 면 아무것도 안 쓰고 어떻게 들어갈지만 답한다 — 미리보기와 실제가
   * 같은 코드로 답해야 어긋나지 않는다.
   */
  importSummaries: (
    payload: Omit<SummaryImportRequest, 'create_missing'>,
    { dry, createMissing }: { dry: boolean; createMissing: boolean }
  ) =>
    api.post<SummaryImport>(`/test-runs/import${dry ? '/preview' : ''}`, {
      ...payload,
      create_missing: createMissing,
    }),

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
  /**
   * 정의 한 벌을 갈아 끼운다. **`expected_revision` 을 함께 보내야 한다**
   * (ADR 0015) — 열었을 때 받은 `revision` 을 그대로 넣는다.
   *
   * 그사이 남이 고쳤으면 서버가 409 로 막는다. 안 막으면 **덮는 것이 아니라
   * 자식까지 통째로 지운다.**
   */
  updateType: (key: string, payload: TestTypeUpdate) =>
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

  createFormat: (payload: FormatSave & { key: string; owner_workspace_slug: string | null }) =>
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

  /**
   * 여러 건을 한 번에 지운다. **한 건이 막혀도 나머지는 지운다** —
   * 20건을 골랐는데 하나가 권한 밖이라 전부 실패하면, 어느 것이 문제인지
   * 모른 채 다시 골라야 한다.
   */
  removeMany: (runIds: string[]) =>
    api.post<RunDeleteResult>('/test-runs/delete', { run_ids: runIds }),

  /**
   * 고른 시험의 **칸 하나**를 같은 값으로 맞춘다.
   *
   * 고칠 수 있는 칸은 서버가 정한다 — 이름을 만드는 값과 처리 흐름이 쓰는
   * 값은 아예 안 받는다.
   */
  bulkUpdate: (runIds: string[], field: BulkUpdateField, value: string) =>
    api.post<BulkUpdateResult>('/test-runs/bulk-update', {
      run_ids: runIds,
      field,
      // 빈 칸은 「지운다」 는 뜻이다. 서버가 빈 문자열과 null 을 같게 본다.
      value: value.trim() || null,
    }),

  /** 무엇으로 거를 수 있고 각각 몇 건인가. **화면이 한 쪽에서 세지 않는다.** */
  runFacets: (workspace?: string) =>
    api.get<RunFacets>(`/test-runs/facets${workspace ? `?workspace=${workspace}` : ''}`),
  /** 장비 파일이 준 시편 치수와, 시편에 지금 들어 있는 값. */
  instrumentDimensions: (id: string) =>
    api.get<InstrumentDimensions>(`/test-runs/${id}/instrument-dimensions`),

  /** 빈 칸만 채운다. 덮어쓰려면 `overwrite`. */
  applyInstrumentDimensions: (id: string, overwrite = false) =>
    api.post<AppliedDimensions>(
      `/test-runs/${id}/apply-instrument-dimensions?overwrite=${overwrite}`,
      {}
    ),

  /**
   * 다시 읽는다. **형식을 고를 수 있다.**
   *
   *   `undefined`  지금 정해진 대로 — 그냥 다시 읽기
   *   `null`       고정을 푼다(자동으로 고르게)
   *   `'키'`       그것으로 읽는다
   *
   * 안 보낸 것과 비운 것을 구별하지 않으면 **그냥 다시 읽을 때마다 고정이
   * 풀린다** — 사람은 골라 뒀는데 다음 사람이 누르는 순간 자동으로 돌아간다.
   */
  /**
   * 올릴 때 잘못 고른 **시험 종류를 바로잡는다.** 이름도 함께 바뀐다.
   *
   * 아직 아무것도 안 나온 시험만 된다 — 곡선도 처리 결과도 없는 것. 이미
   * 읽힌 시험은 서버가 막는다(409).
   */
  retype: (id: string, testTypeKey: string) =>
    api.post<RetypeResult>(`/test-runs/${id}/test-type`, { test_type_key: testTypeKey }),

  reparse: (id: string, profileKey?: string | null) =>
    api.post<ReparseResult>(
      `/test-runs/${id}/reparse`,
      profileKey === undefined ? {} : { profile_key: profileKey }
    ),

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
    division,
    note,
  }: UploadInput) => {
    const form = new FormData()
    form.set('specimen_id', specimenId)
    form.set('test_type', testType)
    form.set('conditions', JSON.stringify(conditions ?? {}))
    form.set('condition_units', JSON.stringify(conditionUnits ?? {}))
    if (operator) form.set('operator', operator)
    if (instrument) form.set('instrument', instrument)
    if (division) form.set('division', division)
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
