/**
 * 열 머리에서 거른다 — **거르는 자리와 걸러지는 열이 같은 자리에 있다.**
 *
 * 전에는 표 위에 검색 상자 하나와 피커 몇 개가 늘어서 있었다. 그러면 어느 상자가
 * 어느 열을 거르는지 **글자로 적어 둬야** 알 수 있고(`Family`·`Category`), 열이
 * 늘 때마다 그 줄이 길어진다. 열 머리에 붙이면 그 설명이 필요 없어진다 — 칸이
 * 곧 그 열이다.
 *
 * ## 서버가 거른다
 *
 * 이 컴포넌트는 값만 들고 있고 거르지 않는다. **화면에서 걸러 버리면 그 페이지에
 * 실린 것만 걸러진다** — 50건짜리 화면에서 「MD」 를 골랐는데 다음 쪽의 MD 는 안
 * 나오는 것이 그 증상이고, 사람은 그것을 「없다」 로 읽는다.
 *
 * ## 머리칸은 두 층이다
 *
 * 이름이 위, 거르는 칸이 아래. 처음에는 `TableHead` 기본값(`h-10 px-2`) 그대로
 * 안에 넣었더니 **두 층이 10 짜리 높이에 눌려 선에 딱 붙었다.** 그래서 머리칸의
 * 높이·여백을 이 파일이 함께 정한다(`FILTER_HEAD`) — 쓰는 쪽마다 클래스를 적으면
 * 표마다 조금씩 달라진다.
 *
 * ## 스물을 눈으로 찾게 하지 않는다
 *
 * 고를 값이 여덟을 넘으면 `<select>` 를 쓰지 않고 **쳐서 좁히는 창**을 연다.
 * 시험 목록의 재료는 102종이고 단계는 12종이다 — 평범한 드롭다운은 그것을
 * 통째로 펼쳐 놓고 눈으로 찾으라고 하고, 못 찾은 사람은 거르기를 안 쓰게 된다.
 * TestScope 의 「보유 장비」 거르개가 같은 문제를 먼저 겪고 `SearchablePicker`
 * 로 풀었다. 넷·다섯짜리 목록(방향·상태)에는 그 칸이 거추장스러우므로
 * `SEARCH_FROM` 아래에서는 그대로 `<select>` 다.
 *
 * **고를 수 있는 것은 목록에 있는 값뿐이고, 옆에 수를 적는다.** 골라도 0건인
 * 선택지가 섞이면 사람은 한 번 겪고 거르기를 안 믿는다.
 *
 * ## 켜진 것이 보여야 한다
 *
 * 거르는 중인 칸은 **테두리만 바꾸지 않는다.** 표에 열이 여덟이면 테두리 하나의
 * 색차는 눈에 안 들어오고, 사람은 "왜 결과가 적지" 를 검색어가 아니라 데이터
 * 탓으로 읽는다. 이름 옆에 점을 찍어 **글자 높이에서** 보이게 한다.
 */

import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronDown, ChevronsUpDown, Search, X } from 'lucide-react'

import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/**
 * 거르는 칸이 든 머리칸에 붙인다.
 *
 * **높이를 푼다** — `TableHead` 기본은 `h-10` 이라 두 층이 안 들어간다.
 *
 * **세로 선을 긋는다.** 배경만으로 띠를 갈랐더니 칸끼리 경계가 없어서, 거르는
 * 상자 여덟이 한 줄에 늘어선 것처럼 보였다 — 어느 상자가 어느 열의 것인지
 * 다시 세어 봐야 했다. 선이 있으면 상자와 열이 같은 칸 안에 있다는 것이 보인다.
 */
export const FILTER_HEAD = 'h-auto border-r py-2.5 align-bottom last:border-r-0'

/** 머리 띠 자체. 배경 + **아래를 굵게** — 첫 줄이 머리인지 자료인지 갈린다. */
export const FILTER_ROW = 'bg-muted/40 hover:bg-muted/40 border-b-2'

/** 이 열로 정렬하는 손잡이. **서버가 정렬한다** — 화면에서 하면 이 쪽에 실린
 *  것만 정렬되고, 사람은 첫 줄을 「가장 오래된 것」 으로 읽는다. */
export interface SortHandle {
  /** 서버가 아는 열 이름. 목록마다 고를 수 있는 것이 다르다. */
  key: string
  /** 지금 정렬 중인 열. */
  active: string
  descending: boolean
  onSort: (key: string) => void
}

export function SortButton({ label, sort }: { label: string; sort: SortHandle }) {
  const on = sort.active === sort.key
  // **꺼져 있을 때도 화살표를 보인다.** 안 보이면 「누를 수 있는 줄」 인지 모르고,
  // 그러면 정렬 기능이 있어도 아무도 안 쓴다. 대신 흐리게 둔다.
  const Icon = on ? (sort.descending ? ArrowDown : ArrowUp) : ChevronsUpDown
  return (
    <button
      type="button"
      className={`hover:text-foreground -mx-1 flex items-center gap-1 rounded px-1 transition-colors ${
        on ? 'text-foreground' : ''
      }`}
      aria-label={`${label} 로 정렬`}
      aria-pressed={on}
      onClick={() => sort.onSort(sort.key)}
    >
      {label}
      <Icon className={`size-3 ${on ? '' : 'opacity-40'}`} aria-hidden />
    </button>
  )
}

/** 거르지 않는 열의 이름. **같은 리듬으로 선다** — 한 줄만 위로 떠 있으면
 *  머리 띠가 들쭉날쭉해 보인다. */
export function ColumnLabel({
  children,
  align = 'left',
  sort,
}: {
  children: React.ReactNode
  align?: 'left' | 'right'
  /** 주면 이름이 정렬 손잡이가 된다. */
  sort?: SortHandle
}) {
  return (
    <div
      className={`flex h-[3.25rem] flex-col justify-end ${align === 'right' ? 'items-end' : ''}`}
    >
      {/* **크기·색을 여기서 정하지 않는다.** `TableHead` 가 이미 표의 글자
          크기와 `font-medium` 을 준다 — 여기서 다시 정하면 필터가 달린 표만
          머리글이 작고 흐려져, 화면을 옮길 때마다 글자가 달라 보인다. */}
      <span className="tracking-wide">
        {sort ? <SortButton label={String(children)} sort={sort} /> : children}
      </span>
    </div>
  )
}

/**
 * 거르는 칸 하나의 생김새. **쉬는 상태에도 테두리가 있다** — 흐리게 뒀더니
 * 「거를 수 있는 칸」 으로 안 읽혔다. 켜지면 색이 바뀌고, 그 차이는 이름 옆의
 * 점이 함께 말한다.
 *
 * `<select>` 와 쳐서 좁히는 창이 **같은 것을 쓴다** — 한 줄에 선 상자들이
 * 열마다 달라 보이면 어느 것이 거르개인지 다시 세어 봐야 한다.
 */
function field(on: boolean): string {
  return (
    'h-8 w-full rounded-md border bg-background text-xs transition-colors ' +
    'focus-visible:ring-ring/40 focus-visible:border-ring focus-visible:ring-2 focus-visible:outline-none ' +
    (on ? 'border-primary/60 bg-primary/[0.04]' : 'border-input hover:border-foreground/30')
  )
}

/** 고를 수 있는 한 줄. **수는 서버가 세어 준 것**이라 없을 수도 있다. */
export interface Facet {
  key: string
  label: string
  count?: number
}

/** 이 수를 넘으면 `<select>` 대신 쳐서 좁히는 창을 연다. */
export const SEARCH_FROM = 8

/** 한 무리. 「거친 것」·「안 거친 것」 처럼 뜻이 다른 묶음을 한 창에 둘 때 쓴다. */
export interface FacetGroup {
  /** 무리 이름. 하나뿐이면 안 그린다 — 이름 하나짜리 제목은 군더더기다. */
  title?: string
  rows: Facet[]
  /** 이 무리에서 고른 값. */
  value?: string
  onPick: (value: string | undefined) => void
  /** 고른 것을 적을 때 앞에 붙일 말. 「없음: 진응력」 처럼 무엇으로 걸었는지. */
  badgePrefix?: string
}

function match(one: Facet, needle: string): boolean {
  if (!needle) return true
  return one.label.toLowerCase().includes(needle) || one.key.toLowerCase().includes(needle)
}

/**
 * 쳐서 좁히는 거르개. **거르는 칸 자리에 선다** — 생김새가 `<select>` 와 같아야
 * 열마다 다른 물건이 서 있는 것처럼 안 보인다.
 */
export function FacetPicker({
  label,
  groups,
  placeholder = '전부',
  align = 'start',
}: {
  /** 화면에는 안 보인다 — 머리칸이 이미 적고 있다. 읽어 주는 이름으로 쓴다. */
  label: string
  groups: FacetGroup[]
  /** 아무것도 안 걸렸을 때 칸에 적을 말. */
  placeholder?: string
  align?: 'start' | 'end'
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  // 닫으면 검색어를 비운다 — 다시 열었을 때 지난 검색이 남아 있으면 짧아진
  // 목록을 「없다」 로 읽는다.
  useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  const total = groups.reduce((sum, one) => sum + one.rows.length, 0)
  const needle = query.trim().toLowerCase()
  const shown = useMemo(
    () => groups.map((one) => ({ ...one, rows: one.rows.filter((row) => match(row, needle)) })),
    [groups, needle]
  )
  const found = shown.reduce((sum, one) => sum + one.rows.length, 0)
  const picked = groups
    .map((one) => {
      const row = one.rows.find((item) => item.key === one.value)
      return row ? `${one.badgePrefix ?? ''}${row.label}` : null
    })
    .find(Boolean)
  const on = Boolean(picked)

  function choose(group: FacetGroup, value: string | undefined) {
    group.onPick(value)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`${label} 로 거르기`}
          className={`${field(on)} flex items-center gap-1 px-2 text-left`}
        >
          <span className={`min-w-0 flex-1 truncate ${on ? '' : 'text-muted-foreground'}`}>
            {picked ?? placeholder}
          </span>
          <ChevronDown className="size-3 shrink-0 opacity-60" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align={align} className="w-64 p-0">
        {total >= SEARCH_FROM && (
          <div className="border-b p-2">
            <Input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="쳐서 좁히기"
              className="h-8"
              onKeyDown={(event) => {
                // **Enter 로 첫 줄을 고른다.** 치고 나서 마우스를 다시 잡게
                // 하면 검색칸이 절반만 일한 것이다.
                if (event.key !== 'Enter') return
                const first = shown.find((one) => one.rows.length > 0)
                if (first) choose(first, first.rows[0].key)
              }}
            />
          </div>
        )}

        <div className="max-h-72 overflow-y-auto py-1">
          {/* **「전부」 가 늘 첫 줄이다.** 고른 것을 푸는 길이 없으면
              새로고침으로 푸는 사람이 생긴다. */}
          <button
            type="button"
            className="hover:bg-muted flex w-full items-center px-3 py-1.5 text-left text-sm"
            onClick={() => {
              groups.forEach((one) => one.onPick(undefined))
              setOpen(false)
            }}
          >
            <span className={on ? '' : 'font-medium'}>전부</span>
          </button>

          {shown.map((group, at) => (
            // **무리에 이름을 붙인다.** 「거친 것」·「안 거친 것」 처럼 줄의
            // 글자가 똑같고 뜻만 다른 무리가 있다 — 제목을 눈으로만 보이면
            // 화면 읽개를 쓰는 사람에게는 같은 줄이 두 번 나올 뿐이다.
            <div
              key={group.title ?? at}
              role={group.title ? 'group' : undefined}
              aria-label={group.title}
            >
              {group.title && group.rows.length > 0 && (
                <p className="text-muted-foreground px-3 pt-2 pb-0.5 text-[11px]">{group.title}</p>
              )}
              {group.rows.map((row) => (
                <button
                  key={`${at}-${row.key}`}
                  type="button"
                  className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                  onClick={() => choose(group, row.key)}
                >
                  <span
                    className={`min-w-0 flex-1 truncate ${group.value === row.key ? 'font-medium' : ''}`}
                  >
                    {row.label}
                  </span>
                  {/* **수를 함께 적는다.** 골라도 0건인 선택지가 없다는 것을
                      보이는 것이 거르기를 믿게 하는 유일한 방법이다. */}
                  {row.count != null && (
                    <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                      {row.count}
                    </span>
                  )}
                </button>
              ))}
            </div>
          ))}

          {found === 0 && (
            <p className="text-muted-foreground px-3 py-6 text-center text-sm">
              찾는 것이 없습니다.
            </p>
          )}
        </div>

        {total >= SEARCH_FROM && (
          <p className="text-muted-foreground border-t px-3 py-1.5 text-xs tabular-nums">
            {total}개 중 {found}개
          </p>
        )}
      </PopoverContent>
    </Popover>
  )
}

export function ColumnFilter({
  label,
  value,
  onChange,
  options,
  placeholder,
  align = 'left',
  sort,
  children,
}: {
  label: string
  value: string
  onChange: (next: string) => void
  /** 주면 이름이 정렬 손잡이가 된다. 거르기와 정렬은 **다른 축**이라 함께 산다 —
   *  「MD 만 보면서 등록 일시 순으로」 가 정상 요구다. */
  sort?: SortHandle
  /** 고를 값이 정해져 있으면 준다. 안 주면 자유 입력.
   *  **개수를 함께 받는다** — 분류 후보는 「실제로 있는 조합」 이라 개수가 붙어
   *  오고, 그 숫자가 고르기 전에 몇 건인지 말해 준다.
   *
   *  **`label` 은 값과 보이는 글자가 다를 때 준다.** 값이 곧 사람이 읽을 말인
   *  자리(방향·사업부)가 대부분이라 기본은 값 그대로지만, 서버 코드값을 거르는
   *  자리(`global`·`mine`)는 그것을 그대로 보이면 목록이 영어로 선다. */
  options?: readonly (string | { value: string; label?: string; count?: number })[]
  placeholder?: string
  align?: 'left' | 'right'
  /** 같은 열을 **다른 축으로** 한 번 더 거를 때. 거르는 칸 아래에 선다 —
   *  「처리」 열이 상태(안 함·채택됨)와 단계를 함께 받는 자리다. */
  children?: React.ReactNode
}) {
  const on = value !== ''

  return (
    <div className={`flex flex-col gap-1.5 ${align === 'right' ? 'items-end' : ''}`}>
      <span className="flex items-center gap-1 tracking-wide">
        {sort ? <SortButton label={label} sort={sort} /> : label}
        {/* **켜진 것을 글자 높이에서 보인다.** 아래 칸의 테두리만으로는 열이
            여럿일 때 눈에 안 들어온다. */}
        {on && <span className="bg-primary size-1.5 rounded-full" aria-hidden />}
      </span>

      {options && options.length >= SEARCH_FROM ? (
        // **여덟을 넘으면 눈으로 못 찾는다.** 같은 자리, 같은 생김새로
        // 쳐서 좁히는 창을 연다.
        <FacetPicker
          label={label}
          groups={[
            {
              rows: options.map((one) =>
                typeof one === 'string'
                  ? { key: one, label: one }
                  : { key: one.value, label: one.label ?? one.value, count: one.count }
              ),
              value: value || undefined,
              onPick: (next) => onChange(next ?? ''),
            },
          ]}
        />
      ) : options ? (
        <select
          aria-label={`${label} 로 거르기`}
          className={`${field(on)} px-2`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">전부</option>
          {options.map((one) => {
            const item = typeof one === 'string' ? { value: one } : one
            return (
              <option key={item.value} value={item.value}>
                {item.label ?? item.value}
                {item.count != null ? ` (${item.count})` : ''}
              </option>
            )
          })}
        </select>
      ) : (
        <div className="relative w-full">
          <Search className="text-muted-foreground/70 pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
          <input
            aria-label={`${label} 로 거르기`}
            className={`${field(on)} pr-7 pl-7 font-normal`}
            value={value}
            placeholder={placeholder ?? '찾기'}
            onChange={(event) => onChange(event.target.value)}
          />
          {/* **비우는 단추를 둔다.** 지워서 비우는 것과 「전부」 로 돌아가는 것이
              같은 동작이지만, 칸이 좁아 글자가 남아 있는지 눈에 잘 안 띈다. */}
          {on && (
            <button
              type="button"
              aria-label={`${label} 거르기 지우기`}
              className="text-muted-foreground hover:bg-muted hover:text-foreground absolute top-1/2 right-1 grid size-5 -translate-y-1/2 place-items-center rounded-full transition-colors"
              onClick={() => onChange('')}
            >
              <X className="size-3" />
            </button>
          )}
        </div>
      )}

      {children}
    </div>
  )
}
