/**
 * 재료 고르기 — **검색과 목록이 한 컨트롤이다.**
 *
 * 전에는 검색 입력과 드롭다운이 나란히 있는 별개 위젯이었다. 실사용 보고:
 * *"재료 검색에는 안 나오는데 우측의 일괄지정을 보면 리스트가 있다."*
 *
 * 검색은 제대로 걸리고 있었다. 다만 **입력칸 아래에 아무것도 안 뜨니 사람은
 * 검색이 안 된 줄 알았고**, 결과는 옆 드롭다운을 열어야 보였다. 두 위젯이
 * 하나의 일을 나눠 갖고 있으면 어느 쪽이 반응하는지 알 수 없다.
 *
 * 재료는 수천 개가 된다. 목록을 전부 받아 화면에서 거르는 방식은 그때 무너지므로
 * **검색은 서버가 한다.** 화면은 상한(50)만큼만 받고 "N개 중 M개" 를 말한다 —
 * 잘렸다는 사실을 숨기면 없는 재료처럼 보인다.
 */

import { useEffect, useRef, useState } from 'react'
import { Check, ChevronsUpDown, Globe2, Search } from 'lucide-react'

import { materialsApi } from '@/modules/materials/api'
import type { Material } from '@/modules/materials/api'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/** 한 번에 받는 수. 사람이 눈으로 훑을 수 있는 정도면 충분하다 — 나머지는 검색으로. */
const PAGE = 50

interface Props {
  /** 지금 고른 재료. 없으면 placeholder 를 보여 준다. */
  value?: Material | null
  onSelect: (material: Material) => void
  placeholder?: string
  disabled?: boolean
  className?: string
  /** 고른 뒤에도 값을 표시하지 않는다 — '일괄 지정' 처럼 동작만 하는 자리. */
  action?: boolean
  /** 화면에 같은 문구의 선택기가 여럿일 때 구분한다(낭독기·테스트). */
  ariaLabel?: string
}

export function MaterialPicker({
  value,
  onSelect,
  placeholder = '재료 고르기',
  disabled,
  className,
  action = false,
  ariaLabel,
}: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [applied, setApplied] = useState('')
  const [items, setItems] = useState<Material[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // 타이핑이 멎으면 찾는다. 글자마다 부르면 목록이 깜빡이고 서버도 시끄럽다.
  useEffect(() => {
    const timer = setTimeout(() => setApplied(query.trim()), 250)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    materialsApi
      .list({ q: applied, limit: PAGE })
      .then((page) => {
        if (cancelled) return
        setItems(page.items)
        setTotal(page.total)
      })
      .catch(() => {
        if (!cancelled) setItems([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, applied])

  // 열자마자 칠 수 있어야 한다. 한 번 더 클릭하게 만들면 검색을 안 쓰게 된다.
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          disabled={disabled}
          aria-label={ariaLabel ?? placeholder}
          className={`justify-between font-normal ${className ?? ''}`}
        >
          <span className="truncate">
            {action || !value ? (
              <span className="text-muted-foreground">{placeholder}</span>
            ) : (
              value.record_name
            )}
          </span>
          <ChevronsUpDown className="size-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-80 p-0">
        <div className="relative border-b">
          <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="이름·별칭·Grade·Family…"
            className="h-9 rounded-none border-0 pl-7 focus-visible:ring-0"
          />
        </div>

        <div className="max-h-64 overflow-y-auto p-1">
          {/* 빈 목록을 그냥 비워 두지 않는다. 검색이 걸러 낸 것인지, 재료가
              없는 것인지, 불러오는 중인지 구분이 안 되면 고장으로 보인다. */}
          {items.length === 0 && (
            <p className="text-muted-foreground p-3 text-center text-xs">
              {loading
                ? '찾는 중…'
                : applied
                  ? `'${applied}' 에 맞는 재료가 없습니다`
                  : '등록된 재료가 없습니다'}
            </p>
          )}

          {items.map((material) => (
            <button
              key={material.id}
              type="button"
              className="hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm"
              onClick={() => {
                onSelect(material)
                setOpen(false)
              }}
            >
              <Check
                className={`size-3.5 shrink-0 ${
                  value?.id === material.id ? '' : 'invisible'
                }`}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-xs">
                  {material.record_name}
                </span>
                {material.alias && (
                  <span className="text-muted-foreground block truncate text-xs">
                    {material.alias}
                  </span>
                )}
              </span>
              {material.is_global && (
                <Globe2 className="text-muted-foreground size-3.5 shrink-0" />
              )}
            </button>
          ))}
        </div>

        {total > items.length && (
          <p className="text-muted-foreground border-t p-2 text-xs">
            {total}개 중 {items.length}개 — 검색으로 좁히세요
          </p>
        )}
      </PopoverContent>
    </Popover>
  )
}
