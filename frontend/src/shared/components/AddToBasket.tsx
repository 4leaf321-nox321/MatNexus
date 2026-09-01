/**
 * 「담기」 — **화면을 오가는 대신 대상이 사람을 따라온다**(ADR 0024).
 *
 * 시험 목록·재료 목록·카드 목록 어디서든 담고, 워크벤치에서 한 번에 민다.
 *
 * ## 줄에 세우지 않고 **떠 있는 패널**로 띄운다
 *
 * 처음에는 선택 줄의 단추였다. 색을 채우고 자리를 옮겨도 **못 찾는다는 말이 두 번
 * 나왔다** — 「레시피 적용」·「일괄 수정」·「삭제」 가 늘어선 줄에서는 하나 더 붙은 단추가
 * 그저 넷째 단추다. 목록을 훑는 눈은 그 줄을 안 읽는다.
 *
 * 그래서 고르는 순간 **화면 위로 떠오르는 패널**이 된다. 색을 진하게 준 것은 장식이
 * 아니라 「이건 저 줄의 일부가 아니다」 를 말하기 위해서다.
 *
 * **끌어서 옮길 수 있다.** 떠 있는 것은 무언가를 가린다 — 하필 지금 보려는 줄을 가리면
 * 그때부터는 방해물이다. 옮긴 자리는 이 브라우저가 기억한다.
 *
 * ## 어디에 담기는지 늘 적는다
 *
 * 「지금 작업」 은 이 브라우저가 기억하지만(`shared/api/basket`), 그 이름을 패널에
 * 적는다. 숨겨 두면 **담고 나서 어디 갔는지 찾아야 한다** — 그런 단추는 한 번 잘못
 * 담긴 뒤로 아무도 안 쓴다.
 *
 * ## 담고 나면 돌아갈 길을 준다
 *
 * 「2건 담았습니다」 로 끝내면 사람은 담아 놓고 **어디로 가야 하는지 모른 채** 선다.
 * 담은 것이 모이는 자리로, 그 작업을 연 채로 가는 링크를 붙인다.
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

import { Check, GripHorizontal, Inbox } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'

import { activeRun, basketApi, setActiveRun } from '@/shared/api/basket'
import type { BasketRun, ItemKind } from '@/shared/api/basket'
import { useMaybeAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'

/** 옮겨 둔 자리. **기억한다** — 매번 같은 데로 돌아오면 매번 다시 치워야 한다. */
const SPOT = 'matnexus.basket.spot'

const PANEL = { width: 320, height: 150, margin: 16 }

interface Spot {
  x: number
  y: number
}

/** 창 안으로 되돌린다. 창을 줄였거나 다른 화면에서 옮겼으면 **밖에 나가 있다**. */
function inView(spot: Spot): Spot {
  const maxX = Math.max(PANEL.margin, window.innerWidth - PANEL.width - PANEL.margin)
  const maxY = Math.max(PANEL.margin, window.innerHeight - PANEL.height - PANEL.margin)
  return {
    x: Math.min(Math.max(PANEL.margin, spot.x), maxX),
    y: Math.min(Math.max(PANEL.margin, spot.y), maxY),
  }
}

function firstSpot(): Spot {
  try {
    const saved = window.localStorage.getItem(SPOT)
    if (saved) return inView(JSON.parse(saved) as Spot)
  } catch {
    // 못 읽으면 기본 자리로. 기억은 편의이지 조건이 아니다.
  }
  // 오른쪽 아래 — 목록은 왼쪽부터 읽는다.
  return inView({ x: window.innerWidth, y: window.innerHeight })
}

export function AddToBasket({
  kind,
  ids,
  onError,
  workspaceSlug,
}: {
  kind: ItemKind
  /** 담을 것. 비어 있으면 패널이 안 뜬다. */
  ids: string[]
  onError?: (error: Error) => void
  /**
   * 워크벤치로 보내는 링크에 쓴다. **안 주면 내 부서로 정한다** — 부서 스코프가
   * 아닌 화면(재료·카드 목록)에서도 돌아갈 자리는 있어야 하고, `default` 로 두면
   * 자기 부서가 아닌 곳을 가리켜 작업 목록이 비어 보인다(`AppShell` 과 같은 규칙).
   */
  workspaceSlug?: string
}) {
  // **로그인 정보가 없어도 패널은 뜬다.** 이 위젯은 여러 화면에 얹히는 곁들이라,
  // 제공자를 요구하면 그것을 품은 화면 전부가 같이 무거워진다.
  const user = useMaybeAuth()?.user
  const slug =
    workspaceSlug ?? user?.home_workspace_slug ?? user?.memberships[0]?.slug ?? DEFAULT_WORKSPACE
  const home = `/w/${slug}/workbench`

  const [runs, setRuns] = useState<BasketRun[] | null>(null)
  const [chosen, setChosen] = useState<string | null>(activeRun())
  const [added, setAdded] = useState(0)
  const [busy, setBusy] = useState(false)
  const [spot, setSpot] = useState<Spot>(() => firstSpot())
  const grab = useRef<{ dx: number; dy: number } | null>(null)

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

  // 창이 줄면 패널이 밖으로 나간다 — 되돌린다.
  useEffect(() => {
    const onResize = () => setSpot((now) => inView(now))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const stopDrag = useCallback(() => {
    if (!grab.current) return
    grab.current = null
    setSpot((now) => {
      try {
        window.localStorage.setItem(SPOT, JSON.stringify(now))
      } catch {
        // 기억 못 해도 옮긴 자리는 이번 화면 동안 유지된다.
      }
      return now
    })
  }, [])

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      if (!grab.current) return
      // 손잡이를 쥔 지점을 유지한다 — 안 그러면 잡는 순간 패널이 튄다.
      setSpot(inView({ x: event.clientX - grab.current.dx, y: event.clientY - grab.current.dy }))
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', stopDrag)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', stopDrag)
    }
  }, [stopDrag])

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

  // **고른 게 없으면 안 뜬다.** 떠 있는 것은 무언가를 가리므로, 할 일이 있을 때만 뜬다.
  if (ids.length === 0) return null

  const panel = (
    <div
      className="fixed z-50 w-80 overflow-hidden rounded-xl border border-violet-300/60 bg-white shadow-2xl ring-1 ring-violet-500/20 dark:border-violet-400/30 dark:bg-neutral-900"
      style={{ left: spot.x, top: spot.y }}
      role="region"
      aria-label="담기"
    >
      {/* 손잡이. **끌어서 옮긴다** — 하필 지금 보려는 줄을 가리면 방해물이 된다. */}
      <div
        className="flex cursor-grab items-center gap-2 bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500 px-3 py-2 text-white select-none active:cursor-grabbing"
        aria-label="끌어서 옮기기"
        onPointerDown={(event) => {
          grab.current = { dx: event.clientX - spot.x, dy: event.clientY - spot.y }
        }}
      >
        <GripHorizontal className="size-4 shrink-0 opacity-80" />
        <Inbox className="size-4 shrink-0" />
        <span className="text-sm font-semibold">{ids.length}건 담기</span>
      </div>

      <div className="space-y-2 p-3">
        {/* **작업이 없으면 만들라고 말한다.** 꺼진 단추만 두면 고장으로 읽힌다. */}
        {runs !== null && runs.length === 0 ? (
          <p className="text-muted-foreground text-xs">
            <Link to={home} className="font-medium text-violet-600 underline underline-offset-2">
              워크벤치에서 작업을 시작
            </Link>
            하면 여기서 담을 수 있습니다.
          </p>
        ) : (
          <>
            <div className="flex items-center gap-1">
              {/* **어디에 담기는지 늘 적는다.** 숨기면 담고 나서 찾아야 한다. */}
              <Button
                className="min-w-0 flex-1 justify-start bg-violet-600 text-white hover:bg-violet-700"
                size="sm"
                disabled={busy || target === null}
                onClick={() => void add()}
              >
                <Inbox className="size-4 shrink-0" />
                <span className="truncate">{target ? `「${target.title}」에 담기` : '담기'}</span>
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
            </div>

            {added > 0 && (
              <p className="text-xs font-medium text-emerald-700 dark:text-emerald-500">
                {added}건 담았습니다 ·{' '}
                <Link
                  to={target ? `${home}?run=${target.id}` : home}
                  className="underline underline-offset-2"
                >
                  워크벤치로
                </Link>
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )

  // **본문 밖에 그린다.** 목록이 스크롤되거나 접혀도 패널은 제자리에 떠 있어야 한다.
  return createPortal(panel, document.body)
}
