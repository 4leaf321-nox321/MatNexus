/** 의뢰 삭제 확인 창의 본문 — 목록과 상세가 같은 말을 한다. */

import type { Commission } from '@/modules/commissions/api'
/**
 * 무엇이 사라지는지 — 이름·수를 적는다. 접수된 뒤(관리자만 지울 수 있는 때)에는 이력과
 * 붙은 시험의 연결이 함께 간다는 것을 말한다. 시험 자체는 남는다.
 */
export function DeleteBody({
  item,
}: {
  item: Pick<Commission, 'seq' | 'title' | 'status' | 'item_count' | 'event_count' | 'progress'>
}) {
  const untouched = item.status === 'draft' || item.status === 'submitted'
  return (
    <>
      <b>
        #{item.seq} {item.title}
      </b>{' '}
      이 항목 {item.item_count}건, 이력 {item.event_count + 1}건과 함께 사라집니다.
      <p className="text-muted-foreground mt-2">
        {untouched
          ? '아직 받는 부서가 손대지 않은 건입니다.'
          : `받는 부서가 이미 다룬 건입니다 — 붙은 시험 ${item.progress.linked}건은 남고 의뢰와의 연결만 풀립니다. 처리가 끝난 건이면 지우는 대신 완료·반려로 두세요.`}
      </p>
    </>
  )
}
