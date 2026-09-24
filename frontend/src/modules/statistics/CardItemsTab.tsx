/**
 * 카드 항목 — **어느 재료에서 무엇까지 볼 수 있나.**
 *
 * 점탄성·경화식·소성 표는 스칼라가 아니라서 비교·분포·추이에 안 나온다. 재료마다 CAE
 * 카드 탭을 열어 봐야 알던 것을 **재료 x 카드 항목란**으로 편다(2026-09-24 요청 —
 * 「어떤 재료에서 어떤 것까지 볼 수 있는지 카드의 각 항목에 대해 확인」).
 *
 * ## 요약과 전체
 *
 *     요약   재료군·분류마다 항목란별 재료 수 — 줄이 분류라 재료가 1만이어도 수십 줄
 *     전체   재료 줄 — 서버가 거르고 한 쪽씩 준다
 *
 * 첫 판은 재료 전부를 한 장에 폈다. 가짜 1만 개로 재 보니 응답 10 MB · 표가 뜨는 데
 * 3.6 초 · 화면 요소 14만이었고, 무엇보다 1만 줄은 읽는 표가 아니다. 그래서 재료가
 * `SUMMARY_FROM` 개를 넘으면 요약부터 연다(「몇천 개 이상부터는 요약과 전체」 — 같은 날
 * 요청). 둘 다 언제든 고른다. 요약의 칸을 누르면 그 분류 · 그 항목의 재료 줄로 간다 —
 * **주소에 남으므로** 재료를 열었다 뒤로 오면 그 자리다.
 *
 * ## 칸은 네 가지다
 *
 *     확정       확정 카드에 있다 — 다른 시스템이 받아 가는 값이다
 *     초안       초안 카드에만 있다
 *     중지       사용 중지한 카드에만 있다 — 있었지만 지금은 못 쓴다
 *     시험·선언   카드는 없지만 그 항목을 내는 시험의 채택 결과, 또는 그 칸으로 갈
 *                선언 물성이 있다 — 「만들 수 있다」 고는 안 한다(아래 `sourceName`)
 *
 * **판정은 서버가 한다**(`state`) — 요약 · 전체 · 칸이 같은 판정이라 요약의 「점탄성 4」
 * 를 누르면 네 줄이 뜬다. 시험·선언만 있는 칸은 켜야 보인다: 선언 물성만 적힌 재료가
 * 많아서(개발 DB 에서 124 가운데 110) 기본으로 펴면 카드가 있는 재료가 묻힌다.
 *
 * ## 빼는 것은 말한다
 *
 * 아무 칸도 없는 재료는 줄로 안 오고 수만 적는다. 아무 재료에도 없는 항목란은 **열을
 * 접되 이름을 적는다** — 빈 열 일곱이 서면 점탄성이 화면 밖으로 밀린다(개발 서버에서
 * 열셋 가운데 일곱이 비었다). 재료군·분류·재료 칸은 가로로 밀어도 남는다 — 오른쪽 열을
 * 볼 때 그 줄이 어느 재료인지 모르면 표가 아니다. 표는 높이를 정한 상자 안에서 두 방향으로
 * 스크롤한다 — 상자가 없으면 가로 스크롤바가 긴 표의 맨 아래에 붙어 안 보인다.
 */

import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { TABLE_PAD, showWithUnit } from '@/modules/statistics/analysisFormat'
import { analysisApi } from '@/modules/statistics/analysisApi'
import type {
  CardItemColumn,
  CardItemState,
  CardItemSummary,
  CardItemTally,
  CardItemValue,
} from '@/modules/statistics/analysisApi'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { useResource } from '@/shared/hooks/useResource'
import { cn } from '@/shared/lib/utils'

/**
 * 이 재료 수부터 **요약이 기본**이다. 재료마다 한 줄인 표는 수천 줄이면 읽는 표가 아니라
 * 찾는 목록이 된다 — 그때는 분류로 접은 것부터 보고 들어간다. 기본만 바뀌고 둘 다 고를
 * 수 있다.
 */
export const SUMMARY_FROM = 2000

/** 전체의 한 쪽 줄 수 — 서버 상한(200) 안. 한 번에 다 그리면 1만 줄에 3.6 초였다. */
export const PAGE = 100

type View = 'summary' | 'all'

/** 카드 상태의 이름 — 카드 목록과 같은 말. */
const STATUS_NAMES: Record<string, string> = {
  published: '확정',
  draft: '초안',
  deprecated: '사용 중지',
}

/**
 * 표 상자 — **높이를 정해 두 방향으로 스크롤한다.** 상자 없이 두면 표가 긴 만큼 가로
 * 스크롤바가 표의 맨 아래에 붙어서, 열이 화면 밖으로 넘쳐도 밀 길이 안 보였다(2026-09-24
 * 지적). 머리 줄과 왼쪽 칸은 상자 안에서 붙어 있다. 높이는 `useFitHeight` 가 잰다.
 */
const SCROLL_BOX = 'max-h-[var(--box-h,70vh)] overflow-auto'

/** 상자가 이보다 낮아지지는 않는다 — 창이 아주 낮으면 상자를 줄이는 대신 본문이 내려간다. */
const MIN_BOX = 280

/**
 * 표 상자의 높이 — **상자 아래 끝(가로 스크롤바)이 본문 창 안에 들게.** 정한 높이
 * (`calc(100vh-…)`)로 두니 위에 붙는 줄(거르기 · 접은 열 안내)이 늘 때 스크롤바가 창
 * 밖으로 밀렸다(1280x800 에서 9 px). 본문(`main`)이 얼마나 내려가 있든 같은 값이 나오게
 * 본문 안에서의 자리로 잰다. 아래 안내 · 쪽 넘기기 자리(`reserve`)는 남긴다.
 */
function useFitHeight(reserve: number) {
  const ref = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState<number | null>(null)
  // 그릴 때마다 잰다 — 위의 줄이 늘고 줄어도 맞춘다. 같은 값이면 다시 그리지 않는다.
  useLayoutEffect(() => {
    function fit() {
      const box = ref.current
      if (!box) return
      const top = box.getBoundingClientRect().top
      const main = box.closest('main')
      const room = main
        ? main.clientHeight -
          (top - main.getBoundingClientRect().top + main.scrollTop) -
          parseFloat(getComputedStyle(main).paddingBottom || '0')
        : window.innerHeight - top
      setHeight(Math.max(MIN_BOX, Math.floor(room - reserve)))
    }
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  })
  const style = (height === null ? {} : { '--box-h': `${height}px` }) as CSSProperties
  return { ref, style }
}

/** 머리 칸 — 세로로 밀어도 남는다. 경계선은 그림자로 긋는다: 겹친 테두리(`border-collapse`)
 *  는 붙은 칸을 따라오지 않고 표에 남는다. */
const HEAD = 'bg-background sticky top-0 z-20 shadow-[inset_0_-1px_0_var(--border)]'

/** 붙은 칸의 오른쪽 경계 — 그 너머가 밀려 지나간다. 머리 칸은 아래 선과 함께 긋는다. */
const EDGE = 'shadow-[inset_-1px_0_0_var(--border)]'
const HEAD_EDGE = 'shadow-[inset_0_-1px_0_var(--border),inset_-1px_0_0_var(--border)]'

/**
 * 가로로 밀어도 남는 칸 — **폭을 정해야** 다음 칸이 설 자리(`left-*`)를 안다. 글자는
 * 자르지 않고 **폭 안에서 줄을 바꾼다** — 요약에서 분류가 「SnAgCu solder..」 처럼 잘려
 * 무슨 분류인지 몰랐다(2026-09-24 지적). `wrap-anywhere` 라 띄어쓰기 없는 긴 이름도 폭을
 * 안 넘는다 — 넘으면 폭이 늘어 다음 칸의 자리가 어긋난다. 분류는 8rem 이었다가 두세
 * 줄로 접혀 12rem 으로 넓혔다(같은 날 요청) — 폭을 바꾸면 뒤 칸의 `left-*` 도 바꾼다.
 */
const PIN = {
  family: 'bg-background sticky left-0 w-28 min-w-28 max-w-28 whitespace-normal wrap-anywhere',
  category: 'bg-background sticky left-28 w-48 min-w-48 max-w-48 whitespace-normal wrap-anywhere',
  material: 'bg-background sticky left-76 w-56 min-w-56 max-w-56 whitespace-normal wrap-anywhere',
}

/** 항목란 설명의 강조 표시(`**`)를 걷는다 — 레지스트리의 설명은 코드 주석과 같은 글이다. */
function plain(text: string): string {
  return text.replace(/\*\*/g, '')
}

/** 이 열에 지금 보이는 칸이 있나 — 없으면 접는다(이름은 적는다). */
function filledColumn(one: CardItemColumn, withSources: boolean): boolean {
  return (
    one.card_materials + one.deprecated_materials > 0 ||
    (withSources && one.source_materials > 0)
  )
}

/** 카드 없는 칸의 이름 — 무엇이 있는지를 그대로 말한다. 「만들 수 있음」 이라고 하지
 *  않는다: 속도별 소성 표는 인장 한 속도로는 못 만든다. 있는 것만 말하고 판단은 사람이. */
function sourceName(tests: boolean, declared: boolean): string {
  if (tests && declared) return '시험·선언'
  return tests ? '시험 있음' : '선언 있음'
}

/** 창의 안내에 쓰는 말 — 「위의 시험 결과만으로」 처럼 문장에 들어간다. */
function sourcePhrase(tests: boolean, declared: boolean): string {
  if (tests && declared) return '시험 결과와 선언 물성'
  return tests ? '시험 결과' : '선언 물성'
}

function valueText(one: CardItemValue): string {
  if (typeof one.value === 'number') return showWithUnit(one.value, one.si_unit)
  if (typeof one.value === 'string') return one.value
  // 레지스트리가 모르는 항목란 — 단위를 몰라 숫자를 안 보인다(Pa 를 MPa 로 읽는다).
  return '값 있음'
}

export function CardItemsTab() {
  const [params, setParams] = useSearchParams()
  const summary = useResource(() => analysisApi.cardItemSummary(), [])
  const data = summary.data

  const chosen = params.get('view')
  const view: View | null =
    chosen === 'summary' || chosen === 'all'
      ? chosen
      : data
        ? data.material_total >= SUMMARY_FROM
          ? 'summary'
          : 'all'
        : null
  const withSources = params.get('sources') === '1'
  const family = params.get('family')
  const category = params.get('category')
  const item = params.get('item')

  /** 주소를 고친다 — 요약에서 들어간 자리가 뒤로 가기로 돌아오게. */
  function update(next: Record<string, string | null>, replace = false) {
    setParams(
      (now) => {
        const copy = new URLSearchParams(now)
        for (const [key, value] of Object.entries(next)) {
          if (value === null) copy.delete(key)
          else copy.set(key, value)
        }
        return copy
      },
      { replace }
    )
  }

  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  // 타이핑이 멎으면 묻는다 — 글자마다 부르면 앞 글자의 응답이 뒤늦게 와서 목록을 덮는다.
  useEffect(() => {
    const timer = setTimeout(() => setQ(typed.trim()), 300)
    return () => clearTimeout(timer)
  }, [typed])

  const nothing = data
    ? data.material_total - data.card_material_count - data.source_only_count
    : 0

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          <Button
            size="sm"
            variant={view === 'summary' ? 'default' : 'outline'}
            aria-pressed={view === 'summary'}
            onClick={() => update({ view: 'summary', family: null, category: null, item: null })}
          >
            요약
          </Button>
          <Button
            size="sm"
            variant={view === 'all' ? 'default' : 'outline'}
            aria-pressed={view === 'all'}
            onClick={() => update({ view: 'all' })}
          >
            전체
          </Button>
        </div>
        <Input
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          placeholder={view === 'summary' ? '재료군·분류' : '재료 이름·재료군·분류'}
          aria-label="재료 찾기"
          className="h-8 w-60"
        />
        <Button
          size="sm"
          variant={withSources ? 'default' : 'outline'}
          aria-pressed={withSources}
          onClick={() => update({ sources: withSources ? null : '1' }, true)}
        >
          시험·선언만 있는 것도 보기
        </Button>
      </div>

      <ErrorNotice error={summary.error} className="mb-3" />
      {summary.loading && !data && <p className="text-muted-foreground text-sm">불러오는 중…</p>}

      {data && (
        <p className="text-muted-foreground mb-2 text-xs">
          카드가 있는 재료 <strong className="text-foreground">{data.card_material_count}</strong>{' '}
          · 카드 없이 시험·선언만 있는 재료 {data.source_only_count} · 둘 다 없는 재료 {nothing}{' '}
          (전체 {data.material_total})
          {!chosen && view === 'summary' && ' — 재료가 많아 요약부터 엽니다.'}
        </p>
      )}

      {data && view === 'summary' && (
        <SummaryView
          data={data}
          q={q}
          withSources={withSources}
          onDrill={(next) => update({ view: 'all', ...next })}
        />
      )}
      {data && view === 'all' && (
        <MaterialsView
          q={q}
          family={family}
          category={category}
          item={item}
          withSources={withSources}
          onFilter={(next) => update(next)}
        />
      )}
    </div>
  )
}

/** 접은 열 — **이름은 적는다.** 「아직 아무도 안 만든 것」 이라는 사실이 요점이다. */
function FoldedNote({
  folded,
  withSources,
  open,
  onToggle,
}: {
  folded: CardItemColumn[]
  withSources: boolean
  open: boolean
  onToggle: () => void
}) {
  if (folded.length === 0) return null
  return (
    <p className="text-muted-foreground mb-2 text-xs">
      이 목록에 {withSources ? '카드도 시험·선언도' : '카드가'} 없는 항목 {folded.length} —{' '}
      {folded.map((one) => one.label).join(' · ')}{' '}
      <button
        type="button"
        className="text-foreground underline underline-offset-2"
        onClick={onToggle}
      >
        {open ? '빈 열 접기' : '빈 열도 보기'}
      </button>
    </p>
  )
}

/** 열 머리 — 항목란 이름과 **몇 재료에 있는지.** 누르면 그 항목이 있는 재료만. */
function ItemHead({
  item,
  withSources,
  active,
  onPick,
}: {
  item: CardItemColumn
  withSources: boolean
  active: boolean
  onPick: () => void
}) {
  const tests = item.tests.length > 0 ? `\n내는 시험: ${item.tests.join(' · ')}` : ''
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={`${item.label} — 이 항목이 있는 재료만 보기`}
      title={`${plain(item.help)}${tests}`}
      className={`rounded px-1 py-0.5 hover:underline ${active ? 'bg-muted' : ''}`}
      onClick={onPick}
    >
      <div className={item.registered ? undefined : 'text-destructive'}>
        {item.label}
        {!item.registered && ' (등록 안 됨)'}
      </div>
      <div className="text-muted-foreground text-xs font-normal">
        재료 {item.card_materials}
        {item.published_materials > 0 && ` · 확정 ${item.published_materials}`}
        {withSources && item.source_materials > 0 && ` · 시험·선언 ${item.source_materials}`}
      </div>
    </button>
  )
}

// --- 요약 ----------------------------------------------------------------------

function shownTally(tally: CardItemTally | undefined, withSources: boolean): boolean {
  if (!tally) return false
  return tally.published + tally.draft + tally.deprecated > 0 || (withSources && tally.source > 0)
}

/**
 * 재료군·분류 x 항목란. 칸은 **그 항목이 든 카드가 있는 재료 수 / 분류의 재료 수** —
 * 분류에 40개인데 5개만 있으면 「있다」 로 읽히면 안 된다. 누르면 그 재료들의 줄로 간다.
 */
function SummaryView({
  data,
  q,
  withSources,
  onDrill,
}: {
  data: CardItemSummary
  q: string
  withSources: boolean
  onDrill: (next: { family: string | null; category: string | null; item: string | null }) => void
}) {
  const [allColumns, setAllColumns] = useState(false)
  const columns = data.columns.filter((one) => allColumns || filledColumn(one, withSources))
  const folded = data.columns.filter((one) => !filledColumn(one, withSources))
  const groups = useMemo(() => {
    const needle = q.toLowerCase()
    if (!needle) return data.groups
    return data.groups.filter((one) =>
      [one.family, one.category].some((text) => text.toLowerCase().includes(needle))
    )
  }, [data.groups, q])
  const fit = useFitHeight(64)

  return (
    <div>
      <FoldedNote
        folded={folded}
        withSources={withSources}
        open={allColumns}
        onToggle={() => setAllColumns((now) => !now)}
      />
      {groups.length === 0 ? (
        <p className="text-muted-foreground text-sm">맞는 분류가 없습니다.</p>
      ) : (
        <div ref={fit.ref} style={fit.style} className={`rounded-md border ${TABLE_PAD}`}>
          <Table containerClassName={SCROLL_BOX}>
            <TableHeader>
              <TableRow>
                <TableHead className={cn(HEAD, PIN.family, 'z-30')}>재료군</TableHead>
                <TableHead className={cn(HEAD, PIN.category, 'z-30', HEAD_EDGE)}>분류</TableHead>
                <TableHead className={cn(HEAD, 'text-center')}>재료</TableHead>
                {columns.map((one) => (
                  <TableHead key={one.key} className={cn(HEAD, 'text-center align-top')}>
                    <ItemHead
                      item={one}
                      withSources={withSources}
                      active={false}
                      onPick={() => onDrill({ family: null, category: null, item: one.key })}
                    />
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map((group) => (
                <TableRow key={`${group.family}\u0000${group.category}`}>
                  <TableCell className={cn(PIN.family, 'z-10')}>{group.family}</TableCell>
                  <TableCell className={cn(PIN.category, 'z-10', EDGE)}>
                    <button
                      type="button"
                      className="text-primary text-left hover:underline"
                      onClick={() =>
                        onDrill({ family: group.family, category: group.category, item: null })
                      }
                    >
                      {group.category}
                    </button>
                  </TableCell>
                  <TableCell className="text-center tabular-nums">
                    {group.material_count}
                    <div className="text-muted-foreground text-xs">
                      카드 {group.card_materials}
                    </div>
                  </TableCell>
                  {columns.map((one) => {
                    const tally = group.cells[one.key]
                    return (
                      <TableCell key={one.key} className="text-center tabular-nums">
                        {tally && shownTally(tally, withSources) ? (
                          <button
                            type="button"
                            className="hover:bg-muted rounded px-1 py-0.5"
                            aria-label={`${group.family} · ${group.category} · ${one.label} 재료 보기`}
                            title={`확정 ${tally.published} · 초안 ${tally.draft} · 중지 ${tally.deprecated} · 시험·선언 ${tally.source} / 재료 ${group.material_count}`}
                            onClick={() =>
                              onDrill({
                                family: group.family,
                                category: group.category,
                                item: one.key,
                              })
                            }
                          >
                            <TallyMark
                              tally={tally}
                              total={group.material_count}
                              withSources={withSources}
                            />
                          </button>
                        ) : (
                          /* **빈 칸이 요점이다.** 0 을 적으면 「있는데 0」 으로 읽힌다. */
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
      <p className="text-muted-foreground mt-2 text-xs">
        칸은 <strong>그 항목이 든 카드가 있는 재료 수 / 분류의 재료 수</strong>입니다(확정 ·
        초안, 아래 줄은 그중 확정). 칸을 누르면 그 재료들을, 분류를 누르면 그 분류의 재료를,
        열 머리를 누르면 그 항목이 있는 재료 전부를 봅니다.
      </p>
    </div>
  )
}

function TallyMark({
  tally,
  total,
  withSources,
}: {
  tally: CardItemTally
  total: number
  withSources: boolean
}) {
  const cards = tally.published + tally.draft
  return (
    <>
      {cards > 0 && (
        <div>
          {cards}/{total}
        </div>
      )}
      {tally.published > 0 && (
        <div className="text-muted-foreground text-xs">확정 {tally.published}</div>
      )}
      {cards === 0 && tally.deprecated > 0 && (
        <div className="text-muted-foreground text-xs">중지 {tally.deprecated}</div>
      )}
      {withSources && tally.source > 0 && (
        <div className="text-xs text-amber-700 dark:text-amber-500">시험·선언 {tally.source}</div>
      )}
    </>
  )
}

// --- 전체 ----------------------------------------------------------------------

/**
 * 재료 줄 — **서버가 거르고 한 쪽씩 준다.** 열의 수도 거른 재료 가운데서 센 것이라, 분류로
 * 들어오면 「이 분류에서 점탄성이 있는 재료」 가 된다.
 */
function MaterialsView({
  q,
  family,
  category,
  item,
  withSources,
  onFilter,
}: {
  q: string
  family: string | null
  category: string | null
  item: string | null
  withSources: boolean
  onFilter: (next: Record<string, string | null>) => void
}) {
  // **거르기가 바뀌면 첫 쪽이다** — 3쪽을 보던 사람이 분류를 바꾸면 빈 화면을 본다. 효과로
  // 되돌리면 옛 쪽으로 한 번 더 묻게 되므로, 쪽을 거르기의 서명과 함께 둔다.
  const sign = [q, family, category, item, withSources].join('\u0000')
  const [paging, setPaging] = useState({ sign, offset: 0 })
  const offset = paging.sign === sign ? paging.offset : 0
  const page = useResource(
    () =>
      analysisApi.cardItemRows({
        q,
        family,
        category,
        item,
        withSources,
        limit: PAGE,
        offset,
      }),
    [q, family, category, item, withSources, offset]
  )
  const [allColumns, setAllColumns] = useState(false)
  const [opened, setOpened] = useState<{
    materialId: string
    materialName: string
    column: CardItemColumn
  } | null>(null)

  const all = page.data?.columns ?? []
  const columns = all.filter(
    (one) => allColumns || filledColumn(one, withSources) || one.key === item
  )
  const folded = all.filter((one) => !filledColumn(one, withSources) && one.key !== item)
  const pickedItem = all.find((one) => one.key === item)
  const rows = page.data?.rows ?? []
  const total = page.data?.total ?? 0
  const fit = useFitHeight(104)

  return (
    <div>
      {(family || category || item) && (
        // **걸려 있다는 것을 보이고, 풀 수 있게.** 조용히 걸어 두면 「재료가 이것뿐인가」 로
        // 읽힌다.
        <div className="mb-2 flex flex-wrap gap-1">
          {(family || category) && (
            <Badge variant="secondary" className="gap-1">
              {[family, category].filter(Boolean).join(' · ')}
              <button
                type="button"
                aria-label="분류 거르기 해제"
                className="hover:text-foreground ml-0.5 opacity-70"
                onClick={() => onFilter({ family: null, category: null })}
              >
                ×
              </button>
            </Badge>
          )}
          {item && (
            <Badge variant="secondary" className="gap-1">
              「{pickedItem?.label ?? item}」 있는 재료만
              <button
                type="button"
                aria-label="항목 거르기 해제"
                className="hover:text-foreground ml-0.5 opacity-70"
                onClick={() => onFilter({ item: null })}
              >
                ×
              </button>
            </Badge>
          )}
        </div>
      )}

      <ErrorNotice error={page.error} className="mb-3" />
      {page.loading && !page.data && <p className="text-muted-foreground text-sm">불러오는 중…</p>}

      <FoldedNote
        folded={folded}
        withSources={withSources}
        open={allColumns}
        onToggle={() => setAllColumns((now) => !now)}
      />

      {page.data && rows.length === 0 && (
        <p className="text-muted-foreground text-sm">
          {withSources
            ? '조건에 맞는 재료가 없습니다.'
            : '조건에 맞는 카드가 없습니다 — 「시험·선언만 있는 것도 보기」 를 켜면 시험·선언 물성이 있는 재료도 보입니다.'}
        </p>
      )}

      {rows.length > 0 && (
        <div ref={fit.ref} style={fit.style} className={`rounded-md border ${TABLE_PAD}`}>
          <Table containerClassName={SCROLL_BOX}>
            <TableHeader>
              <TableRow>
                <TableHead className={cn(HEAD, PIN.family, 'z-30')}>재료군</TableHead>
                <TableHead className={cn(HEAD, PIN.category, 'z-30')}>분류</TableHead>
                <TableHead className={cn(HEAD, PIN.material, 'z-30', HEAD_EDGE)}>재료</TableHead>
                {columns.map((one) => (
                  <TableHead key={one.key} className={cn(HEAD, 'text-center align-top')}>
                    <ItemHead
                      item={one}
                      withSources={withSources}
                      active={item === one.key}
                      onPick={() => onFilter({ item: item === one.key ? null : one.key })}
                    />
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.material_id}>
                  <TableCell className={cn(PIN.family, 'z-10')}>{row.family}</TableCell>
                  <TableCell className={cn(PIN.category, 'z-10')}>{row.category}</TableCell>
                  <TableCell className={cn(PIN.material, 'z-10 font-medium', EDGE)}>
                    <Link
                      to={`/materials/${row.material_id}?tab=cards`}
                      className="text-primary hover:underline"
                    >
                      {row.material_name}
                    </Link>
                  </TableCell>
                  {columns.map((one) => {
                    const cell = row.cells[one.key]
                    return (
                      <TableCell key={one.key} className="text-center">
                        {cell ? (
                          <button
                            type="button"
                            className="hover:bg-muted rounded px-1 py-0.5"
                            aria-label={`${row.material_name} · ${one.label} 자세히`}
                            onClick={() =>
                              setOpened({
                                materialId: row.material_id,
                                materialName: row.material_name,
                                column: one,
                              })
                            }
                          >
                            <StateMark cell={cell} />
                          </button>
                        ) : (
                          /* **빈 칸이 요점이다.** 「없음」 을 글자로 적으면 줄마다 열세 번 읽힌다. */
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

      {/* **조용히 자르지 않는다.** 몇 줄 중 어디를 보는지 적는다. */}
      {total > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-muted-foreground text-xs">
            재료 {total}개 중 {offset + 1}–{offset + rows.length}
            {page.loading && ' · 불러오는 중…'}
          </span>
          {total > PAGE && (
            <>
              <Button
                size="sm"
                variant="outline"
                disabled={offset === 0}
                onClick={() => setPaging({ sign, offset: Math.max(0, offset - PAGE) })}
              >
                이전
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={offset + rows.length >= total}
                onClick={() => setPaging({ sign, offset: offset + PAGE })}
              >
                다음
              </Button>
            </>
          )}
        </div>
      )}

      <p className="text-muted-foreground mt-2 text-xs">
        <strong>확정</strong> 확정 카드에 있음 · <strong>초안</strong> 초안 카드에만 있음 ·{' '}
        <strong>중지</strong> 사용 중지한 카드에만 있음 · <strong>시험 있음 · 선언 있음</strong>{' '}
        카드는 없고, 그 항목을 내는 시험의 채택 결과나 그 칸으로 갈 선언 물성이 있음. 칸을
        누르면 든 값을, 열 머리를 누르면 그 항목이 있는 재료만 봅니다.
      </p>

      {opened && (
        <CellDialog
          materialId={opened.materialId}
          materialName={opened.materialName}
          column={opened.column}
          onClose={() => setOpened(null)}
        />
      )}
    </div>
  )
}

function StateMark({ cell }: { cell: CardItemState }) {
  const more =
    cell.card_count > 1 ? (
      <span className="text-muted-foreground ml-1 text-xs">{cell.card_count}장</span>
    ) : null
  if (cell.state === 'published')
    return (
      <>
        <Badge>확정</Badge>
        {more}
      </>
    )
  if (cell.state === 'draft')
    return (
      <>
        <Badge variant="secondary">초안</Badge>
        {more}
      </>
    )
  if (cell.state === 'deprecated')
    return (
      <>
        <Badge variant="outline">중지</Badge>
        {more}
      </>
    )
  return (
    <span className="text-amber-700 dark:text-amber-500">
      {sourceName(cell.tests, cell.declared)}
    </span>
  )
}

/**
 * 칸 하나 — **무엇까지 들어 있나.** 누를 때 받는다: 카드마다 든 값(항목란이 붙인
 * 이름으로)과 표의 줄 수, 그 항목을 내는 시험과 그 칸으로 갈 선언 물성. 값은 표시
 * 단위로 — 서버는 SI 로 준다.
 */
function CellDialog({
  materialId,
  materialName,
  column,
  onClose,
}: {
  materialId: string
  materialName: string
  column: CardItemColumn
  onClose: () => void
}) {
  const detail = useResource(
    () => analysisApi.cardItemCell(materialId, column.key),
    [materialId, column.key]
  )
  const cell = detail.data
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {materialName} · {column.label}
          </DialogTitle>
          <DialogDescription>{plain(column.help)}</DialogDescription>
        </DialogHeader>

        <ErrorNotice error={detail.error} />
        {detail.loading && !cell && <p className="text-muted-foreground text-sm">불러오는 중…</p>}

        {cell && (
          <div className="max-h-[60vh] space-y-4 overflow-y-auto text-sm">
            {cell.cards.length > 0 && (
              <section>
                <h3 className="mb-1 font-medium">이 항목이 든 카드</h3>
                <ul className="space-y-2">
                  {cell.cards.map((card) => (
                    <li key={card.id} className="rounded-md border p-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{card.label}</span>
                        <Badge
                          variant={
                            card.status === 'published'
                              ? 'default'
                              : card.status === 'deprecated'
                                ? 'outline'
                                : 'secondary'
                          }
                        >
                          {STATUS_NAMES[card.status] ?? card.status}
                        </Badge>
                        {card.row_count > 0 && (
                          <span className="text-muted-foreground text-xs">
                            표 {card.row_count}줄
                          </span>
                        )}
                      </div>
                      <Values values={card.values} />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {cell.tests.length > 0 && (
              <section>
                <h3 className="mb-1 font-medium">이 항목을 내는 시험 — 채택된 결과</h3>
                <ul className="list-inside list-disc">
                  {cell.tests.map((one) => (
                    <li key={one.key}>
                      {one.label} {one.adopted_count}건
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {cell.declared.length > 0 && (
              <section>
                <h3 className="mb-1 font-medium">이 칸으로 갈 선언 물성</h3>
                <Values values={cell.declared} />
              </section>
            )}

            {cell.cards.length === 0 && (
              <p className="text-muted-foreground text-xs">
                아직 이 항목이 든 카드는 없습니다 — 재료의 CAE 카드 탭에서 만듭니다. 위의{' '}
                {sourcePhrase(cell.tests.length > 0, cell.declared.length > 0)}만으로 카드가
                되는지는 항목마다 다릅니다(속도별 소성 표는 속도가 여럿이어야 합니다).
              </p>
            )}
          </div>
        )}

        <div className="flex justify-end">
          <Button asChild>
            <Link to={`/materials/${materialId}?tab=cards`}>재료의 CAE 카드 열기</Link>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Values({ values }: { values: CardItemValue[] }) {
  if (values.length === 0) return null
  return (
    <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
      {values.map((one) => (
        <Fragment key={one.label}>
          <dt className="text-muted-foreground">{one.label}</dt>
          <dd className="tabular-nums">{valueText(one)}</dd>
        </Fragment>
      ))}
    </dl>
  )
}
