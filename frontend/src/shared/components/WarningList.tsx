/**
 * **사람이 확인할 것** 목록(2026-11-14, VOC 53~58) — 노트(무엇을 했나)와 다르다.
 *
 * 처리 결과 · 채택 확인 · 카드 근거가 같은 모양으로 보인다. 노트에 섞여 있던 때는 화면에서만
 * 보이고 채택 · 카드로 넘어가면 사라졌다. 어디서 나온 것인지(시험 점검 · 단계 · 시험 이름)를
 * 앞에 적는다 — 「무엇을 고쳐야 하나」 가 거기서 갈린다.
 */

import { TriangleAlert } from 'lucide-react'

export type WarningItem = {
  label?: string | null
  message: string
  record_name?: string | null
}

export function WarningList({
  items,
  title = '확인할 경고',
  className = '',
}: {
  items: readonly WarningItem[]
  title?: string
  className?: string
}) {
  if (items.length === 0) return null
  return (
    <div
      className={`rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm ${className}`}
      role="note"
    >
      <p className="flex items-center gap-1.5 font-medium text-amber-800 dark:text-amber-300">
        <TriangleAlert className="size-4" />
        {title} {items.length}건
      </p>
      <ul className="mt-1.5 space-y-1">
        {items.map((one, index) => (
          <li key={`${index}-${one.message}`}>
            {(one.record_name || one.label) && (
              <span className="font-medium">
                {[one.record_name, one.label].filter(Boolean).join(' · ')}:{' '}
              </span>
            )}
            {one.message}
          </li>
        ))}
      </ul>
    </div>
  )
}
