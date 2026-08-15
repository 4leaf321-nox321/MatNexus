/**
 * 일괄 등록 — 파일 여러 개를 한 번에.
 *
 * **한 배치에 서로 다른 재료·시료·시험종류가 섞인다.** 실제로 그렇게 올린다고
 * 확인했다. 그래서 "이 배치는 이 시편의 것" 이라고 통째로 정하는 마법사가 아니라,
 * **파일마다 한 줄인 표**로 만든다. 줄마다 다른 재료를 가리킬 수 있어야 한다.
 *
 * 대신 줄마다 손으로 고르게 하면 열 줄부터 일이 된다. 그래서 두 가지를 얹는다.
 *
 *   1. **확장자로 시험 종류를 추정한다.** 정의가 선언한 확장자를 서버가 내려
 *      주므로(`TestType.extensions`), 종류가 스무 개로 늘어도 화면은 그대로다.
 *   2. **선택한 줄에 일괄 지정한다.** 인장은 한 시료에서 시편 여러 개를 연속으로
 *      시험하므로, 재료·시료를 한 번 찍고 "MD 방향으로 새 시편 만들기" 를 누르면
 *      번호가 순서대로 붙는다.
 *
 * 서버에는 배치 개념을 두지 않는다. 줄마다 기존 업로드 API 를 한 번씩 부른다 —
 * 배치 테이블을 만들면 "절반만 올라간 배치" 라는 상태를 누군가 관리해야 하는데,
 * 그 상태는 이 표가 이미 눈앞에 보여 주고 있다. 실패한 줄만 다시 누르면 된다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FileUp,
  Loader2,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { Material, Sample, Specimen } from '@/modules/materials/api'
import { testsApi } from '@/modules/tests/api'
import type { TestType } from '@/modules/tests/api'
import { display } from '@/modules/tests/units'
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

type RowStatus = 'incomplete' | 'ready' | 'uploading' | 'done' | 'error'

interface Row {
  key: string
  file: File
  selected: boolean
  typeKey: string | null
  materialId: string | null
  sampleId: string | null
  /** 기존 시편을 가리키거나, `new:<방향>` 이면 올릴 때 새로 만든다. */
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
  return Boolean(row.typeKey && row.specimen)
}

export default function BatchUploadPage() {
  const { slug } = useParams<{ slug?: string }>()
  const navigate = useNavigate()
  const types = useResource(() => testsApi.types(), [])
  const materials = useResource(() => materialsApi.list({ limit: 200 }), [])

  const [rows, setRows] = useState<Row[]>([])
  const [sampleCache, setSampleCache] = useState<Record<string, Sample[]>>({})
  const [specimenCache, setSpecimenCache] = useState<Record<string, Specimen[]>>({})
  const [conditions, setConditions] = useState<Record<string, Record<string, string>>>({})
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  // `?? []` 를 그대로 두면 매 렌더마다 새 배열이라 아래 훅들이 계속 돈다.
  const availableTypes = useMemo(() => types.data ?? [], [types.data])
  const materialList = materials.data?.items ?? []
  const selected = rows.filter((row) => row.selected)
  const ready = rows.filter((row) => isReady(row) && row.status !== 'done')

  function addFiles(files: FileList | null) {
    if (!files?.length) return
    setRows((current) => [
      ...current,
      ...Array.from(files).map((file, index) => ({
        key: `${file.name}-${file.size}-${current.length + index}`,
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
    setRows((current) =>
      current.map((row) => (row.key === key ? { ...row, ...change } : row))
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

  function assignMaterial(materialId: string) {
    void loadSamples(materialId)
    setRows((current) =>
      current.map((row) =>
        row.selected && row.status !== 'done'
          ? { ...row, materialId, sampleId: null, specimen: null }
          : row
      )
    )
  }

  function assignSample(sampleId: string) {
    void loadSpecimens(sampleId)
    setRows((current) =>
      current.map((row) =>
        row.selected && row.status !== 'done' ? { ...row, sampleId, specimen: null } : row
      )
    )
  }

  /** 선택한 줄마다 새 시편을 만들게 표시한다. 번호는 서버가 순서대로 붙인다. */
  function assignNewSpecimens(orientation: string) {
    setRows((current) =>
      current.map((row) =>
        row.selected && row.sampleId && row.status !== 'done'
          ? { ...row, specimen: `new:${orientation}` }
          : row
      )
    )
  }

  async function upload() {
    setRunning(true)
    setError(null)
    // **한 줄씩 순서대로 올린다.** 동시에 던지면 새 시편 채번이 서로 엉키고
    // (같은 시료에 동시에 만들면 번호가 겹친다), 어느 줄이 실패했는지도 흐려진다.
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
        }
        await testsApi.upload({
          specimenId,
          testType: row.typeKey as string,
          file: row.file,
          conditions: numericConditions(row.typeKey as string, conditions, availableTypes),
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

      <ErrorNotice error={types.error ?? materials.error ?? error} className="mb-4" />

      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          addFiles(event.dataTransfer.files)
        }}
        className={`mb-4 rounded-md border-2 border-dashed p-8 text-center transition-colors ${
          dragging ? 'border-primary bg-primary/5' : 'border-muted'
        }`}
      >
        <FileUp className="text-muted-foreground mx-auto mb-2 size-6" />
        <p className="text-sm">파일을 여기에 끌어다 놓으세요</p>
        <Button
          variant="secondary"
          size="sm"
          className="mt-3"
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
          <div className="bg-muted/30 mb-3 flex flex-wrap items-end gap-3 rounded-md border p-3">
            <div className="text-muted-foreground text-xs">
              선택한 {selected.length}줄에 적용
            </div>

            <div className="space-y-1">
              <Label className="text-muted-foreground text-xs">재료</Label>
              <Select value="" onValueChange={assignMaterial} disabled={selected.length === 0}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="일괄 지정" />
                </SelectTrigger>
                <SelectContent>
                  {materialList.map((material: Material) => (
                    <SelectItem key={material.id} value={material.id}>
                      {material.record_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-muted-foreground text-xs">시료</Label>
              <Select
                value=""
                onValueChange={assignSample}
                disabled={selected.length === 0 || !selected[0]?.materialId}
              >
                <SelectTrigger className="w-44">
                  <SelectValue placeholder="일괄 지정" />
                </SelectTrigger>
                <SelectContent>
                  {(sampleCache[selected[0]?.materialId ?? ''] ?? []).map((sample) => (
                    <SelectItem key={sample.id} value={sample.id}>
                      {String(sample.seq_no).padStart(2, '0')}
                      {sample.lot_no ? ` · ${sample.lot_no}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-muted-foreground text-xs">
                새 시편 만들기 (줄마다 번호 자동)
              </Label>
              <div className="flex gap-1">
                {ORIENTATIONS.map((orientation) => (
                  <Button
                    key={orientation}
                    size="sm"
                    variant="outline"
                    disabled={selected.length === 0 || !selected.every((row) => row.sampleId)}
                    onClick={() => assignNewSpecimens(orientation)}
                  >
                    {orientation}
                  </Button>
                ))}
              </div>
            </div>

            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              onClick={() => setRows((current) => current.filter((row) => !row.selected))}
              disabled={selected.length === 0 || running}
            >
              <Trash2 className="size-4" />
              선택 제거
            </Button>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <input
                    type="checkbox"
                    checked={rows.every((row) => row.selected)}
                    onChange={(event) =>
                      setRows((current) =>
                        current.map((row) => ({ ...row, selected: event.target.checked }))
                      )
                    }
                  />
                </TableHead>
                <TableHead>파일</TableHead>
                <TableHead className="w-40">종류</TableHead>
                <TableHead className="w-52">재료</TableHead>
                <TableHead className="w-36">시료</TableHead>
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
                        {materialList.map((material) => (
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
                      {field.si_unit && ` (${display(field.si_unit).unit})`}
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

          <div className="mt-4 flex items-center gap-3">
            <Button onClick={upload} disabled={running || ready.length === 0}>
              {running ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Upload className="size-4" />
              )}
              {running ? '올리는 중…' : `올리기 (${ready.length})`}
            </Button>
            <p className="text-muted-foreground text-sm">
              완료 {doneCount} · 실패 {failedCount} · 준비 안 됨{' '}
              {rows.filter((row) => !isReady(row)).length}
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
    return (
      <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-500">
        <AlertTriangle className="size-3.5" />
        {!row.typeKey ? '종류 미정' : '시편 미정'}
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
