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
 *
 * ## 두 가지 모드
 *
 * **정적** — `options` 를 통째로 받아 브라우저에서 거른다. 분류처럼 목록이
 * 수백을 안 넘는 자리에 쓴다. 왕복이 없어 즉각적이다.
 *
 * **서버 검색** — `search` 를 주면 타이핑할 때마다 서버에 묻는다. 어휘가 수만
 * 개가 되면(ADR 0010) 전체를 브라우저로 보낼 수 없다 — 페이로드도 문제지만,
 * 2만 개를 받아 놓고 60개만 그리는 것은 그냥 낭비다.
 *
 * 두 모드를 한 컴포넌트에 두는 이유: 쓰는 쪽 화면이 같아야 한다. 나누면 같은
 * 팝오버를 두 벌 그리게 되고, 그때부터 둘이 갈라진다(시료 폼에서 겪었다).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronsUpDown, Plus, Search } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/** 한 번에 그리는 수. 넘으면 **몇 개가 더 있는지 말한다** — 조용히 자르지 않는다. */
const VISIBLE = 60

/**
 * 서버 검색을 미루는 시간(ms).
 *
 * 글자마다 보내면 'SECC' 넉 자에 요청이 넷 나가고, 앞의 셋은 버려진다. 사람이
 * 타이핑을 멈추는 간격이 대략 이 정도다 — 더 길면 반응이 굼떠 보인다.
 */
const DEBOUNCE_MS = 200

export interface Option {
  value: string
  count?: number
}

interface Props {
  label: string
  value: string
  /** 정적 모드의 전체 목록. `search` 를 주면 첫 화면(빈 검색어)에만 쓰인다. */
  options: Option[]
  /**
   * 주면 **서버 검색 모드**가 된다. 타이핑이 멎으면 호출된다.
   *
   * 늦게 온 응답이 최신 결과를 덮지 않게 호출 순서를 지킨다 — 'S' 의 응답이
   * 'SECC' 보다 늦게 오는 일이 실제로 생긴다.
   */
  search?: (term: string) => Promise<Option[]>
  /**
   * 주면 **목록에 없는 값을 더할 수 있다**. `open` 축에서만 쓴다.
   *
   * 서버가 돌려준 값을 그대로 고른다 — 친 글자와 다를 수 있다. `'포스코(주)'`
   * 가 `'포스코'` 의 별칭이면 서버는 `'포스코'` 를 준다. 그때 화면이 친 글자를
   * 고르면 **어휘를 거친 의미가 사라진다.**
   */
  onCreate?: (term: string) => Promise<Option>
  /** 아무것도 안 고른 상태의 이름. 기본은 '전체'. */
  anyLabel?: string
  onChange: (next: string) => void
}

export function OptionPicker({
  label,
  value,
  options,
  search,
  onCreate,
  anyLabel = '전체',
  onChange,
}: Props) {
  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState('')
  const [remote, setRemote] = useState<Option[] | null>(null)
  const [busy, setBusy] = useState(false)
  /** 몇 번째 요청인가. 늦게 온 응답을 버리는 데 쓴다. */
  const issued = useRef(0)

  useEffect(() => {
    if (!search || !open) return
    const seq = ++issued.current
    setBusy(true)
    const timer = setTimeout(() => {
      search(term.trim())
        .then((found) => {
          // **늦게 온 응답은 버린다.** 'S' 가 'SECC' 보다 늦게 도착하면 목록이
          // 방금 친 글자와 어긋난 채로 남는다.
          if (seq === issued.current) setRemote(found)
        })
        .catch(() => {
          if (seq === issued.current) setRemote([])
        })
        .finally(() => {
          if (seq === issued.current) setBusy(false)
        })
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [search, open, term])

  const matched = useMemo(() => {
    // 서버 검색 모드면 거르지 않는다 — 서버가 이미 걸렀다. 여기서 또 거르면
    // 서버가 별칭으로 찾아 준 것이 화면에서 사라진다('포스코(주)' → 포스코).
    if (search) return remote ?? options
    const needle = term.trim().toLowerCase()
    const found = needle
      ? options.filter((item) => item.value.toLowerCase().includes(needle))
      : options
    // 많이 쓰이는 것이 위로. 검색이 붙어 있으므로 가나다순보다 이쪽이 쓸모 있다.
    return [...found].sort((a, b) => (b.count ?? 0) - (a.count ?? 0))
  }, [search, remote, options, term])

  function pick(next: string) {
    onChange(next)
    setOpen(false)
    setTerm('')
  }

  const typed = term.trim()
  // 이미 있는 값이면 '새로 추가' 를 안 보여 준다 — 눌러 봐야 같은 것이 나온다.
  const exists = matched.some((item) => item.value.toLowerCase() === typed.toLowerCase())
  const canCreate = Boolean(onCreate) && typed !== '' && !exists && !busy

  async function create() {
    if (!onCreate) return
    const added = await onCreate(typed)
    // **서버가 준 값을 고른다.** 친 글자가 아니다.
    pick(added.value)
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-muted-foreground text-xs">{label}</span>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          {/* **이름에 어느 칸인지가 들어가야 한다.** 보이는 글자는 고른 값뿐이라,
              한 폼에 피커가 다섯이면 버튼 다섯 개가 전부 '고르지 않음' 이라는
              같은 이름을 갖는다. 스크린리더로는 구분이 안 되고, 실제로 스모크
              시험도 같은 이유로 칸을 못 찾아 깨졌다(v0.7.0 부터 CI 빨강). */}
          <Button
            size="sm"
            variant="outline"
            className="h-7 gap-1 text-xs"
            aria-label={`${label}: ${value || anyLabel}`}
          >
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

            {matched.length === 0 &&
              (busy ? (
                <p className="text-muted-foreground px-2 py-6 text-center text-xs">
                  찾는 중…
                </p>
              ) : (
                <p className="text-muted-foreground px-2 py-6 text-center text-xs">
                  '{term}' 에 맞는 {label} 이(가) 없습니다.
                </p>
              ))}

            {canCreate && (
              <button
                type="button"
                onClick={() => void create()}
                className="hover:bg-muted/60 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm"
              >
                <Plus className="size-3.5 opacity-60" />
                <span>
                  '<b>{typed}</b>' 새로 추가
                </span>
              </button>
            )}
          </div>

          {/* 서버 검색 모드에서는 서버가 이미 상한을 걸어 보낸다. "몇 개 더" 를
              말할 수 없으므로(전체 수를 모른다) 좁히라고만 한다. */}
          {matched.length > VISIBLE && (
            <p className="text-muted-foreground border-t px-2 py-1.5 text-center text-xs">
              {search
                ? '검색으로 좁히세요.'
                : `${matched.length - VISIBLE}개 더 있습니다 — 검색으로 좁히세요.`}
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
