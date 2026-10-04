/**
 * 선언 물성 — **시험이 주지 않는 값을 사람이 적는다**(ADR 0016).
 *
 * 탄성계수는 처리 결과에서만 왔고 선팽창계수(CTE)·비열·열전도율은 자리가 아예 없었다.
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

import { BadgeCheck, BookOpen, Pencil, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type {
  DeclaredProperty,
  DeclaredPropertyIn,
  PropertyItem,
} from '@/modules/materials/api'
import { DeclaredGrade, approvalText } from '@/shared/components/DeclaredGrade'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { display, fromDisplay, significant, toDisplay } from '@/shared/units'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

/**
 * 값이 어디서 왔나. **「모름」이 없다** — 두면 대부분이 거기로 가고, 그때부터
 * 이 칸이 뜻을 잃는다. 대신 '추정' 을 둔다: 추정도 출처다.
 */
export const SOURCES: { value: string; label: string; hint: string }[] = [
  { value: 'literature', label: '문헌', hint: '핸드북·논문·교과서' },
  { value: 'standard', label: '규격', hint: 'KS·ASTM·EN 등' },
  // **한 칸이었다가 갈렸다**(2026-09-06). 성격이 정반대다 — 제품 데이터시트는
  // Grade 의 스펙(재료에 붙는다)이고, 밀시트는 그 로트의 증명(시료에 붙는다).
  // 한 칸일 때는 안전을 위해 둘 다 시료로 막아, 벤더 공칭값이 통째로 잠겼다.
  { value: 'datasheet', label: '제품 데이터시트', hint: '벤더 카탈로그의 Grade 스펙' },
  { value: 'millsheet', label: '밀시트(성적서)', hint: '이 로트를 증명하는 문서' },
  { value: 'estimate', label: '추정', hint: '비슷한 재료에서 미룬 값' },
]

export const SOURCE_LABEL: Record<string, string> = Object.fromEntries(
  SOURCES.map((item) => [item.value, item.label])
)

/** 조건 하나에서의 값 하나. **문자열로 든다** — 지우는 중인 칸이 0 이 되면 안 된다. */
interface Point {
  value: string
  /** 섭씨. **상온을 298 로 적는 사람은 없다** — 보낼 때 K 로 바꾼다. 온도 축 항목에서만 쓴다. */
  temperature: string
  /** 온도가 아닌 축(주파수 · 파장)의 값 — 줄의 `conditionUnit` 단위. */
  condition: string
}

/**
 * 점에서 조건을 드는 칸. **항목이 정한다**(서버의 `condition_key`) — 유전율 · 유전손실은
 * 주파수, 굴절률은 파장, 나머지는 온도(2026-10-01).
 */
type ConditionKey = 'temperature_k' | 'frequency_hz' | 'wavelength_m'
type ConditionUnit = PropertyItem['condition_units'][number]

const AXIS_LABEL: Record<ConditionKey, string> = {
  temperature_k: '온도',
  frequency_hz: '주파수',
  wavelength_m: '파장',
}

/** 조건 값 하나(SI). */
function conditionOf(
  point: DeclaredProperty['points'][number],
  key: ConditionKey
): number | null {
  const value = point[key]
  return typeof value === 'number' ? value : null
}

/** 항목의 축. 항목 목록이 아직 안 왔으면 **점이 든 칸**으로 짐작한다. */
function keyOf(row: DeclaredProperty, spec?: PropertyItem): ConditionKey {
  if (spec?.condition_key) return spec.condition_key as ConditionKey
  if (row.points.some((point) => point.frequency_hz != null)) return 'frequency_hz'
  if (row.points.some((point) => point.wavelength_m != null)) return 'wavelength_m'
  return 'temperature_k'
}

/**
 * 적힌 조건 값을 읽기 좋은 단위로 — **가장 작은 값이 1 이상이 되는 가장 큰 단위.**
 * 1e9 Hz 를 `1000000000 Hz` 로 보이면 자릿수를 세게 된다. 배수는 서버가 준다(ADR 0004).
 */
function pickUnit(values: number[], units: ConditionUnit[]): ConditionUnit | null {
  if (units.length === 0 || values.length === 0) return null
  const sorted = [...units].sort((a, b) => a.to_si - b.to_si)
  const least = Math.min(...values)
  let best = sorted[0]
  for (const unit of sorted) if (least / unit.to_si >= 1) best = unit
  return best
}

/** 새 줄의 조건 단위 — 데이터시트가 적는 단위(GHz · nm)가 있으면 그것. */
function startUnit(units: ConditionUnit[]): ConditionUnit | null {
  return units.find((one) => one.unit === 'GHz' || one.unit === 'nm') ?? units[0] ?? null
}

/** K → 편집 상자의 섭씨 문자열. 비었으면 빈 문자열. */
function celsius(kelvin: number | null | undefined): string {
  return kelvin == null
    ? ''
    : String(Number(toDisplay(kelvin, 'K', 'temperature').toPrecision(10)))
}

/** 편집 중인 한 줄. */
interface Draft {
  item: string
  points: Point[]
  /**
   * 단위 또는 **척도**. 한 칸에 든다 — 그 항목이 어느 쪽인지는 서버가 정하고
   * (`scales` 가 비었나), 화면은 드롭다운의 후보만 갈아 끼운다.
   *
   * 둘을 따로 두면 화면이 「지금 어느 쪽이지」를 매번 판단해야 하고, 그 판단이
   * 서버와 갈라지는 날 경도에 MPa 가 뜬다.
   */
  measure: string
  /**
   * 이 줄이 **척도로 재는 물성인가.**
   *
   * 저장할 때 항목 목록을 다시 뒤지지 않으려고 든다. 목록은 비동기로 오는데,
   * 도착하기 전에 저장을 누르면 **척도를 단위 칸으로 보내고** 서버가 「모르는
   * 단위」로 거절한다 — 사람은 왜인지 모른다.
   */
  isScale: boolean
  /** 점이 드는 조건 — 온도 · 주파수 · 파장. */
  conditionKey: ConditionKey
  /** 온도가 아닌 축의 값을 적는 단위와 그 SI 배수(서버가 준 것). */
  conditionUnit: string
  conditionToSi: number
  /**
   * 온도가 아닌 축 항목의 **측정 온도**(℃, 선택). 점마다 같아야 해서 줄에 하나만 든다 —
   * 「10 GHz, 23 ℃」. 점마다 다르면 서버가 거절한다(2차원 표는 안 담는다).
   */
  measured: string
  /**
   * 선팽창계수 표의 **할선 기준 온도 θ₀**(℃ 글자, 선택 — 2026-10-04). 덱의 Abaqus `ZERO` · ANSYS
   * `REFT` · Nastran `TREF` 가 된다. 표의 측정 온도와 다른 것이다 — 할선 α 는 「θ₀ 에서 그 온도까지의
   * 평균 기울기」 라 θ₀ 를 모르면 열변형을 셀 수 없다.
   */
  secant: string
  source: string
  reference: string
  note: string
}

/** 할선 기준 온도를 받는 물성 — 서버(`materials/declared.SECANT_PROPERTY`)와 같은 키. */
const SECANT_PROPERTY = 'thermal.expansion_linear'

function toDraft(row: DeclaredProperty, spec?: PropertyItem): Draft {
  // **되돌리는 환산도 서버가 한다.** `value` 가 사람이 적은 단위의 값이다 —
  // 화면이 나눗셈을 하면 그 규칙이 서버와 갈라질 자리가 하나 더 생긴다.
  const key = keyOf(row, spec)
  const units = spec?.condition_units ?? []
  const values = row.points
    .map((point) => (key === 'temperature_k' ? null : conditionOf(point, key)))
    .filter((value): value is number => value != null)
  const unit = pickUnit(values, units) ?? startUnit(units)
  const factor = unit?.to_si ?? 1
  return {
    item: row.item,
    points: row.points.map((point) => {
      const at = key === 'temperature_k' ? null : conditionOf(point, key)
      return {
        value: String(Number(point.value.toPrecision(12))),
        // **환산은 표가 한다.** `- 273.15` 를 손으로 적으면 표 바깥에 정본이
        // 하나 더 생기고, 표를 바꾼 날 이 자리만 옛 값을 낸다.
        temperature: key === 'temperature_k' ? celsius(point.temperature_k) : '',
        condition: at == null ? '' : String(Number((at / factor).toPrecision(10))),
      }
    }),
    conditionKey: key,
    // 단위 목록이 아직 없으면 SI 그대로 보인다 — 목록이 오면 다시 그린다(아래 효과).
    conditionUnit: unit?.unit ?? (key === 'frequency_hz' ? 'Hz' : 'm'),
    conditionToSi: factor,
    measured:
      key === 'temperature_k'
        ? ''
        : celsius(row.points.find((point) => point.temperature_k != null)?.temperature_k),
    measure: row.scale ?? row.input_unit ?? '',
    isScale: row.scale != null,
    secant: celsius(row.secant_reference_k),
    source: row.source,
    reference: row.reference,
    note: row.note ?? '',
  }
}

/** 서버 값 전부를 초안으로. 항목 목록이 오면 조건 단위(GHz · nm)를 다시 고른다. */
function draftsOf(saved: DeclaredProperty[], known: PropertyItem[]): Draft[] {
  return saved.map((row) => toDraft(row, known.find((item) => item.item === row.item)))
}

/**
 * 값 칸이 숫자인가. **빈 칸은 숫자가 아니다** — `Number('')` 는 0 이라, 그대로 보내면
 * 「탄성계수 0」 이 저장됐다(2026-10-04).
 */
function isNumber(text: string): boolean {
  return text.trim() !== '' && Number.isFinite(Number(text))
}

/** 온도 표시 단위 — **값 환산과 같은 표에서 읽는다.** */
const TEMPERATURE = display('K', 'temperature')

export function DeclaredPropertiesCard({
  level,
  openItem,
  onOpenChange,
  list = true,
  rows: saved,
  onSave,
  onApprove,
  title,
  hint,
}: {
  /** `재료` | `시료`. **넣을 수 있는 항목이 이것으로 갈린다.** */
  level: string
  /**
   * 지금 창을 열어 둘 항목. `null` 이면 닫혀 있다.
   *
   * **값 목록은 여기 없다** — 물성 요약이 잰 값과 함께 보이고, 거기의 편집
   * 단추가 이 창을 연다. 같은 값을 두 곳에서 보이면 어느 쪽이 진짜인지 묻게 된다.
   */
  openItem?: string | null
  onOpenChange?: (item: string | null) => void
  /**
   * 값 목록을 여기서도 보일까.
   *
   * 재료 쪽은 **끈다** — 물성 요약이 잰 값과 함께 보이므로 같은 값이 두 번
   * 나온다. 시료 쪽(밀시트)에는 그 요약이 없어 여기가 유일한 목록이다.
   */
  list?: boolean
  rows: DeclaredProperty[]
  onSave: (rows: DeclaredPropertyIn[]) => Promise<void>
  /**
   * 승인하거나 거둔다(ADR 0049). **주면 단추가 선다** — 자료 관리자인지는 부모가 안다.
   * 안 주면 승인 상태만 보인다. 판정은 서버가 한다(여기는 눌러 보고 403 을 알게 하지 않는 것).
   */
  onApprove?: (item: string, approve: boolean, note?: string) => Promise<void>
  title?: string
  hint?: React.ReactNode
}) {
  const items = useResource(() => materialsApi.propertyItems(level), [level])
  const known = useMemo(() => items.data ?? [], [items.data])

  const [rows, setRows] = useState<Draft[]>([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  /**
   * 지금 펼쳐 놓은 줄. **`null` 이면 전부 접혀 있다.**
   *
   * 전에는 항목마다 편집 폼을 늘 펼쳐 두었다. 한 항목이 세 줄(단위·출처·값·근거)
   * 이라 **여섯 개만 있어도 화면이 다 찼고**, 그러면 「무엇이 적혀 있나」 를 보려고
   * 스크롤을 하게 된다 — 그것이 이 카드에 가장 자주 하는 일인데.
   *
   * 한 번에 하나만 편다. 둘을 동시에 고칠 일이 없고, 여럿이 펴져 있으면 다시
   * 같은 문제가 된다.
   */
  /**
   * 지금 고치는 항목. **부모가 든다** — 값 목록은 물성 요약에 있고, 거기의 편집
   * 단추가 이 창을 연다(2026-08-30). 상태를 여기 두면 요약이 그것을 못 건드린다.
   */
  const [own, setOwn] = useState<string | null>(null)
  const editing = openItem !== undefined ? openItem : own
  const setEditing = onOpenChange ?? setOwn

  /** 창을 연다. */
  function open(item: string) {
    setError(null)
    setEditing(item)
  }

  /**
   * 고친 것을 버리고 닫는다 — **되돌릴 곳은 서버 값이다.**
   *
   * 창에서 고치고 저장까지 하는 흐름(A안)이면 「닫기」 가 곧 「버리기」 여야 한다.
   * 전에는 연 때의 사본으로 되돌리면서 `dirty` 를 그대로 두었다. 그러면 서버 값을 초안으로
   * 옮기는 아래 효과가 다시는 안 돌아, 다른 재료로 넘어가 저장하면 **앞 재료의 줄이 새
   * 재료에 통째로 들어갔다**(2026-10-04). 창 밖에서는 고칠 길이 없으니 닫으면 늘 깨끗하다.
   */
  function cancel() {
    setRows(draftsOf(saved, known))
    setDirty(false)
    setError(null)
    setEditing(null)
  }

  // 서버 값을 초안으로 옮긴다. **고치는 중이면 안 덮는다** — 저장 전에 목록이
  // 다시 읽히면 타이핑하던 것이 사라진다.
  useEffect(() => {
    if (dirty) return
    // **항목 목록이 오면 다시 그린다** — 조건 단위(GHz · nm)는 항목이 들고 온다.
    setRows(draftsOf(saved, known))
  }, [saved, dirty, known])

  const used = new Set(rows.map((row) => row.item))
  /** **저장된** 줄 — 등급 · 승인은 서버가 저장된 값에 매긴 것이다. 고치는 중인 초안에는 없다. */
  const stored = (item: string) => saved.find((row) => row.item === item)
  const free = known.filter((item) => !used.has(item.item))

  function edit(at: number, patch: Partial<Draft>) {
    setDirty(true)
    setRows((current) => current.map((row, index) => (index === at ? { ...row, ...patch } : row)))
  }

  function add(item: PropertyItem) {
    setDirty(true)
    setError(null)
    // **더하자마자 편다.** 값을 적으려고 더한 것이므로, 접힌 줄을 다시 눌러
    // 열게 하면 한 걸음이 헛돈다.
    setEditing(item.item)
    setRows((current) => [
      ...current,
      {
        item: item.item,
        points: [{ value: '', temperature: '', condition: '' }],
        // 척도를 든 항목은 **첫 척도**로 시작한다. 단위는 정본 SI 로.
        measure: item.scales.length > 0 ? item.scales[0] : item.si_unit,
        isScale: item.scales.length > 0,
        // 조건 칸이 없는 항목(옛 응답)은 온도다.
        conditionKey: (item.condition_key ?? 'temperature_k') as ConditionKey,
        conditionUnit: startUnit(item.condition_units ?? [])?.unit ?? '',
        conditionToSi: startUnit(item.condition_units ?? [])?.to_si ?? 1,
        measured: '',
        secant: '',
        source: 'literature',
        reference: '',
        note: '',
      },
    ])
  }

  /** 한 줄의 점 하나를 고친다. */
  function editPoint(at: number, index: number, patch: Partial<Point>) {
    setDirty(true)
    setRows((current) =>
      current.map((row, position) =>
        position === at
          ? {
              ...row,
              points: row.points.map((point, spot) =>
                spot === index ? { ...point, ...patch } : point
              ),
            }
          : row
      )
    )
  }

  /** 읽는 자리의 값. **편집 상자는 이걸 안 쓴다** — 상자에는 적은 값이 그대로
   *  있어야 하고, 반올림한 값을 보여 주고 저장하면 아무도 안 고쳤는데 값이 달라진다. */
  function shown(text: string): string {
    const value = Number(text)
    return Number.isFinite(value) ? String(significant(value)) : text
  }

  /**
   * 줄 전부를 보낸다 — 서버는 선언 물성을 **통째로 갈아 끼운다.**
   *
   * **성공했는지를 돌려준다.** 전에는 오류를 삼키고 창이 닫혀, 저장이 안 됐는데 고친
   * 것만 사라졌다(2026-10-04).
   */
  async function save(next: Draft[] = rows): Promise<boolean> {
    // **빈 값 칸은 막는다.** `Number('')` 가 0 이라 「탄성계수 0」 이 저장됐다(2026-10-04).
    // 0 을 뜻한 사람은 0 을 적는다.
    const blank = next.find((row) => row.points.some((point) => !isNumber(point.value)))
    if (blank) {
      setError(
        new Error(
          `「${blank.item}」 값 칸이 비었거나 숫자가 아닙니다. 값을 적거나 그 점을 지운 뒤 저장하세요.`
        )
      )
      return false
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(
        next.map((row) => ({
          item: row.item,
          points: row.points.map((point) => {
            // 화면은 ℃ 로 받고 서버에는 K 로 보낸다 — 상온을 298 로 적는
            // 사람은 없다. 온도가 아닌 축의 항목이면 줄의 측정 온도가 점마다 간다.
            const temperature = row.conditionKey === 'temperature_k' ? point.temperature : row.measured
            return {
              value: Number(point.value),
              temperature_k:
                temperature === '' ? null : fromDisplay(Number(temperature), 'K', 'temperature'),
              // **조건은 SI 로 보낸다** — 배수는 서버가 준 것(`condition_units[].to_si`).
              ...(row.conditionKey === 'temperature_k'
                ? {}
                : {
                    [row.conditionKey]:
                      point.condition === '' ? null : Number(point.condition) * row.conditionToSi,
                  }),
            }
          }),
          // **어느 칸으로 보낼지는 줄 자신이 안다.** 항목 목록을 여기서
          // 다시 뒤지면, 목록이 도착하기 전에 저장을 누른 사람이 척도를 단위
          // 자리로 보내게 된다.
          ...(row.isScale ? { scale: row.measure } : { input_unit: row.measure }),
          // **통째 교체라 있던 θ₀ 도 되보낸다** — 안 보내면 지워지고 승인이 풀린다. 비운 칸이면
          // 안 보낸다(= 없다). 화면은 ℃ 로 받고 서버에는 K 로.
          ...(row.secant.trim() === ''
            ? {}
            : { secant_reference_k: fromDisplay(Number(row.secant), 'K', 'temperature') }),
          source: row.source,
          reference: row.reference,
          note: row.note || null,
        }))
      )
      setDirty(false)
      return true
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
      return false
    } finally {
      setSaving(false)
    }
  }

  /**
   * 항목을 지운다 — **누르면 곧바로 서버에 남긴다**(2026-10-04).
   *
   * 전에는 초안에서만 빼고 창을 닫았다. 저장된 것이 없으니 표에는 그대로 보이고, 다른
   * 항목을 저장하는 날 함께 지워졌다 — 지운 사람도, 지워진 날도 모른다.
   */
  async function remove(item: string) {
    // 아직 저장 안 한 줄이면 서버에 보낼 것이 없다 — 버리기와 같다.
    if (!stored(item)) return cancel()
    // **다른 줄은 서버 값 그대로 보낸다.** 이 창에서 고친 것은 이 항목뿐이고, 지우니 버린다.
    if (await save(draftsOf(saved, known).filter((row) => row.item !== item))) setEditing(null)
  }

  const picker = free.length > 0 && (
    <Select value="" onValueChange={(value) => add(free[Number(value)])}>
      <SelectTrigger size="sm" aria-label="선언 물성 추가" className="h-7 w-40 text-xs">
        <Plus className="size-3.5" />
        <SelectValue placeholder="선언 물성 추가" />
      </SelectTrigger>
      <SelectContent>
        {free.map((item, index) => (
          <SelectItem
            key={item.item}
            value={String(index)}
            // 마우스를 올리면 정의문 — 이름만으로 고르다 비슷한 다른 물성을 집지 않게.
            title={item.description ?? undefined}
          >
            {item.item}
            {item.symbol ? ` (${item.symbol})` : ''}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )

  return (
    <>
      {/* **`list=false` 면 박스를 안 두른다.** 값 목록이 물성 표로 갔으므로 여기
          남는 것은 「항목을 넣고 빼는 자리」 하나뿐이고, 그것에 제목과 테두리를
          두르면 빈 상자가 화면 위쪽을 차지한다.

          시료(밀시트) 쪽은 그 물성 표가 없어 여기가 유일한 목록이다 — 그때는
          제목·안내와 함께 상자로 선다. */}
      {list ? (
        <section className="rounded-md border p-4">
          <div className="mb-1 flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-medium">
              <BookOpen className="size-4" />
              {title ?? '선언 물성'}
            </h3>
            {picker}
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

          {/* 저장 오류는 창 안에 선다 — 저장은 창에서만 한다. */}
          <ErrorNotice error={items.error} className="mb-3" />

          {known.length === 0 && !items.loading && (
            <p className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
              {level}에 넣을 수 있는 물성 항목이 없습니다. 온톨로지 편집의 <b>사내 물성 항목</b> 축에
              먼저 등록하고 <b>붙는 곳</b>을 {level} 로 두세요.
            </p>
          )}

          {rows.length === 0 && known.length > 0 && (
            <p className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
              적어 둔 값이 없습니다. 오른쪽 위에서 항목을 고르세요.
            </p>
          )}

          {rows.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>항목</TableHead>
              <TableHead>값</TableHead>
              <TableHead className="w-16" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const spec = known.find((item) => item.item === row.item)
              const points = row.points.filter((point) => point.value !== '')
              return (
                <TableRow key={row.item}>
                  <TableCell className="font-medium">
                    {row.item}
                    {spec?.symbol ? (
                      <span className="text-muted-foreground ml-1 font-mono text-xs">
                        {spec.symbol}
                      </span>
                    ) : null}
                    {stored(row.item) ? (
                      <div>
                        <DeclaredGrade
                          tier={stored(row.item)?.quality_tier ?? 4}
                          approval={stored(row.item)?.approval}
                          catalog={stored(row.item)?.catalog}
                        />
                      </div>
                    ) : null}
                  </TableCell>
                  {/* **단위를 값에 붙이고 낱값을 다 적는다.** 줄여 놓으면 그 값이
                      얼마인지 보려고 매번 창을 열어야 한다. */}
                  <TableCell className="font-mono">
                    {points.length === 0 ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <div className="space-y-0.5">
                        {points.map((point, spot) => (
                          <div key={spot}>
                            {shown(point.value)} {row.measure === '1' ? '' : row.measure}
                            {point.temperature !== '' && (
                              <span className="text-muted-foreground">
                                {' @ '}
                                {/* **단위를 손으로 적지 않는다**(AGENTS.md). 값은
                                    이미 표에서 환산해 왔다(`toDisplay(…, 'K', …)`) —
                                    기호만 손으로 적으면 표를 바꾼 날 라벨이 옛 단위를
                                    적은 채 새 값을 받는다. */}
                                {shown(point.temperature)} {TEMPERATURE.unit}
                              </span>
                            )}
                            {point.condition !== '' && (
                              <span className="text-muted-foreground">
                                {' @ '}
                                {shown(point.condition)} {row.conditionUnit}
                              </span>
                            )}
                          </div>
                        ))}
                        {row.measured !== '' && (
                          <div className="text-muted-foreground text-xs">
                            측정 {shown(row.measured)} {TEMPERATURE.unit}
                          </div>
                        )}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`${row.item} 편집`}
                      title={`${row.item} 값을 고칩니다`}
                      onClick={() => open(row.item)}
                    >
                      <Pencil className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
        </section>
      ) : (
        <>
          {picker}
          <ErrorNotice error={items.error} />
        </>
      )}

      {/* **편집은 창에서 한다.** 줄 안에서 펼치면 표가 흔들리고, 무엇보다 닫는
          길이 분명하지 않았다 — 창은 바깥을 누르거나 Esc 로 닫힌다. */}
      {/* **창에서 저장까지 한다**(2026-08-30). 전에는 창을 닫고 바깥의 저장을
          눌러야 했는데, 값 목록이 물성 표로 옮겨 가면서 **고친 것이 어디에도 안
          보이는** 상태가 생겼다 — 닫고 나면 바뀐 게 없어 보이고, 저장 단추가
          켜진 것을 스스로 알아채야 했다. */}
      <Dialog open={editing !== null} onOpenChange={(next) => !next && cancel()}>
        {/* **좁으면 겹친다.** 값·단위·온도 상자가 한 줄에 오고, 단위 목록은
            `J/(kg.K)` 처럼 긴 이름을 담는다 — 42rem 으로는 모자랐다. */}
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{editing}</DialogTitle>
            <DialogDescription>
              <b>저장</b> 을 눌러야 서버에 남습니다. 닫으면 고친 것이 사라집니다.
            </DialogDescription>
          </DialogHeader>
          {rows.map((row, index) => {
            if (row.item !== editing) return null
            const spec = known.find((item) => item.item === row.item)
            const choices = spec?.units.length ? spec.units : [row.measure]
            const axis = spec?.condition ?? AXIS_LABEL[row.conditionKey]
            const byTemperature = row.conditionKey === 'temperature_k'
            const conditionUnits = spec?.condition_units ?? []
            return (
              <div key={row.item} className="grid grid-cols-12 items-end gap-2">
            <div className="col-span-12 flex justify-end">
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                title={`${row.item} 줄을 지웁니다`}
                disabled={saving}
                onClick={() => void remove(row.item)}
              >
                <Trash2 className="size-4" />
                이 항목 삭제
              </Button>
            </div>

            {/* **이 항목이 무엇인가**(ADR 0050) — 같은 물성으로 이어진 문헌 키의 정의문이다. 이름이
                비슷한 항목을 잘못 골랐는지 값을 적기 전에 본다. */}
            {spec?.description ? (
              <p
                aria-label={`${row.item} 정의`}
                className="text-muted-foreground col-span-12 rounded-md border border-dashed p-2 text-xs"
              >
                {spec.description}
              </p>
            ) : null}

            {/* **한 줄이 표를 든다.** 강판 탄성계수는 상온 206 GPa 가
                400 °C 에서 170 GPa 쯤으로 떨어지고, 열간 성형·용접·화재
                해석은 그 곡선이 필요하다. 그렇다고 줄을 여럿 두면 카드가 어느
                것을 쓸지 못 정한다 — 항목은 하나이고 그 하나가 온도에 따라
                변할 뿐이다. */}
            <div className="col-span-12 sm:col-span-6">
              <Label htmlFor={`${row.item}-unit`} className="text-muted-foreground mb-1 text-[11px]">
                {spec?.scales.length ? '시험 척도' : '단위'}
              </Label>
              {/* **차원이 맞는 단위만 뜬다.** 비열 자리에 W/(m.K) 를 넣으면
                  값은 멀쩡한데 뜻이 다르다 — 서버도 같은 검사를 한다.

                  경도처럼 **척도로 재는 물성**은 여기가 척도 목록이 된다.
                  `HV 200` 과 `HB 200` 은 다른 값이고 환산식이 없어서, 척도는
                  단위가 아니라 값의 일부다. */}
              <Select
                value={row.measure}
                onValueChange={(value) => edit(index, { measure: value })}
              >
                <SelectTrigger id={`${row.item}-unit`} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(spec?.scales.length ? spec.scales : choices).map((unit) => (
                    <SelectItem key={unit} value={unit}>
                      {unit}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="col-span-12">
              <Label className="text-muted-foreground mb-1 text-[11px]">
                값 {row.points.length > 1 && `(${axis} ${row.points.length}점)`}
              </Label>
              <div className="space-y-1">
                {row.points.map((point, spot) => (
                  <div key={spot} className="flex flex-wrap items-center gap-2">
                    <Input
                      aria-label={
                        row.points.length > 1 ? `${row.item} 값 ${spot + 1}` : `${row.item} 값`
                      }
                      className="w-36 shrink-0"
                      value={point.value}
                      inputMode="decimal"
                      onChange={(event) =>
                        editPoint(index, spot, { value: event.target.value })
                      }
                    />
                    <span className="text-muted-foreground text-xs">
                      {row.measure === '1' ? '' : row.measure}
                    </span>
                    <span className="text-muted-foreground text-xs">@</span>
                    <Input
                      aria-label={
                        row.points.length > 1
                          ? `${row.item} ${axis} ${spot + 1}`
                          : `${row.item} ${axis}`
                      }
                      className="w-28 shrink-0"
                      value={byTemperature ? point.temperature : point.condition}
                      inputMode="decimal"
                      placeholder={
                        row.points.length > 1 ? '필수' : byTemperature ? '비우면 상온' : '비우면 미상'
                      }
                      onChange={(event) =>
                        editPoint(
                          index,
                          spot,
                          byTemperature
                            ? { temperature: event.target.value }
                            : { condition: event.target.value }
                        )
                      }
                    />
                    <span className="text-muted-foreground text-xs">
                      {byTemperature ? TEMPERATURE.unit : row.conditionUnit}
                    </span>
                    {row.points.length > 1 && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7"
                        title={`${spot + 1}번째 온도를 지웁니다`}
                        onClick={() => {
                          setDirty(true)
                          setRows((current) =>
                            current.map((one, position) =>
                              position === index
                                ? {
                                    ...one,
                                    points: one.points.filter((_, at) => at !== spot),
                                  }
                                : one
                            )
                          )
                        }}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="mt-1 h-7 px-2 text-[11px]"
                onClick={() => {
                  setDirty(true)
                  setRows((current) =>
                    current.map((one, position) =>
                      position === index
                        ? {
                            ...one,
                            points: [...one.points, { value: '', temperature: '', condition: '' }],
                          }
                        : one
                    )
                  )
                }}
              >
                <Plus className="size-3.5" />
                {axis} 추가
              </Button>
              {row.points.length > 1 && (
                // **조건 없는 점이 섞이면 서버가 거절한다.** 누르기 전에
                // 알려 주는 편이 낫다.
                <p className="text-muted-foreground mt-1 text-[11px]">
                  값이 여럿이면 점마다 {axis} 값을 적어야 합니다.
                  {byTemperature && ' 표 밖에서는 솔버가 끝값을 유지합니다.'}
                </p>
              )}
            </div>

            {!byTemperature && (
              // **온도가 아닌 축의 항목** — 조건 단위와 측정 온도를 고른다. 측정 온도는
              // 점마다 같아야 해서 줄에 하나다(「10 GHz, 23 ℃」).
              <>
                <div className="col-span-6 sm:col-span-3">
                  <Label
                    htmlFor={`${row.item}-condition-unit`}
                    className="text-muted-foreground mb-1 text-[11px]"
                  >
                    {axis} 단위
                  </Label>
                  <Select
                    value={row.conditionUnit}
                    onValueChange={(value) => {
                      const unit = conditionUnits.find((one) => one.unit === value)
                      if (unit) edit(index, { conditionUnit: unit.unit, conditionToSi: unit.to_si })
                    }}
                  >
                    <SelectTrigger id={`${row.item}-condition-unit`} className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {conditionUnits.map((unit) => (
                        <SelectItem key={unit.unit} value={unit.unit}>
                          {unit.unit}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-6 sm:col-span-3">
                  <Label
                    htmlFor={`${row.item}-measured`}
                    className="text-muted-foreground mb-1 text-[11px]"
                  >
                    측정 온도 ({TEMPERATURE.unit}, 선택)
                  </Label>
                  <Input
                    id={`${row.item}-measured`}
                    value={row.measured}
                    inputMode="decimal"
                    placeholder="비우면 상온"
                    onChange={(event) => edit(index, { measured: event.target.value })}
                  />
                </div>
              </>
            )}

            {spec?.property_key === SECANT_PROPERTY ? (
              <div className="col-span-12">
                <Label
                  htmlFor={`${row.item}-secant`}
                  className="text-muted-foreground mb-1 text-[11px]"
                >
                  할선 기준 온도 θ₀ ({TEMPERATURE.unit}, 선택)
                </Label>
                <Input
                  id={`${row.item}-secant`}
                  value={row.secant}
                  inputMode="decimal"
                  placeholder="예: 20 — 표가 몇 도 기준의 평균 α 인지"
                  onChange={(event) => edit(index, { secant: event.target.value })}
                />
                {/* **덱의 ZERO · REFT · TREF 가 된다.** 비우면 덱이 지어 넣지 않고 「없다」 고
                    적는다 — 20 °C 기준 표를 0 K 기준으로 읽으면 열변형이 통째로 어긋난다. */}
                <p className="text-muted-foreground mt-1 text-[11px]">
                  할선 α 표는 θ₀ 에서 그 온도까지의 평균 기울기입니다. 적으면 덱의 Abaqus ZERO ·
                  ANSYS REFT · Nastran TREF 가 되고, 비우면 덱에 「기준 온도 없음」 이 적힙니다.
                </p>
              </div>
            ) : null}

            <div className="col-span-12 sm:col-span-6">
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
          {editing !== null && stored(editing) ? (
            <ApprovalSection
              key={editing}
              row={stored(editing) as DeclaredProperty}
              changed={dirty}
              onApprove={onApprove}
            />
          ) : null}
          {/* **저장 오류는 창 안에 보인다** — 창이 열려 있는 동안 바깥은 가려져 있다. */}
          <ErrorNotice error={error} />
          <DialogFooter>
            {/* **닫기가 곧 버리기다.** 그러니 그렇게 적는다 — 「닫기」 만 있으면
                고친 것이 남는지 사라지는지 눌러 보고서야 안다. */}
            <Button variant="ghost" onClick={cancel} disabled={saving}>
              취소
            </Button>
            <Button
              onClick={async () => {
                // **실패하면 창을 그대로 둔다** — 닫히면 고친 것이 사라진 줄도 모른다(2026-10-04).
                if (await save()) setEditing(null)
              }}
              disabled={saving}
            >
              <Save className="size-4" />
              저장
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </>
  )
}

/**
 * 승인 — 자료 관리자가 근거 문서와 대조해 확인했다는 기록(ADR 0049).
 *
 * **저장된 값을 승인한다.** 고치는 중에는 단추를 잠근다 — 창에 보이는 값과 승인되는 값이
 * 다르면 사람은 자기가 본 값을 승인했다고 믿는다. 승인하면 될 등급은 서버가 준다
 * (`tier_if_approved`) — 「한 단계, 2 까지」 를 여기서 셈하면 규칙이 두 곳에 산다.
 */
function ApprovalSection({
  row,
  changed,
  onApprove,
}: {
  row: DeclaredProperty
  changed: boolean
  onApprove?: (item: string, approve: boolean, note?: string) => Promise<void>
}) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const tier = row.quality_tier ?? 4
  const next = row.tier_if_approved ?? tier

  async function run(approve: boolean) {
    if (!onApprove) return
    setBusy(true)
    setError(null)
    try {
      await onApprove(row.item, approve, note.trim() || undefined)
      setNote('')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('승인하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="승인" className="space-y-2 rounded-md border border-dashed p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <DeclaredGrade tier={tier} approval={row.approval} catalog={row.catalog} />
        {row.approval ? (
          <span>{approvalText(row.approval)}</span>
        ) : (
          <span className="text-muted-foreground">
            승인 전입니다.{' '}
            {next < tier
              ? `자료 관리자가 근거 문서와 대조해 승인하면 한 단계 올라 ${next} 등급이 됩니다.`
              : `승인해도 등급은 ${tier} 그대로입니다 — 승인은 근거를 확인한 기록이지 실측을 만들지 않습니다.`}
          </span>
        )}
      </div>
      {row.approval ? (
        <p className="text-muted-foreground">
          값 · 단위 · 조건 · 출처 · 근거 문서를 고쳐 저장하면 승인이 풀립니다. 비고는 그대로 둡니다.
        </p>
      ) : null}
      {onApprove ? (
        <div className="flex flex-wrap items-center gap-2">
          {row.approval ? (
            <Button size="sm" variant="outline" disabled={busy || changed} onClick={() => run(false)}>
              승인 거두기
            </Button>
          ) : (
            <>
              <Input
                aria-label="무엇을 확인했나"
                placeholder="무엇을 확인했나 (선택) — 예: 원문 p.120 대조"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                className="h-8 min-w-48 flex-1"
              />
              <Button size="sm" disabled={busy || changed} onClick={() => run(true)}>
                <BadgeCheck className="size-4" />
                승인
              </Button>
            </>
          )}
          {changed ? (
            <span className="text-muted-foreground">
              고친 것을 먼저 저장하세요 — 저장된 값을 승인합니다.
            </span>
          ) : null}
        </div>
      ) : null}
      <ErrorNotice error={error} />
    </section>
  )
}
