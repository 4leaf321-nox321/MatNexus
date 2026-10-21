/**
 * 아래까지 **통째로** 지운다 — 물어본 뒤에. 재료 · 시료 삭제 창이 함께 쓴다(2026-10-20).
 *
 * ## 숫자는 서버가 센다
 *
 * 화면이 나름대로 세면 사람이 본 숫자와 실제로 지워지는 것이 어긋나고, 그러면
 * 그 「예」 는 다른 것에 대한 대답이 된다. 그래서 열 때마다 서버에 다시 묻는다(`load`).
 *
 * ## 시험만 칸을 따로 둔다
 *
 * 시료 · 시편은 이름표에 가깝지만 **시험은 잰 값이다** — 곡선과 처리 결과가 거기
 * 매달려 있다. 한 칸으로 묶으면 「시료 정리하려다 측정 데이터를 날렸다」 가 난다.
 * 시험이 있으면 그 칸을 켜야 삭제 단추가 눌린다.
 *
 * ## 왜 하나로 묶었나
 *
 * 시료 삭제 창은 「시편이 남아 있어 지울 수 없습니다」 를 적어 놓고도 확인을 받았고, 누르면
 * 서버가 거절해 **아무 일도 없었다**(2026-10-20 사용자 보고). 재료에는 이 창이 이미 있었다 —
 * 같은 일을 두 벌로 두면 한쪽만 고쳐진다.
 *
 * ## 여럿을 고를 때 — 못 지우는 것은 낱개로
 *
 * 고른 시편 지우기(2026-10-20)도 이 창을 쓴다. 고른 것 중 일부가 막히면(권한 · 남의 시험)
 * **누구의 무엇 때문인지 이유와 함께** 보이고 나머지만 지운다 — 하나 때문에 전부를 다시
 * 고르게 하지 않는다. 전부 막히면 삭제 단추가 안 눌린다.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { TriangleAlert } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'

/** 함께 사라지는 것의 수. 시료를 지울 때는 `samples` 가 없다. */
export interface CascadeCounts {
  samples?: number
  specimens: number
  test_runs: number
  /** 고른 것 중 **지우지 않는 것** — 이유와 함께(여럿을 고를 때). */
  blocked?: { id: string; name: string | null; reason: string }[]
  /** 고른 것 중 실제로 지울 수 있는 수. 0 이면 지울 것이 없다(여럿을 고를 때). */
  left?: number
}

export function CascadeDeleteDialog({
  name,
  what,
  order,
  lead,
  planKey,
  open,
  load,
  remove,
  onClose,
  onDeleted,
}: {
  /** 지울 것의 이름(`SECC_1.0__01`). */
  name: string
  /** 지울 것의 종류 — 「이 재료만 사라집니다」. */
  what: string
  /** 지우는 순서 — 「시험 → 시편 → 시료 → 재료」. */
  order: string
  /** 목록 앞 문장. 기본은 「아래까지 함께 사라집니다」 — 고른 것 자체를 세어 보일 때 바꾼다. */
  lead?: ReactNode
  /** 무엇을 셀지 — 바뀌면 다시 센다(지울 것의 id). */
  planKey: string
  open: boolean
  load: () => Promise<CascadeCounts>
  remove: (includeTestRuns: boolean) => Promise<unknown>
  onClose: () => void
  /** 지운 뒤. 부르는 쪽이 목록으로 옮기거나 다시 읽는다. */
  onDeleted: () => void
}) {
  const [plan, setPlan] = useState<CascadeCounts | null>(null)
  const [runs, setRuns] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Error | null>(null)
  // **부르는 쪽이 그릴 때마다 새 함수를 넘긴다** — 효과의 의존에 넣으면 매번 다시 센다.
  const loader = useRef(load)
  loader.current = load

  useEffect(() => {
    if (!open) return
    // **열 때마다 다시 센다.** 사이에 누가 시편을 넣었으면 숫자가 다르고,
    // 사람은 지금 화면의 숫자를 보고 「예」 를 누른다.
    setPlan(null)
    setRuns(false)
    setFailure(null)
    let live = true
    loader
      .current()
      .then((found) => live && setPlan(found))
      .catch((caught) => live && setFailure(caught instanceof Error ? caught : new Error('세지 못했습니다.')))
    return () => {
      live = false
    }
  }, [open, planKey])

  const attached = plan ? (plan.samples ?? 0) + plan.specimens + plan.test_runs : 0
  // 고른 것이 전부 막혔으면 지울 것이 없다 — 눌러도 아무 일이 없는 단추를 두지 않는다.
  const nothing = plan?.left === 0
  // 시험이 있으면 그 칸을 켜야 지울 수 있다. 없으면 칸 자체가 안 뜬다.
  const ready = plan !== null && !nothing && (plan.test_runs === 0 || runs)
  const blocked = plan?.blocked ?? []

  async function confirm() {
    setBusy(true)
    setFailure(null)
    try {
      await remove(runs)
      onDeleted()
    } catch (caught) {
      setFailure(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{name} 을(를) 지웁니다</DialogTitle>
          <DialogDescription>
            소프트 삭제입니다 — 목록에서 사라지고, 기록은 감사 로그에 남습니다. 휴지통에서
            되살리면 함께 지운 것이 같이 돌아옵니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={failure} />

        {plan === null && !failure && (
          <p className="text-muted-foreground text-sm">무엇이 딸려 있는지 세는 중…</p>
        )}

        {blocked.length > 0 && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm">
            <p className="font-medium">지우지 않는 것 {blocked.length}건 — 그대로 남습니다</p>
            <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto text-xs">
              {blocked.map((one) => (
                <li key={one.id}>
                  <span className="font-mono">{one.name ?? one.id}</span> — {one.reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        {nothing && <p className="text-sm">지울 수 있는 것이 없습니다.</p>}

        {plan !== null && !nothing && attached === 0 && (
          <p className="text-sm">아무것도 딸려 있지 않습니다. 이 {what}만 사라집니다.</p>
        )}

        {plan !== null && !nothing && attached > 0 && (
          <div className="space-y-3">
            <p className="text-sm">
              {lead ?? (
                <>
                  아래까지 <b>함께 사라집니다.</b>
                </>
              )}{' '}
              지우는 순서는 {order}입니다.
            </p>
            <ul className="bg-muted/40 space-y-1 rounded-md border px-3 py-2 text-sm">
              {(plan.samples ?? 0) > 0 && (
                <li>
                  시료 <b>{plan.samples}건</b>
                </li>
              )}
              {plan.specimens > 0 && (
                <li>
                  시편 <b>{plan.specimens}건</b>
                </li>
              )}
              {plan.test_runs > 0 && (
                <li className="text-amber-700 dark:text-amber-500">
                  시험 <b>{plan.test_runs}건</b> — 곡선과 처리 결과가 여기 매달려
                  있습니다
                </li>
              )}
            </ul>

            {/* **시험만 칸을 따로 둔다.** 시료·시편은 이름표에 가깝지만 시험은
                잰 값이다 — 한 칸으로 묶으면 「시료 정리하려다 측정 데이터를
                날렸다」 가 난다. */}
            {plan.test_runs > 0 && (
              <label className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
                {/* shadcn 체크박스 프리미티브가 이 저장소에 없다. 다른 화면도
                    네이티브를 쓴다(`NoticesPage`) — 여기서 새로 들이지 않는다. */}
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={runs}
                  onChange={(event) => setRuns(event.target.checked)}
                />
                <span>
                  <span className="flex items-center gap-1.5 font-medium">
                    <TriangleAlert className="size-3.5" />
                    시험 {plan.test_runs}건도 함께 지웁니다
                  </span>
                  <span className="text-muted-foreground mt-0.5 block text-xs">
                    측정한 곡선과 처리 결과가 사라집니다. 원본 파일은 남지만 화면
                    에서는 닿을 수 없습니다.
                  </span>
                </span>
              </label>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button variant="destructive" onClick={confirm} disabled={!ready || busy}>
            {busy ? '지우는 중…' : '삭제'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
