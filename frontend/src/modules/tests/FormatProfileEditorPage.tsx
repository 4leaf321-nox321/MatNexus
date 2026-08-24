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
 * 배치: **왼쪽은 정하는 곳, 오른쪽은 보는 곳.**
 *
 *   ① 파일          │  저장 상태 — 남은 것이 무엇인지
 *   ② 지문          │  파일 감지 결과 · 경고
 *   ③ 표 선택       │  이 파일에 적용해 본 결과
 *   ④ 열 매핑       │  (오른쪽은 sticky — 왼쪽을 내려도 따라온다)
 *   ⑤ 메타          │
 *   ⑥ 이름 붙여 저장 │
 *
 * 처음에는 전부 세로로 쌓았는데, 그러면 열 매핑을 고치고 결과를 보려고 매번
 * 스크롤해야 해서 **'고치고 → 확인' 이 한 화면에서 돌지 않았다.**
 *
 * 적용해 보기가 있는 이유: 자동 감지는 틀린다. 인코딩이 이중으로 깨진 파일도
 * "성공" 하는데 숫자는 멀쩡하고 글자만 깨지므로(실측), 값을 눈으로 보지 않으면
 * 알 수 없다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  FileUp,
  PlayCircle,
  Save,
  TriangleAlert,
  X,
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
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import { useAuth } from '@/shared/auth/AuthContext'
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
import { toChannelKey } from '@/modules/tests/keys'
import { DIMENSIONS, SI_BY_DIMENSION } from '@/shared/units'
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

/** 채널 드롭다운의 특수 항목. 채널 키와 겹치지 않게 접두어를 붙인다. */
const NEW_CHANNEL = '__new__'
const NEW_TYPE = '__new__'

/**
 * 이 화면에서 함께 만들 채널. **아직 저장되지 않았다.**
 *
 * 파일이 열 이름과 단위를 알려 주는데 사람이 다른 화면에서 그것을 손으로 다시
 * 적게 하는 것은 낭비다. 다만 **제안일 뿐이므로 고칠 수 있어야 한다** — 단위에서
 * 유추한 차원이 항상 맞지는 않는다(빈 단위 칸은 무차원으로 보이지만 장비가 그냥
 * 안 적었을 수도 있다).
 */
interface DraftChannel {
  key: string
  label: string
  dimension: string
  is_required: boolean
  /** 어느 열에서 왔나. 그 열의 매핑을 따라 지우려고 들고 있다. */
  from: string
}

export default function FormatProfileEditorPage() {
  const { key: routeKey } = useParams<{ key: string }>()
  const navigate = useNavigate()
  const creating = routeKey === undefined
  const { user } = useAuth()

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
  /**
   * 누구 것으로 만들지. **`null` 이면 전역이고 시스템 관리자만 할 수 있다.**
   *
   * 관리자 전용으로 두었더니 실무가 막혔다 — 장비는 부서마다 다른데 남의 부서
   * 파일을 어떻게 읽을지를 시스템 관리자가 알 리 없다. 그 지식은 사업부에 있다.
   */
  const [owner, setOwner] = useState<string | null>(null)
  const [extensions, setExtensions] = useState<string[]>([])
  const [headerAny, setHeaderAny] = useState<string[]>([])
  const [metaAny, setMetaAny] = useState<string[]>([])
  const [headerRows, setHeaderRows] = useState(1)
  const [tableMode, setTableMode] = useState<'first' | 'all'>('first')
  const [include, setInclude] = useState('')
  const [derived, setDerived] = useState('')
  const [columnMap, setColumnMap] = useState<Record<string, string>>({})
  const [metaMap, setMetaMap] = useState<Record<string, MetaRule>>({})
  const [drafts, setDrafts] = useState<DraftChannel[]>([])
  const [newType, setNewType] = useState<{ key: string; label: string; abbr: string } | null>(
    null
  )

  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<StructurePreview | null>(null)
  const [tried, setTried] = useState<ProfileTry | null>(null)
  const [busy, setBusy] = useState<'preview' | 'try' | 'save' | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  /** 규칙이 바뀌면 이전 시도 결과는 더 이상 그 규칙의 결과가 아니다. */
  useEffect(() => {
    setTried(null)
  }, [extensions, headerAny, metaAny, headerRows, tableMode, include, derived, columnMap, metaMap])

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
    setOwner(item.owner_workspace_slug)
    setExtensions(definition.match?.extensions ?? [])
    setHeaderAny(definition.match?.header_any ?? [])
    setMetaAny(definition.match?.meta_any ?? [])
    setHeaderRows(definition.reader?.header_rows ?? 1)
    setTableMode(definition.tables?.mode === 'all' ? 'all' : 'first')
    setInclude(definition.tables?.include ?? '')
    setDerived(definition.tables?.derived ?? '')
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

  /** 내가 관리자인 부서만. 아닌 부서 것으로 만들면 서버가 거절한다. */
  const managed = (user?.memberships ?? [])
    .filter((membership) => membership.role === 'manager')
    .map((membership) => ({
      slug: membership.slug,
      name: membership.name,
      path: membership.path,
      depth: membership.depth,
    }))

  /** 규칙에 걸리는 표. 정규식을 치는 동안 어느 표가 남는지 바로 보여 준다 —
   *  안 그러면 저장하고 파싱해 봐야 안다. */
  const classified = useMemo<{ table: TablePreview; kind: 'measured' | 'derived' | null }[]>(
    () => {
      const tables = preview?.tables ?? []
      let measured: RegExp | null = null
      let derivedPattern: RegExp | null = null
      try {
        measured = include ? new RegExp(include) : null
        derivedPattern = derived ? new RegExp(derived) : null
      } catch {
        return tables.map((table) => ({ table, kind: null })) // 아직 다 안 친 정규식
      }
      const rows = tables.map((table) => {
        const name = table.name ?? ''
        if (derivedPattern && name && derivedPattern.test(name)) {
          return { table, kind: 'derived' as const }
        }
        if (!measured || (name && measured.test(name))) {
          return { table, kind: 'measured' as const }
        }
        return { table, kind: null }
      })
      if (tableMode === 'first') {
        const first = rows.findIndex((row) => row.kind !== null)
        return rows.map((row, index) => (index === first ? row : { ...row, kind: null }))
      }
      return rows
    },
    [preview, include, derived, tableMode]
  )

  /** 열 매핑에 쓸 표 — **측정만.** 처리결과의 열(복소 컴플라이언스 등)까지 섞으면
   *  매핑 표가 두 배로 길어지는데, 그 열들은 대개 매핑할 채널이 없다. */
  const selectedTables = useMemo<TablePreview[]>(
    () => classified.filter((row) => row.kind === 'measured').map((row) => row.table),
    [classified]
  )

  /** 매핑해야 할 열. 고른 표들의 헤더 합집합 — `[step]` 마다 열 구성이 다른
   *  장비가 실재하므로(TA DMA850) 첫 표만 보면 안 된다. */
  const columns = useMemo(() => {
    type Info = { unit: string; sample: string; dimension: string | null }
    const seen = new Map<string, Info>()
    for (const table of selectedTables) {
      table.header.forEach((name, index) => {
        if (seen.has(name)) return
        seen.set(name, {
          unit: table.units[index] ?? '',
          sample: table.sample_rows[0]?.[index] ?? '',
          // 차원은 **서버가 알려 준다.** 단위 표를 여기에 복제하면 갈라진다.
          dimension: table.dimensions[index] ?? null,
        })
      })
    }
    // 저장된 프로파일에만 있고 이 파일에는 없는 열도 지우지 않고 보여 준다.
    for (const name of Object.keys(columnMap)) {
      if (!seen.has(name)) seen.set(name, { unit: '', sample: '', dimension: null })
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

  /**
   * 저장하려면 갖춰야 할 것. **비활성 버튼 옆에 이유가 없으면 고장으로 보인다.**
   *
   * 처음에는 "키·이름·시험 종류·지문·열 매핑이 하나씩은 있어야 합니다" 라는 한 줄만
   * 화면 맨 아래에 뒀는데, 그 문장은 *무엇이* 빠졌는지 말해 주지 않고 스크롤해야만
   * 보였다. 항목마다 어디를 봐야 하는지까지 적고, 오른쪽에 붙여 늘 보이게 한다.
   */
  const typeReady = newType
    ? Boolean(newType.key && newType.label && newType.abbr)
    : Boolean(form.test_type_key)

  const checklist: { ok: boolean; label: string; where: string }[] = [
    { ok: Boolean(file) || !creating, label: '장비 파일', where: '①' },
    { ok: hasFingerprint, label: '지문 — 확장자·헤더·메타 중 하나', where: '②' },
    { ok: typeReady, label: newType ? '새 시험 종류 (키·이름·약어)' : '시험 종류', where: '④' },
    { ok: mapped > 0, label: '열 매핑 한 개 이상', where: '④' },
    {
      ok: drafts.every((draft) => draft.key && draft.label),
      label: '새 채널의 키·이름',
      where: '④',
    },
    {
      ok: owner !== null || Boolean(user?.is_system_admin),
      label: '누구 것인지',
      where: '⑥',
    },
    { ok: Boolean(form.key), label: '키', where: '⑥' },
    { ok: Boolean(form.label), label: '이름', where: '⑥' },
    { ok: file === null || tried !== null, label: '적용해 보기', where: '오른쪽' },
  ]
  const remaining = checklist.filter((item) => !item.ok)

  /** 고를 수 있는 채널 = 시험 종류의 것 + 이 화면에서 만들 것. */
  const channelOptions = [
    ...(testType?.channels ?? []).map((channel) => ({
      key: channel.key,
      label: channel.label,
      hint: `${channel.key} · ${channel.si_unit}`,
      draft: false,
    })),
    ...drafts.map((draft) => ({
      key: draft.key,
      label: draft.label || draft.key,
      hint: `${draft.key} · 새로 만듦`,
      draft: true,
    })),
  ]

  /** 열 하나에서 새 채널을 제안한다. **파일이 이미 알려 준 것을 다시 묻지 않는다.** */
  function addDraft(column: { name: string; dimension: string | null }) {
    const base = toChannelKey(column.name)
    const taken = new Set([
      ...(testType?.channels ?? []).map((channel) => channel.key),
      ...drafts.map((draft) => draft.key),
    ])
    let key = base
    for (let suffix = 2; taken.has(key); suffix += 1) key = `${base}_${suffix}`

    setDrafts((current) => [
      ...current,
      {
        key,
        label: column.name || key,
        // 단위에서 유추한다. 모르면 무차원으로 두고 사람이 고른다 — 여기서
        // 아무거나 찍으면 잘못된 차원이 조용히 들어간다.
        dimension: column.dimension ?? 'dimensionless',
        is_required: false, // 필수로 두면 그 열이 없는 파일이 전부 실패한다
        from: column.name,
      },
    ])
    setColumnMap((current) => ({ ...current, [column.name]: key }))
  }

  function dropDraft(key: string) {
    setDrafts((current) => current.filter((draft) => draft.key !== key))
    setColumnMap((current) =>
      Object.fromEntries(
        Object.entries(current).map(([name, value]) => [name, value === key ? '' : value])
      )
    )
  }

  function patchDraft(index: number, change: Partial<DraftChannel>) {
    setDrafts((current) => {
      const next = current.map((draft, position) =>
        position === index ? { ...draft, ...change } : draft
      )
      // 키를 고치면 그 키를 쓰던 열의 매핑도 따라간다.
      const before = current[index]
      const after = next[index]
      if (before && after && before.key !== after.key) {
        setColumnMap((mapping) =>
          Object.fromEntries(
            Object.entries(mapping).map(([name, value]) => [
              name,
              value === before.key ? after.key : value,
            ])
          )
        )
      }
      return next
    })
  }

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
      tables: {
        mode: tableMode,
        ...(include ? { include } : {}),
        ...(derived ? { derived } : {}),
      },
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

  /**
   * 저장 순서: **시험 종류가 먼저다.** 프로파일이 종류를 가리키므로 없으면 거절당한다.
   *
   * 종류를 만들고 프로파일 저장이 실패하면 종류만 남는다. 되돌리지 않는 이유:
   * 그 종류는 '시험종류 정의' 화면에 그대로 보이고 거기서 고치거나 지울 수 있다.
   * 반쯤 만들어진 것을 자동으로 지우면 사람이 방금 채운 채널 정의가 사라진다 —
   * 남겨 두고 알려 주는 편이 낫다.
   */
  async function save() {
    setBusy('save')
    setError(null)
    try {
      const typeKey = await ensureTestType()

      const payload = {
        label: form.label,
        description: form.description || null,
        test_type_key: typeKey,
        definition: definition() as unknown as Record<string, unknown>,
        priority: form.priority,
        is_active: form.is_active,
      }
      if (creating) {
        await testsApi.createFormat({ ...payload, key: form.key, owner_workspace_slug: owner })
      }
      else await testsApi.updateFormat(form.key, payload)
      navigate('/settings/formats')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  /** 시험 종류를 만들거나, 새 채널을 기존 종류에 더한다. 종류 키를 돌려준다. */
  async function ensureTestType(): Promise<string> {
    const channels = drafts.map((draft, index) => ({
      key: draft.key,
      label: draft.label,
      dimension: draft.dimension,
      si_unit: SI_BY_DIMENSION[draft.dimension] ?? '1',
      is_required: draft.is_required,
      sort_order: ((testType?.channels.length ?? 0) + index) * 10,
    }))

    if (newType) {
      await testsApi.createType({
        key: newType.key,
        label: newType.label,
        abbr: newType.abbr,
        description: null,
        parser_key: null, // **파서 없이 프로파일로 읽는다** — 이 설계의 요점
        // 종류도 프로파일과 **같은 부서 것**으로 만든다. 여기가 막다른 길이었다:
        // 종류는 시스템 관리자만 만들 수 있어서, 부서 관리자가 열 20개를 다
        // 매핑하고 저장을 누르는 순간 403 이 났다(ADR 0006). 새 장비란 대개
        // 없는 종류를 재는 장비라 이 경로가 오히려 정상이다.
        owner_workspace_slug: owner,
        is_active: true,
        sort_order: 0,
        max_upload_bytes: null,
        channels,
        conditions: [],
      })
      return newType.key
    }

    if (channels.length && testType) {
      // 채널을 **더하는** 것은 기존 데이터의 해석을 바꾸지 않으므로 서버가 허용한다.
      // 기존 정의를 그대로 다시 보내야 한다 — 정의는 한 벌 통째로 갈아 끼운다.
      await testsApi.updateType(testType.key, {
        // 받은 리비전을 그대로 돌려보낸다 — ADR 0015.
        expected_revision: testType.revision,
        label: testType.label,
        abbr: testType.abbr,
        description: testType.description,
        parser_key: testType.parser_key,
        is_active: testType.is_active,
        sort_order: 0,
        // 위 주석대로 **그대로 다시 보낸다.** `null` 을 박으면 저장된 한도가 사라진다.
        max_upload_bytes: testType.max_upload_bytes,
        channels: [
          ...testType.channels.map((channel, index) => ({
            key: channel.key,
            label: channel.label,
            dimension: channel.dimension,
            si_unit: channel.si_unit,
            is_required: channel.is_required,
            sort_order: index * 10,
          })),
          ...channels,
        ],
        conditions: testType.conditions.map((field, index) => ({
          key: field.key,
          label: field.label,
          value_type: field.value_type,
          dimension: field.dimension,
          si_unit: field.si_unit,
          choices: field.choices,
          is_required: field.is_required,
          sort_order: index * 10,
        })),
      })
      types.reload()
    }
    return form.test_type_key
  }

  return (
    // 큰 화면에서는 **양쪽이 따로 스크롤한다.** 페이지 전체가 함께 굴러가면
    // 열 매핑을 고치는 동안 적용 결과가 화면 밖으로 나가고, 결과를 보려고
    // 내리면 이번엔 고칠 곳이 사라진다. 좁은 화면에서는 그냥 한 줄로 쌓인다 —
    // 칸을 둘로 나눌 폭이 없는데 높이까지 나누면 양쪽 다 못 읽는다.
    <div className="mx-auto flex max-w-7xl flex-col lg:h-full">
      <PageHeader
        title={creating ? '형식 프로파일 만들기' : `${form.label || routeKey} 편집`}
        description="장비 파일을 놓으면 구조는 자동으로 읽습니다. 사람이 정하는 것은 '이 열이 무엇인가' 하나뿐입니다 — 코드도 배포도 필요 없습니다."
        actions={
          <Button variant="ghost" onClick={() => navigate('/settings/formats')}>
            <ArrowLeft className="size-4" />
            목록
          </Button>
        }
      />

      <ErrorNotice error={types.error ?? existing.error ?? error} className="mb-4" />

      {!creating && !existing.loading && existing.data === null && (
        <Warning text={`'${routeKey}' 프로파일이 없습니다. 지워졌거나 주소가 틀렸습니다.`} />
      )}

      {/* 왼쪽은 정하는 곳, 오른쪽은 보는 곳. 각자 스크롤한다. */}
      <div className="grid gap-6 pb-6 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_400px] lg:pb-0">
        <div className="min-w-0 space-y-6 lg:min-h-0 lg:overflow-y-auto lg:pr-2 lg:pb-6">
          {/* ① 파일 ───────────────────────────────────────────── */}
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
          </Section>

          {/* ② 지문 ───────────────────────────────────────────── */}
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
                {[...new Set((preview?.tables ?? []).flatMap((table) => table.header))]
                  .filter(Boolean)
                  .map((name) => (
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
                  ))}
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

          {/* ③ 표 선택 ─────────────────────────────────────────── */}
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
              <div className="min-w-48 flex-1 space-y-1.5">
                <Label className="text-xs">측정 (정규식, 비우면 전부)</Label>
                <Input
                  className="h-8 font-mono text-xs"
                  value={include}
                  placeholder="^Temperature Sweep"
                  onChange={(event) => setInclude(event.target.value)}
                />
              </div>
              {/* **버리지도 섞지도 않는다.** 장비가 계산해 준 표(TTS 마스터 곡선)를
                  버리면 결과를 잃고, 측정과 섞으면 처리가 원본으로 착각한다. */}
              <div className="min-w-48 flex-1 space-y-1.5">
                <Label className="text-xs">처리결과 (장비가 계산해 준 것)</Label>
                <Input
                  className="h-8 font-mono text-xs"
                  value={derived}
                  placeholder="^TTS"
                  onChange={(event) => setDerived(event.target.value)}
                />
              </div>
            </div>

            {preview && (
              <div className="mt-3 space-y-1">
                {classified.map(({ table, kind }) => (
                  <div
                    key={table.index}
                    className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${
                      kind ? '' : 'opacity-40'
                    }`}
                  >
                    <Badge variant={kind === 'measured' ? 'secondary' : 'outline'}>
                      {kind === 'measured' ? '측정' : kind === 'derived' ? '처리결과' : '건너뜀'}
                    </Badge>
                    <span className="font-medium">{table.name ?? `표 ${table.index + 1}`}</span>
                    <span className="text-muted-foreground">
                      {table.row_count}행 × {table.column_count}열 · {table.first_line}줄부터
                    </span>
                  </div>
                ))}
                {classified.some((row) => row.kind === null) && (
                  <p className="text-muted-foreground text-xs">
                    건너뛴 표는 등록할 때 <b>경고로 남습니다</b> — 조용히 빠지면 &ldquo;왜
                    곡선이 이것뿐이지&rdquo; 가 됩니다. <b>장비가 계산해 준 표</b>라면
                    버리지 말고 위의 <b>처리결과</b>에 넣으세요.
                  </p>
                )}
              </div>
            )}
          </Section>

          {/* ④ 열 매핑 ─────────────────────────────────────────── */}
          <Section
            step="④"
            title="각 열이 무엇인가"
            hint="여기가 사람만 아는 부분입니다. 나머지는 전부 자동입니다."
          >
            <div className="mb-3 flex flex-wrap items-end gap-3">
              <div className="w-56 space-y-1.5">
                <Label className="text-xs">시험 종류</Label>
                <Select
                  value={newType ? NEW_TYPE : form.test_type_key}
                  onValueChange={(value) => {
                    // 종류가 바뀌면 이전 채널 키는 그 종류에 없다.
                    setColumnMap((current) =>
                      Object.fromEntries(Object.keys(current).map((name) => [name, '']))
                    )
                    setDrafts([])
                    if (value === NEW_TYPE) {
                      setNewType({ key: '', label: '', abbr: '' })
                      setForm((current) => ({ ...current, test_type_key: '' }))
                      return
                    }
                    setNewType(null)
                    setForm((current) => ({ ...current, test_type_key: value }))
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
                    <SelectItem value={NEW_TYPE}>+ 새 시험 종류 만들기</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* 헤더 줄 수는 **자동으로 못 정한다.** 아래 둘이 생김새가 같다.
                    ,,Tensile,Tensile   ← 그룹 머리. 버려도 되는 경우가 많다
                    Angular,Storage     ← 이름의 앞부분. 버리면 안 된다 */}
              <div className="w-32 space-y-1.5">
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

              {/* 새 종류를 만드는 길에서는 채널이 하나도 없다. 열마다 드롭다운을
                  여는 대신 한 번에 만들 수 있게 한다 — 열이 8~10개인 장비가 흔하다. */}
              {(testType || newType) && columns.length > 0 && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    for (const column of columns) {
                      if (columnMap[column.name]) continue
                      addDraft(column)
                    }
                  }}
                >
                  안 정한 열을 전부 새 채널로
                </Button>
              )}
            </div>

            {newType && (
              <div className="mb-3 rounded-md border border-dashed p-3">
                <p className="mb-2 text-xs font-medium">새 시험 종류</p>
                <div className="grid gap-2 sm:grid-cols-3">
                  <Input
                    className="h-8 font-mono text-xs"
                    placeholder="dma_sweep"
                    value={newType.key}
                    onChange={(event) =>
                      setNewType((current) =>
                        current ? { ...current, key: toChannelKey(event.target.value) } : current
                      )
                    }
                  />
                  <Input
                    className="h-8"
                    placeholder="DMA 스윕"
                    value={newType.label}
                    onChange={(event) =>
                      setNewType((current) =>
                        current ? { ...current, label: event.target.value } : current
                      )
                    }
                  />
                  <Input
                    className="h-8"
                    placeholder="약어 (DMA)"
                    value={newType.abbr}
                    onChange={(event) =>
                      setNewType((current) =>
                        current ? { ...current, abbr: event.target.value } : current
                      )
                    }
                  />
                </div>
                <p className="text-muted-foreground mt-2 text-xs">
                  약어는 시험 이름에 들어갑니다. <b>파서는 붙이지 않습니다</b> — 이
                  프로파일로 읽습니다. 저장할 때 종류가 먼저 만들어지고, 조건 항목은
                  나중에 <b>시험종류 정의</b>에서 더할 수 있습니다.
                </p>
              </div>
            )}

            {testType && (
              <p className="text-muted-foreground mb-2 text-xs">
                필수 채널:{' '}
                {testType.channels
                  .filter((channel) => channel.is_required)
                  .map((channel) => channel.key)
                  .join(', ') || '없음'}
              </p>
            )}

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
                    <TableHead className="w-56">우리 채널</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {columns.map((column) => (
                    <TableRow key={column.name}>
                      <TableCell className="text-sm">{column.name || '(이름 없음)'}</TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {column.unit || '—'}
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {column.sample || '—'}
                      </TableCell>
                      <TableCell>
                        <Select
                          value={columnMap[column.name] || 'none'}
                          onValueChange={(value) => {
                            if (value === NEW_CHANNEL) {
                              addDraft(column)
                              return
                            }
                            setColumnMap((current) => ({
                              ...current,
                              [column.name]: value === 'none' ? '' : value,
                            }))
                          }}
                        >
                          <SelectTrigger className="h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">— 안 정함</SelectItem>
                            {channelOptions.map((channel) => (
                              <SelectItem key={channel.key} value={channel.key}>
                                {channel.label}
                                <span className="text-muted-foreground ml-2 font-mono text-xs">
                                  {channel.hint}
                                </span>
                              </SelectItem>
                            ))}
                            {(testType || newType) && (
                              <SelectItem value={NEW_CHANNEL}>+ 새 채널로 만들기</SelectItem>
                            )}
                          </SelectContent>
                        </Select>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}

            {drafts.length > 0 && (
              <div className="mt-3 rounded-md border border-dashed p-3">
                <p className="mb-1 text-xs font-medium">
                  이 화면에서 함께 만들 채널 {drafts.length}개
                </p>
                <p className="text-muted-foreground mb-2 text-xs">
                  저장할 때 <b>{newType?.label || testType?.label}</b> 에 추가됩니다. 차원은
                  파일의 단위에서 유추한 <b>제안</b>입니다 — 단위 칸이 비어 있으면 무차원으로
                  두었으니 확인하세요.
                </p>
                <div className="space-y-1">
                  {drafts.map((draft, index) => (
                    <div key={draft.from} className="flex flex-wrap items-center gap-2">
                      <Input
                        className="h-8 w-40 font-mono text-xs"
                        value={draft.key}
                        onChange={(event) =>
                          patchDraft(index, { key: toChannelKey(event.target.value) })
                        }
                      />
                      <Input
                        className="h-8 w-40"
                        value={draft.label}
                        placeholder="이름"
                        onChange={(event) => patchDraft(index, { label: event.target.value })}
                      />
                      <Select
                        value={draft.dimension}
                        onValueChange={(value) => patchDraft(index, { dimension: value })}
                      >
                        <SelectTrigger className="h-8 w-40">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DIMENSIONS.map((dimension) => (
                            <SelectItem key={dimension} value={dimension}>
                              {dimension}
                              <span className="text-muted-foreground ml-2 font-mono text-xs">
                                {SI_BY_DIMENSION[dimension]}
                              </span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <label className="flex items-center gap-1 text-xs">
                        <input
                          type="checkbox"
                          checked={draft.is_required}
                          onChange={(event) =>
                            patchDraft(index, { is_required: event.target.checked })
                          }
                        />
                        필수
                      </label>
                      <Button size="sm" variant="ghost" onClick={() => dropDraft(draft.key)}>
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
                <p className="text-muted-foreground mt-2 text-xs">
                  <b>필수</b>로 두면 그 열이 없는 파일은 등록이 실패합니다. 기본은 꺼 둡니다 —
                  같은 장비라도 측정 항목이 매번 같지는 않습니다.
                </p>
              </div>
            )}

            <div className="text-muted-foreground mt-2 space-y-1 text-xs">
              <p>
                안 정한 열도 <b>버려지지 않습니다</b> — 열 이름을 그대로 키로 삼아 곡선에
                들어갑니다. 다만 정의된 채널이 아니므로 워크벤치나 통계에서는 잡히지
                않습니다.
              </p>
              <p>
                <b>채널로 정한 열은 단위를 알아야 합니다.</b> 파일에 단위 줄이 없거나 모르는
                단위면 등록이 실패합니다 — 원값을 SI 인 척 저장하면 201242 MPa 가 201242 Pa
                가 되어 10<sup>6</sup>배 틀리는데, 숫자는 멀쩡해 보이고 뜻만 바뀌어 아무도
                못 잡습니다.
              </p>
              <p>
                열 이름이 <code>modulus</code>·<code>frequency</code>처럼 잘려 보이면 헤더가
                여러 줄인 파일입니다. <b>헤더 줄 수</b>를 늘려 보세요.
              </p>
            </div>
          </Section>

          {/* ⑤ 메타 ───────────────────────────────────────────── */}
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
                    <div
                      key={name}
                      className="flex flex-wrap items-center gap-2 rounded-md border p-2"
                    >
                      <span className="w-40 truncate text-xs font-medium" title={name}>
                        {name}
                      </span>
                      <span
                        className="text-muted-foreground w-36 truncate font-mono text-xs"
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
                        <SelectTrigger className="h-8 w-40">
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
                          className="h-8 w-48 font-mono text-xs"
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

          {/* ⑥ 이름 ───────────────────────────────────────────── */}
          <Section
            step="⑥"
            title="이름 붙이기"
            hint="키는 나중에 못 바꿉니다. 지문이 겹치면 우선순위가 높은 쪽이 이깁니다."
          >
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="space-y-1.5">
                <Label className="text-xs">
                  키 {!form.key && <span className="text-destructive">*</span>}
                </Label>
                <Input
                  className="h-8 font-mono text-xs"
                  value={form.key}
                  disabled={!creating}
                  placeholder="ta_dma850"
                  onChange={(event) =>
                    setForm((current) => ({ ...current, key: event.target.value }))
                  }
                />
                <p className="text-muted-foreground text-xs">소문자·숫자·밑줄</p>
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label className="text-xs">
                  이름 {!form.label && <span className="text-destructive">*</span>}
                </Label>
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
              </div>
            </div>

            <div className="mt-3 space-y-1.5">
              <Label className="text-xs">누구 것인가</Label>
              {creating ? (
                <>
                  <WorkspacePicker
                    workspaces={managed}
                    value={owner}
                    onChange={setOwner}
                    placeholder={
                      user?.is_system_admin ? '전역 — 모든 부서가 씁니다' : '부서를 고르세요'
                    }
                    className="w-full"
                    emptyLabel="관리하는 부서가 없습니다"
                  />
                  <p className="text-muted-foreground text-xs">
                    {user?.is_system_admin
                      ? '비워 두면 전역입니다 — 모든 부서가 쓰고, 시스템 관리자만 고칠 수 있습니다.'
                      : '부서 관리자인 부서만 고를 수 있습니다. 전역은 시스템 관리자가 만듭니다.'}
                  </p>
                </>
              ) : (
                <p className="text-sm">
                  {existing.data?.is_global ? (
                    <>
                      <b>전역</b> — 모든 부서가 씁니다. 시스템 관리자만 고칠 수 있습니다.
                    </>
                  ) : (
                    <>
                      <b>{existing.data?.owner_workspace_name}</b> 소유
                    </>
                  )}
                </p>
              )}
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
          </Section>
        </div>

        {/* 오른쪽 — 보는 곳 ─────────────────────────────────────── */}
        <aside className="flex flex-col gap-4 lg:min-h-0 lg:overflow-hidden">
          <section className="shrink-0 rounded-md border p-4">
            <Button
              className="w-full"
              onClick={save}
              disabled={remaining.length > 0 || busy !== null}
            >
              <Save className="size-4" />
              {busy === 'save' ? '저장하는 중…' : '저장'}
            </Button>

            <ul className="mt-3 space-y-1">
              {checklist.map((item) => (
                <li
                  key={item.label}
                  className={`flex items-start gap-1.5 text-xs ${
                    item.ok ? 'text-muted-foreground' : ''
                  }`}
                >
                  {item.ok ? (
                    <Check className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
                  ) : (
                    <X className="text-destructive mt-0.5 size-3.5 shrink-0" />
                  )}
                  <span>
                    {item.label}
                    {!item.ok && (
                      <span className="text-muted-foreground ml-1">({item.where})</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {preview && (
            <section className="shrink-0 rounded-md border p-4">
              <p className="mb-2 text-sm font-medium">파일에서 읽은 것</p>
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
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
            </section>
          )}

          {/* 결과만 따로 굴린다 — 곡선이 6~10벌이면 이 카드가 아무리 길어져도
              버튼과 왼쪽 칸은 제자리에 있어야 한다. */}
          <section className="flex flex-col rounded-md border lg:min-h-0 lg:flex-1">
            <div className="shrink-0 border-b p-4">
              <p className="mb-1 text-sm font-medium">저장하기 전에 적용해 보기</p>
              <p className="text-muted-foreground mb-3 text-xs">
                자동 감지는 틀립니다. 인코딩이 깨진 파일도 &lsquo;성공&rsquo;하는데 숫자는
                멀쩡하고 글자만 깨지므로, <b>값을 눈으로 보지 않으면</b> 알 수 없습니다.
              </p>
              <Button
                className="w-full"
                variant="secondary"
                onClick={runTry}
                disabled={!file || busy !== null}
              >
                <PlayCircle className="size-4" />
                {busy === 'try' ? '적용하는 중…' : '이 파일에 적용해 보기'}
              </Button>
            </div>

            {!tried && (
              <p className="text-muted-foreground hidden items-center justify-center p-4 text-center text-xs lg:flex lg:min-h-0 lg:flex-1">
                {file
                  ? '아직 적용해 보지 않았습니다. 규칙을 고치면 이전 결과는 지워집니다.'
                  : '파일을 놓으면 여기에 결과가 나옵니다.'}
              </p>
            )}

            {tried && (
              <div className="space-y-3 p-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
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
                    <div className="flex flex-wrap items-center gap-1.5 border-b px-2 py-1.5 text-xs">
                      <span className="font-medium">{curve.label ?? curve.key}</span>
                      <span className="text-muted-foreground">{curve.row_count}행</span>
                    </div>
                    <div className="divide-y">
                      {curve.channels.map((channel) => (
                        <div key={channel.key} className="px-2 py-1.5 text-xs">
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="truncate">{channel.label ?? channel.key}</span>
                            <span className="text-muted-foreground shrink-0 font-mono">
                              {channel.source_unit ?? '—'} → {channel.si_unit}
                            </span>
                          </div>
                          <div className="text-muted-foreground font-mono">
                            {format(channel.first)} … {format(channel.last)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}

                {tried.summary.length > 0 && (
                  <div className="rounded-md border p-2">
                    <p className="mb-1 text-xs font-medium">요약값</p>
                    <div className="space-y-0.5">
                      {tried.summary.map((value) => (
                        <div key={value.key} className="flex justify-between gap-2 text-xs">
                          <span className="truncate">{value.label ?? value.key}</span>
                          <span className="shrink-0 font-mono">
                            {value.text ?? format(value.value)} {value.si_unit ?? ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {Object.keys(tried.metadata).length > 0 && (
                  <div className="rounded-md border p-2">
                    <p className="mb-1 text-xs font-medium">보관될 메타</p>
                    <div className="text-muted-foreground space-y-0.5 font-mono text-xs">
                      {Object.entries(tried.metadata).map(([key, value]) => (
                        <div key={key} className="truncate" title={`${key}=${value}`}>
                          {key}={value}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        </aside>
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
