/**
 * 받는 부서 추천 — **항목을 할 보유 장비가 있는 부서**(TestScope, 2026-10-23).
 *
 * 항목(시험 종류 · 무엇을 재는지)이 바뀌면 잠깐 기다렸다 서버에 묻는다 — 서버가 그 글자를 TestScope 의
 * 시험 항목 · 물성으로 풀어 장비를 찾고, 부서를 이름으로 MatNexus 부서에 잇는다. 이어진 부서는 누르면
 * 「받는 부서」 가 그것으로 바뀐다. **고르는 것은 사람이다** — 추천은 장비가 있다는 사실만 말한다.
 *
 * 연결이 없거나 못 닿으면 한 줄만 말하고 물러난다. 의뢰를 쓰는 데 TestScope 가 필요하지는 않다.
 */

import { useEffect, useMemo, useState } from 'react'

import { commissionsApi } from '@/modules/commissions/api'
import type { LabSuggestionItem, LabSuggestions as Answer } from '@/modules/commissions/api'
import type { ItemDraft } from '@/modules/commissions/ItemsEditor'

/** 묻기 전에 기다리는 시간 — 물성 이름을 치는 동안 매 글자마다 묻지 않게. */
const WAIT_MS = 500

export function LabSuggestions({
  items,
  selected,
  onPick,
}: {
  items: ItemDraft[]
  selected: string
  onPick: (slug: string) => void
}) {
  const asked = useMemo<LabSuggestionItem[]>(
    () =>
      items.map((one) => ({
        test_type_key: one.test_type_key || null,
        property_hint: one.test_type_key ? null : one.property_hint.trim() || null,
      })),
    [items]
  )
  const key = JSON.stringify(asked)
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    const wanted = JSON.parse(key) as LabSuggestionItem[]
    if (!wanted.some((one) => one.test_type_key || one.property_hint)) return
    let alive = true
    const timer = setTimeout(() => {
      commissionsApi
        .labSuggestions(wanted)
        .then((got) => alive && setAnswer(got))
        .catch(() => alive && setAnswer(null))
    }, WAIT_MS)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [key])

  if (!answer) return null
  if (answer.state !== 'ok') {
    return <p className="text-muted-foreground text-xs">{answer.message}</p>
  }
  const number = (index: number) => `${'①②③④⑤⑥⑦⑧⑨⑩'[index] ?? index + 1}`
  const labs = answer.labs ?? []
  const unresolved = answer.unresolved ?? []

  return (
    <div aria-label="받는 부서 추천" className="space-y-1.5 text-sm">
      <p className="text-muted-foreground text-xs">
        장비가 있는 부서(TestScope) — {answer.message}
      </p>
      {labs.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {labs.map((lab) => {
            const names = lab.equipment.map((one) => one.name)
            const label = `${lab.workspace_name} · 항목 ${lab.items.map(number).join('')} · 장비 ${lab.equipment.length}대`
            return (
              <li key={lab.workspace_name}>
                {lab.workspace_slug ? (
                  <button
                    type="button"
                    onClick={() => onPick(lab.workspace_slug ?? '')}
                    aria-pressed={selected === lab.workspace_slug}
                    title={names.join(', ')}
                    className={`rounded-full border px-2 py-0.5 ${
                      selected === lab.workspace_slug ? 'border-primary bg-primary/10' : 'hover:bg-muted'
                    }`}
                  >
                    {label}
                  </button>
                ) : (
                  <span
                    className="text-muted-foreground rounded-full border border-dashed px-2 py-0.5"
                    title={`MatNexus 에 같은 이름의 부서가 없어 고를 수 없습니다 — ${names.join(', ')}`}
                  >
                    {label}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {unresolved.length > 0 && (
        <p className="text-muted-foreground text-xs">
          추천에서 빠진 항목:{' '}
          {unresolved
            .map(
              (one) =>
                `${number(one.item)} 「${one.text}」 ${one.reason}` +
                (one.candidates?.length ? `(${one.candidates.join(' · ')})` : '')
            )
            .join(', ')}
        </p>
      )}
    </div>
  )
}
