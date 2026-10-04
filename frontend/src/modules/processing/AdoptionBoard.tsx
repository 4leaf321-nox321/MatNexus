/**
 * 채택 검토대 — 여러 시험의 결과를 **한 화면에서 견주어** 한 번에 채택한다(ADR 0058).
 *
 * ## 왜 따로 있나
 *
 * 채택은 시험마다 「결과」 탭에서 했다. 스무 건이면 스무 번 열고 닫고, 그사이 한 건만 탄성
 * 구간을 잘못 잡았어도 그 사실은 **다른 시험과 견줘야** 보인다 — 한 건씩 보면 그럴듯하다.
 * 실측(2026-09-11): 결과는 있는데 채택 안 한 시험이 47건이었고, 그 값들은 통계에 안 들어간다.
 *
 * ## 한 화면에 셋
 *
 *     왼쪽      시험마다 고른 결과 · 핵심 값 · 중앙값과의 차이(문턱을 넘으면 칠한다) —
 *               같은 재료 · 시험 종류 · 방향끼리만 견준다(`groupOf`)
 *     오른쪽 위  고른 결과들을 한 판에 겹친다 — 튀는 곡선은 숫자보다 모양으로 먼저 보인다
 *     오른쪽 아래 한 건 자세히 — 자르기 전/후 · E 선 · 오프셋 선 · 항복점(결과 탭의 그 그림)
 *                 과 「지금 채택 → 고른 것」 의 값 차이
 *
 * ## 사람이 누른다
 *
 * 채택은 「이 시험의 물성은 이것」 이라는 선언이다(ADR 0007). 고르는 것까지는 화면이 거들고,
 * 누르기 전에 무엇이 바뀌는지(새로 · 바꿈 · 고칠 수 없음 · 문턱을 넘은 것)를 세어 보인다.
 * 잘못 눌렀으면 **되돌린다** — 채택은 결과를 지우지 않으므로 이전 채택으로 돌려놓을 수 있다.
 */

import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowRight, Check, ExternalLink, Lock, Undo2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  DEFAULT_THRESHOLD,
  chosenOf,
  groupOf,
  headlineOf,
  keysToCompare,
  spreadsOf,
} from '@/modules/processing/adoption'
import type { Spread } from '@/modules/processing/adoption'
import { processingApi } from '@/modules/processing/api'
import type { AdoptManyOut, ResultBrief, ResultLine, RunOverview } from '@/modules/processing/api'
import { changesBetween } from '@/modules/processing/batchRun'
import { ResultCurve } from '@/modules/processing/ResultsPanel'
import { CurveChart } from '@/modules/tests/CurveChart'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { axisLabel, formatScalar, toDisplay } from '@/shared/units'

/** 한 번에 견주는 시험 수 — 서버의 `OVERVIEW_MAX` 와 같다. 넘으면 나눠서 한다. */
export const BOARD_MAX = 200

/** 한 판에 겹치는 곡선 수 — 서버의 `CURVES_MAX`. 넘으면 선이 아니라 면이 된다. */
const LINES_MAX = 60

const SELECT = 'border-input bg-background h-8 w-full min-w-44 rounded-md border px-2'

const when = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

/** 결과 하나를 고르는 자리의 한 줄. 무엇으로 만들었는지가 이름이다. */
function resultName(result: ResultBrief): string {
  const parts = [
    when(result.created_at),
    result.recipe_label ?? '레시피 없이',
    `${result.step_count}단계`,
  ]
  if (result.has_true_stress) parts.push('진응력 포함')
  if (result.stale) parts.push('옛 원본')
  if (result.is_adopted) parts.push('지금 채택')
  return parts.join(' · ')
}

function percent(ratio: number): string {
  return `${ratio > 0 ? '+' : ''}${(ratio * 100).toFixed(1)}%`
}

interface Props {
  testRunIds: string[]
  /** 채택이 바뀌면 — 워크벤치는 담긴 것의 사실을 다시 읽는다. */
  onChanged?: () => void
}

export function AdoptionBoard({ testRunIds, onChanged }: Props) {
  const asked = testRunIds.slice(0, BOARD_MAX)
  const overview = useResource(
    () => (asked.length > 0 ? processingApi.overview(asked) : Promise.resolve([])),
    [asked.join(',')]
  )
  const runs = useMemo(() => overview.data ?? [], [overview.data])

  /** 시험마다 고른 결과. 안 건드린 시험은 기본(`defaultChoice`)이다. */
  const [picked, setPicked] = useState<Record<string, string>>({})
  /** 채택할 것. `null` 이면 기본 — 고른 것이 지금 채택과 다르고 고칠 수 있는 시험. */
  const [checked, setChecked] = useState<Set<string> | null>(null)
  const [focus, setFocus] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(String(DEFAULT_THRESHOLD * 100))
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [done, setDone] = useState<AdoptManyOut | null>(null)
  const [undone, setUndone] = useState(false)

  const choose = (run: RunOverview) => chosenOf(run, picked)
  const limit = Math.max(0, Number(threshold) || 0) / 100
  const spreads = spreadsOf(runs, choose)
  const over = (run: RunOverview) => {
    const spread = spreads.get(run.test_run_id)
    return spread !== null && spread !== undefined && Math.abs(spread.ratio) >= limit
  }

  /** 시험 종류마다 견주는 값 — 줄의 「핵심 값」 도 이 차례다. */
  const keysByType = useMemo(() => {
    const out = new Map<string, string[]>()
    const groups = new Map<string, ResultBrief[]>()
    for (const run of runs) {
      const type = run.test_type_key ?? '?'
      groups.set(type, [...(groups.get(type) ?? []), ...run.results])
    }
    for (const [type, results] of groups) out.set(type, keysToCompare(results))
    return out
  }, [runs])

  /**
   * 차례 — **처음 읽었을 때의 차이로 한 번 정한다.** 고를 때마다 줄이 움직이면 방금 본 줄을
   * 다시 찾아야 한다. 볼 수 없는 것 · 결과가 없는 것은 아래로.
   */
  const order = useMemo(() => {
    const first = spreadsOf(runs, (run) => chosenOf(run, undefined))
    const rank = (run: RunOverview) => {
      if (!run.found) return -2
      if (run.results.length === 0) return -1
      return Math.abs(first.get(run.test_run_id)?.ratio ?? 0)
    }
    return [...runs].sort((a, b) => rank(b) - rank(a)).map((run) => run.test_run_id)
  }, [runs])
  const rows = order
    .map((id) => runs.find((run) => run.test_run_id === id))
    .filter((run): run is RunOverview => run !== undefined)

  const canAdopt = (run: RunOverview) =>
    run.found && run.results.length > 0 && run.access?.can_edit !== false
  const changes = (run: RunOverview) => choose(run)?.id !== (run.adopted_result_id ?? undefined)
  const selected =
    checked ?? new Set(rows.filter((run) => canAdopt(run) && changes(run)).map((run) => run.test_run_id))

  const current = rows.find((run) => run.test_run_id === focus) ?? rows.find((run) => run.found)

  async function adopt() {
    const sending = rows.filter(
      (run) => selected.has(run.test_run_id) && canAdopt(run) && changes(run)
    )
    setBusy(true)
    setError(null)
    try {
      const got = await processingApi.adoptMany(
        sending.map((run) => ({ test_run_id: run.test_run_id, result_id: choose(run)?.id ?? null }))
      )
      setDone(got)
      setUndone(false)
      setConfirming(false)
      setChecked(null)
      overview.reload()
      onChanged?.()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('채택하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  /** **이전 채택으로 돌려놓는다** — 응답의 `previous_adopted_id` 를 그대로 돌려보낸다. */
  async function undo() {
    if (!done) return
    setBusy(true)
    setError(null)
    try {
      await processingApi.adoptMany(
        done.items
          .filter((one) => one.status === 'ok')
          .map((one) => ({
            test_run_id: one.test_run_id,
            result_id: one.previous_adopted_id ?? null,
          }))
      )
      setUndone(true)
      setChecked(null)
      overview.reload()
      onChanged?.()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('되돌리지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function toggle(runId: string) {
    const next = new Set(selected)
    if (next.has(runId)) next.delete(runId)
    else next.add(runId)
    setChecked(next)
  }

  if (testRunIds.length === 0) {
    return (
      <p className="text-muted-foreground rounded-md border border-dashed p-6 text-center text-sm">
        견줄 시험이 없습니다. 앞 단계에서 시험을 담으면 여기 섭니다.
      </p>
    )
  }

  // 확인 창이 셀 것들.
  const targets = rows.filter((run) => selected.has(run.test_run_id))
  // 고칠 수 없는 시험은 고를 수 없다 — 그래도 **몇 건이 빠지는지는 말한다.** 안 말하면 사람은
  // 스무 건을 채택했다고 알고, 남은 셋은 채택 전으로 남는다.
  const locked = rows.filter(
    (run) => run.found && run.results.length > 0 && run.access?.can_edit === false
  )
  const sending = targets.filter((run) => canAdopt(run) && changes(run))
  const fresh = sending.filter((run) => !run.adopted_result_id)
  const moved = sending.filter((run) => run.adopted_result_id)
  const loud = sending.filter(over)

  return (
    <section aria-label="채택 검토대" className="space-y-3">
      <ErrorNotice error={overview.error ?? error} />

      {testRunIds.length > BOARD_MAX && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-sm">
          담은 시험 {testRunIds.length}건 중 앞의 {BOARD_MAX}건만 견줍니다 — 한 화면에서 훑을 수
          있는 수를 넘으면 견주는 뜻이 없습니다. 나머지는 이 작업을 나눠 하세요.
        </p>
      )}

      {done && (
        <Outcome done={done} undone={undone} busy={busy} onUndo={() => void undo()} />
      )}

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span>
          시험 <b>{rows.length}</b>
        </span>
        <span className="text-muted-foreground">·</span>
        <span>
          채택할 것 <b>{sending.length}</b>
        </span>
        {rows.some(over) && (
          <Badge variant="outline" className="border-amber-500/60 text-amber-700 dark:text-amber-400">
            중앙값에서 먼 것 {rows.filter(over).length}
          </Badge>
        )}
        <label className="ml-auto flex items-center gap-1.5">
          <span className="text-muted-foreground">중앙값과 차이 문턱</span>
          <Input
            aria-label="문턱(%)"
            className="h-8 w-16"
            inputMode="decimal"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />
          <span className="text-muted-foreground">%</span>
        </label>
        <Button
          size="sm"
          disabled={busy || sending.length === 0}
          onClick={() => setConfirming(true)}
        >
          <Check className="size-3.5" />
          고른 {sending.length}건 채택
        </Button>
      </div>

      <div className="grid gap-4 2xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] 2xl:items-start">
        <div className="min-w-0 rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">
                  <input
                    type="checkbox"
                    aria-label="모두 고르기"
                    checked={rows.filter(canAdopt).every((run) => selected.has(run.test_run_id))}
                    onChange={(event) =>
                      setChecked(
                        new Set(
                          event.target.checked
                            ? rows.filter(canAdopt).map((run) => run.test_run_id)
                            : []
                        )
                      )
                    }
                  />
                </TableHead>
                <TableHead>시험</TableHead>
                <TableHead>고른 결과</TableHead>
                <TableHead>핵심 값</TableHead>
                <TableHead>중앙값과 차이</TableHead>
                <TableHead>지금</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {overview.loading && rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-muted-foreground py-6 text-center">
                    결과를 읽는 중…
                  </TableCell>
                </TableRow>
              ) : null}
              {rows.map((run) => (
                <BoardRow
                  key={run.test_run_id}
                  run={run}
                  chosen={choose(run)}
                  keys={keysByType.get(run.test_type_key ?? '?') ?? []}
                  spread={spreads.get(run.test_run_id) ?? null}
                  loud={over(run)}
                  focused={current?.test_run_id === run.test_run_id}
                  checked={selected.has(run.test_run_id)}
                  checkable={canAdopt(run)}
                  onCheck={() => toggle(run.test_run_id)}
                  onFocus={() => setFocus(run.test_run_id)}
                  onPick={(resultId) => {
                    setPicked({ ...picked, [run.test_run_id]: resultId })
                    setFocus(run.test_run_id)
                  }}
                />
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="min-w-0 space-y-4 2xl:sticky 2xl:top-28">
          {current && (
            <Overlay
              // **견주는 묶음과 같은 것을 겹친다** — 다른 재료의 곡선이 섞이면 칠한 색과 그림이
              // 다른 이야기를 한다.
              runs={rows.filter((run) => run.found && groupOf(run) === groupOf(current))}
              focus={current}
              choose={choose}
              over={over}
            />
          )}
          {current && <Detail run={current} chosen={choose(current)} />}
        </div>
      </div>

      <ConfirmDialog
        open={confirming}
        title={`${sending.length}건을 채택할까요?`}
        confirmLabel="채택"
        undoable="채택한 뒤 「되돌리기」 로 이전 채택으로 돌려놓을 수 있습니다 — 결과는 지워지지 않습니다."
        busy={busy}
        body={
          <span className="block space-y-1.5">
            <span className="block">
              새로 채택 <b>{fresh.length}</b>건 · 다른 결과로 바꿈 <b>{moved.length}</b>건. 채택한
              값이 그 시험의 물성이 되어 요약값 표 · 재료 통계로 갑니다. 잘못 눌렀으면 끝난 뒤
              「되돌리기」 로 이전 채택으로 돌려놓습니다.
            </span>
            {moved.length > 0 && (
              <span className="block">
                바꾸는 것:{' '}
                {moved
                  .slice(0, 5)
                  .map((run) => run.record_name)
                  .join(', ')}
                {moved.length > 5 ? ` 외 ${moved.length - 5}건` : ''}
              </span>
            )}
            {loud.length > 0 && (
              <span className="block text-amber-700 dark:text-amber-400">
                중앙값에서 문턱({threshold}%)보다 먼 것이 {loud.length}건 들어 있습니다 — 그 곡선을
                보셨는지 확인하세요.
              </span>
            )}
            {locked.length > 0 && (
              <span className="block">
                고칠 수 없는 시험 {locked.length}건은 이번 채택에서 빠집니다 — 등록자 · 편집을 받은
                부서 · 자료 관리자가 합니다(줄의 자물쇠에 누구에게 물을지 적혀 있습니다).
              </span>
            )}
          </span>
        }
        onConfirm={() => void adopt()}
        onClose={() => setConfirming(false)}
      />
    </section>
  )
}

function BoardRow({
  run,
  chosen,
  keys,
  spread,
  loud,
  focused,
  checked,
  checkable,
  onCheck,
  onFocus,
  onPick,
}: {
  run: RunOverview
  chosen: ResultBrief | null
  keys: string[]
  spread: Spread | null
  loud: boolean
  focused: boolean
  checked: boolean
  checkable: boolean
  onCheck: () => void
  onFocus: () => void
  onPick: (resultId: string) => void
}) {
  return (
    <TableRow
      data-state={focused ? 'selected' : undefined}
      className={`cursor-pointer align-top ${loud ? 'bg-amber-500/5' : ''}`}
      onClick={onFocus}
    >
      <TableCell onClick={(event) => event.stopPropagation()}>
        <input
          type="checkbox"
          aria-label={`${run.record_name} 채택`}
          checked={checked}
          disabled={!checkable}
          onChange={onCheck}
        />
      </TableCell>
      <TableCell>
        <span className="block font-mono">{run.code ?? '—'}</span>
        <span className="block">{run.record_name}</span>
        {run.material_name && (
          <span className="text-muted-foreground block">{run.material_name}</span>
        )}
      </TableCell>
      <TableCell onClick={(event) => event.stopPropagation()}>
        {!run.found ? (
          <Missing>볼 수 없는 시험입니다</Missing>
        ) : run.results.length === 0 ? (
          <Missing>처리 결과가 없습니다</Missing>
        ) : (
          <select
            aria-label={`${run.record_name} 결과`}
            className={SELECT}
            value={chosen?.id ?? ''}
            onChange={(event) => onPick(event.target.value)}
          >
            {run.results.map((result) => (
              <option key={result.id} value={result.id}>
                {resultName(result)}
              </option>
            ))}
          </select>
        )}
      </TableCell>
      <TableCell>
        {chosen &&
          headlineOf(chosen, keys).map((scalar) => (
            <span key={scalar.key} className="block whitespace-nowrap">
              <span className="text-muted-foreground">{scalar.label}</span>{' '}
              <span className="font-mono tabular-nums">
                {formatScalar(scalar.value, scalar.si_unit, scalar.dimension ?? undefined)}
              </span>
            </span>
          ))}
      </TableCell>
      <TableCell>
        {spread ? (
          <span
            className={`whitespace-nowrap tabular-nums ${loud ? 'font-medium text-amber-700 dark:text-amber-400' : ''}`}
          >
            {percent(spread.ratio)} <span className="text-muted-foreground">{spread.label}</span>
          </span>
        ) : (
          <Missing>—</Missing>
        )}
      </TableCell>
      <TableCell>
        <State run={run} chosen={chosen} />
      </TableCell>
    </TableRow>
  )
}

/** 값이 아닌 것 — 흐리게(표의 규칙). */
function Missing({ children }: { children: ReactNode }) {
  return <span className="text-muted-foreground">{children}</span>
}

function State({ run, chosen }: { run: RunOverview; chosen: ResultBrief | null }) {
  if (!run.found || run.results.length === 0) return <Missing>—</Missing>
  if (run.access?.can_edit === false) {
    return (
      <span className="text-muted-foreground flex items-center gap-1" title={run.access.reason ?? ''}>
        <Lock className="size-3.5" />
        고칠 수 없음
      </span>
    )
  }
  if (run.adopted_result_id && run.adopted_result_id === chosen?.id) {
    return <Badge className="bg-emerald-600 hover:bg-emerald-600">채택됨</Badge>
  }
  if (run.adopted_result_id) {
    return (
      <Badge variant="outline" className="border-amber-500/60 text-amber-700 dark:text-amber-400">
        바꿈
      </Badge>
    )
  }
  return <Badge variant="outline">채택 전</Badge>
}

/**
 * 겹쳐 보기 — 같은 시험 종류의 고른 결과들을 **한 판에.** 보고 있는 시험은 굵게, 문턱을 넘은
 * 것은 주황으로. 축이 다른 결과(공칭 열이 없는 것)는 겹치지 않는다 — 다른 축의 선을 한 판에
 * 그리면 모양을 견줄 수 없다.
 */
function Overlay({
  runs,
  focus,
  choose,
  over,
}: {
  runs: RunOverview[]
  focus: RunOverview
  choose: (run: RunOverview) => ResultBrief | null
  over: (run: RunOverview) => boolean
}) {
  const [lines, setLines] = useState<Record<string, ResultLine | null>>({})
  const [error, setError] = useState<Error | null>(null)

  // 보고 있는 것 · 튀는 것이 먼저 — 상한에 걸려도 그것들은 그린다.
  const wanted = [focus, ...runs.filter(over), ...runs]
    .map((run) => choose(run)?.id)
    .filter((id): id is string => Boolean(id))
  const ids = [...new Set(wanted)].slice(0, LINES_MAX)
  const missing = ids.filter((id) => !(id in lines))

  useEffect(() => {
    if (missing.length === 0) return
    let cancelled = false
    processingApi
      .lines(missing)
      .then((got) => {
        if (cancelled) return
        const next: Record<string, ResultLine | null> = Object.fromEntries(
          missing.map((id) => [id, null])
        )
        for (const line of got) next[line.result_id] = line
        setLines((before) => ({ ...before, ...next }))
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught : new Error('곡선을 읽지 못했습니다.'))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missing.join(',')])

  const focusId = choose(focus)?.id
  const main = focusId ? lines[focusId] : undefined
  if (error) return <ErrorNotice error={error} />
  if (!focusId) return null
  if (main === undefined) return <p className="text-muted-foreground text-sm">곡선을 읽는 중…</p>
  if (main === null || main.points.length === 0) {
    return <p className="text-muted-foreground text-sm">이 결과에는 그릴 곡선이 없습니다.</p>
  }

  const shown = (line: ResultLine): [number, number][] =>
    line.points.map(([x, y]) => [toDisplay(x, line.units[line.x]), toDisplay(y, line.units[line.y])])
  const byRun = new Map(runs.map((run) => [choose(run)?.id, run]))
  const others = ids
    .filter((id) => id !== focusId)
    .map((id) => lines[id])
    .filter(
      (line): line is ResultLine =>
        line !== undefined && line !== null && line.x === main.x && line.y === main.y
    )
  const loudCount = others.filter((line) => {
    const run = byRun.get(line.result_id)
    return run ? over(run) : false
  }).length

  return (
    <div aria-label="겹쳐 보기" className="rounded-md border p-3">
      <h3 className="mb-2 flex flex-wrap items-baseline gap-2 font-medium">
        겹쳐 보기
        <span className="text-muted-foreground text-xs font-normal">
          {[focus.material_name, focus.test_type_label, focus.orientation]
            .filter(Boolean)
            .join(' · ')}{' '}
          {others.length + 1}건 · 보고 있는 시험이 굵은 선
        </span>
      </h3>
      <CurveChart
        points={shown(main)}
        pointsLabel={focus.record_name}
        xLabel={axisLabel(main.x, main.units[main.x])}
        yLabel={axisLabel(main.y, main.units[main.y])}
        height={300}
        background={others.map((line) => {
          const run = byRun.get(line.result_id)
          return {
            points: shown(line),
            label: run?.record_name ?? line.result_id,
            tone: run && over(run) ? 'stroke-amber-500 dark:stroke-amber-400' : undefined,
          }
        })}
      />
      <ul className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <li className="flex items-center gap-1.5">
          <span className="bg-primary inline-block h-0.5 w-4" />
          보고 있는 시험
        </li>
        <li className="flex items-center gap-1.5">
          <span className="inline-block w-4 border-t-2 border-sky-600 dark:border-sky-400" />
          다른 시험
        </li>
        {loudCount > 0 && (
          <li className="flex items-center gap-1.5">
            <span className="inline-block w-4 border-t-2 border-amber-500 dark:border-amber-400" />
            중앙값에서 먼 시험 {loudCount}
          </li>
        )}
      </ul>
    </div>
  )
}

/**
 * 한 건 자세히 — **처리 전/후를 그 결과 탭의 그림 그대로.** 지금 채택이 따로 있으면 「지금 채택
 * → 고른 것」 의 값 차이를 함께 — 바꾸기 전에 무엇이 바뀌는지가 보여야 한다.
 */
function Detail({ run, chosen }: { run: RunOverview; chosen: ResultBrief | null }) {
  const adopted = run.results.find((one) => one.id === run.adopted_result_id)
  const diffs =
    adopted && chosen && adopted.id !== chosen.id
      ? changesBetween(adopted.scalars, chosen.scalars).filter(
          (one) => one.ratio === null || Math.abs(one.ratio) >= 0.001
        )
      : []
  return (
    <div aria-label="한 건 자세히" className="rounded-md border p-3">
      <h3 className="mb-2 flex flex-wrap items-center gap-2 font-medium">
        {run.record_name}
        <Button size="sm" variant="ghost" className="ml-auto" asChild>
          <Link to={`/test-runs/${run.test_run_id}?tab=results`}>
            이 시험 열기 <ExternalLink className="size-3.5" />
          </Link>
        </Button>
      </h3>
      {chosen === null ? (
        <p className="text-muted-foreground text-sm">
          {run.found ? '처리 결과가 없습니다.' : '볼 수 없는 시험입니다.'}
        </p>
      ) : (
        <>
          {diffs.length > 0 && (
            <div className="mb-3 space-y-0.5 text-xs" aria-label="지금 채택과 차이">
              <p className="text-muted-foreground">지금 채택 → 고른 결과</p>
              {diffs.slice(0, 6).map((one) => (
                <div key={one.key} className="flex items-baseline gap-1.5">
                  <span className="text-muted-foreground min-w-24 truncate">{one.label}</span>
                  <span className="text-muted-foreground font-mono tabular-nums">
                    {one.before === null
                      ? '—'
                      : formatScalar(one.before, one.unit, one.dimension ?? undefined)}
                  </span>
                  <ArrowRight className="size-3 shrink-0 opacity-50" />
                  <span className="font-mono tabular-nums">
                    {one.after === null
                      ? '—'
                      : formatScalar(one.after, one.unit, one.dimension ?? undefined)}
                  </span>
                  {one.ratio !== null && <span className="tabular-nums">{percent(one.ratio)}</span>}
                </div>
              ))}
            </div>
          )}
          {/* **결과 탭의 그 그림이다** — 자르기 전 공칭 곡선 · E 선 · 오프셋 선 · 항복점. 따로
              그리면 두 화면이 같은 결과를 놓고 다른 그림을 보인다. */}
          <ResultCurve key={chosen.id} resultId={chosen.id} />
        </>
      )}
    </div>
  )
}

/** 채택한 뒤 — 건별로 무엇이 됐나, 그리고 되돌리기. */
function Outcome({
  done,
  undone,
  busy,
  onUndo,
}: {
  done: AdoptManyOut
  undone: boolean
  busy: boolean
  onUndo: () => void
}) {
  const failed = done.items.filter((one) => one.status === 'failed')
  return (
    <div
      aria-label="채택 결과"
      className="space-y-2 rounded-md border border-emerald-600/40 bg-emerald-500/5 p-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        {undone ? (
          <b>되돌렸습니다 — 이전 채택으로 돌려놓았습니다.</b>
        ) : (
          <>
            <b>{done.changed}건을 채택했습니다.</b>
            {done.unchanged > 0 && <span>이미 그대로 {done.unchanged}건.</span>}
            {done.failed > 0 && <Badge variant="destructive">실패 {done.failed}</Badge>}
          </>
        )}
        {!undone && done.changed > 0 && (
          <Button size="sm" variant="outline" className="ml-auto" disabled={busy} onClick={onUndo}>
            <Undo2 className="size-3.5" />
            {busy ? '되돌리는 중…' : '되돌리기'}
          </Button>
        )}
      </div>
      {!undone && failed.length > 0 && (
        <ul className="space-y-0.5">
          {failed.map((one) => (
            <li key={one.test_run_id} className="text-destructive">
              <span className="font-mono">{one.record_name}</span> — {one.error}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
