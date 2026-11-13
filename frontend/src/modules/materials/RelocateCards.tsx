/**
 * 옮기는 시험으로 만든 카드 — **코멘트는 반드시, 정리(사용 중지)는 고른다**(2026-09-29).
 *
 * 두께 이관(`RelocateDialog`)과 시료 이동(`SampleMoveDialog`, VOC 59)이 같은 부품을 쓴다 — 카드를
 * 다루는 말 · 판정이 두 창에서 갈리면 같은 카드가 창마다 다르게 보인다.
 */

import type { RelocatePlan } from '@/modules/materials/api'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'

const STATUS_LABEL: Record<string, string> = {
  published: '확정',
  draft: '초안',
  deprecated: '사용 중지',
}

export type CardAction = 'note' | 'deprecate'

export function RelocateCards({
  cards,
  actions,
  onAction,
  comment,
  onComment,
  commentId,
  placeholder,
}: {
  cards: RelocatePlan['cards']
  actions: Record<string, CardAction>
  onAction: (cardId: string, action: CardAction) => void
  comment: string
  onComment: (text: string) => void
  commentId: string
  placeholder: string
}) {
  if (cards.length === 0) return null
  return (
    <div className="space-y-2">
      <p className="font-medium">이 시험으로 만든 카드 {cards.length}장</p>
      <p className="text-muted-foreground text-xs">
        옮기는 것은 막지 않습니다. 카드마다 <b>코멘트가 붙고</b>, 필요하면 정리(사용
        중지)합니다 — 정리한 카드는 나중에 초안으로 되살릴 수 있습니다.
      </p>
      {cards.map((card) => {
        const action = actions[card.id] ?? 'note'
        return (
          <div
            key={card.id}
            className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
          >
            <span className="min-w-0 flex-1">
              <span className="font-medium">{card.label}</span>{' '}
              <Badge variant={card.status === 'published' ? 'default' : 'outline'}>
                {STATUS_LABEL[card.status] ?? card.status}
              </Badge>
              <span className="text-muted-foreground ml-1 text-xs">
                근거 시험 {card.test_runs}건이 옮겨집니다
              </span>
            </span>
            <div
              role="radiogroup"
              aria-label={`${card.label} 처리`}
              className="flex gap-1"
            >
              <Button
                type="button"
                size="sm"
                variant={action === 'note' ? 'secondary' : 'ghost'}
                role="radio"
                aria-checked={action === 'note'}
                onClick={() => onAction(card.id, 'note')}
              >
                코멘트만
              </Button>
              <Button
                type="button"
                size="sm"
                variant={action === 'deprecate' ? 'secondary' : 'ghost'}
                role="radio"
                aria-checked={action === 'deprecate'}
                disabled={!card.can_deprecate}
                title={card.reason ?? '카드를 사용 중지하고 코멘트도 남깁니다'}
                onClick={() =>
                  onAction(card.id, 'deprecate')
                }
              >
                정리(사용 중지)
              </Button>
            </div>
            {!card.can_deprecate && card.reason && (
              <p className="text-muted-foreground w-full text-xs">{card.reason}</p>
            )}
          </div>
        )
      })}
      <div className="space-y-1">
        <Label htmlFor={commentId} className="text-xs">
          카드에 남길 말(선택)
        </Label>
        <Textarea
          id={commentId}
          rows={2}
          value={comment}
          onChange={(event) => onComment(event.target.value)}
          placeholder={placeholder}
        />
      </div>
    </div>
  )
}
