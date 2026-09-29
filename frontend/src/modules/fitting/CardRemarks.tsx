/**
 * 카드에 붙은 **코멘트** — 근거 시험이 다른 두께의 재료로 옮겨진 일 따위(2026-09-29).
 *
 * 확정 카드라도 근거 시편을 옮기는 것은 막지 않는다 — 막으면 잘못 넣은 자료를 영영 못 고친다.
 * 대신 카드를 보는 사람이 「이 값의 근거 일부가 다른 재료로 갔다」 를 알아야 한다. 코멘트는
 * 카드의 값·근거와 따로 산다(서버 `PropertyCardRemark`).
 */

import { MessageSquareWarning } from 'lucide-react'

import type { PropertyCard } from '@/modules/fitting/api'
import { Badge } from '@/shared/components/ui/badge'

type Remark = NonNullable<PropertyCard['remarks']>[number]

/** 누가 언제 — 「관리자 · 2026. 9. 29.」 */
function who(remark: Remark): string {
  return [remark.created_by_name, new Date(remark.created_at).toLocaleDateString('ko-KR')]
    .filter(Boolean)
    .join(' · ')
}

function said(remark: Remark): string {
  return `${remark.message}${remark.comment ? ` — ${remark.comment}` : ''} (${who(remark)})`
}

/** 펼친 카드의 머리에 — 코멘트 전부. */
export function CardRemarks({ card }: { card: PropertyCard }) {
  const remarks = card.remarks ?? []
  if (remarks.length === 0) return null
  return (
    <ul
      aria-label="카드 코멘트"
      className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs"
    >
      {remarks.map((remark) => (
        <li key={remark.id} className="flex items-start gap-1.5">
          <MessageSquareWarning className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
          <span>
            {remark.message}
            {remark.comment && <b className="ml-1">— {remark.comment}</b>}
            <span className="text-muted-foreground ml-1">({who(remark)})</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/** 목록 한 줄에 — 몇 개 붙었는지만, 내용은 가리키면 보인다. */
export function RemarkBadge({ card }: { card: PropertyCard }) {
  const remarks = card.remarks ?? []
  if (remarks.length === 0) return null
  return (
    <Badge
      variant="outline"
      className="gap-1 border-amber-500/50 font-normal text-amber-700 dark:text-amber-500"
      title={remarks.map(said).join('\n')}
    >
      <MessageSquareWarning className="size-3" />
      코멘트 {remarks.length}
    </Badge>
  )
}
