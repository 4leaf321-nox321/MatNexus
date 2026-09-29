/**
 * 시험 목록의 **상세 조건** 칸 — 시험일 · 장비 · 시험 조건 범위(2026-09-29).
 *
 * 칸은 **찾기를 누를 때** 걸린다 — 찾기 상자와 같은 규칙이다. 무엇을 서버에 싣는지는
 * `runSearch.runDetailQuery` 가 정한다. 여기는 칸만 그린다.
 */

import type { StandardCondition } from '@/modules/tests/api'
import { conditionUnit } from '@/modules/tests/runSearch'
import type { RunDetail } from '@/modules/tests/runSearch'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const SELECT = 'border-input bg-background h-8 w-full rounded-md border px-2 text-sm'

export function RunSearchFields({
  value,
  onChange,
  standards,
  instruments,
  dirty,
  onReset,
}: {
  value: RunDetail
  onChange: (next: RunDetail) => void
  /** 표준 시험 조건 — 부서마다 다른 칸 이름이 이 키로 모인다. */
  standards: StandardCondition[]
  /** 장비별 건수. **서버가 센 것**이다 — 한 쪽만 받아 세면 숫자가 거짓말을 한다. */
  instruments: { key: string; label: string; count: number }[]
  dirty: boolean
  onReset: () => void
}) {
  function set(key: keyof RunDetail, next: string) {
    onChange({ ...value, [key]: next })
  }
  const standard = standards.find((one) => one.key === value.condition)
  const unit = standard ? conditionUnit(standard) : ''

  return (
    <div className="bg-muted/30 grid gap-3 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="space-y-1 sm:col-span-2">
        <Label htmlFor="find-tested-from" className="text-muted-foreground text-xs">
          시험일
        </Label>
        <div className="flex items-center gap-1.5">
          <Input
            id="find-tested-from"
            aria-label="시험일 시작"
            className="h-8"
            type="date"
            value={value.testedFrom}
            onChange={(event) => set('testedFrom', event.target.value)}
          />
          <span className="text-muted-foreground">~</span>
          <Input
            aria-label="시험일 끝"
            className="h-8"
            type="date"
            value={value.testedTo}
            onChange={(event) => set('testedTo', event.target.value)}
          />
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="find-instrument" className="text-muted-foreground text-xs">
          장비
        </Label>
        <select
          id="find-instrument"
          className={SELECT}
          value={value.instrument}
          onChange={(event) => set('instrument', event.target.value)}
        >
          <option value="">전체</option>
          {instruments.map((one) => (
            <option key={one.key} value={one.key}>
              {one.label} ({one.count})
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="find-condition" className="text-muted-foreground text-xs">
          시험 조건
        </Label>
        <select
          id="find-condition"
          className={SELECT}
          value={value.condition}
          onChange={(event) => set('condition', event.target.value)}
        >
          <option value="">고르지 않음</option>
          {standards.map((one) => (
            <option key={one.key} value={one.key}>
              {one.label}
            </option>
          ))}
        </select>
      </div>
      {standard && (
        <div className="space-y-1 sm:col-span-2">
          {/* 단위는 **표에서 읽는다**(`shared/units`) — 보내는 단위와 라벨이 한 곳에서 온다. */}
          <Label htmlFor="find-condition-min" className="text-muted-foreground text-xs">
            {standard.label} 범위{unit && ` (${unit})`}
          </Label>
          <div className="flex items-center gap-1.5">
            <Input
              id="find-condition-min"
              aria-label="조건 하한"
              className="h-8"
              type="number"
              step="any"
              value={value.conditionMin}
              onChange={(event) => set('conditionMin', event.target.value)}
              placeholder="부터"
            />
            <span className="text-muted-foreground">~</span>
            <Input
              aria-label="조건 상한"
              className="h-8"
              type="number"
              step="any"
              value={value.conditionMax}
              onChange={(event) => set('conditionMax', event.target.value)}
              placeholder="까지"
            />
          </div>
          <p className="text-muted-foreground text-xs">
            조건 칸을 이 표준 조건에 이은 시험 종류만 걸립니다.
          </p>
        </div>
      )}
      <div className="flex items-end justify-end gap-2 sm:col-span-2 lg:col-span-4">
        <Button type="button" variant="ghost" size="sm" onClick={onReset}>
          초기화
        </Button>
        <Button type="submit" size="sm" disabled={!dirty}>
          이 조건으로 찾기
        </Button>
      </div>
    </div>
  )
}
