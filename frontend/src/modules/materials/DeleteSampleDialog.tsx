/**
 * 시료를 **아래까지 통째로** 지운다 — 물어본 뒤에(2026-10-20).
 *
 * 전에는 시편이 남은 시료를 못 지웠다. 그런데 삭제 창은 「시편이 남아 있어 지울 수 없습니다」 를
 * 적어 놓고도 확인을 받았고, 누르면 서버가 거절해 **아무 일도 없었다** — 사용자 보고: 「시험
 * 데이터가 있다고 묻길래 지운다고 했는데 안 지워진다」. 재료와 같은 창이다: 무엇이 함께
 * 사라지는지 서버가 세고, 시험이 있으면 그 칸을 켜야 지운다(`CascadeDeleteDialog`).
 */

import { CascadeDeleteDialog } from '@/modules/materials/CascadeDeleteDialog'
import { materialsApi } from '@/modules/materials/api'

export function DeleteSampleDialog({
  sampleId,
  sampleName,
  open,
  onClose,
  onDeleted,
}: {
  sampleId: string
  sampleName: string
  open: boolean
  onClose: () => void
  /** 지운 뒤. 부르는 쪽이 고른 시료를 비우고 다시 읽는다. */
  onDeleted: () => void
}) {
  return (
    <CascadeDeleteDialog
      name={sampleName}
      what="시료"
      order="시험 → 시편 → 시료"
      planKey={sampleId}
      open={open}
      load={() => materialsApi.sampleDeletePlan(sampleId)}
      remove={(runs) => materialsApi.removeSampleCascade(sampleId, runs)}
      onClose={onClose}
      onDeleted={onDeleted}
    />
  )
}
