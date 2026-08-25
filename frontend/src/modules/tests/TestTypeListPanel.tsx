/**
 * 시험 종류 목록 옆패널 — **한 번에 하나만 본다.**
 *
 * 전에는 종류마다 카드 하나를 세로로 쌓았다. 카드 하나가 채널 표 + 조건 표 +
 * 확장자 + 소유 표시라 백 줄이 넘는데, 개발 DB 만 해도 종류 넷에 **채널이
 * 스물셋**이다 — 한 화면에 다 쌓으니 무엇을 보고 있었는지 잃는다.
 *
 * 세로 목록으로 고르고 본문은 고른 하나만 그린다. 기준정보 축 패널과 같은
 * 모양이다(`VocabularyAxisPanel`).
 *
 * ## 거르는 것과 고르는 것은 다르다
 *
 * `TestTypeFilterPanel` 은 **목록을 좁힌다**(레시피·파일 형식). 「전체」가 있고
 * 안 고르면 다 보인다. 여기는 **하나를 고른다** — 전체를 볼 이유가 없고, 안
 * 고른 상태도 없다(첫 것을 연다). 그래서 합치지 않았다.
 */

import { Globe2 } from 'lucide-react'

import type { TestType } from '@/modules/tests/api'
import { Badge } from '@/shared/components/ui/badge'
import { LeftPanel } from '@/shared/layout/SidePanel'

export function TestTypeListPanel({
  types,
  current,
  onPick,
}: {
  types: TestType[]
  current: string | null
  onPick: (key: string) => void
}) {
  return (
    <LeftPanel label="시험 종류">
      <aside className="bg-background flex h-full w-60 flex-col border-r">
        <div className="min-h-0 flex-1 overflow-auto py-1">
          {types.map((type) => {
            const here = type.key === current
            return (
              <button
                key={type.key}
                type="button"
                aria-current={here ? 'true' : undefined}
                onClick={() => onPick(type.key)}
                className={`block w-full px-3 py-2 text-left text-sm ${
                  here ? 'bg-muted font-medium' : 'hover:bg-muted/50'
                }`}
              >
                <div className="flex items-center gap-1">
                  <span className="truncate">{type.label}</span>
                  {/* **누구 것인지 안 보이면 왜 못 고치는지 알 수 없다.**
                      전역은 시스템 관리자만 손댄다 — 목록에서부터 보여야
                      편집을 눌러 보고 403 을 받는 일이 없다. */}
                  {type.is_global && (
                    <Globe2
                      className="text-muted-foreground size-3 shrink-0"
                      aria-label="전역"
                    />
                  )}
                  {!type.is_active && (
                    <Badge variant="outline" className="ml-auto shrink-0 text-[11px]">
                      중단
                    </Badge>
                  )}
                </div>
                <div className="text-muted-foreground mt-0.5 truncate font-mono text-xs">
                  {type.key}
                </div>
                {/* 채널·조건 수. **고르기 전에 규모를 안다.** */}
                <div className="text-muted-foreground mt-0.5 text-xs">
                  채널 {type.channels.length} · 조건 {type.conditions.length}
                  {type.run_count > 0 && ` · 시험 ${type.run_count}`}
                </div>
              </button>
            )
          })}

          {types.length === 0 && (
            <p className="text-muted-foreground p-3 text-sm">정의된 종류가 없습니다.</p>
          )}
        </div>
      </aside>
    </LeftPanel>
  )
}
