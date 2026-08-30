/**
 * 재료 물성 — **여러 시편이 같은 것을 말하는가.**
 *
 * 시편 하나의 물성은 그 시편의 물성이다. "이 재료의 항복강도" 라고 말하려면 여러
 * 번 재고 그 흩어짐을 봐야 한다. 이 화면이 그 흩어짐을 보여 준다.
 *
 * ## 묶음은 시험종류 + 방향이다
 *
 * 인장은 압연 방향에 따라 물성이 다르다. MD 5개와 TD 5개를 한 통계로 묶으면 CV 가
 * 15% 로 나오는데, **그것은 산포가 아니라 다른 것을 섞은 것이다.**
 *
 * ## 아무것도 조용히 빠지지 않는다
 *
 * 채택 안 된 시험이 몇 건인지, 이상치 후보가 무엇인지, 곡선을 왜 못 냈는지 —
 * 전부 이유와 함께 적는다. n 이 왜 그 수인지 모르면 그 평균은 근거가 없다.
 *
 * ## 평균과 중앙값을 나란히
 *
 * 표준편차는 이상치 하나에 크게 휘둘린다. 둘이 많이 다르다는 것 자체가 신호다.
 */

import { useState } from 'react'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Pencil,
  Save,
  Sigma,
} from 'lucide-react'

import { DistributionPanel } from '@/modules/statistics/DistributionPanel'
import { statisticsApi } from '@/modules/statistics/api'
import type { ScalarStats, StatisticsGroup } from '@/modules/statistics/api'
import { CurveChart } from '@/modules/tests/CurveChart'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import type { components } from '@/shared/api/schema'
import { cn } from '@/shared/lib/utils'
import { useResource } from '@/shared/hooks/useResource'
import { axisLabel, formatScalar, significant, toDisplay } from '@/shared/units'

/** 이 이상이면 흩어짐이 크다고 눈에 띄게 한다. **버리거나 고치지는 않는다.** */
const NOTABLE_CV = 0.05

/**
 * 재료에 적어 둔 값.
 *
 * **`materials/api` 에서 안 가져온다** — 모듈끼리 직접 부르지 않는 것이 이
 * 저장소의 규칙이고(`src/test/boundaries.test.ts`), 타입 하나 때문에 예외를
 * 늘리면 다음 사람은 그 예외를 근거로 함수도 가져온다. 스키마는 공용이다.
 */
type DeclaredProperty = components['schemas']['DeclaredPropertyOut']

/**
 * 글로벌 피팅 결과 — **시편 여럿의 데이터를 한 번에 적합한 것**(ADR 0020).
 *
 * 통계와 다르다: 통계는 시편 n개를 **세어 본 것**이고, 이쪽은 그 데이터를 모아
 * **한 번에 적합**한다(마스터커브 다섯 → Prony 계수 한 벌). 결과물이 곧 물성이므로
 * 다른 물성과 **한 표에 서야** 견줄 수 있다.
 */
type GroupResult = components['schemas']['GroupResultOut']
type GroupingSpec = components['schemas']['GroupingSpecOut']

interface Props {
  materialId: string
  /**
   * 재료에 적어 둔 값. **잰 값과 나란히 놓으려고 받는다.**
   *
   * 카드는 「잰 값 > 적은 값」 으로 자동으로 고르는데, 그 둘이 크게 어긋나면
   * 둘 중 하나가 틀린 것이다 — 지금은 그것을 볼 자리가 어디에도 없었다.
   */
  declared?: DeclaredProperty[]
  /**
   * 적어 둔 값을 고치러 간다. **없으면 편집 단추를 안 만든다** — 시료 화면처럼
   * 그 창을 들 수 없는 자리도 있다.
   */
  onEditDeclared?: (item: string) => void
  /**
   * 이 재료의 묶음 결과. **`materials` 가 가져와 넘긴다** — 모듈끼리 직접 부르지
   * 않는 것이 이 저장소의 규칙이고, 묶음 API 는 그쪽에 있다.
   */
  groupResults?: GroupResult[]
  /** 묶음 방법 목록. 값의 사람 이름이 여기서 온다(`makes_values`). */
  groupKinds?: GroupingSpec[]
  /**
   * 물성 상자 머리에 함께 세울 것 — **글로벌 피팅**.
   *
   * **아코디언 안에 두지 않는다**(2026-08-30). 묶음의 단위는 시험종류이고 방향은
   * 안 본다 — 「인장시험 MD」 카드 안에 두면 MD 만 묶는 것처럼 보이고, 접혀 있으면
   * 아예 안 보인다. 결과도 물성 표에 서므로 **더하는 자리가 그 머리에** 있는 것이
   * 맞다(선언 물성 추가와 같은 성격이다 — 물성을 늘리는 일).
   */
  groupSlot?: React.ReactNode
  /**
   * 물성 상자 오른쪽 위에 세울 것 — **선언 물성을 넣는 자리**.
   *
   * 제 상자를 따로 두면 값 목록이 없는 빈 상자가 화면 위쪽을 차지한다. 더하는
   * 일은 물성 목록에 하는 일이므로 그 머리에 붙는다.
   */
  header?: React.ReactNode
}

export function PropertiesPanel({
  materialId,
  declared = [],
  onEditDeclared,
  groupResults = [],
  groupKinds = [],
  groupSlot,
  header,
}: Props) {
  const stats = useResource(() => statisticsApi.forMaterial(materialId), [materialId])
  const [error, setError] = useState<Error | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const groups = stats.data?.groups ?? []
  // **어느 시험종류를 볼까.** `null` 이면 전부 — 종류가 늘어도 화면이 안 길어진다.
  const [kind, setKind] = useState<string | null>(null)
  const kinds: [string, string, number][] = [
    ...groups
      .reduce((seen, group) => {
        const found = seen.get(group.test_type_key)
        seen.set(group.test_type_key, [
          group.test_type_label,
          (found?.[1] ?? 0) + group.sample_count,
        ])
        return seen
      }, new Map<string, [string, number]>())
      .entries(),
  ].map(([key, [label, count]]) => [key, label, count])
  const shown = kind === null ? groups : groups.filter((one) => one.test_type_key === kind)

  /**
   * 사람이 직접 여닫은 것만 담는다. **기본값을 미리 채우지 않는다** — 채우면
   * 통계가 늦게 온 묶음이 그 판정을 못 받아 늘 접힌 채로 뜬다.
   */
  const [toggled, setToggled] = useState<Record<string, boolean>>({})
  const keyOf = (one: StatisticsGroup) => `${one.test_type_key}-${one.orientation}`
  const isOpen = (one: StatisticsGroup) => toggled[keyOf(one)] ?? speaks(one)
  // 하나라도 펴져 있으면 접는 쪽이 다음 할 일이다.
  const anyOpen = shown.some(isOpen)
  const setAll = (open: boolean) =>
    setToggled((was) => ({
      ...was,
      ...Object.fromEntries(shown.map((one) => [keyOf(one), open])),
    }))

  async function save(group: StatisticsGroup) {
    setError(null)
    try {
      await statisticsApi.save({
        material_id: materialId,
        test_type_key: group.test_type_key,
        orientation: group.orientation,
      })
      setSaved(`${group.test_type_label} · ${group.orientation}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('남기지 못했습니다.'))
    }
  }

  return (
    // **왼쪽은 결론, 오른쪽은 근거다.** 「이 재료 물성이 얼마인가」 와 「그게
    // 어디서 나왔나」 는 다른 물음이고, 앞엣것을 훨씬 자주 묻는다.
    //
    // 폭은 4:6 이다. 왼쪽은 표 세 열이라 남는 자리가 생기는데, 오른쪽은 8열 표와
    // 곡선이 다시 좌우로 갈리므로 **좁으면 그 안이 또 눌린다.**
    <section className="grid h-full min-h-0 gap-6 xl:grid-cols-[minmax(0,4fr)_minmax(0,6fr)]">
      <div className="min-h-0 space-y-4 overflow-y-auto pr-2">
      <ErrorNotice error={stats.error ?? error} className="mb-4" />

      {saved && (
        <div className="mb-4 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
          <b>{saved}</b> 통계를 남겼습니다. 지금 표본으로 낸 값이 그대로 박혀 있어, 시험이 더 붙어도
          그 값은 바뀌지 않습니다.
        </div>
      )}

      {/* **결론이 먼저다.** 아래 묶음 카드는 「이 평균을 믿어도 되나」 에 답하는데,
          그 앞에 「그래서 얼마인가」 가 있어야 한다 — 이 화면에 가장 자주 하는
          일이 그것이다. */}
      {/* **값이 하나도 없어도 상자는 뜬다.** 「선언 물성 추가」 가 그 머리에
          있으므로, 안 그리면 첫 값을 넣을 길이 사라진다. */}
      {(
        <PropertySummary
          groups={groups}
          declared={declared}
          groupResults={groupResults}
          groupKinds={groupKinds}
          onEditDeclared={onEditDeclared}
          actions={
            <>
              {header}
              {groupSlot}
            </>
          }
        />
      )}
      </div>

      {/* 오른쪽은 근거다 — 어느 시험에서 나왔고 얼마나 흩어졌나.
          **칩 줄은 스크롤에서 뺀다.** 무엇을 보고 있나(전체·인장·DMA)와 전체
          여닫기는 목록을 내려 보는 동안에도 손이 닿아야 한다 — 그것을 쓰려고
          위로 되돌아가면 보던 자리를 잃는다. */}
      <div className="flex min-h-0 flex-col">
        {/* **빈 안내도 근거 쪽이다.** 왼쪽에 두면 「물성이 없다」 로 읽히는데,
            없는 것은 시험이다 — 적어 둔 값만 있는 재료도 물성은 있다. */}
        {!stats.loading && groups.length === 0 && (
          <div className="text-muted-foreground shrink-0 rounded-md border py-12 text-center text-sm">
            <Sigma className="mx-auto mb-2 size-5 opacity-50" />
            아직 시험이 없습니다.
          </div>
        )}

      {/* **시험종류가 늘어도 화면이 안 길어진다.** 위 표가 값을 다 보이므로,
          아래 상세는 지금 보려는 종류의 것만 있으면 된다 — 종류가 다섯이면
          카드가 열 개 넘게 쌓이던 자리다. */}
      {groups.length > 1 && (
        <div className="mb-3 flex shrink-0 flex-wrap items-center gap-1">
          {kinds.length > 1 && (
            <Button
              size="sm"
              variant={kind === null ? 'secondary' : 'ghost'}
              className="h-7 text-xs"
              aria-pressed={kind === null}
              aria-label="모든 시험종류 보기"
              onClick={() => setKind(null)}
            >
              전체 {groups.length}
            </Button>
          )}
          {kinds.length > 1 &&
            kinds.map(([key, label, count]) => (
            <Button
              key={key}
              size="sm"
              variant={kind === key ? 'secondary' : 'ghost'}
              className="h-7 text-xs"
              aria-pressed={kind === key}
              aria-label={`${label} 만 보기`}
              onClick={() => setKind(key)}
            >
              {label} {count}
            </Button>
            ))}

          {/* **한 번에 여닫는다.** 묶음이 여럿이면 하나씩 누르는 것이 그 수만큼
              반복되고, 무엇을 이미 폈는지도 흐려진다.

              **문구가 지금 상태를 말한다.** 「전체 여닫기」 처럼 두면 누르기 전에
              어느 쪽이 될지 모른다 — 하나라도 펴져 있으면 접는 쪽이 다음 할 일이다. */}
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-7 text-xs"
            onClick={() => setAll(!anyOpen)}
          >
            {anyOpen ? (
              <>
                <ChevronsDownUp className="size-3.5" />
                전체 접기
              </>
            ) : (
              <>
                <ChevronsUpDown className="size-3.5" />
                전체 펼치기
              </>
            )}
          </Button>
        </div>
      )}

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pr-2">
        {shown.map((group) => (
          <GroupCard
            key={`${group.test_type_key}-${group.orientation}`}
            materialId={materialId}
            group={group}
            onSave={() => save(group)}
            open={isOpen(group)}
            onToggle={() =>
              setToggled((was) => ({ ...was, [keyOf(group)]: !isOpen(group) }))
            }
          />
        ))}
      </div>
      </div>
    </section>
  )
}

/**
 * **항목이 행이다** — 시험종류가 아니라.
 *
 * 시험종류마다 표를 두면 종류가 다섯일 때 표가 다섯 개 세로로 선다. 그런데 사람이
 * 묻는 것은 「인장시험 MD 묶음에 뭐가 있나」 가 아니라 **「이 재료 인장강도가
 * 얼마인가」** 다.
 *
 * ## 한 표가 셋을 다 든다
 *
 *     [통계]  시편마다 낸 값의 평균과 흩어짐 — n 개를 세어 본 것
 *     [피팅]  시편 여럿의 데이터를 한 번에 적합한 것(글로벌 피팅) — 마스터커브
 *             다섯 → Prony 계수 한 벌. **평균이 아니다.**
 *     [선언]  사람이 적은 값 — 핸드북·규격·데이터시트
 *
 * 「계산」 이라고 적었을 때는 앞의 둘이 안 갈렸다 — 둘 다 계산이다. 갈리는 것은
 * **여럿을 세어 본 것**과 **여럿을 한 번에 적합한 것**이다.
 *
 * **셋이 나란히 서야 견줄 수 있다.** 같은 탄성계수가 인장 206 GPa · DMA 198 GPa ·
 * 문헌 210 GPa 로 나올 수 있고, 그 차이가 볼 값의 전부일 때가 있다. 카드는 「잰
 * 값 > 적은 값」 으로 말없이 한쪽을 싣는다.
 */
function PropertySummary({
  groups,
  declared,
  groupResults,
  groupKinds,
  onEditDeclared,
  actions,
}: {
  groups: StatisticsGroup[]
  declared: DeclaredProperty[]
  groupResults: GroupResult[]
  groupKinds: GroupingSpec[]
  onEditDeclared?: (item: string) => void
  actions?: React.ReactNode
}) {
  type Line = {
    where: string
    stats: ScalarStats | null
    /** 통계가 아닌 값(묶음·선언)이면 적을 글자. */
    stated?: string
    kind: '통계' | '피팅' | '선언'
  }

  const rows = new Map<string, Line[]>()
  const push = (label: string, line: Line) => {
    const found = rows.get(label) ?? []
    found.push(line)
    rows.set(label, found)
  }

  for (const group of groups) {
    for (const scalar of group.scalars) {
      push(scalar.label, {
        where: [group.test_type_label, group.orientation].filter(Boolean).join(' · '),
        stats: scalar,
        kind: '통계',
      })
    }
  }

  // **글로벌 피팅 결과도 물성이다.** 옆 패널에만 두면 「이 재료의 물성」 목록에서
  // 빠진다 — 카드에는 실리는데 목록에는 없는 상태가 된다.
  for (const made of groupResults) {
    const spec = groupKinds.find((one) => one.id === made.plugin_id)
    for (const [key, value] of Object.entries(made.values ?? {})) {
      const produced = spec?.makes_values.find((one) => one.key === key)
      push(produced?.label ?? key, {
        where: `${spec?.label ?? made.plugin_id} · 시험 ${made.used.length}건`,
        stats: null,
        kind: '피팅',
        stated: produced?.si_unit
          ? formatScalar(value, produced.si_unit, null)
          : String(significant(value)),
      })
    }
  }

  for (const row of declared) {
    const first = row.points?.[0]
    if (!first) continue
    push(row.item, {
      where: row.reference || row.source,
      stats: null,
      kind: '선언',
      stated: `${significant(Number(first.value))} ${row.input_unit ?? row.scale ?? ''}`.trim(),
    })
  }

  return (
    <div className="rounded-md border" aria-label="물성">
      <header className="flex flex-wrap items-center gap-2 border-b p-3">
        <Sigma className="text-muted-foreground size-4" />
        <h3 className="font-medium">물성</h3>
        <span className="text-muted-foreground text-xs">
          같은 항목이 여러 곳에서 나오면 나란히 둡니다
        </span>
        {/* **가로로 나란히.** `ml-auto` 만 주면 그 안이 block 이라 단추가
            위아래로 쌓인다. */}
        {actions ? (
          <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </header>

      {/* **한 행에 하나.** 카드로 흘려 두면 폭이 넓을 때는 좋지만, 여기는 왼쪽
          열이라 표가 훑기 좋다 — 눈이 세로로만 내려간다. */}
      <Table aria-label="물성 요약">
        <TableHeader>
          <TableRow>
            <TableHead>항목</TableHead>
            <TableHead>값</TableHead>
            <TableHead>어디서</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...rows.entries()].map(([label, lines]) =>
            lines.map((line, at) => (
              <TableRow key={`${label}-${at}`} aria-label={label}>
                {/* 두 번째 줄부터는 **눈에만 안 보이게** 한다 — 이름을 아예 빼면
                    스크린리더가 그 줄이 무엇의 값인지 못 읽는다. */}
                <TableCell
                  className={cn('font-medium whitespace-nowrap', at > 0 && 'text-transparent')}
                >
                  {label}
                </TableCell>
                <TableCell className="font-mono whitespace-nowrap">
                  {line.stats ? <SummaryValue row={line.stats} /> : line.stated}
                </TableCell>
                <TableCell>
                  <span className="text-muted-foreground flex flex-wrap items-center gap-1 text-[11px]">
                    {/* **어디서 왔나를 배지가 말한다.** 「인장시험 · MD」 만으로는
                        그것이 시편마다 잰 값인지, 여럿으로 한 번에 구한 값인지,
                        사람이 적은 값인지 자리로 안 드러난다 — 그리고 셋은 카드에
                        실릴 때 다루는 법이 다르다. */}
                    <Badge
                      variant={line.kind === '통계' ? 'secondary' : 'outline'}
                      className="px-1 py-0 text-[10px] font-normal"
                    >
                      {line.kind}
                    </Badge>
                    {line.stats ? <Spread row={line.stats} /> : null}
                    {line.stats ? '·' : ''}
                    {line.where}
                    {line.kind === '선언' && onEditDeclared && (
                      <button
                        type="button"
                        aria-label={`${label} 적어 둔 값 편집`}
                        title="적어 둔 값을 고칩니다"
                        className="hover:text-foreground"
                        onClick={() => onEditDeclared(label)}
                      >
                        <Pencil className="size-3" />
                      </button>
                    )}
                    {at > 0 && apart(lines) && (
                      <span className="text-amber-600">· 값이 크게 다릅니다</span>
                    )}
                  </span>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}

/** 값과 경고. **흔들리는 값은 값 옆에서 보여야 한다.** */
function SummaryValue({ row }: { row: ScalarStats }) {
  const notableCv =
    row.coefficient_of_variation !== null && row.coefficient_of_variation >= NOTABLE_CV
  return (
    <>
      {formatScalar(row.mean, row.si_unit, row.dimension)}
      {notableCv && (
        <AlertTriangle
          className="ml-1 inline size-3.5 text-amber-500"
          aria-label={`CV ${(row.coefficient_of_variation! * 100).toFixed(1)}%`}
        />
      )}
    </>
  )
}

/** 산포와 표본 수. **값만 보고 쓰는 사람이 생긴다.** */
function Spread({ row }: { row: ScalarStats }) {
  return (
    <>
      {row.sample_sd !== null
        ? `± ${formatScalar(row.sample_sd, row.si_unit, row.dimension).split(' ')[0]} · `
        : ''}
      n={row.count}
    </>
  )
}

/**
 * 이 묶음이 사람에게 할 말이 있는가 — 조용히 빠진 시험이나 흔들리는 값.
 *
 * **접어 두면 아무도 안 본다.** 이 화면이 그것을 알리려고 있는데. 그래서 기본은
 * 접힘이지만 할 말이 있으면 펴 둔다.
 */
function speaks(group: StatisticsGroup): boolean {
  return (
    group.notes.length > 0 ||
    group.scalars.some(
      (one) =>
        one.outliers.length > 0 ||
        (one.coefficient_of_variation !== null &&
          one.coefficient_of_variation >= NOTABLE_CV)
    )
  )
}

/** 한 항목의 값들이 서로 두 배 넘게 벌어지는가. */
function apart(lines: { stats: ScalarStats | null; stated?: string }[]): boolean {
  const values = lines
    .map((one) => (one.stats ? one.stats.mean : Number(one.stated?.split(' ')[0])))
    .filter((one) => Number.isFinite(one) && one !== 0)
  if (values.length < 2) return false
  return Math.max(...values) / Math.min(...values) >= 2
}

function GroupCard({
  group,
  materialId,
  onSave,
  open,
  onToggle,
}: {
  group: StatisticsGroup
  materialId: string
  onSave: () => void
  /** **상태를 부모가 든다** — 「전체 접기」 가 그것을 한꺼번에 바꾼다. */
  open: boolean
  onToggle: () => void
}) {
  const enough = group.sample_count >= 2
  /**
   * **기본은 접혀 있다** (2026-08-30).
   *
   * 위 요약이 「그래서 얼마인가」 에 답하므로, 8열 표(중앙값·표준편차·CV·신뢰구간·
   * 이상치)와 곡선과 분포가 늘 펼쳐져 있을 이유가 없다. 묶음이 셋이면 그것이 셋씩
   * 세로로 쌓여, 값을 보려던 사람이 스크롤을 하게 된다.
   *
   * **다만 할 말이 있으면 펴 둔다.** 조용히 빠진 시험이나 흔들리는 값은 접어 두면
   * 아무도 안 본다 — 이 화면이 그것을 알리려고 있는데.
   */
  return (
    <div className="rounded-md border">
      <header className="flex flex-wrap items-center gap-2 border-b p-3">
        <Button
          size="icon"
          variant="ghost"
          className="size-6"
          aria-label={`${group.test_type_label} ${group.orientation} ${open ? '접기' : '펴기'}`}
          onClick={onToggle}
        >
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </Button>
        <h3 className="font-medium">{group.test_type_label}</h3>
        {/* **방향을 섞지 않는다.** 압연 방향에 따라 물성이 다르다. */}
        <Badge variant="secondary">{group.orientation}</Badge>
        <span className="text-muted-foreground text-sm">채택 {group.sample_count}건</span>
        {group.skipped_unadopted > 0 && (
          <Badge variant="outline" className="text-xs">
            미채택 {group.skipped_unadopted}
          </Badge>
        )}
        {/* **접혀 있어도 할 말이 있다는 것은 보여야 한다.** */}
        {!open && speaks(group) && (
          <Badge variant="outline" className="border-amber-500/50 text-xs text-amber-600">
            <AlertTriangle className="size-3" />볼 것 있음
          </Badge>
        )}
        {enough && (
          <Button size="sm" variant="outline" className="ml-auto" onClick={onSave}>
            <Save className="size-3.5" />이 통계 남기기
          </Button>
        )}
      </header>

      {/* **곡선을 옆으로 보낸다.** 세로로 이어 붙이면 그래프 하나가 화면
          높이의 절반을 먹고, 묶음이 여럿이면 값을 보려고 그래프를 계속 지나쳐
          스크롤하게 된다.

          6:4 인 이유는 **왼쪽이 8열 표**이기 때문이다(항목·n·평균·중앙값·표준
          편차·CV·신뢰구간·이상치). 반씩 나눠도 넓은 화면에서 가로 스크롤이
          남았다 — 곡선은 4할에서도 변형률 축이 충분히 길다. */}
      <div
        className="grid gap-4 p-3 xl:grid-cols-[minmax(0,6fr)_minmax(0,4fr)] xl:items-start"
        hidden={!open}
      >
        <div className="min-w-0 space-y-4">
        {group.notes.length > 0 && (
          <ul className="text-muted-foreground space-y-1 text-xs">
            {group.notes.map((note) => (
              <li key={note} className="border-l-2 pl-2">
                {note}
              </li>
            ))}
          </ul>
        )}

        {group.scalars.length > 0 && (
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>항목</TableHead>
                <TableHead className="text-right">n</TableHead>
                <TableHead className="text-right">평균</TableHead>
                <TableHead className="text-right">중앙값</TableHead>
                <TableHead className="text-right">표준편차</TableHead>
                <TableHead className="text-right">CV</TableHead>
                <TableHead className="text-right">95% 신뢰구간</TableHead>
                <TableHead>이상치</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {group.scalars.map((row) => (
                <ScalarRow key={row.key} row={row} />
              ))}
            </TableBody>
          </Table>
          </div>
        )}
        </div>

        {/* 오른쪽은 그림이다 — 곡선과 분포. */}
        <div className="min-w-0 space-y-4">
        {group.curve && <EnsembleCurve group={group} />}

        {/* **흩어짐이 얼마나 큰지와 어떤 모양인지는 다른 물음이다.** 위 표가
            앞엣것을 냈다. 설계가 묻는 하위 5% 는 모양이 정한다 — 같은 평균과
            같은 SD 에서도 달라진다.

            기본으로 접어 둔다. 부트스트랩 999회가 도는 일이라 물어보지도 않았는데
            돌릴 일이 아니다. */}
        {group.sample_count > 0 && (
          <DistributionPanel
            materialId={materialId}
            testTypeKey={group.test_type_key}
            orientation={group.orientation}
          />
        )}
        </div>
      </div>
    </div>
  )
}

function ScalarRow({ row }: { row: ScalarStats }) {
  const value = (input: number | null) =>
    input === null ? '—' : formatScalar(input, row.si_unit, row.dimension)
  const notableCv =
    row.coefficient_of_variation !== null && row.coefficient_of_variation >= NOTABLE_CV
  // **평균과 중앙값이 많이 다르면 그 자체가 신호다.** 표준편차는 이상치 하나에
  // 크게 휘둘리므로 둘을 나란히 둔다.
  return (
    <TableRow>
      <TableCell>
        <span className="text-sm">{row.label}</span>
        <p className="text-muted-foreground font-mono text-xs">{row.key}</p>
      </TableCell>
      <TableCell className="text-right tabular-nums">{row.count}</TableCell>
      <TableCell className="text-right tabular-nums">{value(row.mean)}</TableCell>
      <TableCell className="text-muted-foreground text-right tabular-nums">
        {value(row.median)}
      </TableCell>
      <TableCell className="text-right tabular-nums">{value(row.sample_sd)}</TableCell>
      <TableCell className="text-right tabular-nums">
        {row.coefficient_of_variation === null ? (
          '—'
        ) : (
          <span className={notableCv ? 'font-medium text-amber-700 dark:text-amber-500' : ''}>
            {(row.coefficient_of_variation * 100).toPrecision(3)}%
          </span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground text-right tabular-nums text-xs">
        {row.ci95_low === null ? '—' : `${value(row.ci95_low)} ~ ${value(row.ci95_high)}`}
      </TableCell>
      <TableCell>
        {row.outliers.length === 0 ? (
          <span className="text-muted-foreground text-xs">—</span>
        ) : (
          <div className="space-y-0.5">
            {row.outliers.map((item) => (
              <div key={item.test_run_id} className="text-xs">
                <Badge variant="outline" className="gap-1 text-amber-700 dark:text-amber-500">
                  <AlertTriangle className="size-3" />
                  {item.record_name.split('__').at(-1) ?? item.record_name}
                </Badge>
                {/* **버리지 않았다.** 재료 특성인지 시험 실수인지는 사람이 안다. */}
                <p className="text-muted-foreground mt-0.5">{item.reason}</p>
              </div>
            ))}
          </div>
        )}
      </TableCell>
    </TableRow>
  )
}

function EnsembleCurve({ group }: { group: StatisticsGroup }) {
  // **훅이 조건 뒤에 오면 안 된다.** 곡선이 없는 렌더에서만 훅 하나가 빠져
  // 호출 순서가 달라지고, React 는 그 상태를 다른 훅의 것으로 읽는다.
  const [mode, setMode] = useState<'mean' | 'median'>('mean')
  const curve = group.curve
  if (!curve) return null

  // 표시 단위로 맞춘다. 축만 바꾸고 점을 안 바꾸면 1000배 어긋난다.
  //
  // **단위는 서버가 준다.** 전에는 채널 이름 앞글자로 짐작했다 —
  // `stress*` 면 Pa, 나머지는 전부 무차원. 그래서 변위·온도가 있는 묶음에서
  // m 와 K 가 그대로 나왔고, 축에는 단위가 아예 안 붙었다.
  //
  // 차원은 이름으로 남긴다 — 변형률과 tan δ 는 저장 단위가 둘 다 `1` 이라
  // 단위만으로는 못 가른다(`shared/units.ts` 의 `BY_DIMENSION`).
  const unitOf = (name: string) => curve.units?.[name] ?? '1'
  const dimensionOf = (name: string) => (name.startsWith('strain') ? 'strain' : null)
  const shown = (points: [number, number][]): [number, number][] =>
    points.map(([x, y]) => [
      toDisplay(x, unitOf(curve.x), dimensionOf(curve.x)),
      toDisplay(y, unitOf(curve.y), dimensionOf(curve.y)),
    ])

  const points = shown((mode === 'mean' ? curve.mean : curve.median) as [number, number][])
  /**
   * 대표를 만든 **시편별 원곡선**. 뒤에 흐리게 깔린다.
   *
   * 평균선 하나로는 「열 개가 겹쳐 있다」와 「하나가 딴 데로 가서 평균이
   * 끌려갔다」가 똑같이 생겼다 — 그 둘을 가르는 것이 이 그림의 목적이다.
   */
  const raw = (curve.members ?? []).map((member) => ({
    label: member.record_name,
    points: shown(member.points as [number, number][]),
  }))
  // **1개면 평균도 중앙값도 그 곡선이다.** 고를 것이 없는데 버튼을 두면 눌러
  // 보고 아무것도 안 변하는 것을 확인하게 된다 — 그건 고장으로 읽힌다.
  const single = group.sample_count === 1

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{single ? '곡선' : '대표 곡선'}</span>
        {/* **둘 다 낸다.** 이상치가 있을 때 중앙값이 낫고, 어느 것을 쓸지는
            피팅할 때 고르면 된다. */}
        {!single &&
          (['mean', 'median'] as const).map((option) => (
            <Button
              key={option}
              size="sm"
              variant={mode === option ? 'default' : 'outline'}
              className="h-7 text-xs"
              onClick={() => setMode(option)}
            >
              {option === 'mean' ? '평균' : '중앙값'}
            </Button>
          ))}
        <span className="text-muted-foreground ml-auto text-xs">
          {curve.mean.length}점 · 시편 {group.sample_count}개
          {raw.length > 1 && (
            // **줄였다는 것은 화면이 말한다.** 뒤에 깔린 선이 원본 그대로인 줄
            // 알면, 뾰족한 데가 없는 것을 데이터의 성질로 읽는다.
            <> · 뒤의 흐린 선 {raw.length}개가 시편별 원곡선(솎음)</>
          )}
        </span>
      </div>
      <CurveChart
        points={points}
        background={raw}
        // **축에 단위를 붙인다.** 채널 키만 있으면 `stress_true` 가 Pa 인지
        // MPa 인지 화면 어디에도 없다.
        xLabel={axisLabel(curve.x, unitOf(curve.x), dimensionOf(curve.x))}
        yLabel={axisLabel(curve.y, unitOf(curve.y), dimensionOf(curve.y))}
        height={280}
      />
      <p className="text-muted-foreground mt-2 text-xs">
        {single ? (
          <>
            시편 1개의 곡선입니다 — <b>평균이 아니라 그 시편의 값</b>입니다. 이 곡선이{' '}
            <b>피팅의 입력</b>이 되고, 카드에도 시편 1개라고 적힙니다.
          </>
        ) : (
          <>
            점마다 시편 {group.sample_count}개의 {mode === 'mean' ? '평균' : '중앙값'}
            입니다. 이 곡선이 <b>피팅의 입력</b>이 됩니다.
          </>
        )}
      </p>
    </div>
  )
}
