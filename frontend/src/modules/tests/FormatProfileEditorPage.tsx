/**
 * 형식 프로파일 만들기 — **파일을 보면서 만든다.**
 *
 * 이 화면이 ADR 0005 의 층 2다. 구조(인코딩·구분자·표·헤더·단위)는 서버가 자동으로
 * 읽어 온다. 사람이 하는 일은 하나뿐이다 — *"`Storage modulus` 가 우리의 어느
 * 채널인가"*. 그것만 정하면 새 장비가 붙는다. 코드도 배포도 없다.
 *
 * **운영 서버에서 실제 파일을 보며 만드는 것이 핵심이다.** 현장 파일이 개발자에게
 * 갈 필요가 없어지는 것이 이 방식의 값이고, 그러려면 JSON 을 손으로 적는 게 아니라
 * 파일을 놓고 표를 보며 고르는 화면이어야 한다.
 *
 * 화면 순서가 곧 판단 순서다.
 *
 *   ① 파일을 놓는다        → 서버가 구조를 읽어 온다 (저장하지 않는다)
 *   ② 무엇으로 알아볼지     → 지문. 없으면 서버가 저장을 거절한다
 *   ③ 어느 표를 쓸지        → `[step]` 이 여럿인 장비가 실재한다
 *   ④ 각 열이 무엇인지      → 사람만 아는 것
 *   ⑤ 메타를 어떻게 할지    → 시편 치수 / 요약값 / 그냥 보관 / 버림
 *   ⑥ 시도해 본다          → **저장 전에** 결과를 본다
 *
 * ⑥이 있는 이유: 자동 감지는 틀린다. 인코딩이 이중으로 깨진 파일도 "성공" 하는데
 * 숫자는 멀쩡하고 글자만 깨지므로(실측), 값을 눈으로 보지 않으면 알 수 없다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  CheckCircle2,
  FileUp,
  Fingerprint,
  PlayCircle,
  Save,
  TriangleAlert,
} from 'lucide-react'

import { testsApi } from '@/modules/tests/api'
import type {
  FormatProfile,
  ProfileDefinition,
  ProfileTry,
  StructurePreview,
  TablePreview,
  TestType,
} from '@/modules/tests/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

/** 메타 한 줄을 어떻게 할지. 기계는 못 가르는 판단이다 — `.tra` 의 요약부는
 *  구조적으로 메타와 똑같이 생겼는데, 하나는 **시험 결과**이고 하나는 **입력**이다. */
type MetaRole = 'keep' | 'specimen' | 'summary' | 'drop'

interface MetaRule {
  role: MetaRole
  target: string
}

/** 시편 치수로 자주 쓰는 키. 강제하지는 않는다 — 장비가 무엇을 주는지는 다양하다. */
const SPECIMEN_KEYS = [
  'specimen_thickness',
  'specimen_width',
  'gauge_length',
  'specimen_number',
  'specimen_diameter',
]

const META_ROLE_LABEL: Record<MetaRole, string> = {
  keep: '그대로 보관',
  specimen: '시편 치수',
  summary: '요약값(시험 결과)',
  drop: '버림',
}

export default function FormatProfileEditorPage() {
  const { key: routeKey } = useParams<{ key: string }>()
  const navigate = useNavigate()
  const creating = routeKey === undefined

  const types = useResource(() => testsApi.types(), [])
  const existing = useResource<FormatProfile | null>(
    () =>
      routeKey
        ? testsApi.formats().then((all) => all.find((item) => item.key === routeKey) ?? null)
        : Promise.resolve(null),
    [routeKey]
  )

  const [form, setForm] = useState({
    key: '',
    label: '',
    description: '',
    test_type_key: '',
    priority: 10,
    is_active: true,
  })
  const [extensions, setExtensions] = useState<string[]>([])
  const [headerAny, setHeaderAny] = useState<string[]>([])
  const [metaAny, setMetaAny] = useState<string[]>([])
  const [headerRows, setHeaderRows] = useState(1)
  const [tableMode, setTableMode] = useState<'first' | 'all'>('first')
  const [include, setInclude] = useState('')
  const [columnMap, setColumnMap] = useState<Record<string, string>>({})
  const [metaMap, setMetaMap] = useState<Record<string, MetaRule>>({})

  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<StructurePreview | null>(null)
  const [tried, setTried] = useState<ProfileTry | null>(null)
  const [busy, setBusy] = useState<'preview' | 'try' | 'save' | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  /** 규칙이 바뀌면 이전 시도 결과는 더 이상 그 규칙의 결과가 아니다. */
  useEffect(() => {
    setTried(null)
  }, [extensions, headerAny, metaAny, headerRows, tableMode, include, columnMap, metaMap])

  // 저장된 프로파일을 화면 상태로 편다. JSON 을 그대로 보여 주지 않는 이유:
  // 손으로 고치게 하면 결국 "JSON 을 아는 사람만 장비를 붙일 수 있다" 가 된다.
  useEffect(() => {
    const item = existing.data
    if (!item) return
    const definition = item.definition as unknown as ProfileDefinition
    setForm({
      key: item.key,
      label: item.label,
      description: item.description ?? '',
      test_type_key: item.test_type_key,
      priority: item.priority,
      is_active: item.is_active,
    })
    setExtensions(definition.match?.extensions ?? [])
    setHeaderAny(definition.match?.header_any ?? [])
    setMetaAny(definition.match?.meta_any ?? [])
    setHeaderRows(definition.reader?.header_rows ?? 1)
    setTableMode(definition.tables?.mode === 'all' ? 'all' : 'first')
    setInclude(definition.tables?.include ?? '')
    setColumnMap(
      Object.fromEntries(
        Object.entries(definition.columns ?? {}).map(([name, rule]) => [name, rule.channel])
      )
    )
    setMetaMap({
      ...Object.fromEntries(
        Object.entries(definition.specimen ?? {}).map(([name, target]) => [
          name,
          { role: 'specimen' as const, target },
        ])
      ),
      ...Object.fromEntries(
        Object.entries(definition.summary ?? {}).map(([name, rule]) => [
          name,
          { role: 'summary' as const, target: rule.key },
        ])
      ),
      ...Object.fromEntries(
        (definition.metadata ?? []).map((name) => [name, { role: 'keep' as const, target: '' }])
      ),
    })
  }, [existing.data])

  const testType = (types.data ?? []).find((item) => item.key === form.test_type_key) ?? null

  /** 규칙에 걸리는 표. 정규식을 치는 동안 어느 표가 남는지 바로 보여 준다 —
   *  안 그러면 저장하고 파싱해 봐야 안다. */
  const selectedTables = useMemo<TablePreview[]>(() => {
    const tables = preview?.tables ?? []
    let kept = tables
    if (include) {
      try {
        const pattern = new RegExp(include)
        kept = tables.filter((table) => table.name !== null && pattern.test(table.name))
      } catch {
        return [] // 아직 다 안 친 정규식
      }
    }
    return tableMode === 'first' ? kept.slice(0, 1) : kept
  }, [preview, include, tableMode])

  /** 매핑해야 할 열. 고른 표들의 헤더 합집합 — `[step]` 마다 열 구성이 다른
   *  장비가 실재하므로(TA DMA850) 첫 표만 보면 안 된다. */
  const columns = useMemo(() => {
    const seen = new Map<string, { unit: string; sample: string }>()
    for (const table of selectedTables) {
      table.header.forEach((name, index) => {
        if (seen.has(name)) return
        seen.set(name, {
          unit: table.units[index] ?? '',
          sample: table.sample_rows[0]?.[index] ?? '',
        })
      })
    }
    // 저장된 프로파일에만 있고 이 파일에는 없는 열도 지우지 않고 보여 준다.
    for (const name of Object.keys(columnMap)) {
      if (!seen.has(name)) seen.set(name, { unit: '', sample: '' })
    }
    return [...seen.entries()].map(([name, info]) => ({ name, ...info }))
  }, [selectedTables, columnMap])

  const metaRows = useMemo(() => {
    const rows = new Map<string, string>(preview?.meta.map(([k, v]) => [k, v]) ?? [])
    for (const name of Object.keys(metaMap)) if (!rows.has(name)) rows.set(name, '')
    return [...rows.entries()]
  }, [preview, metaMap])

  const hasFingerprint = extensions.length > 0 || headerAny.length > 0 || metaAny.length > 0
  const mapped = Object.values(columnMap).filter(Boolean).length

  function definition(): ProfileDefinition {
    const columnRules: ProfileDefinition['columns'] = {}
    for (const [name, channel] of Object.entries(columnMap)) {
      if (channel) columnRules[name] = { channel }
    }
    const specimen: Record<string, string> = {}
    const summary: Record<string, { key: string }> = {}
    const metadata: string[] = []
    for (const [name, rule] of Object.entries(metaMap)) {
      if (rule.role === 'specimen' && rule.target) specimen[name] = rule.target
      else if (rule.role === 'summary' && rule.target) summary[name] = { key: rule.target }
      else if (rule.role === 'keep') metadata.push(name)
    }
    return {
      ...(headerRows > 1 ? { reader: { header_rows: headerRows } } : {}),
      match: {
        ...(extensions.length ? { extensions } : {}),
        ...(headerAny.length ? { header_any: headerAny } : {}),
        ...(metaAny.length ? { meta_any: metaAny } : {}),
      },
      tables: { mode: tableMode, ...(include ? { include } : {}) },
      columns: columnRules,
      ...(Object.keys(specimen).length ? { specimen } : {}),
      ...(Object.keys(summary).length ? { summary } : {}),
      metadata,
    }
  }

  async function loadPreview(picked: File, rows = headerRows) {
    setBusy('preview')
    setError(null)
    setTried(null)
    try {
      const result = await testsApi.previewFormat(picked, rows)
      setFile(picked)
      setPreview(result)

      // 지문과 이름을 미리 채운다. 빈 화면에서 시작하면 무엇을 지문으로 삼아야
      // 좋은지 알기 어렵다 — 확장자는 파일이 알고, 헤더는 표가 알려 준다.
      if (creating) {
        const suffix = picked.name.includes('.')
          ? picked.name.slice(picked.name.lastIndexOf('.')).toLowerCase()
          : ''
        if (suffix) setExtensions([suffix])
        setForm((current) => ({ ...current, label: current.label || picked.name }))
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('파일을 읽지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  async function runTry() {
    if (!file) return
    setBusy('try')
    setError(null)
    try {
      setTried(await testsApi.tryFormat(file, definition()))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('적용해 보지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  async function save() {
    setBusy('save')
    setError(null)
    try {
      const payload = {
        label: form.label,
        description: form.description || null,
        test_type_key: form.test_type_key,
        definition: definition() as unknown as Record<string, unknown>,
        priority: form.priority,
        is_active: form.is_active,
      }
      if (creating) await testsApi.createFormat({ ...payload, key: form.key })
      else await testsApi.updateFormat(form.key, payload)
      navigate('/admin/formats')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  // 파일이 올라와 있으면 **시도해 보기를 통과해야 저장된다.** 저장 전에 값을
  // 확인하지 않으면 이 화면의 절반은 없는 것과 같다.
  const blocked =
    !form.key || !form.label || !form.test_type_key || !hasFingerprint || mapped === 0
  const needsTry = file !== null && tried === null

  return (
    <div className="mx-auto max-w-5xl pb-16">
      <PageHeader
        title={creating ? '형식 프로파일 만들기' : `${form.label || routeKey} 편집`}
        description="장비 파일을 놓으면 구조는 자동으로 읽습니다. 사람이 정하는 것은 '이 열이 무엇인가' 하나뿐입니다 — 코드도 배포도 필요 없습니다."
        actions={
          <Button variant="ghost" onClick={() => navigate('/admin/formats')}>
            <ArrowLeft className="size-4" />
            목록
          </Button>
        }
      />

      <ErrorNotice error={types.error ?? existing.error ?? error} className="mb-4" />

      {!creating && !existing.loading && existing.data === null && (
        <Warning text={`'${routeKey}' 프로파일이 없습니다. 지워졌거나 주소가 틀렸습니다.`} />
      )}

      <div className="space-y-6">
        {/* ① 파일 ─────────────────────────────────────────────── */}
        <Section
          step="①"
          title="장비 파일"
          hint="저장하지 않습니다. 구조만 읽어 봅니다 — 아직 어느 시편의 것인지도 모르니까요."
        >
          <div
            className="hover:border-primary/50 cursor-pointer rounded-md border border-dashed p-6 text-center"
            onClick={() => fileInput.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              const dropped = event.dataTransfer.files[0]
              if (dropped) void loadPreview(dropped)
            }}
          >
            <FileUp className="text-muted-foreground mx-auto mb-2 size-6" />
            <p className="text-sm">
              {busy === 'preview'
                ? '읽는 중…'
                : file
                  ? file.name
                  : '파일을 끌어다 놓거나 눌러서 고르세요'}
            </p>
            <input
              ref={fileInput}
              type="file"
              className="hidden"
              onChange={(event) => {
                const picked = event.target.files?.[0]
                if (picked) void loadPreview(picked)
              }}
            />
          </div>

          {preview && (
            <>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="secondary" className="font-mono">
                  {preview.encoding}
                </Badge>
                <Badge variant="secondary" className="font-mono">
                  구분자 {preview.delimiter === '\t' ? '탭' : preview.delimiter}
                </Badge>
                <Badge variant="outline">{preview.line_count}줄</Badge>
                <Badge variant="outline">표 {preview.tables.length}개</Badge>
                <Badge variant="outline">메타 {preview.meta.length}쌍</Badge>
              </div>

              {preview.warnings.map((warning) => (
                <Warning key={warning} text={warning} />
              ))}

              {preview.matched_profile && preview.matched_profile !== form.key && (
                <Warning
                  text={`이미 '${preview.matched_profile}' 프로파일이 이 파일을 잡습니다. 새로 만들 필요가 없을 수 있습니다.`}
                />
              )}
            </>
          )}
        </Section>

        {/* ② 지문 ─────────────────────────────────────────────── */}
        <Section
          step="②"
          title="무엇으로 이 형식을 알아볼까"
          hint="확장자만으로는 못 가릅니다 — .csv 는 어느 장비나 씁니다. 헤더의 열 이름이 장비를 가장 잘 나타냅니다."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <TokenField
              label="확장자"
              placeholder=".csv"
              values={extensions}
              onChange={setExtensions}
            />
            <TokenField
              label="메타 키가 있으면"
              placeholder="Instrument name"
              values={metaAny}
              onChange={setMetaAny}
              options={preview?.meta.map(([key]) => key) ?? []}
            />
          </div>

          <div className="mt-3">
            <Label className="text-xs">헤더에 이 열 이름이 있으면</Label>
            <p className="text-muted-foreground mb-2 text-xs">
              하나만 맞아도 이 프로파일로 봅니다. 그 장비에만 있는 이름을 고르세요.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {[...new Set((preview?.tables ?? []).flatMap((table) => table.header))].map(
                (name) => (
                  <button
                    key={name}
                    type="button"
                    className={`rounded-md border px-2 py-1 text-xs ${
                      headerAny.includes(name) ? 'bg-primary text-primary-foreground' : ''
                    }`}
                    onClick={() =>
                      setHeaderAny((current) =>
                        current.includes(name)
                          ? current.filter((item) => item !== name)
                          : [...current, name]
                      )
                    }
                  >
                    {name}
                  </button>
                )
              )}
              {!preview && (
                <span className="text-muted-foreground text-xs">파일을 먼저 놓으세요.</span>
              )}
            </div>
            {headerAny.length === 0 && metaAny.length === 0 && (
              <p className="text-muted-foreground mt-2 text-xs">
                헤더나 메타 지문 없이 확장자만 쓰면 <b>같은 확장자의 모든 파일</b>이 이
                규칙으로 읽힙니다.
              </p>
            )}
          </div>

          {!hasFingerprint && (
            <Warning text="지문이 하나도 없습니다. 이대로는 저장되지 않습니다 — 지문 없는 프로파일은 모든 파일에 맞아 다른 장비 파일까지 읽어 버립니다." />
          )}
        </Section>

        {/* ③ 표 선택 ───────────────────────────────────────────── */}
        <Section
          step="③"
          title="어느 표를 읽을까"
          hint="한 파일에 표가 여럿인 장비가 있습니다. TA DMA850 은 [step] 마다 별개 측정이라 이어 붙이면 서로 다른 온도의 곡선이 한 줄이 됩니다."
        >
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-40 space-y-1.5">
              <Label className="text-xs">범위</Label>
              <Select
                value={tableMode}
                onValueChange={(value) => setTableMode(value === 'all' ? 'all' : 'first')}
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="first">첫 표만</SelectItem>
                  <SelectItem value="all">맞는 표 전부 (곡선 여러 벌)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-56 flex-1 space-y-1.5">
              <Label className="text-xs">표 이름이 이것과 맞을 때만 (정규식, 비우면 전부)</Label>
              <Input
                className="h-8 font-mono text-xs"
                value={include}
                placeholder="^Temperature Sweep"
                onChange={(event) => setInclude(event.target.value)}
              />
            </div>
          </div>

          {preview && (
            <div className="mt-3 space-y-1">
              {preview.tables.map((table) => {
                const kept = selectedTables.includes(table)
                return (
                  <div
                    key={table.index}
                    className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${
                      kept ? '' : 'opacity-40'
                    }`}
                  >
                    <Badge variant={kept ? 'secondary' : 'outline'}>{kept ? '읽음' : '건너뜀'}</Badge>
                    <span className="font-medium">{table.name ?? `표 ${table.index + 1}`}</span>
                    <span className="text-muted-foreground">
                      {table.row_count}행 × {table.column_count}열 · {table.first_line}줄부터
                    </span>
                  </div>
                )
              })}
              {preview.tables.length > selectedTables.length && (
                <p className="text-muted-foreground text-xs">
                  건너뛴 표는 등록할 때 <b>경고로 남습니다</b> — 조용히 빠지면 &ldquo;왜 곡선이
                  이것뿐이지&rdquo; 가 됩니다.
                </p>
              )}
            </div>
          )}
        </Section>

        {/* ④ 열 매핑 ───────────────────────────────────────────── */}
        <Section
          step="④"
          title="각 열이 무엇인가"
          hint="여기가 사람만 아는 부분입니다. 나머지는 전부 자동입니다."
        >
          <div className="mb-3 flex flex-wrap items-end gap-3">
            <div className="w-56 space-y-1.5">
              <Label className="text-xs">시험 종류</Label>
              <Select
                value={form.test_type_key}
                onValueChange={(value) => {
                  // 종류가 바뀌면 이전 채널 키는 그 종류에 없다.
                  setForm((current) => ({ ...current, test_type_key: value }))
                  setColumnMap((current) =>
                    Object.fromEntries(Object.keys(current).map((name) => [name, '']))
                  )
                }}
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="고르세요" />
                </SelectTrigger>
                <SelectContent>
                  {(types.data ?? []).map((item: TestType) => (
                    <SelectItem key={item.key} value={item.key}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {/* 헤더 줄 수는 **자동으로 못 정한다.** 아래 둘이 생김새가 같다.
                  ,,Tensile,Tensile   ← 그룹 머리. 버려도 되는 경우가 많다
                  Angular,Storage     ← 이름의 앞부분. 버리면 안 된다
                열 이름이 잘려 보이면(`modulus`, `frequency`) 늘려 보게 한다. */}
            <div className="w-40 space-y-1.5">
              <Label className="text-xs">헤더 줄 수</Label>
              <Select
                value={String(headerRows)}
                onValueChange={(value) => {
                  const next = Number(value)
                  setHeaderRows(next)
                  if (file) void loadPreview(file, next)
                }}
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[1, 2, 3, 4, 5].map((count) => (
                    <SelectItem key={count} value={String(count)}>
                      {count}줄
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {testType && columns.length > 0 && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  setColumnMap((current) => ({
                    ...current,
                    ...autoMap(
                      columns.map((column) => column.name),
                      testType
                    ),
                  }))
                }
              >
                이름이 비슷한 것끼리 채우기
              </Button>
            )}
            {testType && (
              <span className="text-muted-foreground text-xs">
                필수 채널:{' '}
                {testType.channels
                  .filter((channel) => channel.is_required)
                  .map((channel) => channel.key)
                  .join(', ') || '없음'}
              </span>
            )}
          </div>

          {columns.length === 0 ? (
            <p className="text-muted-foreground rounded-md border py-6 text-center text-xs">
              파일을 놓으면 열이 나옵니다.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>파일의 열 이름</TableHead>
                  <TableHead>단위</TableHead>
                  <TableHead>첫 값</TableHead>
                  <TableHead className="w-64">우리 채널</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {columns.map((column) => (
                  <TableRow key={column.name}>
                    <TableCell className="text-sm">{column.name}</TableCell>
                    <TableCell className="text-muted-foreground font-mono text-xs">
                      {column.unit || '—'}
                    </TableCell>
                    <TableCell className="text-muted-foreground font-mono text-xs">
                      {column.sample || '—'}
                    </TableCell>
                    <TableCell>
                      <Select
                        value={columnMap[column.name] || 'none'}
                        onValueChange={(value) =>
                          setColumnMap((current) => ({
                            ...current,
                            [column.name]: value === 'none' ? '' : value,
                          }))
                        }
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">— 안 정함</SelectItem>
                          {(testType?.channels ?? []).map((channel) => (
                            <SelectItem key={channel.key} value={channel.key}>
                              {channel.label}
                              <span className="text-muted-foreground ml-2 font-mono text-xs">
                                {channel.key} · {channel.si_unit}
                              </span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          <div className="text-muted-foreground mt-2 space-y-1 text-xs">
            <p>
              안 정한 열도 <b>버려지지 않습니다</b> — 열 이름을 그대로 키로 삼아 곡선에
              들어갑니다. 다만 정의된 채널이 아니므로 워크벤치나 통계에서는 잡히지
              않습니다.
            </p>
            <p>
              <b>채널로 정한 열은 단위를 알아야 합니다.</b> 파일에 단위 줄이 없거나
              모르는 단위면 등록이 실패합니다 — 원값을 SI 인 척 저장하면 201242 MPa 가
              201242 Pa 가 되어 10<sup>6</sup>배 틀리는데, 숫자는 멀쩡해 보이고 뜻만
              바뀌어 아무도 못 잡습니다.
            </p>
            <p>
              열 이름이 <code>modulus</code>·<code>frequency</code>처럼 잘려 보이면 헤더가
              여러 줄인 파일입니다. 위의 <b>헤더 줄 수</b>를 늘려 보세요.
            </p>
          </div>
        </Section>

        {/* ⑤ 메타 ─────────────────────────────────────────────── */}
        <Section
          step="⑤"
          title="표 앞의 키-값을 어떻게 할까"
          hint="기계는 못 가릅니다. '최대하중 3466 N' 은 시험 결과이고 '두께 0.989 mm' 는 입력인데, 파일에서는 똑같이 생겼습니다."
        >
          {metaRows.length === 0 ? (
            <p className="text-muted-foreground rounded-md border py-6 text-center text-xs">
              파일을 놓으면 메타가 나옵니다.
            </p>
          ) : (
            <div className="space-y-1">
              {metaRows.map(([name, value]) => {
                const rule = metaMap[name] ?? { role: 'keep' as MetaRole, target: '' }
                return (
                  <div key={name} className="flex flex-wrap items-center gap-2 rounded-md border p-2">
                    <span className="w-44 truncate text-xs font-medium" title={name}>
                      {name}
                    </span>
                    <span
                      className="text-muted-foreground w-40 truncate font-mono text-xs"
                      title={value}
                    >
                      {value || '—'}
                    </span>
                    <Select
                      value={rule.role}
                      onValueChange={(next) =>
                        setMetaMap((current) => ({
                          ...current,
                          [name]: { ...rule, role: next as MetaRole },
                        }))
                      }
                    >
                      <SelectTrigger className="h-8 w-44">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(Object.keys(META_ROLE_LABEL) as MetaRole[]).map((role) => (
                          <SelectItem key={role} value={role}>
                            {META_ROLE_LABEL[role]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {(rule.role === 'specimen' || rule.role === 'summary') && (
                      <Input
                        className="h-8 w-52 font-mono text-xs"
                        list={rule.role === 'specimen' ? 'specimen-keys' : undefined}
                        placeholder={
                          rule.role === 'specimen' ? 'specimen_thickness' : 'tensile_strength'
                        }
                        value={rule.target}
                        onChange={(event) =>
                          setMetaMap((current) => ({
                            ...current,
                            [name]: { ...rule, target: event.target.value },
                          }))
                        }
                      />
                    )}
                  </div>
                )
              })}
              <datalist id="specimen-keys">
                {SPECIMEN_KEYS.map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </div>
          )}
        </Section>

        {/* ⑥ 시도 ─────────────────────────────────────────────── */}
        <Section
          step="⑥"
          title="저장하기 전에 적용해 본다"
          hint="자동 감지는 틀립니다. 인코딩이 깨진 파일도 '성공'하는데 숫자는 멀쩡하고 글자만 깨지므로, 값을 눈으로 보지 않으면 알 수 없습니다."
        >
          <Button onClick={runTry} disabled={!file || busy !== null}>
            <PlayCircle className="size-4" />
            {busy === 'try' ? '적용하는 중…' : '이 파일에 적용해 보기'}
          </Button>

          {tried && (
            <div className="mt-3 space-y-3">
              {tried.warnings.map((warning) => (
                <Warning key={warning} text={warning} />
              ))}

              <p className="flex items-center gap-1.5 text-sm">
                <CheckCircle2 className="size-4 text-emerald-600" />
                곡선 {tried.curves.length}벌
                {tried.summary.length > 0 && ` · 요약값 ${tried.summary.length}개`}
              </p>

              {tried.curves.map((curve) => (
                <div key={curve.key} className="rounded-md border">
                  <div className="flex items-center gap-2 border-b px-3 py-2 text-xs">
                    <span className="font-medium">{curve.label ?? curve.key}</span>
                    <Badge variant="outline" className="font-mono">
                      {curve.key}
                    </Badge>
                    <span className="text-muted-foreground">{curve.row_count}행</span>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>채널</TableHead>
                        <TableHead>파일 단위</TableHead>
                        <TableHead>저장 단위</TableHead>
                        <TableHead>첫 값</TableHead>
                        <TableHead>끝 값</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {curve.channels.map((channel) => (
                        <TableRow key={channel.key}>
                          <TableCell className="text-xs">
                            {channel.label ?? channel.key}
                            <span className="text-muted-foreground ml-2 font-mono">
                              {channel.key}
                            </span>
                          </TableCell>
                          <TableCell className="text-muted-foreground font-mono text-xs">
                            {channel.source_unit ?? '—'}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{channel.si_unit}</TableCell>
                          <TableCell className="font-mono text-xs">
                            {format(channel.first)}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {format(channel.last)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ))}

              {tried.summary.length > 0 && (
                <div className="rounded-md border p-3">
                  <p className="mb-2 text-xs font-medium">요약값</p>
                  <div className="flex flex-wrap gap-2">
                    {tried.summary.map((value) => (
                      <span key={value.key} className="rounded-md border px-2 py-1 text-xs">
                        {value.label ?? value.key}{' '}
                        <b className="font-mono">
                          {value.text ?? format(value.value)} {value.si_unit ?? ''}
                        </b>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {Object.keys(tried.metadata).length > 0 && (
                <div className="rounded-md border p-3">
                  <p className="mb-2 text-xs font-medium">보관될 메타</p>
                  <div className="text-muted-foreground flex flex-wrap gap-2 font-mono text-xs">
                    {Object.entries(tried.metadata).map(([key, value]) => (
                      <span key={key}>
                        {key}={value}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </Section>

        {/* 저장 ───────────────────────────────────────────────── */}
        <Section step={<Fingerprint className="size-4" />} title="이름 붙여 저장" hint="">
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="space-y-1.5">
              <Label className="text-xs">키</Label>
              <Input
                className="h-8 font-mono text-xs"
                value={form.key}
                disabled={!creating}
                placeholder="ta_dma850"
                onChange={(event) =>
                  setForm((current) => ({ ...current, key: event.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label className="text-xs">이름</Label>
              <Input
                className="h-8"
                value={form.label}
                placeholder="TA DMA850 CSV"
                onChange={(event) =>
                  setForm((current) => ({ ...current, label: event.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">우선순위</Label>
              <Input
                className="h-8"
                type="number"
                value={form.priority}
                onChange={(event) =>
                  setForm((current) => ({ ...current, priority: Number(event.target.value) }))
                }
              />
              <p className="text-muted-foreground text-xs">지문이 겹치면 높은 쪽이 이깁니다</p>
            </div>
          </div>

          <div className="mt-3 space-y-1.5">
            <Label className="text-xs">설명</Label>
            <Input
              className="h-8"
              value={form.description}
              placeholder="예: 소프트웨어 v2.3 이후 내보내기 형식"
              onChange={(event) =>
                setForm((current) => ({ ...current, description: event.target.value }))
              }
            />
          </div>

          <label className="mt-3 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) =>
                setForm((current) => ({ ...current, is_active: event.target.checked }))
              }
            />
            사용
            <span className="text-muted-foreground text-xs">
              끄면 지문이 맞아도 이 규칙을 쓰지 않습니다 — 지우지 않고 멈출 때
            </span>
          </label>

          <div className="mt-4 flex items-center gap-2">
            <Button onClick={save} disabled={blocked || needsTry || busy !== null}>
              <Save className="size-4" />
              {busy === 'save' ? '저장하는 중…' : '저장'}
            </Button>
            {needsTry && !blocked && (
              <span className="text-muted-foreground text-xs">
                ⑥에서 한 번 적용해 보고 저장하세요.
              </span>
            )}
            {blocked && (
              <span className="text-muted-foreground text-xs">
                키·이름·시험 종류·지문·열 매핑이 하나씩은 있어야 합니다.
              </span>
            )}
          </div>
        </Section>
      </div>
    </div>
  )
}

function Section({
  step,
  title,
  hint,
  children,
}: {
  step: ReactNode
  title: string
  hint: string
  children: ReactNode
}) {
  return (
    <section className="rounded-md border">
      <header className="border-b px-4 py-3">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <span className="text-muted-foreground">{step}</span>
          {title}
        </h2>
        {hint && <p className="text-muted-foreground mt-0.5 text-xs">{hint}</p>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  )
}

function Warning({ text }: { text: string }) {
  return (
    <p className="mt-2 flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-800 dark:text-amber-400">
      <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
      {text}
    </p>
  )
}

/** 쉼표·공백으로 여러 값을 받는 칸. */
function TokenField({
  label,
  placeholder,
  values,
  onChange,
  options,
}: {
  label: string
  placeholder: string
  values: string[]
  onChange: (next: string[]) => void
  options?: string[]
}) {
  const id = `token-${label}`
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input
        className="h-8 font-mono text-xs"
        list={options?.length ? id : undefined}
        placeholder={placeholder}
        value={values.join(', ')}
        onChange={(event) =>
          onChange(
            event.target.value
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean)
          )
        }
      />
      {options?.length ? (
        <datalist id={id}>
          {options.map((item) => (
            <option key={item} value={item} />
          ))}
        </datalist>
      ) : null}
    </div>
  )
}

/**
 * 이름이 비슷한 열을 채널에 붙여 본다. **제안일 뿐이다.**
 *
 * 자동 매핑을 저장까지 자동으로 하지 않는 이유: 반반 확률로 맞히는 것보다 한 번
 * 묻는 편이 낫다. **잘못 매핑된 곡선은 그럴듯해 보인다** — 축 이름이 맞으니 눈으로
 * 걸러지지 않는다.
 */
function autoMap(names: string[], type: TestType): Record<string, string> {
  const normalize = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, '')
  const channels = type.channels.map((channel) => ({
    key: channel.key,
    hints: [normalize(channel.key), normalize(channel.label)],
  }))

  const result: Record<string, string> = {}
  for (const name of names) {
    const target = normalize(name)
    const hit = channels.find((channel) =>
      channel.hints.some((hint) => hint === target || target.includes(hint))
    )
    result[name] = hit?.key ?? ''
  }
  return result
}

function format(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value !== 0 && (Math.abs(value) >= 1e5 || Math.abs(value) < 1e-3)) {
    return value.toExponential(4)
  }
  return String(Number(value.toFixed(6)))
}
