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
 * ## 켜진 것이 보여야 한다
 *
 * 거르는 중인 칸은 **테두리만 바꾸지 않는다.** 표에 열이 여덟이면 테두리 하나의
 * 색차는 눈에 안 들어오고, 사람은 "왜 결과가 적지" 를 검색어가 아니라 데이터
 * 탓으로 읽는다. 이름 옆에 점을 찍어 **글자 높이에서** 보이게 한다.
 */

import { ArrowDown, ArrowUp, ChevronsUpDown, Search, X } from 'lucide-react'

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
      <span className="text-muted-foreground text-[11px] font-medium tracking-wide">
        {sort ? <SortButton label={String(children)} sort={sort} /> : children}
      </span>
    </div>
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
}: {
  label: string
  value: string
  onChange: (next: string) => void
  /** 주면 이름이 정렬 손잡이가 된다. 거르기와 정렬은 **다른 축**이라 함께 산다 —
   *  「MD 만 보면서 등록 일시 순으로」 가 정상 요구다. */
  sort?: SortHandle
  /** 고를 값이 정해져 있으면 준다. 안 주면 자유 입력.
   *  **개수를 함께 받는다** — 분류 후보는 「실제로 있는 조합」 이라 개수가 붙어
   *  오고, 그 숫자가 고르기 전에 몇 건인지 말해 준다. */
  options?: readonly (string | { value: string; count?: number })[]
  placeholder?: string
  align?: 'left' | 'right'
}) {
  const on = value !== ''

  // **쉬는 상태에도 테두리가 있다.** 흐리게 뒀더니 「거를 수 있는 칸」 으로
  // 안 읽혔다 — 상자인지 그냥 글자인지가 눈에 안 들어온다. 켜지면 색이
  // 바뀌고, 그 차이는 이름 옆의 점이 함께 말한다.
  const field =
    'h-8 w-full rounded-md border bg-background text-xs transition-colors ' +
    'focus-visible:ring-ring/40 focus-visible:border-ring focus-visible:ring-2 focus-visible:outline-none ' +
    (on ? 'border-primary/60 bg-primary/[0.04]' : 'border-input hover:border-foreground/30')

  return (
    <div className={`flex flex-col gap-1.5 ${align === 'right' ? 'items-end' : ''}`}>
      <span className="text-muted-foreground flex items-center gap-1 text-[11px] font-medium tracking-wide">
        {sort ? <SortButton label={label} sort={sort} /> : label}
        {/* **켜진 것을 글자 높이에서 보인다.** 아래 칸의 테두리만으로는 열이
            여럿일 때 눈에 안 들어온다. */}
        {on && <span className="bg-primary size-1.5 rounded-full" aria-hidden />}
      </span>

      {options ? (
        <select
          aria-label={`${label} 로 거르기`}
          className={`${field} px-2`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">전부</option>
          {options.map((one) => {
            const item = typeof one === 'string' ? { value: one } : one
            return (
              <option key={item.value} value={item.value}>
                {item.value}
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
            className={`${field} pr-7 pl-7 font-normal`}
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
    </div>
  )
}
