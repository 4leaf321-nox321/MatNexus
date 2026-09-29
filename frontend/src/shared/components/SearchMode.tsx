/**
 * 찾는 방식 단추와 「왜 걸렸나」 배지 — 전체 검색과 재료·시험 목록이 함께 쓴다(2026-09-29).
 *
 * 방식과 이유의 **말**은 `shared/searchModes` 에 있다. 여기는 그리기만 한다.
 */

import { MATCH_LABELS, SEARCH_MODES } from '@/shared/searchModes'
import type { SearchMode } from '@/shared/searchModes'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'

export function SearchModeToggle({
  mode,
  onChange,
  showHint = false,
}: {
  mode: SearchMode
  onChange: (next: SearchMode) => void
  /** 고른 방식의 설명을 옆에 적는다. 자리가 좁은 목록에서는 끄고 `title` 로만 준다. */
  showHint?: boolean
}) {
  const active = SEARCH_MODES.find((one) => one.key === mode) ?? SEARCH_MODES[1]
  return (
    <div className="flex items-center gap-2">
      <div role="group" aria-label="찾는 방식" className="flex gap-1">
        {SEARCH_MODES.map((one) => (
          <Button
            key={one.key}
            type="button"
            size="sm"
            variant={one.key === mode ? 'default' : 'outline'}
            aria-pressed={one.key === mode}
            title={one.hint}
            onClick={() => onChange(one.key)}
          >
            {one.label}
          </Button>
        ))}
      </div>
      {showHint && <span className="text-muted-foreground text-xs">{active.hint}</span>}
    </div>
  )
}

/**
 * 목록 한 줄이 **왜 걸렸나** — 「비슷」 으로 찾았을 때만 서버가 준다.
 *
 * 「포함」 은 안 적는다 — 목록 대부분이 그 이유라 줄마다 붙이면 배지가 표를 덮는다. 글자가
 * 비슷해서, 또는 뜻으로만 걸린 줄에만 선다.
 */
export function MatchBadge({
  matched,
  meaning = MATCH_LABELS.meaning,
}: {
  matched: string | null | undefined
  /** 뜻으로 걸렸을 때의 말. 시험은 「재료의 뜻이 가까움」 이다 — 뜻을 재는 것이 재료라서. */
  meaning?: string
}) {
  if (matched !== 'similar' && matched !== 'meaning') return null
  return (
    <Badge variant="outline" className="ml-1.5 align-middle font-sans font-normal">
      {matched === 'meaning' ? meaning : MATCH_LABELS.similar}
    </Badge>
  )
}
