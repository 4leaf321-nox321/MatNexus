/**
 * 빈 목록.
 *
 * **비어 있는 이유를 말한다.** "없습니다" 만 적으면 사람은 그것이 데이터가 없는
 * 것인지, 거르기가 너무 좁은 것인지, 권한이 없는 것인지 구별할 수 없다 — 셋은
 * 해야 할 일이 전혀 다르다.
 */

import type { ReactNode } from 'react'

interface EmptyStateProps {
  title: string
  /** 왜 비었는지, 무엇을 하면 되는지. */
  hint?: ReactNode
  action?: ReactNode
}

export function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="rounded-md border border-dashed py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-muted-foreground mx-auto mt-1 max-w-md text-sm">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}
