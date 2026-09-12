/**
 * 「담기」 — **화면을 오가는 대신 대상이 사람을 따라온다**(ADR 0024).
 *
 * 시험 목록·재료 목록·카드 목록 어디서든 담고, 워크벤치에서 한 번에 민다.
 *
 * ## 언제 뜨는가 — **담으러 온 사람에게만 저절로**
 *
 * 처음에는 선택 줄의 단추였다. 색을 채우고 자리를 옮겨도 **못 찾는다는 말이 두 번
 * 나왔다** — 「일괄 데이터 처리」·「일괄 수정」·「삭제」 가 늘어선 줄에서는 하나 더 붙은 단추가
 * 그저 넷째 단추다. 그래서 고르는 순간 저절로 뜨게 했다.
 *
 * 그랬더니 반대쪽에서 말이 나왔다(2026-09-11): **담을 생각이 없는데 체크만 해도
 * 창이 뜬다.** 목록에서 줄을 고르는 일은 지우기·일괄 수정·일괄 데이터 처리에도 쓰는데,
 * 그때마다 담기 창이 화면을 가린다.
 *
 * 둘 다 맞는 말이라 **누가 왔는지로 가른다.**
 *
 *     평소                단추만 선다 (「일괄 데이터 처리」 옆) — 누르면 창이 뜬다
 *     워크벤치에서 왔다     고르는 순간 뜬다 — 그 사람은 담으러 온 것이다
 *
 * 워크벤치가 담으러 보낼 때 주소에 `?collect=` 를 단다(`COLLECT_AT`). 화면이 그것을
 * 읽어 `auto` 로 넘긴다 — 「지금 활성 작업이 있나」 로 판단하지 않는다. 그 값은 한 번
 * 워크벤치를 쓴 뒤로 계속 남아 있어서, 그걸로 가르면 결국 늘 뜨는 것과 같아진다.
 *
 * 떠 있는 패널이라는 것은 그대로다. 색을 진하게 준 것은 장식이 아니라 「이건 저 줄의
 * 일부가 아니다」 를 말하기 위해서다. **닫는 단추가 있다** — 저절로 뜬 것도 사람이
 * 치울 수 있어야 한다.
 *
 * **끌어서 옮길 수 있다.** 떠 있는 것은 무언가를 가린다 — 하필 지금 보려는 줄을 가리면
 * 그때부터는 방해물이다. 옮긴 자리는 이 브라우저가 기억한다.
 *
 * ## 무엇을 담는지도 적는다
 *
 * 수만 적으면(「3건 담기」) 고른 것이 맞는지 확인하려고 목록으로 눈을 되돌려야 한다 —
 * 그 사이에 스크롤이 어긋나 있으면 확인이 안 된다. 고른 것의 이름을 패널이 들고 있는다.
 * 길면 앞의 몇만 적고 나머지는 수로 접는다.
 *
 * ## 어디에 담기는지 늘 적는다 — 그리고 그것이 무엇인지도
 *
 * 「지금 작업」 은 이 브라우저가 기억하지만(`shared/api/basket`), 그 이름을 패널에
 * 적는다. 숨겨 두면 **담고 나서 어디 갔는지 찾아야 한다** — 그런 단추는 한 번 잘못
 * 담긴 뒤로 아무도 안 쓴다.
 *
 * 이름만 적어서는 모자랐다(2026-09-05). 「test11에 담기」 가 불쑥 떠서 「test11 이
 * 뭔데」 가 됐다 — 그것이 **진행 중인 워크벤치 작업**이라는 말과, 고를 수 있는 작업
 * 목록을 늘 보인다. 작업이 하나뿐이어도 고르는 칸을 둔다: 그래야 이것이 「작업」이고
 * 바꿀 수 있는 것임을 안다.
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

import { GripHorizontal, Inbox, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'

import { activeRun, basketApi, setActiveRun } from '@/shared/api/basket'
import type { BasketRun, ItemKind } from '@/shared/api/basket'
import { useMaybeAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/components/ui/button'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'

/** 옮겨 둔 자리. **기억한다** — 매번 같은 데로 돌아오면 매번 다시 치워야 한다. */
const SPOT = 'matnexus.basket.spot'

const PANEL = { width: 320, height: 230, margin: 16 }

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
  // **처음에는 한가운데.** 구석에 두면 「떠 있다」 는 것부터 못 알아본다 — 그것이
  // 줄 안의 단추를 두 번 못 찾은 이유였다. 가려서 거슬리면 끌어서 치우면 된다.
  return inView({
    x: (window.innerWidth - PANEL.width) / 2,
    y: (window.innerHeight - PANEL.height) / 2,
  })
}

interface BasketProps {
  kind: ItemKind
  /** 담을 것. 비어 있으면 패널이 안 뜬다. */
  ids: string[]
  /** 고른 것의 이름. `ids` 와 같은 차례. 안 주면 수만 적는다. */
  labels?: string[]
  onError?: (error: Error) => void
  /**
   * 워크벤치로 보내는 링크에 쓴다. **안 주면 내 부서로 정한다** — 부서 스코프가
   * 아닌 화면(재료·카드 목록)에서도 돌아갈 자리는 있어야 하고, `default` 로 두면
   * 자기 부서가 아닌 곳을 가리켜 작업 목록이 비어 보인다(`AppShell` 과 같은 규칙).
   */
  workspaceSlug?: string
  /**
   * 고르는 순간 창이 뜨나. **워크벤치에서 담으러 온 길에서만 참이다**
   * (`?collect=`). 평소에는 단추만 서고, 누를 때 뜬다.
   */
  auto?: boolean
}

export function AddToBasket({ kind, ids, labels, onError, workspaceSlug, auto }: BasketProps) {
  const [spot, setSpot] = useState<Spot>(() => firstSpot())
  const grab = useRef<{ dx: number; dy: number } | null>(null)
  const [open, setOpen] = useState(false)

  // **고른 것이 없어지면 처음으로 돌아간다.** 닫아 둔 것을 기억한 채로 두면,
  // 다음에 담으러 와서 골라도 안 뜬다.
  useEffect(() => {
    if (ids.length === 0) setOpen(false)
    else if (auto) setOpen(true)
  }, [ids.length === 0, auto])

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

  // **고른 게 없으면 안 뜬다.** 떠 있는 것은 무언가를 가리므로, 할 일이 있을 때만 뜬다.
  if (ids.length === 0) return null

  // 줄에 서는 단추. **창이 뜨면 물러난다** — 「담기」 라고 적힌 것이 둘이면
  // 어느 것을 눌러야 하는지 사람이 판단해야 한다. 닫으면 다시 선다.
  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Inbox className="size-4" />
        워크벤치에 추가
      </Button>
    )
  }

  const panel = (
    <div
      className="fixed z-50 w-80 overflow-hidden rounded-xl border border-sky-300 bg-white shadow-2xl ring-1 ring-sky-400/25 dark:border-sky-500/40 dark:bg-neutral-900"
      style={{ left: spot.x, top: spot.y }}
      role="region"
      aria-label="추가"
    >
      {/* 손잡이. **끌어서 옮긴다** — 하필 지금 보려는 줄을 가리면 방해물이 된다. */}
      <div
        className="flex cursor-grab items-center gap-2 border-b border-sky-200 bg-gradient-to-r from-sky-100 via-sky-100 to-blue-100 px-3 py-2 text-sky-900 select-none active:cursor-grabbing dark:border-sky-500/30 dark:from-sky-950 dark:via-sky-900 dark:to-blue-950 dark:text-sky-100"
        aria-label="끌어서 이동"
        onPointerDown={(event) => {
          grab.current = { dx: event.clientX - spot.x, dy: event.clientY - spot.y }
        }}
      >
        <GripHorizontal className="size-4 shrink-0 opacity-80" />
        <Inbox className="size-4 shrink-0" />
        <span className="text-sm font-semibold">워크벤치 작업에 추가</span>
        <span className="ml-auto text-xs font-medium opacity-80">{ids.length}건</span>
        {/* **닫을 수 있어야 한다.** 저절로 뜬 것을 치울 길이 없으면 그것은
            창이 아니라 방해물이다. 선택은 그대로 둔다 — 담기만 접는 것이다. */}
        <button
          type="button"
          className="-mr-1 rounded p-0.5 opacity-70 hover:bg-sky-200/60 hover:opacity-100 dark:hover:bg-sky-800/60"
          aria-label="닫기"
          onClick={() => setOpen(false)}
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="p-3">
        <BasketForm
          kind={kind}
          ids={ids}
          labels={labels}
          onError={onError}
          workspaceSlug={workspaceSlug}
        />
      </div>
    </div>
  )

  // **본문 밖에 그린다.** 목록이 스크롤되거나 접혀도 패널은 제자리에 떠 있어야 한다.
  return createPortal(panel, document.body)
}

/**
 * 담기의 몸통 — **떠 있는 패널과 카드 목록의 띠가 같은 것을 쓴다.**
 *
 * 카드 목록에서는 내보내기 띠와 나란히 뜨는 것이 「팝업 두 개」 로 읽혀서, 그 화면은
 * 띠 하나에 탭으로 가른다(`fitting/SelectionBar`). 담는 규칙이 두 벌이 되지 않도록
 * 몸통을 여기서 하나로 둔다.
 */
export function BasketForm({ kind, ids, labels, onError, workspaceSlug }: BasketProps) {
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

  return (
      <div className="space-y-2">
        {/* **무엇을 담는지 보여 준다.** 수만 적으면 고른 것이 맞는지 확인하려고
            목록으로 눈을 되돌려야 한다. */}
        {labels && labels.length > 0 && (
          <ul className="text-muted-foreground max-h-24 space-y-0.5 overflow-y-auto text-xs">
            {labels.slice(0, 5).map((label, at) => (
              <li key={`${label}-${at}`} className="truncate">
                {label}
              </li>
            ))}
            {labels.length > 5 && <li>외 {labels.length - 5}건</li>}
          </ul>
        )}
        {/* **작업이 없으면 만들라고 말한다.** 꺼진 단추만 두면 고장으로 읽힌다. */}
        {runs !== null && runs.length === 0 ? (
          <p className="text-muted-foreground text-xs">
            진행 중인 워크벤치 작업이 없습니다.{' '}
            <Link to={home} className="font-medium text-sky-700 underline underline-offset-2 dark:text-sky-400">
              워크벤치에서 작업을 시작
            </Link>
            하면 여기서 담을 수 있습니다.
          </p>
        ) : (
          <>
            {/* **무엇에 담기는지 말한다.** 작업 이름만 뜨면 「그게 뭔데」 가 된다. */}
            <p className="text-muted-foreground text-xs">
              진행 중인 <b>워크벤치 작업</b> 하나를 골라 담습니다. 담은 것은 그 작업의
              워크벤치에서 한 번에 씁니다.
            </p>
            {/* **늘 고르는 칸이다.** 하나뿐일 때 숨기면 그것이 작업이라는 것도, 바꿀 수
                있다는 것도 안 보인다. */}
            <label className="block space-y-1 text-xs">
              <span className="text-muted-foreground">담을 작업</span>
              <select
                aria-label="담을 작업"
                className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
                value={chosen ?? ''}
                onChange={(event) => {
                  setChosen(event.target.value)
                  setActiveRun(event.target.value)
                }}
              >
                {(runs ?? []).map((one) => (
                  <option key={one.id} value={one.id}>
                    {one.title}
                  </option>
                ))}
              </select>
            </label>
            {/* **어디에 담기는지 늘 적는다.** 숨기면 담고 나서 찾아야 한다. */}
            <Button
              className="w-full min-w-0 justify-start bg-sky-600 text-white hover:bg-sky-700"
              size="sm"
              disabled={busy || target === null}
              onClick={() => void add()}
            >
              <Inbox className="size-4 shrink-0" />
              <span className="truncate">{target ? `「${target.title}」에 추가` : '추가'}</span>
            </Button>

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
  )
}
