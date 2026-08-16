/**
 * 레시피 고르기 — **검색이 붙은 선택기와, 자세히 보는 창.**
 *
 * ## 왜 드롭다운으로는 안 되나
 *
 * 레시피는 부서마다·규격마다 쌓인다. 인장 하나만 해도 사내규격·KS·ASTM 이
 * 갈리고, 거기에 "네킹 잘라서" 같은 변형이 붙는다. 스무 개만 넘어가도 이름만
 * 늘어놓은 목록에서는 원하는 것을 못 찾는다 — 재료 선택기에서 이미 겪은 문제다.
 *
 * ## 왜 상세 창이 따로 필요한가
 *
 * **레시피는 이름만 봐서는 고를 수 없다.** "인장 표준" 이 두 개 있을 때 무엇이
 * 다른지는 단계와 옵션을 봐야 안다 — 탄성 구간이 0.05~0.25% 인지 0~5% 인지,
 * 네킹을 자르는지. 좁은 팝오버에 그걸 다 넣으면 목록이 안 보이고, 목록만 보여
 * 주면 고를 근거가 없다. 그래서 **훑기(팝오버)와 견주기(모달)를 나눈다.**
 *
 * 재료 선택기와 다른 점: 재료는 수천 개라 **서버가** 검색하지만, 레시피는 부서당
 * 수십 개 규모라 한 번 받아 화면에서 거른다. 서버 검색을 붙이면 API 가 하나
 * 늘고 얻는 것이 없다 — 규모가 커지면 그때 옮긴다.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronsUpDown, Globe2, Layers, Search } from 'lucide-react'

import type { Recipe, RecipeStep } from '@/modules/processing/api'
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
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

/** 팝오버에 한 번에 보여 주는 수. 넘으면 "검색하세요" 를 말한다. */
const GLIMPSE = 8

/** 이름·키·부서·시험종류·단계 이름 어디에 걸려도 찾힌다. */
export function matches(recipe: Recipe, query: string): boolean {
  if (!query) return true
  const haystack = [
    recipe.label,
    recipe.key,
    recipe.description ?? '',
    recipe.test_type_label,
    recipe.owner_workspace_name ?? '전역',
    // **단계 이름으로도 찾을 수 있어야 한다.** "네킹 자르는 레시피가 뭐였더라"
    // 가 실제로 사람이 기억하는 방식이다.
    ...(recipe.steps as unknown as RecipeStep[]).map((step) => step.plugin),
  ]
    .join(' ')
    .toLowerCase()
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word))
}

interface Props {
  recipes: Recipe[]
  value?: Recipe | null
  onSelect: (recipe: Recipe) => void
  placeholder?: string
  ariaLabel?: string
  className?: string
  /** 고른 뒤에도 값을 표시하지 않는다 — '불러오기' 처럼 동작만 하는 자리. */
  action?: boolean
}

export function RecipePicker({
  recipes,
  value,
  onSelect,
  placeholder = '레시피 고르기',
  ariaLabel,
  className,
  action = false,
}: Props) {
  const [open, setOpen] = useState(false)
  const [browsing, setBrowsing] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const found = useMemo(
    () => recipes.filter((item) => matches(item, query.trim())),
    [recipes, query]
  )

  // 열자마자 칠 수 있어야 한다. 한 번 더 클릭하게 만들면 검색을 안 쓰게 된다.
  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])

  function pick(recipe: Recipe) {
    onSelect(recipe)
    setOpen(false)
    setBrowsing(false)
    setQuery('')
  }

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            aria-label={ariaLabel ?? placeholder}
            className={`justify-between font-normal ${className ?? ''}`}
          >
            <span className="truncate">
              {action || !value ? (
                <span className="text-muted-foreground">{placeholder}</span>
              ) : (
                value.label
              )}
            </span>
            <ChevronsUpDown className="size-3.5 opacity-50" />
          </Button>
        </PopoverTrigger>

        <PopoverContent className="w-96 p-0" align="start">
          <div className="relative border-b">
            <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="이름·부서·단계…"
              className="h-9 rounded-none border-0 pl-7 focus-visible:ring-0"
            />
          </div>

          <div className="max-h-72 overflow-y-auto">
            {found.length === 0 ? (
              <p className="text-muted-foreground p-4 text-center text-xs">
                {recipes.length === 0
                  ? '저장된 레시피가 없습니다. 단계를 맞춘 뒤 [레시피로 저장]을 누르세요.'
                  : '찾는 레시피가 없습니다.'}
              </p>
            ) : (
              found.slice(0, GLIMPSE).map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className="hover:bg-accent flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left"
                  onClick={() => pick(item)}
                >
                  <span className="flex w-full items-center gap-1.5">
                    <span className="truncate text-sm">{item.label}</span>
                    {item.is_global && <Globe2 className="text-muted-foreground size-3" />}
                    <span className="text-muted-foreground ml-auto shrink-0 text-xs">
                      {item.steps.length}단계
                    </span>
                  </span>
                  <span className="text-muted-foreground truncate text-xs">
                    {item.test_type_label} ·{' '}
                    {item.is_global ? '전역' : item.owner_workspace_name}
                  </span>
                </button>
              ))
            )}
          </div>

          {/* **잘렸다는 사실을 숨기지 않는다.** 안 보이는 것을 없는 것으로
              읽으면 사람은 같은 레시피를 하나 더 만든다. */}
          <div className="flex items-center gap-2 border-t px-3 py-2">
            <span className="text-muted-foreground text-xs">
              {found.length > GLIMPSE
                ? `${found.length}개 중 ${GLIMPSE}개`
                : `${found.length}개`}
            </span>
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto h-7 text-xs"
              onClick={() => {
                setOpen(false)
                setBrowsing(true)
              }}
            >
              <Layers className="size-3" />
              자세히 보기
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      {browsing && (
        <RecipeBrowser
          recipes={recipes}
          initialQuery={query}
          onClose={() => setBrowsing(false)}
          onSelect={pick}
        />
      )}
    </>
  )
}

/**
 * 전용 창 — **단계까지 보고 견준다.**
 *
 * 이름이 비슷한 레시피가 여럿일 때 무엇이 다른지는 옵션을 봐야 안다. 왼쪽에서
 * 고르면 오른쪽에 단계가 펼쳐진다 — 팝오버에서는 자리가 없어 못 하던 일이다.
 */
function RecipeBrowser({
  recipes,
  initialQuery,
  onClose,
  onSelect,
}: {
  recipes: Recipe[]
  initialQuery: string
  onClose: () => void
  onSelect: (recipe: Recipe) => void
}) {
  const [query, setQuery] = useState(initialQuery)
  const found = useMemo(
    () => recipes.filter((item) => matches(item, query.trim())),
    [recipes, query]
  )
  const [activeKey, setActiveKey] = useState(found[0]?.key ?? '')
  const active = found.find((item) => item.key === activeKey) ?? found[0] ?? null

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>레시피 찾기</DialogTitle>
          <DialogDescription>
            이름이 비슷하면 단계를 보고 고르세요. 어느 구간에서 탄성계수를 재는지,
            네킹을 자르는지가 여기서 갈립니다.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="text-muted-foreground absolute top-1/2 left-2 size-4 -translate-y-1/2" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="이름·부서·시험 종류·단계 이름으로 찾기"
            className="pl-8"
            aria-label="레시피 검색"
          />
        </div>

        <div className="grid h-96 grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3">
          <div className="overflow-y-auto rounded-md border">
            {found.length === 0 ? (
              <p className="text-muted-foreground p-6 text-center text-xs">
                찾는 레시피가 없습니다.
              </p>
            ) : (
              found.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`flex w-full flex-col items-start gap-0.5 border-b px-3 py-2 text-left last:border-b-0 ${
                    active?.key === item.key ? 'bg-accent' : 'hover:bg-accent/50'
                  }`}
                  onClick={() => setActiveKey(item.key)}
                  onDoubleClick={() => onSelect(item)}
                >
                  <span className="flex w-full items-center gap-1.5">
                    <span className="truncate text-sm font-medium">{item.label}</span>
                    {!item.is_active && (
                      <Badge variant="destructive" className="text-xs">
                        중단
                      </Badge>
                    )}
                  </span>
                  <span className="text-muted-foreground truncate font-mono text-xs">
                    {item.key}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {item.test_type_label} ·{' '}
                    {item.is_global ? '전역' : item.owner_workspace_name} ·{' '}
                    {item.steps.length}단계
                  </span>
                </button>
              ))
            )}
          </div>

          <div className="overflow-y-auto rounded-md border p-3">
            {active ? (
              <>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{active.label}</span>
                  {active.is_global ? (
                    <Badge variant="outline" className="gap-1 text-xs">
                      <Globe2 className="size-3" />
                      전역
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="text-xs">
                      {active.owner_workspace_name}
                    </Badge>
                  )}
                </div>
                {active.description && (
                  <p className="text-muted-foreground mb-2 text-xs">{active.description}</p>
                )}
                <ol className="space-y-2">
                  {(active.steps as unknown as RecipeStep[]).map((step, index) => (
                    <li key={`${step.plugin}-${index}`} className="text-xs">
                      <span className="text-muted-foreground font-mono">{index + 1}.</span>{' '}
                      <span className="font-mono">{step.plugin}</span>
                      {/* **옵션이 곧 차이다.** 이름이 같은 레시피 둘을 가르는
                          것은 여기 적힌 숫자다. */}
                      {Object.keys(step.options ?? {}).length > 0 && (
                        <dl className="text-muted-foreground mt-0.5 ml-4 grid grid-cols-[auto_1fr] gap-x-2 border-l pl-2">
                          {Object.entries(step.options).map(([key, raw]) => (
                            <div key={key} className="contents">
                              <dt className="font-mono">{key}</dt>
                              <dd className="font-mono">{String(raw)}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                    </li>
                  ))}
                </ol>
              </>
            ) : (
              <p className="text-muted-foreground text-center text-xs">
                왼쪽에서 하나를 고르세요.
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-xs">{found.length}개</span>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" onClick={onClose}>
              취소
            </Button>
            <Button disabled={!active} onClick={() => active && onSelect(active)}>
              이 레시피 쓰기
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
