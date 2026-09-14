/**
 * 의뢰 항목 표 — 「이 시험 종류를 이 조건으로 n 개, 무엇으로 받을지」.
 *
 * 조건 칸은 **시험 종류의 조건 정의**(`TestType.conditions`)에서 온다 — 시험 등록
 * 화면과 같은 칸, 같은 단위. 서버가 같은 규칙(`shared.conditions`)으로 SI 로 바꾼다.
 * 여기 칸을 따로 적어 두면 종류에 조건이 늘었을 때 의뢰만 옛 칸을 든다.
 *
 * 「받을 것」 은 카드 블록 선언(`fittingApi.blocks`)의 종류가 되는 블록 + 「곡선·처리
 * 결과」. 이름은 `kindLabel` 이 정한다 — 경화식 블록은 「탄소성」 으로 읽힌다.
 *
 * **시험 종류를 모르면 물성 이름만 적는다**(2026-09-14). 「80 °C 탄성계수」 처럼 무엇을
 * 잴지만 있고 무슨 시험으로 잴지는 받는 쪽이 정한다 — 그때 조건 칸은 없다(종류가
 * 정해진 뒤 그 칸으로). 둘 중 하나는 있어야 보낼 수 있다.
 */

import { Plus, Trash2 } from 'lucide-react'

import {
  DELIVERABLE_CURVES,
  DELIVERABLE_CURVES_LABEL,
} from '@/modules/commissions/api'
import type { BlockSpec } from '@/modules/fitting/api'
import { kindLabel } from '@/modules/fitting/cardKind'
import { ORIENTATIONS } from '@/modules/materials/api'
import type { TestType } from '@/modules/tests/api'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { conditionUnits, display, toDisplay } from '@/shared/units'

/** 화면이 들고 있는 항목 한 줄 — 조건은 **화면 단위의 글자**다. 보낼 때 단위를 함께 싣는다. */
export interface ItemDraft {
  test_type_key: string
  /** 종류 미정일 때 무엇을 재는지 — 물성 이름. */
  property_hint: string
  conditions: Record<string, string>
  orientations: string[]
  count: number
  deliverable: string
  note: string
}

export function emptyItem(testTypeKey = ''): ItemDraft {
  return {
    test_type_key: testTypeKey,
    property_hint: '',
    conditions: {},
    orientations: [],
    count: 1,
    deliverable: '',
    note: '',
  }
}

/** 서버가 준 항목(SI)을 화면 단위 글자로 — 편집 폼을 채울 때. */
export function draftFromItem(
  item: {
    test_type_key: string | null
    property_hint: string | null
    conditions: Record<string, unknown>
    input_units: Record<string, string>
    orientations: string[]
    count: number
    deliverable: string | null
    note: string | null
  },
  testType: TestType | undefined
): ItemDraft {
  const conditions: Record<string, string> = {}
  for (const field of testType?.conditions ?? []) {
    const raw = item.conditions[field.key]
    if (raw === undefined || raw === null) continue
    if (field.value_type === 'number' && field.si_unit && typeof raw === 'number') {
      conditions[field.key] = String(toDisplay(raw, field.si_unit, field.dimension))
    } else {
      conditions[field.key] = String(raw)
    }
  }
  return {
    test_type_key: item.test_type_key ?? '',
    property_hint: item.property_hint ?? '',
    conditions,
    orientations: [...item.orientations],
    count: item.count,
    deliverable: item.deliverable ?? '',
    note: item.note ?? '',
  }
}

/** 보낼 형태 — 숫자 칸은 숫자로, 단위는 정의의 표시 단위로. */
export function toPayload(draft: ItemDraft, testType: TestType | undefined) {
  const fields = testType?.conditions ?? []
  const conditions = Object.fromEntries(
    Object.entries(draft.conditions)
      .filter(([, value]) => value !== '')
      .map(([key, value]) => {
        const field = fields.find((one) => one.key === key)
        return [key, field?.value_type === 'number' ? Number(value) : value]
      })
  )
  return {
    test_type_key: draft.test_type_key || null,
    property_hint: draft.property_hint.trim() || null,
    conditions: draft.test_type_key ? conditions : {},
    condition_units: draft.test_type_key ? conditionUnits(fields) : {},
    orientations: draft.orientations,
    count: draft.count,
    deliverable: draft.deliverable || null,
    note: draft.note || null,
  }
}

/** 보낼 수 있는 항목인가 — 시험 종류 또는 물성 이름 중 하나는 있어야 한다. */
export function itemReady(draft: ItemDraft): boolean {
  return draft.test_type_key !== '' || draft.property_hint.trim() !== ''
}

/**
 * 항목마다 빠진 것을 **말로**. 단추가 왜 안 눌리는지 화면이 말해야 한다 — 비활성 단추만
 * 있으면 사용자는 폼을 위아래로 훑으며 무엇이 비었는지 찾는다(2026-09-14).
 */
export function missingInItems(items: ItemDraft[]): string[] {
  const out: string[] = []
  if (items.length === 0) out.push('항목 하나 이상')
  items.forEach((one, index) => {
    if (!itemReady(one)) out.push(`${index + 1}번 항목의 시험 종류 또는 물성 이름`)
  })
  return out
}

/** 받을 것 후보 — 종류가 되는 블록만(`kind_priority` 있는 것). */
export function deliverableOptions(specs: BlockSpec[]): { key: string; label: string }[] {
  const kinds = specs
    .filter((spec) => spec.kind_priority !== null && spec.kind_priority !== undefined)
    .sort((a, b) => (a.kind_priority ?? 0) - (b.kind_priority ?? 0))
    .map((spec) => ({ key: spec.key, label: `${kindLabel(spec.key, specs)} 카드` }))
  return [{ key: DELIVERABLE_CURVES, label: DELIVERABLE_CURVES_LABEL }, ...kinds]
}

export function deliverableLabel(key: string | null, specs: BlockSpec[]): string {
  if (!key) return '미정'
  if (key === DELIVERABLE_CURVES) return DELIVERABLE_CURVES_LABEL
  return `${kindLabel(key, specs)} 카드`
}

export function ItemsEditor({
  items,
  onChange,
  testTypes,
  blocks,
}: {
  items: ItemDraft[]
  onChange: (next: ItemDraft[]) => void
  testTypes: TestType[]
  blocks: BlockSpec[]
}) {
  const options = deliverableOptions(blocks)

  function update(index: number, patch: Partial<ItemDraft>) {
    onChange(items.map((one, at) => (at === index ? { ...one, ...patch } : one)))
  }

  return (
    <div className="space-y-3">
      {items.map((item, index) => {
        const testType = testTypes.find((one) => one.key === item.test_type_key)
        return (
          <div key={index} className="rounded-md border p-3" aria-label={`${index + 1}번 항목`}>
            <div className="mb-2 flex items-center gap-2">
              <span className="text-muted-foreground w-8 shrink-0 tabular-nums">{index + 1}.</span>
              <select
                aria-label={`${index + 1}번 시험 종류`}
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={item.test_type_key}
                onChange={(event) =>
                  // 종류가 바뀌면 조건 칸이 달라진다 — 옛 조건은 비운다.
                  update(index, { test_type_key: event.target.value, conditions: {} })
                }
              >
                <option value="">— 미정 (물성 이름으로) —</option>
                {testTypes.map((one) => (
                  <option key={one.key} value={one.key}>
                    {one.label}
                  </option>
                ))}
              </select>
              <Label className="ml-2">수량</Label>
              <Input
                type="number"
                min={1}
                max={1000}
                aria-label={`${index + 1}번 수량`}
                className="w-20"
                value={item.count}
                onChange={(event) => update(index, { count: Math.max(1, Number(event.target.value) || 1) })}
              />
              <Label className="ml-2">받을 것</Label>
              <select
                aria-label={`${index + 1}번 받을 것`}
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={item.deliverable}
                onChange={(event) => update(index, { deliverable: event.target.value })}
              >
                <option value="">— 미정 —</option>
                {options.map((one) => (
                  <option key={one.key} value={one.key}>
                    {one.label}
                  </option>
                ))}
              </select>
              {items.length > 1 && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="ml-auto size-8"
                  aria-label={`${index + 1}번 항목 삭제`}
                  onClick={() => onChange(items.filter((_, at) => at !== index))}
                >
                  <Trash2 className="size-4" />
                </Button>
              )}
            </div>

            {!item.test_type_key && (
              <div className="mb-2 space-y-1">
                <Label htmlFor={`item-${index}-property`} className="text-muted-foreground text-xs">
                  무엇을 잴지 (물성 이름) <span className="text-destructive">*</span>
                </Label>
                <Input
                  id={`item-${index}-property`}
                  value={item.property_hint}
                  onChange={(event) => update(index, { property_hint: event.target.value })}
                  placeholder="예: 80 °C 탄성계수, 접착 강도 — 시험 종류는 받는 부서가 정합니다"
                />
              </div>
            )}

            <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
              <span className="text-muted-foreground">방향</span>
              {ORIENTATIONS.map((orientation) => (
                <label key={orientation} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={item.orientations.includes(orientation)}
                    onChange={(event) =>
                      update(index, {
                        orientations: event.target.checked
                          ? [...item.orientations, orientation]
                          : item.orientations.filter((one) => one !== orientation),
                      })
                    }
                  />
                  {orientation}
                </label>
              ))}
              <span className="text-muted-foreground">(비우면 방향 무관)</span>
            </div>

            {testType && testType.conditions.length > 0 && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {testType.conditions.map((field) => (
                  <div key={field.key} className="space-y-1">
                    <Label htmlFor={`item-${index}-${field.key}`} className="text-muted-foreground text-xs">
                      {field.label}
                      {field.si_unit && ` (${display(field.si_unit, field.dimension).unit})`}
                      {field.is_required && <span className="text-destructive"> *</span>}
                    </Label>
                    {field.value_type === 'choice' ? (
                      <select
                        id={`item-${index}-${field.key}`}
                        className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                        value={item.conditions[field.key] ?? ''}
                        onChange={(event) =>
                          update(index, { conditions: { ...item.conditions, [field.key]: event.target.value } })
                        }
                      >
                        <option value="">—</option>
                        {(field.choices ?? []).map((one) => (
                          <option key={one} value={one}>
                            {one}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        id={`item-${index}-${field.key}`}
                        type={field.value_type === 'number' ? 'number' : 'text'}
                        step="any"
                        value={item.conditions[field.key] ?? ''}
                        onChange={(event) =>
                          update(index, { conditions: { ...item.conditions, [field.key]: event.target.value } })
                        }
                      />
                    )}
                  </div>
                ))}
              </div>
            )}

            <Input
              className="mt-2"
              aria-label={`${index + 1}번 메모`}
              placeholder="메모 — 지그·규격·특별히 볼 것"
              value={item.note}
              onChange={(event) => update(index, { note: event.target.value })}
            />
          </div>
        )
      })}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...items, emptyItem(items[items.length - 1]?.test_type_key ?? '')])}
      >
        <Plus className="size-4" />
        항목 추가
      </Button>
    </div>
  )
}
