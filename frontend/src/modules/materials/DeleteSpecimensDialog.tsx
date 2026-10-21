/**
 * 시편을 **매달린 시험까지** 지운다 — 하나든 여럿이든(2026-10-20).
 *
 * 사용자 보고: 잘못된 옵션으로 올린 시험을 치우려면 시험을 하나씩 지운 뒤에야 시편을 지울 수
 * 있었다. 전에 시편 삭제 창은 「시험이 남아 있어 지울 수 없습니다」 를 적어 놓고 확인 단추를
 * 그대로 두었다. 재료 · 시료와 같은 창이다(`CascadeDeleteDialog`) — 서버가 세고, 시험이 있으면
 * 그 칸을 켜야 지우고, 막히는 것은 이유와 함께 보인다.
 */

import { useRef } from 'react'

import { CascadeDeleteDialog } from '@/modules/materials/CascadeDeleteDialog'
import { materialsApi } from '@/modules/materials/api'
import type { SpecimenDeleteResult } from '@/modules/materials/api'

export function DeleteSpecimensDialog({
  specimens,
  open,
  onClose,
  onDeleted,
}: {
  /** 지울 시편. 하나면 그 이름으로, 여럿이면 「고른 시편 N건」 으로 묻는다. */
  specimens: { id: string; record_name: string }[]
  open: boolean
  onClose: () => void
  /** 지운 뒤 — **지운 것**(요청한 것이 아니라)과 남은 것. 부르는 쪽이 알리고 다시 읽는다. */
  onDeleted: (done: SpecimenDeleteResult) => void
}) {
  const ids = specimens.map((one) => one.id)
  const single = specimens.length === 1
  const done = useRef<SpecimenDeleteResult | null>(null)
  return (
    <CascadeDeleteDialog
      name={single ? specimens[0].record_name : `고른 시편 ${specimens.length}건`}
      what="시편"
      order="시험 → 시편"
      // 여럿이면 고른 시편 자체를 세어 보인다 — 「아래까지」 가 아니다.
      lead={single ? undefined : '다음이 사라집니다.'}
      planKey={ids.join(',')}
      open={open}
      load={async () => {
        const plan = await materialsApi.specimenDeletePlan(ids)
        return {
          // 하나면 그 시편은 지울 대상이지 「딸린 것」 이 아니다.
          specimens: single ? 0 : plan.specimens,
          test_runs: plan.test_runs,
          blocked: plan.blocked,
          left: plan.specimens,
        }
      }}
      remove={async (includeTestRuns) => {
        done.current = await materialsApi.removeSpecimens(ids, includeTestRuns)
      }}
      onClose={onClose}
      onDeleted={() => done.current && onDeleted(done.current)}
    />
  )
}
