/**
 * 카드 목록 옆패널 — **좁히는 축 셋.**
 *
 * 상태(초안·확정·내려짐) · 시험 종류 · 부서. 앞의 둘은 늘 보이고, 부서는
 * 켜고 끈다(`TestTypeFilterPanel` 의 「부서로 나누기」와 같은 판단) — 부서가
 * 하나인 곳에서는 그 줄이 자리만 차지한다.
 *
 * ## 개수를 화면에서 세지 않는다
 *
 * 레시피 필터는 목록을 통째로 받으므로 화면에서 셌다(`testTypesIn(rows)`).
 * 카드는 **쪽으로 온다** — 50장만 받아 세면 「인장시험 12」라고 적히는데 실제로는
 * 40장일 수 있고, 그러면 **필터 옆의 숫자가 거짓말을 한다.** 서버가 세어 준다
 * (`GET /fitting/cards/facets`).
 *
 * ## 셈은 필터를 따라가지 않는다
 *
 * 「무엇이 있나」를 답하는 자리다. 필터를 걸 때마다 다른 축의 숫자가 같이 줄면
 * **필터를 풀기 전에는 그 축에 무엇이 있는지 알 수 없다.**
 */

import { useEffect, useState } from 'react'

import type { CardFacets } from '@/modules/fitting/api'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { LeftPanel } from '@/shared/layout/SidePanel'

/** 「부서로 나누기」를 기억한다. 켜고 끄는 것은 취향이라 새로고침마다 묻지 않는다. */
const SPLIT_KEY = 'matnexus.cards.split-by-owner'

function useSticky(key: string, fallback: boolean): [boolean, (next: boolean) => void] {
  const [value, setValue] = useState(() => {
    // **읽기가 던져도 화면은 떠야 한다** — 사생활 보호 창이나 저장 차단이면
    // 접근 자체가 예외를 낸다.
    try {
      const saved = localStorage.getItem(key)
      return saved === null ? fallback : saved === '1'
    } catch {
      return fallback
    }
  })
  return [
    value,
    (next: boolean) => {
      setValue(next)
      try {
        localStorage.setItem(key, next ? '1' : '0')
      } catch {
        // 못 적어도 이번 세션에는 켜져 있다.
      }
    },
  ]
}

function Section({
  title,
  rows,
  current,
  onPick,
}: {
  title: string
  rows: { key: string; label: string; count: number }[]
  current: string | null
  onPick: (key: string | null) => void
}) {
  if (rows.length === 0) return null
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  return (
    <div className="border-b py-1">
      <p className="text-muted-foreground px-3 pt-1 pb-0.5 text-[11px] font-medium">{title}</p>
      {/* **「전체」가 첫 줄이다.** 고른 것을 푸는 길이 없으면 새로고침으로
          푸는 사람이 생긴다. */}
      <button
        type="button"
        aria-current={current === null ? 'true' : undefined}
        onClick={() => onPick(null)}
        className={`flex w-full items-center gap-1 px-3 py-1 text-left text-xs ${
          current === null ? 'bg-muted font-medium' : 'hover:bg-muted/50'
        }`}
      >
        <span className="truncate">전체</span>
        <span className="text-muted-foreground ml-auto tabular-nums">{total}</span>
      </button>
      {rows.map((row) => {
        const here = row.key === current
        return (
          <button
            key={row.key}
            type="button"
            aria-current={here ? 'true' : undefined}
            onClick={() => onPick(row.key)}
            className={`flex w-full items-center gap-1 px-3 py-1 text-left text-xs ${
              here ? 'bg-muted font-medium' : 'hover:bg-muted/50'
            }`}
          >
            <span className="truncate">{row.label}</span>
            <span className="text-muted-foreground ml-auto tabular-nums">{row.count}</span>
          </button>
        )
      })}
    </div>
  )
}

export function CardFilterPanel({
  facets,
  status,
  testType,
  owner,
  onPickStatus,
  onPickTestType,
  onPickOwner,
}: {
  facets: CardFacets | null
  status: string | null
  testType: string | null
  owner: string | null
  onPickStatus: (key: string | null) => void
  onPickTestType: (key: string | null) => void
  onPickOwner: (key: string | null) => void
}) {
  const [split, setSplit] = useSticky(SPLIT_KEY, false)

  // 축을 끄면 걸어 둔 필터도 푼다. **안 풀면 안 보이는 필터가 걸린 채로 남고**,
  // 목록이 왜 짧은지 알 방법이 없다.
  useEffect(() => {
    if (!split && owner) onPickOwner(null)
  }, [split, owner, onPickOwner])

  return (
    <LeftPanel label="카드 거르기">
      <aside className="bg-background flex h-full w-56 flex-col border-r">
        {/* **맨 위다.** 목록을 가르는 스위치라 목록 사이에 두면 못 찾는다. */}
        <div className="flex items-center justify-between gap-1 border-b px-3 py-2">
          <span className="text-muted-foreground text-[11px]">부서로 나누기</span>
          <Button
            size="sm"
            variant={split ? 'default' : 'outline'}
            className="h-6 px-2 text-[11px]"
            aria-pressed={split}
            onClick={() => setSplit(!split)}
          >
            {split ? '켜짐' : '꺼짐'}
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          <Section
            title="상태"
            rows={facets?.statuses ?? []}
            current={status}
            onPick={onPickStatus}
          />
          <Section
            title="시험 종류"
            rows={facets?.test_types ?? []}
            current={testType}
            onPick={onPickTestType}
          />
          {split && (
            <Section
              title="부서"
              rows={facets?.owners ?? []}
              current={owner}
              onPick={onPickOwner}
            />
          )}
        </div>

        {facets && facets.statuses.length === 0 && (
          <p className="text-muted-foreground p-3 text-xs">아직 만든 카드가 없습니다.</p>
        )}

        {/* 걸린 것을 한눈에. **어디에 걸었는지 모르면 목록이 왜 짧은지 모른다.** */}
        {(status || testType || owner) && (
          <div className="flex items-center gap-1 border-t px-3 py-2">
            <Badge variant="secondary" className="text-[10px]">
              필터 {[status, testType, owner].filter(Boolean).length}
            </Badge>
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto h-6 px-2 text-[11px]"
              onClick={() => {
                onPickStatus(null)
                onPickTestType(null)
                onPickOwner(null)
              }}
            >
              모두 풀기
            </Button>
          </div>
        )}
      </aside>
    </LeftPanel>
  )
}
