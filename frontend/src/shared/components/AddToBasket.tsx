/**
 * 「담기」 — **화면을 오가는 대신 대상이 사람을 따라온다**(ADR 0024).
 *
 * 시험 목록·재료 목록·카드 목록 어디서든 담고, 워크벤치에서 한 번에 민다.
 *
 * ## 어디에 담기는지 단추가 늘 적는다
 *
 * 「지금 작업」 은 이 브라우저가 기억하지만(`shared/api/basket`), 그 이름을 단추에
 * 적는다. 숨겨 두면 **담고 나서 어디 갔는지 찾아야 한다** — 그런 단추는 한 번 잘못
 * 담긴 뒤로 아무도 안 쓴다.
 *
 * ## 작업은 여기서 만들지 않는다
 *
 * 진행 중인 작업이 없으면 워크벤치로 보낸다. 목록 화면에서 작업을 만들게 하면
 * 「무엇을 하는 작업인가」(워크플로)를 여기서 또 골라야 하고, 그러면 시작하는 자리가
 * 둘이 된다.
 *
 * ## `shared` 에 있는 이유
 *
 * 도메인 모듈이 워크벤치 모듈을 부르면 방향이 뒤집힌다. 바구니는 인증·알림처럼 앱을
 * 가로지르는 배관이라, 이 파일도 아무 도메인 모듈을 import 하지 않는다.
 */

import { Check, Inbox } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { activeRun, basketApi, setActiveRun } from '@/shared/api/basket'
import type { BasketRun, ItemKind } from '@/shared/api/basket'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'

export function AddToBasket({
  kind,
  ids,
  onError,
  workspaceSlug,
}: {
  kind: ItemKind
  /** 담을 것. 비어 있으면 단추가 꺼진다. */
  ids: string[]
  onError?: (error: Error) => void
  /** 워크벤치로 보내는 링크에 쓴다. 없으면 링크를 안 건다. */
  workspaceSlug?: string
}) {
  const [runs, setRuns] = useState<BasketRun[] | null>(null)
  const [chosen, setChosen] = useState<string | null>(activeRun())
  const [added, setAdded] = useState(0)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let alive = true
    void basketApi
      .runs('running')
      .then((found) => {
        if (!alive) return
        setRuns(found)
        // 기억해 둔 작업이 끝났거나 남의 부서 것이면 그 값은 못 쓴다.
        setChosen((now) => (found.some((one) => one.id === now) ? now : (found[0]?.id ?? null)))
      })
      .catch(() => alive && setRuns([]))
    return () => {
      alive = false
    }
  }, [])

  const target = (runs ?? []).find((one) => one.id === chosen) ?? null

  async function add() {
    if (!target || ids.length === 0) return
    setBusy(true)
    try {
      await basketApi.add(target.id, kind, ids)
      setActiveRun(target.id)
      setAdded(ids.length)
    } catch (caught) {
      onError?.(caught instanceof Error ? caught : new Error('담지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  // **작업이 없으면 만들라고 말한다.** 꺼진 단추만 두면 고장으로 읽힌다.
  if (runs !== null && runs.length === 0) {
    return (
      <span className="text-muted-foreground text-xs">
        {workspaceSlug ? (
          <Link to={`/w/${workspaceSlug}/workbench`} className="underline underline-offset-2">
            워크벤치에서 작업을 시작
          </Link>
        ) : (
          '워크벤치에서 작업을 시작'
        )}
        하면 여기서 담을 수 있습니다.
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1">
      <Button
        size="sm"
        variant="outline"
        disabled={busy || ids.length === 0 || target === null}
        onClick={() => void add()}
      >
        <Inbox className="size-3.5" />
        {/* **어디에 담기는지 늘 적는다.** 숨기면 담고 나서 찾아야 한다. */}
        {target ? `「${target.title}」에 담기` : '담기'}
        {ids.length > 1 && ` ${ids.length}건`}
      </Button>

      {(runs ?? []).length > 1 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="ghost" aria-label="담을 작업 고르기">
              ▾
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel className="text-xs font-normal">
              어느 작업에 담을까요
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {(runs ?? []).map((one) => (
              <DropdownMenuItem
                key={one.id}
                onSelect={() => {
                  setChosen(one.id)
                  setActiveRun(one.id)
                }}
              >
                {one.id === chosen && <Check className="size-3.5" />}
                {one.title}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {added > 0 && (
        <span className="text-muted-foreground text-xs">{added}건 담았습니다</span>
      )}
    </span>
  )
}
