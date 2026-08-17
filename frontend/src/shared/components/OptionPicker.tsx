/**
 * 값 하나 고르기 — **검색이 붙은 선택기.**
 *
 * ## 왜 늘어놓지 않나
 *
 * 처음에는 값을 버튼으로 줄줄이 폈다. Family 가 둘일 때는 그게 제일 빠르다 —
 * 열어 보지 않아도 무엇이 있는지 보인다. 그런데 **분류는 쌓인다.** 강종 하나만
 * 해도 Steel 밑에 HSS·AHSS·DP·TRIP 이 갈리고, 부서가 늘면 더 갈린다. 스무 개만
 * 넘어가도 줄이 무너지고, 그때 고치려면 화면을 다시 짜야 한다.
 *
 * 레시피 선택기가 같은 이유로 이 모양이다(`modules/processing/RecipePicker`).
 * 거기는 레시피의 단계를 견주는 상세 창까지 필요했는데, 분류는 **이름과 개수가
 * 전부**라 팝오버 하나면 된다.
 *
 * ## 개수를 함께 보여 주는 이유
 *
 * 고를 수는 있는데 결과가 0건인 값이 목록에 있으면 사람은 필터를 의심한다.
 * 개수가 붙어 있으면 고르기 전에 안다.
 *
 * 도메인을 모른다 — 값과 개수만 받는다.
 */

import { useMemo, useState } from 'react'
import { Check, ChevronsUpDown, Search } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/** 한 번에 그리는 수. 넘으면 **몇 개가 더 있는지 말한다** — 조용히 자르지 않는다. */
const VISIBLE = 60

export interface Option {
  value: string
  count?: number
}

interface Props {
  label: string
  value: string
  options: Option[]
  /** 아무것도 안 고른 상태의 이름. 기본은 '전체'. */
  anyLabel?: string
  onChange: (next: string) => void
}

export function OptionPicker({ label, value, options, anyLabel = '전체', onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState('')

  const matched = useMemo(() => {
    const needle = term.trim().toLowerCase()
    const found = needle
      ? options.filter((item) => item.value.toLowerCase().includes(needle))
      : options
    // 많이 쓰이는 것이 위로. 검색이 붙어 있으므로 가나다순보다 이쪽이 쓸모 있다.
    return [...found].sort((a, b) => (b.count ?? 0) - (a.count ?? 0))
  }, [options, term])

  function pick(next: string) {
    onChange(next)
    setOpen(false)
    setTerm('')
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-muted-foreground text-xs">{label}</span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button size="sm" variant="outline" className="h-7 gap-1 text-xs">
            {/* **고른 값이 트리거에 보인다.** 열어 봐야 아는 필터는 필터가 아니다. */}
            {value || anyLabel}
            <ChevronsUpDown className="size-3 opacity-50" />
          </Button>
        </PopoverTrigger>

        <PopoverContent className="w-72 p-0" align="start">
          <div className="relative border-b">
            <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
            <Input
              autoFocus
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder={`${label} 찾기`}
              className="h-9 border-0 pl-8 text-xs focus-visible:ring-0"
            />
          </div>

          <div className="max-h-72 overflow-y-auto p-1">
            <Row
              label={anyLabel}
              selected={value === ''}
              onClick={() => pick('')}
              muted
            />
            {matched.slice(0, VISIBLE).map((item) => (
              <Row
                key={item.value}
                label={item.value}
                count={item.count}
                selected={value === item.value}
                onClick={() => pick(item.value)}
              />
            ))}

            {matched.length === 0 && (
              <p className="text-muted-foreground px-2 py-6 text-center text-xs">
                '{term}' 에 맞는 {label} 이(가) 없습니다.
              </p>
            )}
          </div>

          {matched.length > VISIBLE && (
            <p className="text-muted-foreground border-t px-2 py-1.5 text-center text-xs">
              {matched.length - VISIBLE}개 더 있습니다 — 검색으로 좁히세요.
            </p>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}

function Row({
  label,
  count,
  selected,
  muted,
  onClick,
}: {
  label: string
  count?: number
  selected: boolean
  muted?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`hover:bg-muted flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs ${
        muted ? 'text-muted-foreground' : ''
      }`}
    >
      <Check className={`size-3.5 shrink-0 ${selected ? '' : 'invisible'}`} />
      <span className="flex-1 truncate">{label}</span>
      {count != null && <span className="text-muted-foreground tabular-nums">{count}</span>}
    </button>
  )
}
