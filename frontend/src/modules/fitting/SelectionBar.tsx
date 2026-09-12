/**
 * 고른 카드로 할 일 — **띠 하나에 탭 둘.**
 *
 * 카드를 하나 체크하면 두 곳이 반응했다: 떠 있는 「담기」 패널(워크벤치 작업에 담기)과
 * 하단 띠(묶음 내보내기). 둘은 일부러 갈라 둔 것이었는데(ADR 0024) 한 번의 선택에
 * 응답하는 자리가 둘이라 「팝업이 두 개 뜬다」 로 읽혔다(2026-09-05).
 *
 * 그래서 카드 목록에서는 띠 하나만 뜨고, 그 안에서 탭으로 가른다. 담기가 기본 탭이다 —
 * 담기를 줄 안의 단추로 뒀을 때 「못 찾겠다」 가 두 번 나왔으므로, 열리자마자 보이게
 * 하고 색도 그 패널처럼 준다. 다른 화면(시험·재료 목록)은 내보내기 띠가 없으니 떠 있는
 * 패널이 그대로 담기를 맡는다.
 */

import { FileDown, Inbox, X } from 'lucide-react'
import { useState } from 'react'

import { BundleBar } from '@/modules/fitting/BundleBar'
import type { ExportFormat } from '@/modules/fitting/api'
import { BasketForm } from '@/shared/components/AddToBasket'
import { Button } from '@/shared/components/ui/button'

type Tab = 'basket' | 'export'

export function SelectionBar({
  ids,
  labels,
  formats,
  onClear,
  onError,
}: {
  ids: string[]
  labels: string[]
  formats: ExportFormat[]
  onClear: () => void
  onError: (error: Error) => void
}) {
  const [tab, setTab] = useState<Tab>('basket')

  // **고른 게 없으면 안 뜬다.** 늘 떠 있으면 목록 아래가 항상 가려진다.
  if (ids.length === 0) return null

  return (
    <div
      className="bg-background sticky bottom-0 z-10 mt-3 rounded-md border border-sky-300 shadow-lg dark:border-sky-500/40"
      aria-label="고른 카드"
    >
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <span className="text-sm font-medium">{ids.length}장 골랐습니다</span>
        <div role="tablist" aria-label="고른 카드로 할 일" className="flex gap-1">
          <TabButton active={tab === 'basket'} onClick={() => setTab('basket')}>
            <Inbox className="size-3.5" />
            워크벤치 작업에 추가
          </TabButton>
          <TabButton active={tab === 'export'} onClick={() => setTab('export')}>
            <FileDown className="size-3.5" />
            묶음 내보내기
          </TabButton>
        </div>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onClear}>
          <X className="size-3.5" />
          고른 것 초기화
        </Button>
      </div>

      <div className="p-3">
        {tab === 'basket' ? (
          <div className="max-w-md">
            <BasketForm kind="card" ids={ids} labels={labels} onError={onError} />
          </div>
        ) : (
          <BundleBar ids={ids} formats={formats} onError={onError} embedded />
        )}
      </div>
    </div>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={`flex items-center gap-1 rounded-md border px-2 py-1 text-xs ${
        active ? 'border-sky-600 bg-sky-600 text-white' : 'hover:bg-muted'
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
