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
 *
 * 창 자체는 시료 삭제와 함께 쓴다(`CascadeDeleteDialog`, 2026-10-20).
 */

import { CascadeDeleteDialog } from '@/modules/materials/CascadeDeleteDialog'
import { materialsApi } from '@/modules/materials/api'

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
  return (
    <CascadeDeleteDialog
      name={materialName}
      what="재료"
      order="시험 → 시편 → 시료 → 재료"
      planKey={materialId}
      open={open}
      load={() => materialsApi.deletePlan(materialId)}
      remove={(runs) => materialsApi.removeCascade(materialId, runs)}
      onClose={onClose}
      onDeleted={onDeleted}
    />
  )
}
