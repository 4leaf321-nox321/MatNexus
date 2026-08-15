/**
 * 일괄 등록 — 파일 여러 개를 한 번에.
 *
 * **한 배치에 서로 다른 재료·시료·시험종류가 섞인다.** 실제로 그렇게 올린다고
 * 확인했다. 그래서 "이 배치는 이 시편의 것" 이라고 통째로 정하는 마법사가 아니라,
 * **파일마다 한 줄인 표**로 만든다. 줄마다 다른 재료를 가리킬 수 있어야 한다.
 *
 * 대신 줄마다 손으로 고르게 하면 열 줄부터 일이 된다. 그래서 확장자로 종류를
 * 추정하고, 선택한 줄에 일괄 지정한다.
 *
 * 서버에는 배치 개념을 두지 않는다. 줄마다 기존 업로드 API 를 한 번씩 부른다 —
 * 배치 테이블을 만들면 "절반만 올라간 배치" 라는 상태를 누군가 관리해야 하는데,
 * 그 상태는 이 표가 이미 눈앞에 보여 주고 있다. 실패한 줄만 다시 누르면 된다.
 *
 * 적대적 리뷰가 잡아낸 것들을 여기서 막는다. 전부 **조용히 잘못되는** 부류였다.
 *
 *   - 올리는 도중 줄을 고치면, 루프는 시작 시점 스냅샷을 읽으므로 화면과 다른
 *     시편에 붙는데 표시는 '올림' 이 된다 → 도는 동안 편집을 잠근다.
 *   - 새로 만든 시편 id 를 줄에 되돌려 쓰지 않으면, 실패 후 다시 누를 때마다
 *     시험 없는 빈 시편이 하나씩 더 생긴다 → 만들자마자 줄에 기록한다.
 *   - 시료 일괄 지정이 재료를 안 보면, 재료 B 파일이 재료 A 의 시료에 붙고
 *     화면은 끝까지 B 라고 보여 준다 → 선택한 줄의 재료가 같을 때만 허용한다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FileUp,
  Loader2,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { Material, Sample, Specimen } from '@/modules/materials/api'
import { testsApi } from '@/modules/tests/api'
import type { TestType } from '@/modules/tests/api'
import { conditionUnits, display } from '@/modules/tests/units'
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

const ORIENTATIONS = ['MD', 'TD', 'DD', 'NA'] as const
/** 이방성 세트. 한 시료에서 세 방향을 뜨는 것이 인장의 기본 작업이다. */
const ANISOTROPY_SET = ['MD', 'TD', 'DD'] as const

type RowStatus = 'incomplete' | 'uploading' | 'done' | 'error'

interface Row {
  key: string
  file: File
  selected: boolean
  typeKey: string | null
  materialId: string | null
  sampleId: string | null
  /** 기존 시편 id 이거나, `new:<방향>` 이면 올릴 때 새로 만든다. */
  specimen: string | null
  status: RowStatus
  message?: string
}

function extensionOf(name: string): string {
  const index = name.lastIndexOf('.')
  // 대소문자를 맞춘다 — 디스크에 .tra 와 .TRA 가 함께 있는 것을 실측했다.
  return index < 0 ? '' : name.slice(index).toLowerCase()
}

function guessType(file: File, types: TestType[]): string | null {
  const extension = extensionOf(file.name)
  const matches = types.filter((type) => type.extensions.includes(extension))
  // 두 종류가 같은 확장자를 선언하면 자동으로 고르지 않는다. 반반 확률로 맞히는
  // 것보다 사람에게 묻는 편이 낫다 — 잘못 고르면 파싱이 조용히 성공할 수 있다.
  return matches.length === 1 ? matches[0].key : null
}

function isReady(row: Row): boolean {
  return Boolean(row.typeKey && row.materialId && row.sampleId && row.specimen)
}

export default function BatchUploadPage() {
  const { slug } = useParams<{ slug?: string }>()
  const navigate = useNavigate()
  const types = useResource(() => testsApi.types(), [])

  const [rows, setRows] = useState<Row[]>([])
  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const materials = useResource(() => materialsApi.list({ q: applied, limit: 200 }), [applied])

  const [sampleCache, setSampleCache] = useState<Record<string, Sample[]>>({})
  const [specimenCache, setSpecimenCache] = useState<Record<string, Specimen[]>>({})
  const [conditions, setConditions] = useState<Record<string, Record<string, string>>>({})
  const [running, setRunning] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  // `?? []` 를 그대로 두면 매 렌더마다 새 배열이라 아래 훅들이 계속 돈다.
  const availableTypes = useMemo(() => types.data ?? [], [types.data])
  const found = useMemo(() => materials.data?.items ?? [], [materials.data])
  const total = materials.data?.total ?? 0

  /**
   * 한 번이라도 본 재료를 모아 둔다. 검색으로 목록이 좁아져도 **이미 고른 재료가
   * 줄의 Select 에서 사라지면 안 되기 때문**이다 — Radix Select 는 값에 맞는
   * 항목이 없으면 트리거를 비워 버려서, 상태에는 값이 있는데 화면은 빈칸이 된다.
   */
  const [known, setKnown] = useState<Record<string, Material>>({})
  useEffect(() => {
    if (found.length === 0) return
    setKnown((current) => {
      const next = { ...current }
      for (const material of found) next[material.id] = material
      return next
    })
  }, [found])

  const selected = rows.filter((row) => row.selected && row.status !== 'done')
  const ready = rows.filter((row) => isReady(row) && row.status !== 'done')

  /** 선택한 줄의 재료가 모두 같을 때만 시료를 일괄 지정할 수 있다. */
  const commonMaterial = useMemo(() => {
    const ids = new Set(selected.map((row) => row.materialId))
    return ids.size === 1 ? ([...ids][0] ?? null) : null
  }, [selected])

  function addFiles(files: FileList | null) {
    if (!files?.length) return
    setRows((current) => [
      ...current,
      ...Array.from(files).map((file, index) => ({
        // 같은 파일을 두 번 담아도 키가 겹치지 않게 담은 시각을 섞는다.
        key: `${file.name}-${file.size}-${current.length + index}-${performance.now()}`,
        file,
        selected: true,
        typeKey: guessType(file, availableTypes),
        materialId: null,
        sampleId: null,
        specimen: null,
        status: 'incomplete' as RowStatus,
      })),
    ])
  }

  // 종류 정의가 늦게 도착하면 이미 담긴 파일도 다시 추정해 준다.
  useEffect(() => {
    if (availableTypes.length === 0) return
    setRows((current) =>
      current.map((row) =>
        row.typeKey ? row : { ...row, typeKey: guessType(row.file, availableTypes) }
      )
    )
  }, [availableTypes])

  function patch(key: string, change: Partial<Row>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...change } : row)))
  }

  /** 아직 안 올라간 선택 줄에만 적용한다. `done` 은 건드리지 않는다. */
  function assignSelected(change: Partial<Row>) {
    setRows((current) =>
      current.map((row) =>
        row.selected && row.status !== 'done' ? { ...row, ...change } : row
      )
    )
  }

  async function loadSamples(materialId: string) {
    if (sampleCache[materialId]) return
    const rowsForMaterial = await materialsApi.samples(materialId)
    setSampleCache((current) => ({ ...current, [materialId]: rowsForMaterial }))
  }

  async function loadSpecimens(sampleId: string) {
    if (specimenCache[sampleId]) return
    const rowsForSample = await materialsApi.specimens(sampleId)
    setSpecimenCache((current) => ({ ...current, [sampleId]: rowsForSample }))
  }

  /** 방향을 돌려 가며 지정한다. `['MD']` 면 전부 MD, `MD·TD·DD` 면 순환. */
  function assignNewSpecimens(cycle: readonly string[]) {
    let index = 0
    setRows((current) =>
      current.map((row) => {
        if (!row.selected || !row.sampleId || row.status === 'done') return row
        const orientation = cycle[index % cycle.length]
        index += 1
        return { ...row, specimen: `new:${orientation}` }
      })
    )
  }

  async function upload() {
    setRunning(true)
    // **한 줄씩 순서대로 올린다.** 동시에 던지면 같은 시료에 새 시편을 만들 때
    // 채번이 엉키고, 어느 줄이 실패했는지도 흐려진다.
    //
    // 루프가 읽는 `rows` 는 시작 시점의 스냅샷이다. 그래서 도는 동안 표의 편집을
    // 전부 잠근다(`running`) — 안 잠그면 사용자가 고친 값이 화면에만 반영되고
    // 실제로는 옛 값으로 올라간 뒤 '올림' 으로 표시된다.
    for (const row of rows) {
      if (!isReady(row) || row.status === 'done') continue
      patch(row.key, { status: 'uploading', message: undefined })
      try {
        let specimenId = row.specimen as string
        if (specimenId.startsWith('new:')) {
          const created = await materialsApi.createSpecimen(row.sampleId as string, {
            orientation: specimenId.slice(4),
            length_unit: 'mm',
          })
          specimenId = created.id
          // **만들자마자 줄에 되돌려 쓴다.** 안 그러면 이 줄이 실패했을 때 다시
          // 누를 때마다 시편이 하나씩 더 생겨, 시험 없는 빈 시편이 쌓인다.
          patch(row.key, { specimen: specimenId })
          const sampleId = row.sampleId as string
          setSpecimenCache((current) => ({
            ...current,
            [sampleId]: [...(current[sampleId] ?? []), created],
          }))
        }
        const definition = availableTypes.find((type) => type.key === row.typeKey)
        await testsApi.upload({
          specimenId,
          testType: row.typeKey as string,
          file: row.file,
          conditions: numericConditions(row.typeKey as string, conditions, availableTypes),
          conditionUnits: conditionUnits(definition?.conditions ?? []),
        })
        patch(row.key, { status: 'done', selected: false })
      } catch (caught) {
        patch(row.key, {
          status: 'error',
          message: caught instanceof Error ? caught.message : '올리지 못했습니다.',
        })
      }
    }
    setRunning(false)
  }

  const typesInBatch = useMemo(() => {
    const keys = new Set(rows.map((row) => row.typeKey).filter(Boolean) as string[])
    return availableTypes.filter((type) => keys.has(type.key) && type.conditions.length > 0)
  }, [rows, availableTypes])

  const doneCount = rows.filter((row) => row.status === 'done').length
  const failedCount = rows.filter((row) => row.status === 'error').length

  /** 줄의 Select 가 쓸 재료 목록 — 검색 결과 + 이 줄이 이미 가리키는 재료. */
  function optionsFor(row: Row): Material[] {
    const current = row.materialId ? known[row.materialId] : undefined
    if (!current || found.some((material) => material.id === current.id)) return found
    return [current, ...found]
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="일괄 등록"
        description="파일을 한꺼번에 올립니다. 줄마다 다른 재료·시료·시험 종류를 가리킬 수 있습니다."
        actions={
          <Button variant="outline" onClick={() => navigate(`/w/${slug ?? 'default'}/tests`)}>
            목록으로
          </Button>
        }
      />

      <ErrorNotice error={types.error ?? materials.error} className="mb-4" />

      <div
        onDragOver={(event) => {
          event.preventDefault()
          if (!running) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          if (!running) addFiles(event.dataTransfer.files)
        }}
        className={`mb-4 rounded-md border-2 border-dashed p-8 text-center transition-colors ${
          dragging ? 'border-primary bg-primary/5' : 'border-muted'
        } ${running ? 'opacity-50' : ''}`}
      >
        <FileUp className="text-muted-foreground mx-auto mb-2 size-6" />
        <p className="text-sm">파일을 여기에 끌어다 놓으세요</p>
        <Button
          variant="secondary"
          size="sm"
          className="mt-3"
          disabled={running}
          onClick={() => fileInput.current?.click()}
        >
          파일 고르기
        </Button>
        <input
          ref={fileInput}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => {
            addFiles(event.target.files)
            event.target.value = ''
          }}
        />
        {availableTypes.length > 0 && (
          <p className="text-muted-foreground mt-3 text-xs">
            자동 인식: {availableTypes.flatMap((t) => t.extensions).join(' · ') || '없음'}
          </p>
        )}
      </div>

      {rows.length > 0 && (
        <>
          <fieldset
            disabled={running}
            className="bg-muted/30 mb-3 flex flex-wrap items-end gap-3 rounded-md border p-3"
          >
            <div className="text-muted-foreground text-xs">
              선택한 {selected.length}줄에 적용
            </div>

            <div className="space-y-1">
              <Label className="text-muted-foreground text-xs">시험 종류</Label>
              <Select value="" onValueChange={(typeKey) => assignSelected({ typeKey })}>
                <SelectTrigger className="w-36">
                  <SelectValue placeholder="일괄 지정" />
                </SelectTrigger>
                <SelectContent>
                  {availableTypes.map((type) => (
                    <SelectItem key={type.key} value={type.key}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-muted-foreground text-xs">
                재료
                {total > found.length && (
                  <span className="text-amber-600 dark:text-amber-500">
                    {' '}
                    · {total}개 중 {found.length}개만 — 검색하세요
                  </span>
                )}
              </Label>
              <div className="flex gap-1">
                <div className="relative">
                  <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
                  <Input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    onKeyDown={(event) => event.key === 'Enter' && setApplied(search.trim())}
                    onBlur={() => setApplied(search.trim())}
                    placeholder="재료 찾기"
                    className="h-9 w-32 pl-7"
                  />
                </div>
                <Select
                  value=""
                  onValueChange={(materialId) => {
                    void loadSamples(materialId)
                    assignSelected({ materialId, sampleId: null, specimen: null })
                  }}
                >
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="일괄 지정" />
                  </SelectTrigger>
                  <SelectContent>
                    {found.map((material) => (
                      <SelectItem key={material.id} value={material.id}>
                        {material.record_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-muted-foreground text-xs">
                시료
                {selected.length > 0 && !commonMaterial && (
                  <span className="text-amber-600 dark:text-amber-500">
                    {' '}
                    · 선택한 줄의 재료가 다릅니다
                  </span>
                )}
              </Label>
              {/* 재료가 섞인 채로 시료를 지정하면 재료 B 파일이 재료 A 의 시료에
                  붙는다. 화면은 끝까지 B 라고 보여 준다 — 그래서 막는다. */}
              <Select
                value=""
                onValueChange={(sampleId) => {
                  void loadSpecimens(sampleId)
                  assignSelected({ sampleId, specimen: null })
                }}
                disabled={!commonMaterial}
              >
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="일괄 지정" />
                </SelectTrigger>
                <SelectContent>
                  {(sampleCache[commonMaterial ?? ''] ?? []).map((sample) => (
                    <SelectItem key={sample.id} value={sample.id}>
                      {String(sample.seq_no).padStart(2, '0')}
                      {sample.lot_no ? ` · ${sample.lot_no}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-muted-foreground text-xs">새 시편 (번호 자동)</Label>
              <div className="flex gap-1">
                {ORIENTATIONS.map((orientation) => (
                  <Button
                    key={orientation}
                    size="sm"
                    variant="outline"
                    disabled={!selected.some((row) => row.sampleId)}
                    onClick={() => assignNewSpecimens([orientation])}
                  >
                    {orientation}
                  </Button>
                ))}
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={!selected.some((row) => row.sampleId)}
                  title="선택한 줄에 MD·TD·DD 를 돌아가며 지정합니다"
                  onClick={() => assignNewSpecimens(ANISOTROPY_SET)}
                >
                  MD·TD·DD
                </Button>
              </div>
            </div>

            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              onClick={() => setRows((current) => current.filter((row) => !row.selected))}
              disabled={selected.length === 0}
            >
              <Trash2 className="size-4" />
              선택 제거
            </Button>
          </fieldset>

          <fieldset disabled={running}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8">
                    <input
                      type="checkbox"
                      checked={rows.length > 0 && rows.every((row) => row.selected)}
                      onChange={(event) =>
                        setRows((current) =>
                          current.map((row) => ({ ...row, selected: event.target.checked }))
                        )
                      }
                    />
                  </TableHead>
                  <TableHead>파일</TableHead>
                  <TableHead className="w-36">종류</TableHead>
                  <TableHead className="w-52">재료</TableHead>
                  <TableHead className="w-32">시료</TableHead>
                  <TableHead className="w-36">시편</TableHead>
                  <TableHead className="w-44">상태</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.key} className={row.status === 'done' ? 'opacity-50' : ''}>
                    <TableCell>
                      <input
                        type="checkbox"
                        checked={row.selected}
                        onChange={(event) => patch(row.key, { selected: event.target.checked })}
                      />
                    </TableCell>
                    <TableCell className="max-w-56 truncate text-xs" title={row.file.name}>
                      {row.file.name}
                      <span className="text-muted-foreground ml-1">
                        {(row.file.size / 1024).toFixed(0)}KB
                      </span>
                    </TableCell>

                    <TableCell>
                      <Select
                        value={row.typeKey ?? ''}
                        onValueChange={(value) => patch(row.key, { typeKey: value })}
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue placeholder="고르세요" />
                        </SelectTrigger>
                        <SelectContent>
                          {availableTypes.map((type) => (
                            <SelectItem key={type.key} value={type.key}>
                              {type.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>

                    <TableCell>
                      <Select
                        value={row.materialId ?? ''}
                        onValueChange={(value) => {
                          void loadSamples(value)
                          patch(row.key, { materialId: value, sampleId: null, specimen: null })
                        }}
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue placeholder="고르세요" />
                        </SelectTrigger>
                        <SelectContent>
                          {optionsFor(row).map((material) => (
                            <SelectItem key={material.id} value={material.id}>
                              {material.record_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>

                    <TableCell>
                      <Select
                        value={row.sampleId ?? ''}
                        onValueChange={(value) => {
                          void loadSpecimens(value)
                          patch(row.key, { sampleId: value, specimen: null })
                        }}
                        disabled={!row.materialId}
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue placeholder="—" />
                        </SelectTrigger>
                        <SelectContent>
                          {(sampleCache[row.materialId ?? ''] ?? []).map((sample) => (
                            <SelectItem key={sample.id} value={sample.id}>
                              {String(sample.seq_no).padStart(2, '0')}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>

                    <TableCell>
                      <Select
                        value={row.specimen ?? ''}
                        onValueChange={(value) => patch(row.key, { specimen: value })}
                        disabled={!row.sampleId}
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue placeholder="—" />
                        </SelectTrigger>
                        <SelectContent>
                          {(specimenCache[row.sampleId ?? ''] ?? []).map((specimen) => (
                            <SelectItem key={specimen.id} value={specimen.id}>
                              {specimen.orientation} {String(specimen.seq_no).padStart(2, '0')}
                            </SelectItem>
                          ))}
                          {ORIENTATIONS.map((orientation) => (
                            <SelectItem key={`new-${orientation}`} value={`new:${orientation}`}>
                              + 새 {orientation} 시편
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>

                    <TableCell>
                      <RowStatusCell row={row} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </fieldset>

          <fieldset disabled={running}>
            {typesInBatch.map((type) => (
              <section key={type.key} className="mt-4 rounded-md border p-3">
                <p className="mb-2 text-sm font-medium">
                  {type.label} 조건
                  <span className="text-muted-foreground ml-2 text-xs">
                    이 종류의 모든 줄에 같이 적용됩니다
                  </span>
                </p>
                <div className="grid grid-cols-4 gap-3">
                  {type.conditions.map((field) => (
                    <div key={field.key} className="space-y-1">
                      <Label className="text-muted-foreground text-xs">
                        {field.label}
                        {field.si_unit && ` (${display(field.si_unit, field.dimension).unit})`}
                        {field.is_required && <span className="text-destructive"> *</span>}
                      </Label>
                      <Input
                        className="h-8"
                        type={field.value_type === 'number' ? 'number' : 'text'}
                        step="any"
                        value={conditions[type.key]?.[field.key] ?? ''}
                        onChange={(event) =>
                          setConditions((current) => ({
                            ...current,
                            [type.key]: {
                              ...(current[type.key] ?? {}),
                              [field.key]: event.target.value,
                            },
                          }))
                        }
                      />
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </fieldset>

          <div className="mt-4 flex items-center gap-3">
            <Button onClick={upload} disabled={running || ready.length === 0}>
              {running ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Upload className="size-4" />
              )}
              {running ? '올리는 중… (편집 잠김)' : `올리기 (${ready.length})`}
            </Button>
            <p className="text-muted-foreground text-sm">
              완료 {doneCount} · 실패 {failedCount} · 준비 안 됨{' '}
              {rows.filter((row) => !isReady(row) && row.status !== 'done').length}
            </p>
            {doneCount > 0 && !running && (
              <Button
                variant="outline"
                className="ml-auto"
                onClick={() => navigate(`/w/${slug ?? 'default'}/tests`)}
              >
                목록에서 확인
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function RowStatusCell({ row }: { row: Row }) {
  if (row.status === 'done') {
    return (
      <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-500">
        <CheckCircle2 className="size-3.5" />
        올림
      </span>
    )
  }
  if (row.status === 'uploading') {
    return (
      <span className="text-muted-foreground flex items-center gap-1 text-xs">
        <Loader2 className="size-3.5 animate-spin" />
        올리는 중
      </span>
    )
  }
  if (row.status === 'error') {
    return (
      <span className="text-destructive flex items-start gap-1 text-xs" title={row.message}>
        <X className="mt-0.5 size-3.5 shrink-0" />
        <span className="line-clamp-2">{row.message}</span>
      </span>
    )
  }
  if (!isReady(row)) {
    const missing = !row.typeKey
      ? '종류 미정'
      : !row.materialId
        ? '재료 미정'
        : !row.sampleId
          ? '시료 미정'
          : '시편 미정'
    return (
      <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-500">
        <AlertTriangle className="size-3.5" />
        {missing}
      </span>
    )
  }
  return <Badge variant="outline">준비됨</Badge>
}

/** 문자열로 받은 조건을 정의에 맞춰 숫자로 바꾼다. 빈 칸은 보내지 않는다. */
function numericConditions(
  typeKey: string,
  all: Record<string, Record<string, string>>,
  types: TestType[]
): Record<string, unknown> {
  const definition = types.find((type) => type.key === typeKey)
  const raw = all[typeKey] ?? {}
  return Object.fromEntries(
    Object.entries(raw)
      .filter(([, value]) => value !== '')
      .map(([key, value]) => {
        const field = definition?.conditions.find((c) => c.key === key)
        return [key, field?.value_type === 'number' ? Number(value) : value]
      })
  )
}
