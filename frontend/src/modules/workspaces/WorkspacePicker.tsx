/**
 * 부서 고르기 — 검색되고, **경로가 보인다.**
 *
 * ReportArchive 의 `WorkspaceCombobox` 를 참조했다. 거기서 가져온 판단 둘:
 *
 *   1. **경로를 보여 준다**(`개발본부 / 품질팀`). 같은 이름의 팀이 본부마다 있을
 *      수 있는데, 이름만 보여 주면 사람이 어느 쪽인지 고를 수 없다. 검색도 경로
 *      전체에 걸리므로 `개발 품질` 로 찾힌다.
 *   2. **보관된 부서를 새로 배정하는 자리에서는 감춘다**(`excludeArchived`).
 *      다만 *이미 골라져 있는* 값이 보관 부서면 그 항목만은 남긴다 — 안 그러면
 *      라벨이 빈칸이 되어 무엇이 골라져 있는지 알 수 없다.
 *
 * 목록은 화면에서 거른다. 재료(수천 개)와 달리 부서는 수십~수백이고 트리 순서가
 * 중요해서, 서버가 정한 순서를 그대로 들고 있는 편이 낫다.
 */

import { useMemo, useRef, useState } from 'react'
import { Building2, Check, ChevronsUpDown, Search } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/** 부서 선택기가 필요로 하는 최소 모양. 가입 화면의 `WorkspaceOption` 도 맞는다. */
export interface PickableWorkspace {
  slug: string
  name: string
  path: string
  depth: number
  is_active?: boolean
}

interface Props {
  workspaces: PickableWorkspace[]
  value: string | null
  onChange: (slug: string) => void
  placeholder?: string
  /** 보관된 부서를 목록에서 감춘다. 새로 배정하는 자리(가입·이동)에 쓴다. */
  excludeArchived?: boolean
  disabled?: boolean
  className?: string
  /** 고른 뒤에도 값을 표시하지 않는다 — 동작만 하는 자리. */
  action?: boolean
  emptyLabel?: string
}

export function WorkspacePicker({
  workspaces,
  value,
  onChange,
  placeholder = '부서 고르기',
  excludeArchived = false,
  disabled,
  className,
  action = false,
  emptyLabel = '부서가 없습니다',
}: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = workspaces.find((item) => item.slug === value) ?? null

  const options = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
    return workspaces.filter((item) => {
      // 보관 부서는 감추되 **지금 골라져 있는 것은 남긴다.**
      if (excludeArchived && item.is_active === false && item.slug !== value) return false
      if (words.length === 0) return true
      // 경로 전체에 건다 — 사람은 `개발 품질` 처럼 위아래를 섞어 친다.
      const haystack = `${item.path} ${item.slug}`.toLowerCase()
      return words.every((word) => haystack.includes(word))
    })
  }, [workspaces, query, excludeArchived, value])

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) {
          setQuery('')
          requestAnimationFrame(() => inputRef.current?.focus())
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          disabled={disabled}
          className={`justify-between font-normal ${className ?? ''}`}
          title={selected?.path}
        >
          <span className="flex min-w-0 items-center gap-1.5">
            <Building2 className="size-4 shrink-0 opacity-70" />
            <span className="truncate">
              {action || !selected ? (
                <span className="text-muted-foreground">{placeholder}</span>
              ) : (
                selected.path
              )}
            </span>
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-80 p-0">
        <div className="relative border-b">
          <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="부서 이름으로 찾기"
            className="h-9 rounded-none border-0 pl-7 focus-visible:ring-0"
          />
        </div>

        <div className="max-h-72 overflow-y-auto p-1">
          {options.length === 0 && (
            <p className="text-muted-foreground p-3 text-center text-xs">
              {query ? `'${query}' 에 맞는 부서가 없습니다` : emptyLabel}
            </p>
          )}

          {options.map((item) => (
            <button
              key={item.slug}
              type="button"
              className="hover:bg-accent hover:text-accent-foreground flex w-full items-center gap-2 rounded-md py-1.5 pr-2 text-left text-sm"
              // 들여쓰기로 계층을 보여 준다. 검색 중에도 유지한다 — 걸러진 결과에서
              // 깊이가 사라지면 `품질팀` 둘이 다시 구분이 안 된다.
              style={{ paddingLeft: `${item.depth * 14 + 8}px` }}
              onClick={() => {
                onChange(item.slug)
                setOpen(false)
              }}
            >
              <Check
                className={`size-3.5 shrink-0 ${item.slug === value ? '' : 'invisible'}`}
              />
              <span className="min-w-0 flex-1 truncate">{item.name}</span>
              {item.is_active === false && (
                <span className="text-muted-foreground shrink-0 text-xs">보관</span>
              )}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
