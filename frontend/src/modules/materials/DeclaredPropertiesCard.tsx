/**
 * 선언 물성 — **시험이 주지 않는 값을 사람이 적는다**(ADR 0016).
 *
 * 탄성계수는 처리 결과에서만 왔고 열팽창계수·비열·열전도도는 자리가 아예 없었다.
 * 그런데 그것들은 인장시험이 안 준다 — 핸드북·규격·밀시트에서 온다. 시험을 안 한
 * 재료가 대부분인데, 그 재료로는 해석용 카드를 만들 수 없었다.
 *
 * ## 왜 '수정' 대화상자가 아니라 여기인가
 *
 * `EditMaterialDialog` 는 **재료를 무엇이라 부르는가**(분류·Grade·두께)를 고친다.
 * 선언 물성은 줄이 늘었다 줄었다 하는 목록이고 항목마다 단위·출처·근거가 붙는다 —
 * 그 대화상자에 넣으면 이름 한 글자를 고치러 연 사람이 물성 표를 마주한다.
 *
 * 물성 탭에 두는 이유는 **잰 값 바로 옆이어야 하기 때문**이다. 탄성계수를 적으려는
 * 사람은 먼저 "시험에서 나온 게 있나" 를 봐야 하고, 그 둘이 다른 화면에 있으면
 * 잰 값이 있는 재료에 문헌값을 또 적는다.
 *
 * ## 재료와 시료가 같은 화면을 쓴다
 *
 * 층만 다르고 하는 일이 같다 — 항목을 고르고, 값과 단위를 적고, 출처와 근거
 * 문서를 남긴다. 무엇을 넣을 수 있는지만 다르고 **그 판정은 서버가 한다**
 * (`?level=`). 화면을 둘로 나누면 한쪽만 고쳐지는 날이 온다.
 *
 *     문헌·규격   Grade 가 같으면 같다   E · ν · α · Cp · k   → 재료
 *     밀시트      로트마다 다르다        항복강도 · 인장강도    → 시료
 *
 * ## 항목 목록을 코드에 박지 않는다
 *
 * 무엇을 넣을 수 있는지는 `/materials/property-items` 가 준다 — 기준정보의
 * `물성 항목` 축이다(D7). 열해석을 안 하는 부서에 비열 칸이 뜰 이유가 없고,
 * 반대로 박아 두면 필요한 항목 하나를 넣으려고 배포를 기다려야 한다.
 *
 * 단위 후보도 같다 — **항목이 자기 단위를 들고 온다.** 그래서 비열 자리에는
 * `W/(m.K)` 가 아예 안 뜬다. 차원으로 거르는 일을 화면이 하면 그 규칙이 두 곳에
 * 생기고, 서버와 갈라지는 날 잘못된 단위가 목록에 뜬다(막는 것은 서버다).
 */

import { BookOpen, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type {
  DeclaredProperty,
  DeclaredPropertyIn,
  PropertyItem,
} from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { useResource } from '@/shared/hooks/useResource'

/**
 * 값이 어디서 왔나. **「모름」이 없다** — 두면 대부분이 거기로 가고, 그때부터
 * 이 칸이 뜻을 잃는다. 대신 '추정' 을 둔다: 추정도 출처다.
 */
export const SOURCES: { value: string; label: string; hint: string }[] = [
  { value: 'literature', label: '문헌', hint: '핸드북·논문·교과서' },
  { value: 'standard', label: '규격', hint: 'KS·ASTM·EN 등' },
  { value: 'datasheet', label: '밀시트·데이터시트', hint: '공급사가 준 문서' },
  { value: 'estimate', label: '추정', hint: '비슷한 재료에서 미룬 값' },
]

export const SOURCE_LABEL: Record<string, string> = Object.fromEntries(
  SOURCES.map((item) => [item.value, item.label])
)

/** 편집 중인 한 줄. **값은 문자열로 든다** — 지우는 중인 칸이 0 이 되면 안 된다. */
interface Draft {
  item: string
  value: string
  input_unit: string
  source: string
  reference: string
  temperature: string
  note: string
}

function toDraft(row: DeclaredProperty): Draft {
  // **되돌리는 환산도 서버가 한다.** `value` 가 사람이 적은 단위의 값이다 —
  // 화면이 나눗셈을 하면 그 규칙이 서버와 갈라질 자리가 하나 더 생긴다.
  return {
    item: row.item,
    value: String(Number(row.value.toPrecision(12))),
    input_unit: row.input_unit,
    source: row.source,
    reference: row.reference,
    temperature: row.temperature_k == null ? '' : String(row.temperature_k - 273.15),
    note: row.note ?? '',
  }
}

export function DeclaredPropertiesCard({
  level,
  rows: saved,
  onSave,
  title,
  hint,
}: {
  /** `재료` | `시료`. **넣을 수 있는 항목이 이것으로 갈린다.** */
  level: string
  rows: DeclaredProperty[]
  onSave: (rows: DeclaredPropertyIn[]) => Promise<void>
  title?: string
  hint?: React.ReactNode
}) {
  const items = useResource(() => materialsApi.propertyItems(level), [level])
  const known = useMemo(() => items.data ?? [], [items.data])

  const [rows, setRows] = useState<Draft[]>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // 서버 값을 초안으로 옮긴다. **고치는 중이면 안 덮는다** — 저장 전에 목록이
  // 다시 읽히면 타이핑하던 것이 사라진다.
  useEffect(() => {
    if (dirty) return
    setRows(saved.map(toDraft))
  }, [saved, dirty])

  const used = new Set(rows.map((row) => row.item))
  const free = known.filter((item) => !used.has(item.item))

  function edit(at: number, patch: Partial<Draft>) {
    setDirty(true)
    setRows((current) => current.map((row, index) => (index === at ? { ...row, ...patch } : row)))
  }

  function add(item: PropertyItem) {
    setDirty(true)
    setRows((current) => [
      ...current,
      {
        item: item.item,
        value: '',
        input_unit: item.si_unit,
        source: 'literature',
        reference: '',
        temperature: '',
        note: '',
      },
    ])
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await onSave(
        rows.map((row) => ({
          item: row.item,
          value: Number(row.value),
          input_unit: row.input_unit,
          source: row.source,
          reference: row.reference,
          // 화면은 ℃ 로 받고 서버에는 K 로 보낸다 — 상온을 298 로 적는
          // 사람은 없다.
          temperature_k: row.temperature === '' ? null : Number(row.temperature) + 273.15,
          note: row.note || null,
        }))
      )
      setDirty(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-md border p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium">
          <BookOpen className="size-4" />
          {title ?? '선언 물성'}
        </h3>
        <div className="flex items-center gap-2">
          {free.length > 0 && (
            <Select value="" onValueChange={(value) => add(free[Number(value)])}>
              <SelectTrigger size="sm" aria-label="항목 추가" className="w-44">
                <Plus className="size-4" />
                <SelectValue placeholder="항목 추가" />
              </SelectTrigger>
              <SelectContent>
                {free.map((item, index) => (
                  <SelectItem key={item.item} value={String(index)}>
                    {item.item}
                    {item.symbol ? ` (${item.symbol})` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button size="sm" onClick={save} disabled={!dirty || saving}>
            <Save className="size-4" />
            저장
          </Button>
        </div>
      </div>

      <p className="text-muted-foreground mb-3 text-xs">
        {hint ?? (
          <>
            <b>인장시험이 주지 않는 값</b>입니다 — 핸드북·규격에서 옵니다. 여기 적은 값은{' '}
            <b>잰 값이 없을 때만</b> 물성 카드에 실리고, 덱에는 「사람이 적은 값」이라고
            근거 문서와 함께 나갑니다.
          </>
        )}
      </p>

      <ErrorNotice error={items.error ?? error} className="mb-3" />

      {known.length === 0 && !items.loading && (
        <p className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
          {level}에 넣을 수 있는 물성 항목이 없습니다. 기준정보의 <b>물성 항목</b> 축에
          먼저 등록하고 <b>붙는 곳</b>을 {level} 로 두세요 — 무엇을 넣을 수 있는지는 코드가
          아니라 기준정보가 정합니다.
        </p>
      )}

      {rows.length === 0 && known.length > 0 && (
        <p className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
          적어 둔 값이 없습니다. 오른쪽 위에서 항목을 고르세요.
        </p>
      )}

      <div className="space-y-3">
        {rows.map((row, index) => {
          const spec = known.find((item) => item.item === row.item)
          const choices = spec?.units ?? [row.input_unit]
          return (
            <div key={row.item} className="grid grid-cols-12 items-end gap-2 rounded-md border p-3">
              <div className="col-span-12 sm:col-span-3">
                <Label className="text-muted-foreground mb-1 text-[11px]">항목</Label>
                <div className="text-sm font-medium">
                  {row.item}
                  {spec?.symbol && (
                    <span className="text-muted-foreground ml-1 font-mono text-xs">
                      {spec.symbol}
                    </span>
                  )}
                </div>
              </div>

              <div className="col-span-5 sm:col-span-2">
                <Label htmlFor={`${row.item}-value`} className="text-muted-foreground mb-1 text-[11px]">
                  값
                </Label>
                <Input
                  id={`${row.item}-value`}
                  value={row.value}
                  inputMode="decimal"
                  onChange={(event) => edit(index, { value: event.target.value })}
                />
              </div>

              <div className="col-span-7 sm:col-span-2">
                <Label htmlFor={`${row.item}-unit`} className="text-muted-foreground mb-1 text-[11px]">
                  단위
                </Label>
                {/* **차원이 맞는 단위만 뜬다.** 비열 자리에 W/(m.K) 를 넣으면
                    값은 멀쩡한데 뜻이 다르다 — 서버도 같은 검사를 한다. */}
                <Select
                  value={row.input_unit}
                  onValueChange={(value) => edit(index, { input_unit: value })}
                >
                  <SelectTrigger id={`${row.item}-unit`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {choices.map((unit) => (
                      <SelectItem key={unit} value={unit}>
                        {unit}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="col-span-6 sm:col-span-2">
                <Label htmlFor={`${row.item}-source`} className="text-muted-foreground mb-1 text-[11px]">
                  출처
                </Label>
                <Select
                  value={row.source}
                  onValueChange={(value) => edit(index, { source: value })}
                >
                  <SelectTrigger id={`${row.item}-source`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCES.map((source) => (
                      <SelectItem key={source.value} value={source.value}>
                        {source.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="col-span-6 sm:col-span-2">
                <Label
                  htmlFor={`${row.item}-temperature`}
                  className="text-muted-foreground mb-1 text-[11px]"
                >
                  잰 온도 (℃)
                </Label>
                <Input
                  id={`${row.item}-temperature`}
                  value={row.temperature}
                  inputMode="decimal"
                  placeholder="비우면 상온"
                  onChange={(event) => edit(index, { temperature: event.target.value })}
                />
              </div>

              <div className="col-span-12 flex justify-end sm:col-span-1">
                <Button
                  size="icon"
                  variant="ghost"
                  title={`${row.item} 줄을 지웁니다`}
                  onClick={() => {
                    setDirty(true)
                    setRows((current) => current.filter((_, at) => at !== index))
                  }}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>

              <div className="col-span-12">
                <Label
                  htmlFor={`${row.item}-reference`}
                  className="text-muted-foreground mb-1 text-[11px]"
                >
                  근거 문서
                </Label>
                {/* **'문헌' 만으로는 어느 핸드북 몇 판인지 알 수 없다.** 값이
                    의심스러울 때 확인할 길이 없으면 적어 둔 뜻이 반쯤 사라진다. */}
                <Input
                  id={`${row.item}-reference`}
                  value={row.reference}
                  placeholder="예: ASM Handbook Vol.1 p.123 / KS D 3512 표 3"
                  onChange={(event) => edit(index, { reference: event.target.value })}
                />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
