/**
 * 열 머리에서 거르기 — **길어지면 쳐서 찾는다.**
 *
 * ## 왜 드롭다운만으로는 안 되나 (2026-09-11 지적)
 *
 * 시험 목록의 재료는 102종이고 단계는 12종이다. 평범한 드롭다운은 그것을 통째로
 * 펼쳐 놓고 눈으로 찾으라고 한다 — 스물이 넘으면 그 일은 실패한다. 못 찾은
 * 사람은 **거르기를 안 쓰게 되고**, 그러면 목록을 눈으로 훑는다.
 *
 * TestScope 의 「보유 장비」 거르개가 같은 문제를 먼저 겪고 `SearchablePicker` 로
 * 풀었다. 여기도 같은 손에 맞아야 해서 같은 규칙을 따른다 — 다만 이쪽은 **열
 * 머리에 서는 작은 것**이라, 그 컴포넌트를 옮겨 오지 않고 머리글 크기로 짓는다.
 *
 * ## 짧으면 칸을 안 낸다
 *
 * 방향 넷·상태 셋에 검색칸을 달면 그것이 거추장스럽다. `SEARCH_FROM` 을 넘을
 * 때만 낸다 — 「손에 꼽는 것은 드롭다운」 이라는 TestScope 의 판단과 같다.
 *
 * ## 고를 수 있는 것은 **목록에 있는 값뿐**이다
 *
 * 기준정보 전체가 아니라 서버가 센 것(facets)만 준다. 골라도 0건인 선택지가
 * 섞이면 사람은 한 번 겪고 거르기를 안 믿는다. 그래서 옆에 **수를 함께** 적는다.
 *
 * ## 「전체」 가 늘 첫 줄이다
 *
 * 고른 것을 푸는 길이 없으면 새로고침으로 푸는 사람이 생긴다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'

import { Badge } from '@/shared/components/ui/badge'
import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/** 고를 수 있는 한 줄. 서버가 센 수를 함께 든다. */
export interface Facet {
  key: string
  label: string
  count: number
}

/** 이 수를 넘으면 검색칸을 낸다. 넷·다섯짜리 목록에는 거추장스럽다. */
export const SEARCH_FROM = 8

/** 한 무리. 「거친 것」·「안 거친 것」 처럼 뜻이 다른 묶음을 한 창에 둘 때 쓴다. */
export interface FacetGroup {
  /** 무리 이름. 하나뿐이면 안 그린다 — 이름 하나짜리 제목은 군더더기다. */
  title?: string
  rows: Facet[]
  /** 이 무리에서 고른 값. */
  value?: string
  onPick: (value: string | undefined) => void
  /** 배지에 붙일 말. 「없음: 진응력」 처럼 무엇으로 걸었는지 드러낸다. */
  badgePrefix?: string
}

function match(one: Facet, needle: string): boolean {
  if (!needle) return true
  return one.label.toLowerCase().includes(needle) || one.key.toLowerCase().includes(needle)
}

export function FacetPicker({
  label,
  groups,
  align = 'start',
}: {
  label: string
  groups: FacetGroup[]
  align?: 'start' | 'end'
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const box = useRef<HTMLInputElement>(null)

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

  if (total === 0) return <span>{label}</span>

  function choose(group: FacetGroup, value: string | undefined) {
    group.onPick(value)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="hover:text-foreground -ml-1 inline-flex max-w-full items-center gap-1 rounded px-1"
        >
          {label}
          {/* **걸린 것이 보여야 한다.** 목록이 왜 짧은지 여기서 설명된다. */}
          {picked && (
            <Badge variant="secondary" className="max-w-32 truncate text-[10px]">
              {picked}
            </Badge>
          )}
          <ChevronDown className="size-3 shrink-0 opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align={align} className="w-64 p-0">
        {total >= SEARCH_FROM && (
          <div className="border-b p-2">
            <Input
              ref={box}
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
          <button
            type="button"
            className="hover:bg-muted flex w-full items-center px-3 py-1.5 text-left text-sm"
            onClick={() => groups.forEach((one) => one.onPick(undefined))}
          >
            <span className={groups.some((one) => one.value) ? '' : 'font-medium'}>전체</span>
          </button>

          {shown.map((group, at) => (
            // **무리에 이름을 붙인다.** 「거친 것」·「안 거친 것」 처럼 줄의
            // 글자가 똑같고 뜻만 다른 무리가 있다 — 제목을 눈으로만 보이면
            // 화면 읽개를 쓰는 사람에게는 같은 줄이 두 번 나올 뿐이다.
            <div key={group.title ?? at} role={group.title ? 'group' : undefined} aria-label={group.title}>
              {group.title && group.rows.length > 0 && (
                <p className="text-muted-foreground px-3 pt-2 pb-0.5 text-[11px]">
                  {group.title}
                </p>
              )}
              {group.rows.map((row) => (
                <button
                  key={`${at}-${row.key}`}
                  type="button"
                  className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                  onClick={() => choose(group, row.key)}
                >
                  <span
                    className={`min-w-0 flex-1 truncate ${
                      group.value === row.key ? 'font-medium' : ''
                    }`}
                  >
                    {row.label}
                  </span>
                  {/* **수를 함께 적는다.** 골라도 0건인 선택지가 없다는 것을
                      보이는 것이 거르기를 믿게 하는 유일한 방법이다. */}
                  <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                    {row.count}
                  </span>
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
