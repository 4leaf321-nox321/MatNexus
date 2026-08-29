/**
 * 시료·시편 탐색기 — **왼쪽에서 시료를 고르고, 오른쪽 표에서 시편을 견준다.**
 *
 * 전에는 아코디언 3단 중첩이었다(시료 ▸ 시편 ▸ 시험). 세 가지가 한꺼번에 나빴다:
 *
 *   1. **아무것도 안 펼친 상태가 기본**이라, 열기 전에는 무엇이 있는지 모른다.
 *   2. **가로로 못 견준다.** 시편의 방향·치수를 비교하려면 전부 펼쳐 세로로
 *      늘어놓고 스크롤해야 한다 — 표라면 한눈에 볼 것을 세로로 흩어 놓았다.
 *   3. **깊이가 3단**이라 접었다 펴는 사이에 어디였는지 놓친다.
 *
 * 표로 바꾸면 셋이 함께 풀린다. 시료가 하나든 서른이든 왼쪽 목록의 길이만 달라지고,
 * 시편이 몇 개든 표의 줄 수만 달라진다 — **분포에 기대지 않는다.**
 *
 * ## 시험을 어디에 보이나 — 두 모드를 다 둔다
 *
 * 줄 안에서 펼치는 것과 오른쪽에 띄우는 것 중 무엇이 나은지는 **써 봐야 안다.**
 * 그래서 지금은 고를 수 있게 두고, 한쪽으로 정해지면 다른 쪽을 걷는다.
 */

import { Fragment, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Columns2,
  FileText,
  Pencil,
  Plus,
  Rows3,
  Table2,
  Trash2,
} from 'lucide-react'

import { EditSampleDialog } from '@/modules/materials/EditSampleDialog'
import { EditSpecimenDialog } from '@/modules/materials/EditSpecimenDialog'
import { MillSheetDialog } from '@/modules/materials/MillSheetDialog'
import { NewSpecimenDialog } from '@/modules/materials/NewSpecimenDialog'
import { materialsApi } from '@/modules/materials/api'
import type { Sample, Specimen } from '@/modules/materials/api'
import { SpecimenTests } from '@/modules/tests/SpecimenTests'
import { SummaryImportDialog } from '@/modules/tests/SummaryImportDialog'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { display, toDisplay } from '@/shared/units'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { cn } from '@/shared/lib/utils'

/** 시험을 어디에 그리나. **정해지면 한쪽을 걷는다.** */
type Mode = 'inline' | 'side'

/**
 * **`.choice` 로 갈아탄 이유.** 앞 판은 화면을 열기만 해도 지금 모드를 적었다
 * (`useEffect` 가 마운트에서 한 번 돈다). 그러면 **아무도 고른 적 없는 값**이
 * 저장되어 있고, 뒤에 「고른 사람의 뜻이 이긴다」 규칙을 붙이자 그 값이 사람의
 * 뜻 행세를 하며 폭을 영영 무시했다 — 창을 늘려도 모드가 안 바뀌었다.
 *
 * 옛 열쇠는 그대로 둔다. 지우려 들면 그 코드가 또 한동안 남고, 값이 몇 바이트다.
 */
const MODE_KEY = 'mnx.sampleExplorer.mode.choice'

/**
 * 옆에 띄울 만큼 넓은가. **`xl` 과 같은 자리다** — 그보다 좁으면 표와 시험이
 * 반씩 나눠 가져 둘 다 못 쓴다.
 */
const WIDE_ENOUGH = '(min-width: 1280px)'

/**
 * 화면 폭이 정한다 — **사람이 고르기 전까지는.**
 *
 * 넓으면 옆에 띄우는 편이 낫다(시편을 바꿔 가며 견준다). 좁으면 줄 안에서 펼치는
 * 것 말고 길이 없다. 그 판단을 매번 사람에게 시킬 이유가 없다.
 *
 * 다만 **고르고 나면 그 뜻이 이긴다.** 넓은 화면에서 일부러 「줄 안에서」 를 고른
 * 사람에게 창을 늘렸다고 되돌려 놓으면, 그건 고른 것을 무시하는 것이다.
 */
function useAutoMode(): [Mode, (next: Mode) => void] {
  const [chosen, setChosen] = useState<Mode | null>(() => {
    try {
      const saved = localStorage.getItem(MODE_KEY)
      return saved === 'side' || saved === 'inline' ? saved : null
    } catch {
      // 사생활 보호 창에서는 못 읽는다. 그때는 폭이 정한다.
      return null
    }
  })
  const [wide, setWide] = useState(
    () => typeof matchMedia === 'function' && matchMedia(WIDE_ENOUGH).matches
  )

  useEffect(() => {
    if (typeof matchMedia !== 'function') return
    const query = matchMedia(WIDE_ENOUGH)
    const onChange = () => setWide(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  const choose = (next: Mode) => {
    setChosen(next)
    try {
      localStorage.setItem(MODE_KEY, next)
    } catch {
      // 못 적어도 이번 방문 동안은 고른 대로 간다.
    }
  }

  return [chosen ?? (wide ? 'side' : 'inline'), choose]
}

function sizeText(specimen: Specimen): string {
  if (specimen.sizes.length === 0) return '—'
  return specimen.sizes
    .map((size) => {
      const shown = display(size.si_unit, size.dimension)
      const value = Number(toDisplay(size.value, size.si_unit, size.dimension).toPrecision(4))
      return `${size.label} ${value}${shown.unit ? shown.unit : ''}`
    })
    .join(' · ')
}

/**
 * 시험 수 한 칸 — **수만으로는 상태를 모른다.** 3건 중 채택이 0 이면 그 시편은
 * 아직 물성을 못 낸 것이고, 실패가 섞여 있으면 다시 읽어야 한다.
 */
function RunTally({
  total,
  adopted,
  failed,
}: {
  total: number
  adopted: number
  failed: number
}) {
  if (total === 0) return <span className="text-muted-foreground text-xs">시험 0</span>
  return (
    <span className="flex items-center gap-1.5 text-xs">
      <span>시험 {total}</span>
      {adopted > 0 && (
        <span className="inline-flex items-center gap-0.5 text-emerald-700 dark:text-emerald-500">
          <CheckCircle2 className="size-3" />
          채택 {adopted}
        </span>
      )}
      {failed > 0 && (
        <span className="inline-flex items-center gap-0.5 text-destructive">
          <AlertTriangle className="size-3" />
          실패 {failed}
        </span>
      )}
    </span>
  )
}

export function SampleExplorer({
  materialId,
  samples,
  onChanged,
}: {
  materialId: string
  samples: Sample[]
  /** 시료·시편이 늘거나 줄면 위의 요약 줄과 시료 목록이 달라진다. */
  onChanged: () => void
}) {
  // **시료가 하나뿐이어도 고른 상태로 시작한다.** 한 항목짜리 층을 눌러서
  // 통과하게 하지 않는다 — 그것이 아코디언에서 가장 자주 하던 헛클릭이다.
  const [sampleId, setSampleId] = useState<string | null>(null)
  const [specimenId, setSpecimenId] = useState<string | null>(null)
  const [mode, setMode] = useAutoMode()

  const active = samples.find((one) => one.id === sampleId) ?? samples[0] ?? null

  const specimens = useResource(
    () => (active ? materialsApi.specimens(active.id) : Promise.resolve([])),
    [active?.id, materialId]
  )
  const rows = useMemo(() => specimens.data ?? [], [specimens.data])

  // 시료를 바꾸면 고른 시편은 그 시료의 것이 아니다. 안 지우면 오른쪽에 남의
  // 시편의 시험이 떠 있고, 그것이 어느 시편의 것인지 화면에 없다.
  useEffect(() => setSpecimenId(null), [active?.id])

  const picked = rows.find((one) => one.id === specimenId) ?? null

  // **아코디언에 있던 일이 여기로 온다.** 표로 바꾸면서 편집·밀시트·삭제가
  // 사라지면 그건 개선이 아니라 기능 삭제다.
  const [editingSample, setEditingSample] = useState(false)
  const [mill, setMill] = useState(false)
  const [removingSample, setRemovingSample] = useState(false)
  const [adding, setAdding] = useState(false)
  const [importing, setImporting] = useState(false)
  const [editingSpecimen, setEditingSpecimen] = useState<Specimen | null>(null)
  const [removingSpecimen, setRemovingSpecimen] = useState<Specimen | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Error | null>(null)

  async function run(job: () => Promise<unknown>, done: () => void) {
    setBusy(true)
    setFailure(null)
    try {
      await job()
      done()
      specimens.reload()
      onChanged()
    } catch (caught) {
      setFailure(caught instanceof Error ? caught : new Error('처리하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (samples.length === 0) return null

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(200px,260px)_minmax(0,1fr)] lg:items-start">
      <div className="space-y-1">
        <p className="text-muted-foreground px-1 text-xs font-medium">시료 {samples.length}</p>
        {samples.map((sample) => (
          <button
            key={sample.id}
            type="button"
            onClick={() => setSampleId(sample.id)}
            aria-current={sample.id === active?.id ? 'true' : undefined}
            className={cn(
              'w-full rounded-md border px-2.5 py-2 text-left text-sm',
              sample.id === active?.id ? 'bg-muted border-foreground/20' : 'hover:bg-muted/50'
            )}
          >
            <div className="truncate font-mono text-xs">{sample.record_name}</div>
            {/* **로트와 제조사가 시료를 가르는 것이다.** 이름만으로는 `__01`·
                `__02` 라 무엇이 다른지 알 수 없다. */}
            <div className="text-muted-foreground mt-0.5 truncate text-xs">
              {[sample.manufacturer, sample.lot_no].filter(Boolean).join(' · ') || '—'}
            </div>
            <div className="text-muted-foreground mt-0.5 text-xs">
              시편 {sample.specimen_count} · 시험 {sample.test_run_count}
            </div>
          </button>
        ))}
      </div>

      <div className="min-w-0">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1">
            <p className="text-muted-foreground mr-1 text-xs font-medium">
              {active?.record_name} 의 시편 {rows.length}
            </p>
            {/* **고른 시료에 하는 일이다.** 왼쪽 카드에 밀어 넣으면 좁아서 아이콘만
                남고, 아이콘만으로는 무엇을 지우는지 알 수 없다. */}
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setEditingSample(true)}
            >
              <Pencil className="size-3.5" />
              시료 편집
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setMill(true)}
            >
              <FileText className="size-3.5" />
              밀시트
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setRemovingSample(true)}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
          <div className="flex items-center gap-1">
            {/* **곡선 없는 시험도 데이터다.** 기존 표에 쌓인 것을 못 가져오면
                사용자가 옮겨오지 않는다. */}
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setImporting(true)}
            >
              <Table2 className="size-3.5" />
              표로 시험 넣기
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="h-7 text-xs"
              onClick={() => setAdding(true)}
            >
              <Plus className="size-3.5" />
              시편 추가
            </Button>
            {/* **어느 쪽이 나은지는 써 봐야 안다.** 정해지면 한쪽을 걷는다. */}
            <Button
              size="sm"
              variant={mode === 'inline' ? 'secondary' : 'ghost'}
              className="h-7 text-xs"
              onClick={() => setMode('inline')}
              aria-pressed={mode === 'inline'}
              title="시편 줄 아래에 시험을 펼칩니다"
            >
              <Rows3 className="size-3.5" />
              줄 안에서
            </Button>
            <Button
              size="sm"
              variant={mode === 'side' ? 'secondary' : 'ghost'}
              className="h-7 text-xs"
              onClick={() => setMode('side')}
              aria-pressed={mode === 'side'}
              title="오른쪽에 시험을 띄웁니다 — 시편을 바꿔 가며 견주기 좋습니다"
            >
              <Columns2 className="size-3.5" />
              옆에서
            </Button>
          </div>
        </div>

        <ErrorNotice error={specimens.error} className="mb-2" />

        <div
          className={cn(
            'grid gap-4',
            mode === 'side' && 'xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] xl:items-start'
          )}
        >
          <div className="min-w-0 overflow-x-auto rounded-md border">
            {specimens.loading && rows.length === 0 ? (
              <Skeleton className="h-24" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    {/* **시편이 가장 넓다.** 이름·규격·치수가 여기 걸리고, 나머지는
                        짧은 값이라 자리를 덜 먹어야 한다. */}
                    <TableHead>시편</TableHead>
                    <TableHead className="w-16">방향</TableHead>
                    <TableHead className="w-28">규격</TableHead>
                    <TableHead>치수</TableHead>
                    {/* **머리와 내용의 정렬을 맞춘다.** `text-right` 를 줬는데 칸
                        안은 flex 라 그 값이 안 먹었다 — 머리만 오른쪽으로 붙어
                        어긋나 보였다. */}
                    <TableHead className="w-32">시험</TableHead>
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((specimen) => {
                    const open = specimen.id === specimenId
                    return (
                      // **열쇠는 조각에 붙인다.** 목록이 받는 자식이 이 조각이라,
                      // 안쪽 `TableRow` 에 붙이면 React 는 못 본다.
                      <Fragment key={specimen.id}>
                        <TableRow
                          onClick={() => setSpecimenId(open ? null : specimen.id)}
                          aria-selected={open}
                          className={cn('cursor-pointer', open && 'bg-muted/60')}
                        >
                          <TableCell className="text-muted-foreground">
                            {open ? (
                              <ChevronDown className="size-3.5" />
                            ) : (
                              <ChevronRight className="size-3.5" />
                            )}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {specimen.record_name}
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">{specimen.orientation}</Badge>
                          </TableCell>
                          <TableCell className="text-xs">{specimen.standard ?? '—'}</TableCell>
                          <TableCell className="text-muted-foreground text-xs">
                            {sizeText(specimen)}
                          </TableCell>
                          <TableCell>
                            <RunTally
                              total={specimen.test_run_count}
                              adopted={specimen.adopted_count}
                              failed={specimen.failed_count}
                            />
                          </TableCell>
                          <TableCell
                            className="text-right"
                            onClick={(event) => event.stopPropagation()}
                          >
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-7"
                              title="시편 편집"
                              onClick={() => setEditingSpecimen(specimen)}
                            >
                              <Pencil className="size-3.5" />
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-7"
                              title="시편 삭제"
                              onClick={() => setRemovingSpecimen(specimen)}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          </TableCell>

                        </TableRow>
                        {mode === 'inline' && open && (
                          <TableRow>
                            <TableCell colSpan={7} className="bg-muted/30 p-3">
                              <SpecimenTests
                                specimenId={specimen.id}
                                specimenName={specimen.record_name}
                              />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>

          {mode === 'side' && (
            <div className="min-w-0 rounded-md border p-3">
              {picked ? (
                <SpecimenTests specimenId={picked.id} specimenName={picked.record_name} />
              ) : (
                <p className="text-muted-foreground text-sm">
                  왼쪽 표에서 시편을 고르면 그 시험이 여기 뜹니다.
                </p>
              )}
            </div>
          )}
        </div>

        {rows.length === 0 && !specimens.loading && (
          <p className="text-muted-foreground mt-2 text-sm">
            이 시료에는 시편이 없습니다. 시편을 만들어야 시험을 붙일 수 있습니다.
          </p>
        )}

        {failure && <p className="text-destructive mt-2 text-xs">{failure.message}</p>}
      </div>

      {active && (
        <>
          <EditSampleDialog
            sample={active}
            open={editingSample}
            onClose={() => setEditingSample(false)}
            onSaved={() => {
              setEditingSample(false)
              onChanged()
            }}
          />
          <MillSheetDialog
            sample={active}
            open={mill}
            onClose={() => setMill(false)}
            onSaved={onChanged}
          />
          <ConfirmDialog
            open={removingSample}
            busy={busy}
            title="이 시료를 지웁니다"
            body={
              <>
                <p>
                  <b className="font-mono">{active.record_name}</b>
                  {active.lot_no ? ` (로트 ${active.lot_no})` : ''} 이 사라집니다.
                </p>
                {/* **무엇이 막는지 미리 말한다.** 눌러 보고 오류로 아는 것보다 낫다. */}
                {active.specimen_count > 0 && (
                  <p className="text-destructive mt-2 text-xs">
                    시편 {active.specimen_count}건이 남아 있어 지울 수 없습니다. 시편을
                    먼저 지우세요.
                  </p>
                )}
              </>
            }
            onConfirm={() =>
              void run(
                () => materialsApi.removeSample(active.id),
                () => {
                  setRemovingSample(false)
                  setSampleId(null)
                }
              )
            }
            onClose={() => setRemovingSample(false)}
          />
          <NewSpecimenDialog
            sampleId={active.id}
            open={adding}
            onClose={() => setAdding(false)}
            onDone={() => {
              setAdding(false)
              specimens.reload()
              onChanged()
            }}
          />
          {importing && (
            <SummaryImportDialog
              sampleId={active.id}
              sampleName={active.record_name}
              testType="tensile"
              testTypeLabel="인장시험"
              onClose={() => setImporting(false)}
              onDone={() => {
                specimens.reload()
                onChanged()
              }}
            />
          )}
        </>
      )}

      {editingSpecimen && (
        <EditSpecimenDialog
          specimen={editingSpecimen}
          open
          onClose={() => setEditingSpecimen(null)}
          onSaved={() => {
            setEditingSpecimen(null)
            specimens.reload()
            onChanged()
          }}
        />
      )}

      <ConfirmDialog
        open={removingSpecimen !== null}
        busy={busy}
        title="이 시편을 지웁니다"
        body={
          <p>
            <b className="font-mono">{removingSpecimen?.record_name}</b> 이 사라집니다.
            {(removingSpecimen?.test_run_count ?? 0) > 0 && (
              <span className="text-destructive block text-xs">
                시험 {removingSpecimen?.test_run_count}건이 함께 가려집니다.
              </span>
            )}
          </p>
        }
        onConfirm={() =>
          removingSpecimen &&
          void run(
            () => materialsApi.removeSpecimen(removingSpecimen.id),
            () => setRemovingSpecimen(null)
          )
        }
        onClose={() => setRemovingSpecimen(null)}
      />
    </div>
  )
}
