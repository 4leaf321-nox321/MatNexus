/**
 * 물성 분석 — **다섯 물음, 한 화면.**
 *
 *     비교        어느 재료가 센가
 *     분포        우리 값이 보통 어디쯤인가 · 이상치는 무엇인가
 *     사양 대비   카탈로그 값과 우리가 잰 값이 얼마나 다른가
 *     추이        해가 가며 값이 흐르는가
 *     커버리지    무엇을 아직 안 쟀는가
 *
 * ## 값은 표시 단위로 보인다
 *
 * 서버는 언제나 SI 로 준다(Pa). 사람이 읽는 자리에서는 표(`shared/units`)를 거쳐
 * MPa 로 보인다 — **라벨에 단위를 손으로 적지 않는다**(AGENTS.md). 표만 바꾸면
 * 라벨이 옛 단위를 적은 채 새 값을 받는 사고가 그래서 안 난다.
 *
 * ## 안 채택된 것은 안 센다, 다만 말한다
 *
 * 채택은 「이 시험의 물성은 이것」 이라는 사람의 결정이다(ADR 0007). 그 전 값은
 * 아직 물성이 아니라 평균에 섞으면 안 된다. 대신 **몇 건이 빠졌는지 화면이
 * 말한다** — 조용히 빼면 n 이 왜 이 수인지 아무도 모른다.
 */

import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { analysisApi } from '@/modules/statistics/analysisApi'
import type { AnalysisScalar, Spread } from '@/modules/statistics/analysisApi'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'
import { axisLabel, toDisplay } from '@/shared/units'

const TABS = [
  { key: 'compare', label: '재료 비교' },
  { key: 'distribution', label: '분포' },
  { key: 'spec', label: '사양 대비' },
  { key: 'trend', label: '추이' },
  { key: 'coverage', label: '커버리지' },
] as const
type Tab = (typeof TABS)[number]['key']

/** SI 값을 표시 단위로. **자릿수는 크기에 맞춘다** — 0.0000002 도 200000 도 안 읽힌다. */
export function show(value: number, siUnit: string): string {
  const shown = toDisplay(value, siUnit)
  const size = Math.abs(shown)
  if (size === 0) return '0'
  if (size >= 1000) return shown.toFixed(0)
  if (size >= 10) return shown.toFixed(1)
  if (size >= 0.1) return shown.toFixed(3)
  return shown.toPrecision(3)
}

const TABLE_PAD =
  '[&_td]:px-3 [&_th]:px-3 [&_td:first-child]:pl-4 [&_th:first-child]:pl-4 ' +
  '[&_td:last-child]:pr-4 [&_th:last-child]:pr-4'

export default function AnalysisPage() {
  const [params, setParams] = useSearchParams()
  const wanted = params.get('tab')
  const tab: Tab = TABS.some((one) => one.key === wanted) ? (wanted as Tab) : 'compare'

  return (
    <div>
      <PageHeader
        title="물성 분석"
        description="채택된 결과만 셉니다 — 처리 전 값은 아직 물성이 아닙니다."
      />
      <Tabs value={tab} onValueChange={(next) => setParams({ tab: next })} className="mb-4">
        <TabsList>
          {TABS.map((one) => (
            <TabsTrigger key={one.key} value={one.key}>
              {one.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {tab === 'compare' && <CompareTab />}
      {tab === 'distribution' && <DistributionTab />}
      {tab === 'spec' && <SpecGapTab />}
      {tab === 'trend' && <TrendTab />}
      {tab === 'coverage' && <CoverageTab />}
    </div>
  )
}

/** 빠진 건수 — **말하지 않으면 n 이 설명되지 않는다.** 0 이면 줄이 사라진다. */
function Skipped({ count }: { count: number }) {
  if (count === 0) return null
  return (
    <p className="text-muted-foreground mt-2 text-xs">
      채택되지 않아 {count}건이 빠졌습니다 — 처리·채택을 마치면 여기에 들어옵니다.
    </p>
  )
}

/** 항목 고르기. 건수를 함께 보여 준다 — 고르기 전에 몇 건인지 알아야 한다. */
function ScalarPicker({
  scalars,
  value,
  onChange,
}: {
  scalars: AnalysisScalar[]
  value: string
  onChange: (next: string) => void
}) {
  if (scalars.length === 0) return null
  return (
    <select
      aria-label="물성 항목"
      className="border-input bg-background h-8 rounded-md border px-2 text-sm"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {scalars.map((one) => (
        <option key={one.key} value={one.key}>
          {one.label} ({one.count})
        </option>
      ))}
    </select>
  )
}

function GroupPicker({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (next: string) => void
  options: readonly { key: string; label: string }[]
}) {
  return (
    <div className="flex gap-1">
      {options.map((one) => (
        <Button
          key={one.key}
          size="sm"
          variant={value === one.key ? 'default' : 'outline'}
          onClick={() => onChange(one.key)}
        >
          {one.label}
        </Button>
      ))}
    </div>
  )
}

// --- ① 재료 비교 -------------------------------------------------------------

/**
 * 재료 몇 개를 나란히. **항목이 열, 재료가 행이다.**
 *
 * 재료를 고르지 않으면 빈 표다 — 전체를 자동으로 세우면 94개짜리 표가 나오고,
 * 그건 비교가 아니라 목록이다.
 */
function CompareTab() {
  const [picked, setPicked] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const compare = useResource(() => analysisApi.compare(picked), [picked.join(',')])

  // 고른 재료들이 **함께 가진** 항목만 열로 세운다 — 한쪽에만 있는 값을 나란히
  // 놓으면 빈 칸이 「0」 으로 읽힌다.
  const columns = useMemo(() => {
    const rows = compare.data?.materials ?? []
    if (rows.length === 0) return []
    const counts = new Map<string, { label: string; unit: string; n: number }>()
    for (const row of rows) {
      for (const cell of row.scalars) {
        const at = counts.get(cell.scalar_key)
        counts.set(cell.scalar_key, {
          label: cell.scalar_label,
          unit: cell.si_unit,
          n: (at?.n ?? 0) + 1,
        })
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1].n - a[1].n || a[1].label.localeCompare(b[1].label))
      .map(([key, one]) => ({ key, ...one }))
  }, [compare.data])

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => setOpen(true)}>
          재료 고르기
        </Button>
        {picked.length > 0 && (
          <span className="text-muted-foreground text-xs">{picked.length}개 담김</span>
        )}
      </div>
      {open && (
        <MaterialPickerDialog picked={picked} onClose={() => setOpen(false)} onChange={setPicked} />
      )}

      {picked.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {(compare.data?.materials ?? []).map((one) => (
            <Badge key={one.material_id} variant="outline" className="gap-1">
              {one.material_name}
              <button
                type="button"
                aria-label={`${one.material_name} 빼기`}
                className="text-muted-foreground hover:text-foreground"
                onClick={() => setPicked((now) => now.filter((id) => id !== one.material_id))}
              >
                ×
              </button>
            </Badge>
          ))}
          <Button size="sm" variant="ghost" onClick={() => setPicked([])}>
            모두 빼기
          </Button>
        </div>
      )}

      <ErrorNotice error={compare.error} className="mb-3" />
      {picked.length === 0 && (
        <p className="text-muted-foreground text-sm">
          「재료 고르기」 를 눌러 담아 주세요 — 채택된 물성이 있는 재료만 뜹니다. 두 개부터 표가
          뜻이 있습니다.
        </p>
      )}
      {picked.length > 0 && columns.length === 0 && !compare.loading && (
        <p className="text-muted-foreground text-sm">고른 재료에 채택된 물성이 없습니다.</p>
      )}
      {columns.length > 0 && (
        <div className={`overflow-x-auto rounded-md border ${TABLE_PAD}`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>재료</TableHead>
                {columns.map((one) => (
                  <TableHead key={one.key} className="text-center">
                    {axisLabel(one.label, one.unit)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {(compare.data?.materials ?? []).map((row) => (
                <TableRow key={row.material_id}>
                  <TableCell className="font-medium">
                    <Link
                      to={`/materials/${row.material_id}`}
                      className="text-primary hover:underline"
                    >
                      {row.material_name}
                    </Link>
                    <span className="text-muted-foreground ml-1 text-xs">{row.family}</span>
                  </TableCell>
                  {columns.map((column) => {
                    const cell = row.scalars.find((one) => one.scalar_key === column.key)
                    return (
                      <TableCell key={column.key} className="text-center tabular-nums">
                        {cell ? (
                          <>
                            <div>{show(cell.mean, cell.si_unit)}</div>
                            <div className="text-muted-foreground text-xs">
                              n={cell.count}
                              {/* **1건이면 흩어짐이 없다** — 0 은 「일정하다」 로 읽힌다. */}
                              {cell.sample_sd != null
                                ? ` · ±${show(cell.sample_sd, cell.si_unit)}`
                                : ''}
                            </div>
                          </>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <Skipped count={compare.data?.skipped_unadopted ?? 0} />
    </div>
  )
}

/**
 * 재료 고르기 — **채택된 물성이 있는 것만 뜬다.**
 *
 * 자유 입력 칸이었다. 그러면 무엇을 칠 수 있는지 알 수 없고, 쳐서 찾은 재료에 물성이
 * 없으면 담고 나서야 빈 줄을 본다. 목록으로 바꾸고 **무엇을 몇 건 갖고 있는지**
 * 함께 보인다.
 */
function MaterialPickerDialog({
  picked,
  onClose,
  onChange,
}: {
  picked: string[]
  onClose: () => void
  onChange: (next: string[]) => void
}) {
  const list = useResource(() => analysisApi.materials(), [])
  const [term, setTerm] = useState('')
  const rows = useMemo(() => {
    const needle = term.trim().toLowerCase()
    const all = list.data ?? []
    if (!needle) return all
    return all.filter(
      (one) =>
        one.material_name.toLowerCase().includes(needle) ||
        one.family.toLowerCase().includes(needle) ||
        one.category.toLowerCase().includes(needle)
    )
  }, [list.data, term])

  function toggle(id: string) {
    onChange(picked.includes(id) ? picked.filter((one) => one !== id) : [...picked, id])
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>재료 고르기</DialogTitle>
          <DialogDescription>
            채택된 물성이 있는 재료만 있습니다 — 물성이 없는 재료는 담아도 빈 줄입니다.
          </DialogDescription>
        </DialogHeader>
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="이름·재료군·분류로 좁히기"
          aria-label="재료 찾기"
        />
        <ErrorNotice error={list.error} />
        {list.loading && !list.data && (
          <p className="text-muted-foreground text-sm">불러오는 중…</p>
        )}
        {list.data && rows.length === 0 && (
          <p className="text-muted-foreground text-sm">맞는 재료가 없습니다.</p>
        )}
        {rows.length > 0 && (
          <ul className="max-h-96 divide-y overflow-y-auto rounded-md border text-sm">
            {rows.map((one) => (
              <li key={one.material_id}>
                <button
                  type="button"
                  className="hover:bg-muted flex w-full items-center gap-2 px-3 py-2 text-left"
                  aria-pressed={picked.includes(one.material_id)}
                  onClick={() => toggle(one.material_id)}
                >
                  <input
                    type="checkbox"
                    readOnly
                    checked={picked.includes(one.material_id)}
                    tabIndex={-1}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{one.material_name}</span>
                    <span className="text-muted-foreground ml-1 text-xs">
                      {one.family} · {one.category}
                    </span>
                  </span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    항목 {one.scalar_count} · 시험 {one.run_count}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-between">
          <Button variant="ghost" onClick={() => onChange([])} disabled={picked.length === 0}>
            모두 빼기
          </Button>
          <Button onClick={onClose}>{picked.length}개 담고 닫기</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 항목 토글 — **여럿 고르면 열이 여럿이 된다.**
 *
 * 드롭다운 하나로는 「인장강도와 탄성계수를 나란히」 를 못 본다. 켜고 끄는 목록으로
 * 두되 **하나는 남긴다** — 다 끄면 빈 표가 되고 그건 고장으로 읽힌다.
 */
function ScalarToggles({
  scalars,
  picked,
  onChange,
}: {
  scalars: AnalysisScalar[]
  picked: string[]
  onChange: (next: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  if (scalars.length === 0) return null
  const label =
    picked.length === 1
      ? (scalars.find((one) => one.key === picked[0])?.label ?? '물성 항목')
      : `물성 항목 ${picked.length}개`

  return (
    <div className="relative">
      <Button size="sm" variant="outline" aria-expanded={open} onClick={() => setOpen((n) => !n)}>
        {label} ▾
      </Button>
      {open && (
        <>
          <button
            type="button"
            aria-label="항목 목록 닫기"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <ul className="bg-background absolute z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-md border p-1 text-sm shadow-md">
            {scalars.map((one) => {
              const on = picked.includes(one.key)
              return (
                <li key={one.key}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={on}
                    className="hover:bg-muted flex w-full items-center gap-2 rounded px-2 py-1.5 text-left"
                    onClick={() =>
                      onChange(
                        on
                          ? // **마지막 하나는 못 끈다** — 다 끄면 빈 표가 되고 그건
                            // 고장으로 읽힌다.
                            picked.length > 1
                            ? picked.filter((key) => key !== one.key)
                            : picked
                          : [...picked, one.key]
                      )
                    }
                  >
                    <input type="checkbox" readOnly checked={on} tabIndex={-1} aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{one.label}</span>
                    <span className="text-muted-foreground text-xs">{one.count}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}

// --- ② 분포 ------------------------------------------------------------------

// **사업부는 없다.** 흩어짐은 재료의 성질이지 누가 쟀는가의 성질이 아니다 —
// 사업부별 건수는 홈에 있다(실사용 요청, 2026-08-29).
const DISTRIBUTION_GROUPS = [
  { key: 'family', label: '재료군' },
  { key: 'category', label: '분류' },
] as const

/**
 * 흩어짐 — **이상치가 곧 재시험 후보다.**
 *
 * 상자그림을 글자 없이 그리면 「예쁜 그림」 이 되고 만다. 여기서는 상자와 함께
 * 숫자(중앙값·n·이상치 수)를 나란히 둔다 — 사람이 옮겨 적는 것은 숫자다.
 */
function DistributionTab() {
  const [scalars, setScalars] = useState<string[]>([])
  const [groupBy, setGroupBy] = useState<string>('family')
  const report = useResource(
    () => analysisApi.distribution(scalars, groupBy),
    [scalars.join(','), groupBy]
  )
  const data = report.data
  const selected = data?.selected ?? []

  /** 눈금은 **항목마다 따로**다 — 인장강도(수백 MPa)와 R²(0~1)를 같은 자로 재면
   *  한쪽이 선이 된다. 열마다 그 열의 범위로 그린다. */
  const bounds = useMemo(() => {
    const out: Record<string, { low: number; high: number }> = {}
    for (const one of selected) {
      const spans = (data?.groups ?? []).flatMap((group) => {
        const cell = group.cells[one.key]
        return cell ? [cell.minimum, cell.maximum, ...cell.outliers] : []
      })
      if (spans.length) out[one.key] = { low: Math.min(...spans), high: Math.max(...spans) }
    }
    return out
  }, [data, selected])

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ScalarToggles
          scalars={data?.scalars ?? []}
          picked={selected.map((one) => one.key)}
          onChange={setScalars}
        />
        <GroupPicker value={groupBy} onChange={setGroupBy} options={DISTRIBUTION_GROUPS} />
      </div>
      <ErrorNotice error={report.error} className="mb-3" />
      {data && data.groups.length === 0 && (
        <p className="text-muted-foreground text-sm">채택된 물성이 아직 없습니다.</p>
      )}
      {data && data.groups.length > 0 && (
        <div className={`overflow-x-auto rounded-md border ${TABLE_PAD}`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{DISTRIBUTION_GROUPS.find((o) => o.key === groupBy)?.label}</TableHead>
                {selected.map((one) => (
                  <TableHead key={one.key} className="text-center">
                    {axisLabel(one.label, one.si_unit)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.groups.map((row) => (
                <TableRow key={row.group}>
                  <TableCell className="font-medium">{row.group}</TableCell>
                  {selected.map((one) => {
                    const cell = row.cells[one.key]
                    const span = bounds[one.key]
                    return (
                      <TableCell key={one.key} className="min-w-56 text-center">
                        {cell && span ? (
                          <>
                            <BoxPlot spread={cell} low={span.low} high={span.high} />
                            <div className="text-muted-foreground mt-0.5 text-xs tabular-nums">
                              중앙 {show(cell.median, one.si_unit)} · n={cell.count}
                              {cell.outliers.length > 0 && (
                                <span className="ml-1 text-amber-700">
                                  이상치 {cell.outliers.length}
                                </span>
                              )}
                            </div>
                          </>
                        ) : (
                          <span className="text-muted-foreground text-xs">
                            {cell === null ? '2건 미만' : '—'}
                          </span>
                        )}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <Skipped count={data?.skipped_unadopted ?? 0} />
    </div>
  )
}

/** 상자그림 한 칸. 라이브러리 없이 — 상자 하나에 recharts 를 부를 이유가 없다. */
function BoxPlot({ spread, low, high }: { spread: Spread; low: number; high: number }) {
  const span = high - low || 1
  const at = (value: number) => ((value - low) / span) * 100
  return (
    <svg viewBox="0 0 100 20" className="h-5 w-full" role="img" aria-label="흩어짐">
      <line
        x1={at(spread.minimum)}
        x2={at(spread.maximum)}
        y1={10}
        y2={10}
        stroke="currentColor"
        strokeOpacity={0.4}
        strokeWidth={0.6}
      />
      <rect
        x={at(spread.q1)}
        y={4}
        width={Math.max(at(spread.q3) - at(spread.q1), 0.6)}
        height={12}
        fill="currentColor"
        fillOpacity={0.15}
        stroke="currentColor"
        strokeOpacity={0.5}
        strokeWidth={0.5}
      />
      <line
        x1={at(spread.median)}
        x2={at(spread.median)}
        y1={4}
        y2={16}
        stroke="currentColor"
        strokeWidth={1}
      />
      {spread.outliers.map((one, index) => (
        <circle key={index} cx={at(one)} cy={10} r={1.2} fill="#f59e0b" />
      ))}
    </svg>
  )
}

// --- ③ 사양 대비 --------------------------------------------------------------

/**
 * 선언한 값 vs 잰 값. **이 화면 아니면 알 수 없는 숫자다** — 공급사와 이야기할 때
 * 그대로 쓴다.
 *
 * 못 견준 항목을 숨기지 않는다. 「차이 없음」 과 「견줄 값이 없음」 은 다르다.
 */
function SpecGapTab() {
  const report = useResource(() => analysisApi.specGap(), [])
  const data = report.data

  return (
    <div>
      <ErrorNotice error={report.error} className="mb-3" />
      {data && data.rows.length === 0 && (
        <p className="text-muted-foreground text-sm">
          견줄 수 있는 항목이 없습니다 — 재료에 선언 물성을 적고, 같은 이름의 물성을 재면 여기에
          나타납니다.
        </p>
      )}
      {data && data.rows.length > 0 && (
        <div className={`overflow-x-auto rounded-md border ${TABLE_PAD}`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>재료</TableHead>
                <TableHead>항목</TableHead>
                <TableHead className="text-center">선언값</TableHead>
                <TableHead className="text-center">잰 값</TableHead>
                <TableHead className="text-center">차이</TableHead>
                <TableHead>근거</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row) => {
                const percent = row.gap_ratio * 100
                const big = Math.abs(percent) >= 10
                return (
                  <TableRow key={`${row.material_id}-${row.item}`}>
                    <TableCell className="font-medium">
                      <Link
                        to={`/materials/${row.material_id}`}
                        className="text-primary hover:underline"
                      >
                        {row.material_name}
                      </Link>
                    </TableCell>
                    <TableCell>{row.item}</TableCell>
                    <TableCell className="text-center tabular-nums">
                      {show(row.declared_si, row.si_unit)}
                    </TableCell>
                    <TableCell className="text-center tabular-nums">
                      {show(row.measured_mean, row.si_unit)}
                      <span className="text-muted-foreground ml-1 text-xs">
                        n={row.measured_count}
                      </span>
                    </TableCell>
                    <TableCell className="text-center tabular-nums">
                      {/* **부호가 방향을 말한다.** 절댓값만 보이면 "우리가 더 센가"
                          를 알 수 없다. 10% 를 넘으면 눈에 띄게. */}
                      <span className={big ? 'font-medium text-amber-700' : ''}>
                        {percent > 0 ? '+' : ''}
                        {percent.toFixed(1)}%
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {row.declared_reference ?? row.declared_source ?? '—'}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
      {data && data.unmatched_items.length > 0 && (
        <p className="text-muted-foreground mt-2 text-xs">
          선언은 있으나 잰 값이 없어 못 견준 항목: {data.unmatched_items.join(' · ')}
        </p>
      )}
    </div>
  )
}

// --- ④ 추이 ------------------------------------------------------------------

const TREND_GROUPS = [
  { key: 'division', label: '사업부' },
  { key: 'material', label: '재료' },
  { key: 'family', label: '재료군' },
] as const

/** 해가 가며 값이 흐르는가. **해는 시험일** — 등록일로 세면 이관한 해에 몰린다. */
function TrendTab() {
  const [scalar, setScalar] = useState('')
  const [groupBy, setGroupBy] = useState<string>('division')
  const report = useResource(() => analysisApi.trend(scalar, groupBy), [scalar, groupBy])
  const data = report.data
  const years = useMemo(
    () =>
      [...new Set((data?.series ?? []).flatMap((one) => one.points.map((p) => p.period)))].sort(),
    [data]
  )

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ScalarPicker
          scalars={data?.scalars ?? []}
          value={data?.scalar_key ?? ''}
          onChange={setScalar}
        />
        <GroupPicker value={groupBy} onChange={setGroupBy} options={TREND_GROUPS} />
      </div>
      <ErrorNotice error={report.error} className="mb-3" />
      {data && data.series.length === 0 && (
        <p className="text-muted-foreground text-sm">채택된 물성이 아직 없습니다.</p>
      )}
      {data && data.series.length > 0 && (
        <div className={`overflow-x-auto rounded-md border ${TABLE_PAD}`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{TREND_GROUPS.find((o) => o.key === groupBy)?.label}</TableHead>
                {years.map((year) => (
                  <TableHead key={year} className="text-center">
                    {year}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.series.map((row) => (
                <TableRow key={row.key}>
                  <TableCell className="font-medium">{row.label}</TableCell>
                  {years.map((year) => {
                    const point = row.points.find((one) => one.period === year)
                    return (
                      <TableCell key={year} className="text-center tabular-nums">
                        {point ? (
                          <>
                            <div>{show(point.mean, data.si_unit)}</div>
                            <div className="text-muted-foreground text-xs">n={point.count}</div>
                          </>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <p className="text-muted-foreground mt-2 text-xs">
        해는 <strong>시험일</strong> 기준입니다 — 옛 시험을 오늘 올려도 그 해로 셉니다.
      </p>
      <Skipped count={data?.skipped_unadopted ?? 0} />
    </div>
  )
}

// --- ⑤ 커버리지 ---------------------------------------------------------------

/**
 * 재료군·분류 × 시험 종류. **빈 칸이 다음에 할 시험이다.**
 *
 * 재료마다 한 줄이면 94줄이 되고, 그 표에서는 「무엇을 안 쟀나」 가 안 읽힌다.
 * 분류로 접으면 「Metal/Steel 은 인장은 했고 점탄성은 안 했다」 가 한 줄에 온다.
 */
function CoverageTab() {
  const report = useResource(() => analysisApi.coverage(), [])
  const data = report.data
  const [onlyGaps, setOnlyGaps] = useState(false)

  const rows = useMemo(() => {
    const all = data?.groups ?? []
    if (!onlyGaps) return all
    const types = data?.test_types ?? []
    return all.filter((row) => types.some((type) => !row.cells[type.key]))
  }, [data, onlyGaps])

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Button
          size="sm"
          variant={onlyGaps ? 'default' : 'outline'}
          onClick={() => setOnlyGaps((now) => !now)}
        >
          빈 칸 있는 것만
        </Button>
        <span className="text-muted-foreground text-xs">
          칸은 <strong>시험한 재료 수 / 그 분류의 재료 수</strong>, 괄호는 채택된 시험 수입니다.
        </span>
      </div>
      <ErrorNotice error={report.error} className="mb-3" />
      {data && rows.length === 0 && (
        <p className="text-muted-foreground text-sm">보여 줄 재료가 없습니다.</p>
      )}
      {data && rows.length > 0 && (
        <div className={`overflow-x-auto rounded-md border ${TABLE_PAD}`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>재료군</TableHead>
                <TableHead>분류</TableHead>
                <TableHead className="text-center">재료</TableHead>
                {data.test_types.map((type) => (
                  <TableHead key={type.key} className="text-center">
                    {type.label}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={`${row.family}-${row.category}`}>
                  <TableCell className="font-medium">{row.family}</TableCell>
                  <TableCell>{row.category}</TableCell>
                  <TableCell className="text-center tabular-nums">{row.material_count}</TableCell>
                  {data.test_types.map((type) => {
                    const cell = row.cells[type.key]
                    // **몇 개 중 몇 개인가.** 분류에 재료가 10개인데 1개만 쟀으면
                    // 「쟀다」 로 읽히면 안 된다.
                    const partial = cell && cell.material_count < row.material_count
                    return (
                      <TableCell key={type.key} className="text-center tabular-nums">
                        {cell ? (
                          <span
                            className={
                              cell.adopted_count === 0
                                ? 'text-amber-700'
                                : partial
                                  ? 'text-muted-foreground'
                                  : undefined
                            }
                          >
                            {cell.material_count}/{row.material_count}
                            <span className="text-muted-foreground text-xs">
                              {' '}
                              ({cell.adopted_count})
                            </span>
                          </span>
                        ) : (
                          /* **빈 칸이 요점이다.** 0 을 적으면 「쟀는데 0건」 으로 읽힌다. */
                          <span className="text-muted-foreground/40">·</span>
                        )}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
