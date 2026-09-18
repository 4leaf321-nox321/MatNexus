/** 계정 상태 표시. 색과 한글 이름을 한 곳에서 정한다. */

import { Badge } from '@/shared/components/ui/badge'

const LABELS: Record<string, { text: string; className: string }> = {
  pending: {
    text: '승인 대기',
    className: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400',
  },
  active: {
    text: '활성',
    className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  },
  suspended: {
    text: '정지',
    className: 'border-destructive/40 bg-destructive/10 text-destructive',
  },
  // 삭제는 정지가 아니다 — 되살릴 수 없고, 아이디는 풀려 있다.
  deleted: {
    text: '삭제됨',
    className: 'border-muted-foreground/40 bg-muted text-muted-foreground line-through',
  },
}

export function StatusBadge({ status }: { status: string }) {
  const item = LABELS[status] ?? { text: status, className: '' }
  return (
    <Badge variant="outline" className={item.className}>
      {item.text}
    </Badge>
  )
}
