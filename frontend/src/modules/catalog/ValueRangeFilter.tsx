/**
 * 값 범위로 거르기 — **「항복강도 200~300 MPa 인 재료」** (2026-10-03).
 *
 * ## 단위는 화면의 단위로 받고, SI 로 보낸다
 *
 * 값은 SI 로 저장돼 있어 200 MPa 는 `200,000,000` 이다. 사람은 「200」 이라고 친다. 칸 옆에
 * 화면의 단위(MPa)를 적고, 보낼 때 단위표(`shared/units`)로 SI 로 바꿔 **SI 단위와 함께**
 * 보낸다 — 서버는 단위 없는 범위를 거절한다(짐작하면 8 Pa 짜리가 걸린다).
 *
 * ## 거는 것은 「걸기」 를 누를 때
 *
 * 칠 때마다 걸면 「2」 · 「20」 · 「200」 이 차례로 서버에 가고 목록이 세 번 바뀐다.
 *
 * ## 두 목록이 쓴다 (2026-10-04)
 *
 * 문헌 카탈로그(`world="catalog"`)와 사내 재료 목록(`world="internal"`). 고를 수 있는 물성이
 * 다르다 — 문헌 값이 있는 물성과, 시험으로 재거나 선언 항목으로 이어진 물성. 값이 없는 물성을
 * 고르게 두면 늘 0건이다.
 */

import { useEffect, useState } from 'react'
import { X } from 'lucide-react'

import { catalogApi } from '@/modules/catalog/api'
import type { PropertyCandidate } from '@/modules/catalog/api'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { display, formatValue, fromDisplay, toDisplay } from '@/shared/units'

/** 걸린 범위. `min`·`max` 는 **SI** 다(`siUnit`). */
export interface ValueRange {
  key: string
  name: string
  siUnit: string
  min?: number
  max?: number
}

/** 범위의 끝 하나를 화면 단위의 글로 — 단위는 붙이지 않는다(옆에 따로 선다). */
export function shownNumber(value: number, siUnit: string): string {
  return formatValue(toDisplay(value, siUnit), null, null)
}

/** `200 ~ 300 MPa` · `≥ 200 MPa` — 걸린 범위를 한 줄로. */
export function describeRange(range: ValueRange): string {
  const unit = display(range.siUnit).unit
  const low = range.min !== undefined ? shownNumber(range.min, range.siUnit) : null
  const high = range.max !== undefined ? shownNumber(range.max, range.siUnit) : null
  const span = low && high ? `${low} ~ ${high}` : low ? `≥ ${low}` : `≤ ${high}`
  return `${range.name} ${span}${unit ? ` ${unit}` : ''}`
}

/** 이 목록에서 고를 수 있는 물성인가 — 값이 하나도 없을 물성은 후보에서 뺀다. */
function usable(one: PropertyCandidate, world: 'catalog' | 'internal'): boolean {
  if (one.deprecated) return false
  if (world === 'catalog') return one.value_count > 0
  // 식의 변수 묶음(Prony …)은 서버가 범위로 안 거른다 — 고르면 422 다.
  return !one.parameterized && ((one.measured_keys?.length ?? 0) > 0 || one.internal_items.length > 0)
}

/** 후보 줄 오른쪽 — 그 목록에서 무엇으로 걸리는지. */
function hint(one: PropertyCandidate, world: 'catalog' | 'internal'): string {
  const unit = display(one.si_unit || '1').unit
  const where =
    world === 'catalog'
      ? `값 ${one.value_count.toLocaleString('ko-KR')}건`
      : [
          (one.measured_keys?.length ?? 0) > 0 ? '시험 값' : '',
          one.internal_items.length > 0 ? `항목 ${one.internal_items.join(' · ')}` : '',
        ]
          .filter(Boolean)
          .join(' · ')
  return [unit, where].filter(Boolean).join(' · ')
}

export function ValueRangeFilter({
  applied,
  onApply,
  world = 'catalog',
}: {
  applied: ValueRange | null
  onApply: (next: ValueRange | null) => void
  world?: 'catalog' | 'internal'
}) {
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<PropertyCandidate[]>([])
  const [picked, setPicked] = useState<PropertyCandidate | null>(null)
  const [low, setLow] = useState('')
  const [high, setHigh] = useState('')
  const [problem, setProblem] = useState<string | null>(null)

  // 이름을 치면 서버가 푼다 — 값 넣기 창과 같은 길(`resolveProperty`).
  useEffect(() => {
    const needle = query.trim()
    if (picked || needle.length < 1) {
      setCandidates([])
      return
    }
    let alive = true
    const timer = setTimeout(() => {
      catalogApi
        .resolveProperty(needle)
        .then((got) => {
          // 값이 없는 물성으로는 아무것도 못 거른다 — 고르게 두면 늘 0건이다.
          if (alive) setCandidates(got.candidates.filter((one) => usable(one, world)))
        })
        .catch(() => {
          if (alive) setCandidates([])
        })
    }, 200)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [query, picked, world])

  const siUnit = picked ? picked.si_unit || '1' : ''
  const unit = picked ? display(siUnit).unit : ''

  function apply() {
    if (!picked) return
    const parse = (text: string) => (text.trim() === '' ? undefined : Number(text))
    const min = parse(low)
    const max = parse(high)
    if (min === undefined && max === undefined) {
      setProblem('최솟값이나 최댓값 중 하나는 적어 주세요.')
      return
    }
    if ((min !== undefined && Number.isNaN(min)) || (max !== undefined && Number.isNaN(max))) {
      setProblem('숫자로 적어 주세요.')
      return
    }
    if (min !== undefined && max !== undefined && min > max) {
      setProblem('최솟값이 최댓값보다 큽니다.')
      return
    }
    setProblem(null)
    onApply({
      key: picked.key,
      name: picked.name,
      siUnit,
      min: min === undefined ? undefined : fromDisplay(min, siUnit),
      max: max === undefined ? undefined : fromDisplay(max, siUnit),
    })
  }

  function clear() {
    setPicked(null)
    setQuery('')
    setLow('')
    setHigh('')
    setProblem(null)
    onApply(null)
  }

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">값 범위</span>
        {picked ? (
          <span className="flex items-center gap-1 rounded-md border px-2 py-1 text-sm">
            {picked.name}
            <span className="text-muted-foreground font-mono">{picked.key}</span>
            <button
              type="button"
              aria-label="물성 다시 고르기"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => setPicked(null)}
            >
              <X className="size-3.5" />
            </button>
          </span>
        ) : (
          <Input
            aria-label="값으로 거를 물성"
            placeholder="물성 이름 — 항복강도, 열전도율…"
            className="max-w-64"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        )}
        <Input
          aria-label="최솟값"
          inputMode="decimal"
          placeholder="최소"
          className="w-28"
          disabled={!picked}
          value={low}
          onChange={(event) => setLow(event.target.value)}
        />
        <span>~</span>
        <Input
          aria-label="최댓값"
          inputMode="decimal"
          placeholder="최대"
          className="w-28"
          disabled={!picked}
          value={high}
          onChange={(event) => setHigh(event.target.value)}
        />
        {unit && <span className="text-sm">{unit}</span>}
        {/* 폼 안에 놓일 수 있다(재료 목록의 상세 조건) — 누르면 그 폼을 내지 않게. */}
        <Button type="button" size="sm" disabled={!picked} onClick={apply}>
          걸기
        </Button>
        {applied && (
          <Button type="button" size="sm" variant="ghost" onClick={clear}>
            풀기
          </Button>
        )}
      </div>

      {!picked && candidates.length > 0 && (
        <ul className="max-h-48 max-w-xl overflow-y-auto rounded-md border">
          {candidates.map((one) => (
            <li key={one.key}>
              <button
                type="button"
                className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                onClick={() => {
                  setPicked(one)
                  setQuery('')
                }}
              >
                <span className="font-medium">{one.name}</span>
                <span className="text-muted-foreground font-mono">{one.key}</span>
                <span className="text-muted-foreground ml-auto">{hint(one, world)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {problem && (
        <p className="text-destructive text-sm" role="alert">
          {problem}
        </p>
      )}
      {applied && (
        <p className="text-sm" role="status">
          {world === 'catalog'
            ? `${describeRange(applied)} 인 값이 있는 재료만 보는 중입니다 — 식의 변수(Prony 의 E0 같은)는 그 물성의 값으로 치지 않습니다.`
            : `${describeRange(applied)} 인 값(채택된 시험 결과 · 선언 물성)이 있는 재료만 보는 중입니다.`}
        </p>
      )}
    </div>
  )
}
