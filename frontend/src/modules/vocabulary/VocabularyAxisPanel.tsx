/**
 * 기준정보 축 목록 — **왼쪽 사이드바 옆 세로 목록.**
 *
 * 전에는 본문 위에 가로 버튼 줄이었다. 축이 11개(Family·Category·Grade·제조사·
 * 거래처·판매 유형·시편 분류·시편 규격·장비·적용 제품·적용 부위)라 줄이 넘치고,
 * **부모-자식 관계가 안 보였다** — `Grade` 가 `Category` 아래 있고 `Category` 는
 * `Family` 아래인데, 나란히 놓으면 그냥 열한 개다.
 *
 * 세로로 세우면 들여쓰기로 그 계층을 그릴 수 있다.
 *
 * 자리는 재료 목록과 같다(`SidePanel`). 본문 안에 두면 `max-w-[1600px]` 을 따라
 * 가운데로 딸려 들어가고, 화면 왼쪽 끝에는 여백만 남는다.
 */

import type { Vocabulary } from '@/modules/vocabulary/api'
import { LeftPanel } from '@/shared/layout/SidePanel'

/** 부모를 따라 몇 단인지. `Grade` 는 `Category` 아래, 그건 `Family` 아래라 2단. */
function depthOf(axis: Vocabulary, all: Vocabulary[]): number {
  let depth = 0
  let parent = axis.parent_slug
  // 축이 열한 개라 순환은 없지만, 데이터가 꼬였을 때 멈추지 않으면 화면이 죽는다.
  while (parent && depth < 5) {
    depth += 1
    parent = all.find((item) => item.slug === parent)?.parent_slug ?? null
  }
  return depth
}

export function VocabularyAxisPanel({
  axes,
  current,
  onPick,
}: {
  axes: Vocabulary[]
  current: string | null
  onPick: (slug: string) => void
}) {
  return (
    <LeftPanel label="기준정보 축">
      <aside className="bg-background flex h-full w-60 flex-col border-r">
        <div className="min-h-0 flex-1 overflow-auto py-1">
          {axes.map((axis) => {
            const here = axis.slug === current
            const depth = depthOf(axis, axes)
            return (
              <button
                key={axis.slug}
                type="button"
                aria-current={here ? 'true' : undefined}
                onClick={() => onPick(axis.slug)}
                className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-sm ${
                  here ? 'bg-muted font-medium' : 'hover:bg-muted/50'
                }`}
                // 들여쓰기로 부모-자식을 그린다. 유틸리티 클래스로는 단계를
                // 못 만들어서(pl-3·pl-6·pl-9 를 조건으로 고르면 그 자체가 표다)
                // 여기만 계산한다.
                style={{ paddingLeft: `${0.75 + depth * 0.75}rem` }}
              >
                <span className="truncate">{axis.label}</span>
                <span className="text-muted-foreground ml-2 shrink-0 tabular-nums">
                  {axis.term_count}
                </span>
              </button>
            )
          })}
        </div>
      </aside>
    </LeftPanel>
  )
}
