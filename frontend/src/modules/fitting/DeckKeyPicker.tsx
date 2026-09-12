/**
 * 덱 정의의 값 자리를 **골라 채운다** — `elastic.youngs_modulus` 를 손으로 적지 않는다.
 *
 * 목록은 블록 선언(`fittingApi.blocks`)에서 온다. 화면이 블록 이름을 하나도 모른다 —
 * 새 물성을 확장으로 붙여도 여기 자동으로 선다. 미리보기 카드가 고른 채면 그 카드에
 * **실제로 있는지**도 함께 적는다: 없는 값을 꽂은 정의는 덱이 안 나온다(2026-09-05).
 *
 * 손으로 적는 길은 남긴다. 고르기는 틀릴 자리를 줄이는 것이지 막는 것이 아니다.
 */

import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import type { BlockSpec, DeckKeys } from '@/modules/fitting/api'
import { Button } from '@/shared/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/components/ui/popover'

export type PickTarget = 'value' | 'column'

export function DeckKeyPicker({
  specs,
  cardKeys,
  target,
  table,
  label,
  onPick,
}: {
  specs: BlockSpec[]
  /** 고른 카드에 든 것. 없으면(카드를 안 골랐으면) 있고 없음을 안 적는다. */
  cardKeys: DeckKeys | null
  /** 값 자리(`블록.값`)인가, 표의 열(`열 이름`)인가. */
  target: PickTarget
  /** 열을 고를 때 어느 표의 열인가. */
  table?: string
  label: string
  onPick: (path: string) => void
}) {
  const [open, setOpen] = useState(false)
  const inCard = cardKeys ? new Set(cardKeys.values.map((one) => one.path)) : null
  const tableColumns = cardKeys
    ? new Set(
        cardKeys.tables.find((one) => one.block === table)?.columns.map((one) => one.key) ?? []
      )
    : null

  const groups =
    target === 'value'
      ? specs
          .filter((spec) => spec.produces.length > 0)
          .map((spec) => ({
            key: spec.key,
            label: spec.label,
            items: spec.produces.map((one) => ({
              path: `${spec.key}.${one.key}`,
              label: one.label,
              unit: one.si_unit,
              present: inCard ? inCard.has(`${spec.key}.${one.key}`) : null,
            })),
          }))
      : specs
          .filter((spec) => spec.rows.length > 0 && (!table || spec.key === table))
          .map((spec) => ({
            key: spec.key,
            label: spec.label,
            items: spec.rows.map((one) => ({
              path: one.key,
              label: one.label,
              unit: one.si_unit,
              present: tableColumns ? tableColumns.has(one.key) : null,
            })),
          }))

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8" aria-label={label} title={label}>
          선택
          <ChevronDown className="size-3" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="max-h-80 w-96 overflow-y-auto p-2">
        {groups.length === 0 && (
          <p className="text-muted-foreground p-2 text-xs">고를 것이 없습니다.</p>
        )}
        {groups.map((group) => (
          <div key={group.key} className="mb-2">
            <p className="text-muted-foreground px-1 text-xs font-medium">{group.label}</p>
            <ul>
              {group.items.map((one) => (
                <li key={one.path}>
                  <button
                    type="button"
                    // 이름(라벨 + 키)을 붙인다 — 칸이 나뉘어 있어 화면 낭독기와 시험이 한 이름으로 못 읽는다.
                    aria-label={`${one.label} ${one.path}`}
                    className="hover:bg-muted flex w-full items-center gap-2 rounded px-1 py-1 text-left text-xs"
                    onClick={() => {
                      onPick(one.path)
                      setOpen(false)
                    }}
                  >
                    <span className={one.present === false ? 'text-muted-foreground' : ''}>
                      {one.label}
                    </span>
                    <span className="text-muted-foreground font-mono">{one.path}</span>
                    {one.unit && one.unit !== '1' && (
                      <span className="text-muted-foreground">{one.unit}</span>
                    )}
                    {one.present === false && (
                      <span className="ml-auto text-amber-700 dark:text-amber-500">
                        이 카드엔 없음
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </PopoverContent>
    </Popover>
  )
}
