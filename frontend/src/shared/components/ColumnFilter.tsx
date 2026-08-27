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
 * ## 고르는 칸과 치는 칸
 *
 * `options` 를 주면 고르는 칸, 안 주면 치는 칸이다. **값이 정해져 있으면 고르게
 * 한다** — 방향은 넷뿐인데 자유 입력으로 두면 `md` 를 쳐서 0건을 보게 된다.
 */

import { Search, X } from 'lucide-react'

export function ColumnFilter({
  label,
  value,
  onChange,
  options,
  placeholder,
  align = 'left',
}: {
  label: string
  value: string
  onChange: (next: string) => void
  /** 고를 값이 정해져 있으면 준다. 안 주면 자유 입력.
   *  **개수를 함께 받는다** — 분류 후보는 「실제로 있는 조합」 이라 개수가 붙어
   *  오고, 그 숫자가 고르기 전에 몇 건인지 말해 준다. */
  options?: readonly (string | { value: string; count?: number })[]
  placeholder?: string
  align?: 'left' | 'right'
}) {
  const on = value !== ''
  return (
    <div className={`space-y-1 ${align === 'right' ? 'text-right' : ''}`}>
      <div className="text-xs font-medium">{label}</div>
      {options ? (
        <select
          aria-label={`${label} 로 거르기`}
          className={`border-input bg-background h-7 w-full rounded-md border px-1.5 text-xs ${
            on ? 'border-primary' : ''
          }`}
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
        <div className="relative">
          <Search className="text-muted-foreground pointer-events-none absolute top-1.5 left-1.5 size-3.5" />
          <input
            aria-label={`${label} 로 거르기`}
            className={`border-input bg-background h-7 w-full rounded-md border pr-5 pl-6 text-xs ${
              on ? 'border-primary' : ''
            }`}
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
              className="text-muted-foreground hover:text-foreground absolute top-1.5 right-1"
              onClick={() => onChange('')}
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
