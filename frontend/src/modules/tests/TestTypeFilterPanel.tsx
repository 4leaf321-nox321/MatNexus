/**
 * 시험 종류로 거르는 옆패널 — **파일 형식과 레시피가 같은 것을 쓴다.**
 *
 * 둘 다 시험 종류에 매달린 목록이다. 인장 레시피를 손보는 사람에게 DMA 레시피는
 * 소음이고, DMA 프로파일을 찾는 사람에게 인장 프로파일이 그렇다. 그런데 두
 * 화면 다 `test_type_label` 을 **표에 보여만 주고 거르지는 못했다** — 눈으로
 * 훑어야 했다.
 *
 * 자리는 재료 목록·기준정보 축과 같다(`SidePanel`). 본문 안에 두면
 * `max-w-[1600px]` 을 따라 가운데로 딸려 들어간다.
 *
 * ## 개수는 목록이 정한다
 *
 * 시험 종류 전체를 뿌리지 않고 **지금 목록에 실제로 있는 것**만 준다. 등록된
 * 종류는 스무 개인데 레시피가 인장에만 있으면, 나머지 열아홉은 눌러 봐야 0건인
 * 칸이다 — 재료 분류가 같은 이유로 `classifications` 를 쓴다(고정 목록을 박지
 * 않는다).
 */

import type { ReactNode } from 'react'

import { LeftPanel } from '@/shared/layout/SidePanel'

/** 거를 수 있는 최소한. 프로파일이든 레시피든 이 둘만 있으면 된다. */
export interface HasTestType {
  test_type_key: string
  test_type_label: string
}

/** 목록에 실제로 있는 종류와 그 개수. 없는 종류는 애초에 안 보인다. */
export function testTypesIn(rows: HasTestType[]): { key: string; label: string; count: number }[] {
  const seen = new Map<string, { key: string; label: string; count: number }>()
  for (const row of rows) {
    const found = seen.get(row.test_type_key)
    if (found) found.count += 1
    else seen.set(row.test_type_key, { key: row.test_type_key, label: row.test_type_label, count: 1 })
  }
  return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label, 'ko'))
}

export function TestTypeFilterPanel({
  label,
  rows,
  current,
  onPick,
  footer,
}: {
  /** 상단 바 단추에 뜨는 이름. 「레시피 종류」처럼 무엇의 목록인지 적는다. */
  label: string
  rows: HasTestType[]
  /** `null` 이면 전체. */
  current: string | null
  onPick: (key: string | null) => void
  footer?: ReactNode
}) {
  const kinds = testTypesIn(rows)

  return (
    <LeftPanel label={label}>
      <aside className="bg-background flex h-full w-56 flex-col border-r">
        <div className="min-h-0 flex-1 overflow-auto py-1">
          <Row
            label="전체"
            count={rows.length}
            here={current === null}
            onClick={() => onPick(null)}
          />
          {kinds.map((kind) => (
            <Row
              key={kind.key}
              label={kind.label}
              count={kind.count}
              here={current === kind.key}
              onClick={() => onPick(kind.key)}
            />
          ))}

          {/* **비어 있으면 왜 비었는지 말한다.** 빈 옆패널은 고장으로 보인다. */}
          {rows.length === 0 && (
            <p className="text-muted-foreground p-3 text-xs">아직 등록된 것이 없습니다.</p>
          )}
        </div>
        {footer}
      </aside>
    </LeftPanel>
  )
}

function Row({
  label,
  count,
  here,
  onClick,
}: {
  label: string
  count: number
  here: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-current={here ? 'true' : undefined}
      onClick={onClick}
      className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs ${
        here ? 'bg-muted font-medium' : 'hover:bg-muted/50'
      }`}
    >
      <span className="truncate">{label}</span>
      <span className="text-muted-foreground ml-2 shrink-0 tabular-nums">{count}</span>
    </button>
  )
}
