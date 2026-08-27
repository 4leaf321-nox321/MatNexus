/**
 * 재료를 **아래까지 통째로** 지운다 — 물어본 뒤에.
 *
 * ## 왜 필요했나
 *
 * *"재료를 삭제할 때 하위 시료/시편이 있으면 삭제 안 되는 문제가 있다"* — 실사용
 * 에서 나왔다. 서버가 막는 것은 맞다: 재료 하나를 지우는 뜻으로 누른 버튼이 시험
 * 200건을 함께 지우면 안 된다. 그런데 그러면 **정리할 방법이 아예 없었다** —
 * 시편을 하나씩, 시료를 하나씩 지워 올라가야 했다.
 *
 * 그리고 그전에는 삭제 버튼에 **확인이 아예 없었다.** 누르면 바로 지우려 들고,
 * 실패하면 그제서야 이유가 떴다.
 *
 * ## 숫자는 서버가 센다
 *
 * 화면이 나름대로 세면 사람이 본 숫자와 실제로 지워지는 것이 어긋나고, 그러면
 * 그 「예」 는 다른 것에 대한 대답이 된다. 그래서 열 때 `delete-plan` 을 부른다.
 *
 * ## 시험만 칸을 따로 둔다
 *
 * 시료·시편은 이름표에 가깝지만 **시험은 잰 값이다** — 곡선과 처리 결과가 거기
 * 매달려 있다. 한 칸으로 묶으면 「시료 정리하려다 측정 데이터를 날렸다」 가 난다.
 */

import { useEffect, useState } from 'react'
import { TriangleAlert } from 'lucide-react'

import { materialsApi } from '@/modules/materials/api'
import type { DeletePlan } from '@/modules/materials/api'
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

export function DeleteMaterialDialog({
  materialId,
  materialName,
  open,
  onClose,
  onDeleted,
}: {
  materialId: string
  materialName: string
  open: boolean
  onClose: () => void
  /** 지운 뒤. 부르는 쪽이 목록으로 옮기거나 다시 읽는다. */
  onDeleted: () => void
}) {
  const [plan, setPlan] = useState<DeletePlan | null>(null)
  const [runs, setRuns] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Error | null>(null)

  useEffect(() => {
    if (!open) return
    // **열 때마다 다시 센다.** 사이에 누가 시편을 넣었으면 숫자가 다르고,
    // 사람은 지금 화면의 숫자를 보고 「예」 를 누른다.
    setPlan(null)
    setRuns(false)
    setFailure(null)
    let live = true
    materialsApi
      .deletePlan(materialId)
      .then((found) => live && setPlan(found))
      .catch((caught) => live && setFailure(caught instanceof Error ? caught : new Error('세지 못했습니다.')))
    return () => {
      live = false
    }
  }, [open, materialId])

  const attached = plan ? plan.samples + plan.specimens + plan.test_runs : 0
  // 시험이 있으면 그 칸을 켜야 지울 수 있다. 없으면 칸 자체가 안 뜬다.
  const ready = plan !== null && (plan.test_runs === 0 || runs)

  async function remove() {
    setBusy(true)
    setFailure(null)
    try {
      await materialsApi.removeCascade(materialId, runs)
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
          <DialogTitle>{materialName} 을(를) 지웁니다</DialogTitle>
          <DialogDescription>
            소프트 삭제입니다 — 목록에서 사라지고, 기록은 감사 로그에 남습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={failure} />

        {plan === null && !failure && (
          <p className="text-muted-foreground text-sm">무엇이 딸려 있는지 세는 중…</p>
        )}

        {plan !== null && attached === 0 && (
          <p className="text-sm">아무것도 딸려 있지 않습니다. 이 재료만 사라집니다.</p>
        )}

        {plan !== null && attached > 0 && (
          <div className="space-y-3">
            <p className="text-sm">
              아래까지 <b>함께 사라집니다.</b> 지우는 순서는 시험 → 시편 → 시료 →
              재료입니다.
            </p>
            <ul className="bg-muted/40 space-y-1 rounded-md border px-3 py-2 text-sm">
              {plan.samples > 0 && (
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
          <Button variant="destructive" onClick={remove} disabled={!ready || busy}>
            {busy ? '지우는 중…' : '지우기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
