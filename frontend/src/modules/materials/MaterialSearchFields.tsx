/**
 * 재료 목록의 **상세 조건** 칸 — 이름 말고 다른 것으로 찾는다(2026-09-29).
 *
 * 칸은 **찾기를 누를 때** 걸린다 — 찾기 상자와 같은 규칙이다. 한 글자마다 목록을 다시
 * 부르면 늦게 온 응답이 최신 결과를 덮는다.
 *
 * 무엇을 서버에 싣는지는 `materialSearch.detailQuery` 가 정한다. 여기는 칸만 그린다.
 */

import { LENGTH_UNIT } from '@/modules/materials/api'
import { CARD_CHOICES } from '@/modules/materials/materialSearch'
import type { MaterialDetail } from '@/modules/materials/materialSearch'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const SELECT = 'border-input bg-background h-8 w-full rounded-md border px-2 text-sm'

function Field({
  id,
  label,
  children,
  wide = false,
}: {
  id: string
  label: string
  children: React.ReactNode
  wide?: boolean
}) {
  return (
    <div className={`space-y-1 ${wide ? 'sm:col-span-2' : ''}`}>
      <Label htmlFor={id} className="text-muted-foreground text-xs">
        {label}
      </Label>
      {children}
    </div>
  )
}

export function MaterialSearchFields({
  value,
  onChange,
  testTypes,
  dirty,
  onReset,
}: {
  value: MaterialDetail
  onChange: (next: MaterialDetail) => void
  /** 「이 종류의 시험이 있는 재료」 의 선택지. 서버의 시험 종류 그대로다. */
  testTypes: { key: string; label: string }[]
  /** 적은 것이 아직 안 걸렸나 — 「이 조건으로 찾기」 를 켠다. */
  dirty: boolean
  onReset: () => void
}) {
  function set(key: keyof MaterialDetail, next: string) {
    onChange({ ...value, [key]: next })
  }

  return (
    <div className="bg-muted/30 grid gap-3 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field id="find-use" label="용도(적용 제품·부위)">
        <Input
          id="find-use"
          className="h-8"
          value={value.use}
          onChange={(event) => set('use', event.target.value)}
          placeholder="예: 범퍼"
        />
      </Field>
      <Field id="find-maker" label="제조사·거래처">
        <Input
          id="find-maker"
          className="h-8"
          value={value.maker}
          onChange={(event) => set('maker', event.target.value)}
          placeholder="예: 포스코 — 별칭으로도 찾습니다"
        />
      </Field>
      <Field id="find-lot" label="시료 로트 번호">
        <Input
          id="find-lot"
          className="h-8"
          value={value.lot}
          onChange={(event) => set('lot', event.target.value)}
        />
      </Field>
      <Field id="find-test-type" label="이 시험이 있는 재료">
        <select
          id="find-test-type"
          className={SELECT}
          value={value.testType}
          onChange={(event) => set('testType', event.target.value)}
        >
          <option value="">전체</option>
          {testTypes.map((one) => (
            <option key={one.key} value={one.key}>
              {one.label}
            </option>
          ))}
        </select>
      </Field>
      <Field id="find-thickness-min" label={`스펙 두께 (${LENGTH_UNIT})`}>
        <div className="flex items-center gap-1.5">
          <Input
            id="find-thickness-min"
            aria-label="두께 하한"
            className="h-8"
            type="number"
            step="any"
            min={0}
            value={value.thicknessMin}
            onChange={(event) => set('thicknessMin', event.target.value)}
            placeholder="부터"
          />
          <span className="text-muted-foreground">~</span>
          <Input
            aria-label="두께 상한"
            className="h-8"
            type="number"
            step="any"
            min={0}
            value={value.thicknessMax}
            onChange={(event) => set('thicknessMax', event.target.value)}
            placeholder="까지"
          />
        </div>
      </Field>
      <Field id="find-card" label="물성 카드">
        <select
          id="find-card"
          className={SELECT}
          value={value.card}
          onChange={(event) => set('card', event.target.value)}
        >
          <option value="">전체</option>
          {CARD_CHOICES.map((one) => (
            <option key={one.value} value={one.value}>
              {one.label}
            </option>
          ))}
        </select>
      </Field>
      <Field id="find-registered-from" label="등록일" wide>
        <div className="flex items-center gap-1.5">
          <Input
            id="find-registered-from"
            aria-label="등록일 시작"
            className="h-8"
            type="date"
            value={value.registeredFrom}
            onChange={(event) => set('registeredFrom', event.target.value)}
          />
          <span className="text-muted-foreground">~</span>
          <Input
            aria-label="등록일 끝"
            className="h-8"
            type="date"
            value={value.registeredTo}
            onChange={(event) => set('registeredTo', event.target.value)}
          />
        </div>
      </Field>
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
