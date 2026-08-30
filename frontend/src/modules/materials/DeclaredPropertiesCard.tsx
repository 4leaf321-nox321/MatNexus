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

import { BookOpen, Pencil, Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type {
  DeclaredProperty,
  DeclaredPropertyIn,
  PropertyItem,
} from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { fromDisplay, significant, toDisplay } from '@/shared/units'
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
  { value: 'datasheet', label: '밀시트·데이터시트', hint: '공급사가 준 문서' },
  { value: 'estimate', label: '추정', hint: '비슷한 재료에서 미룬 값' },
]

export const SOURCE_LABEL: Record<string, string> = Object.fromEntries(
  SOURCES.map((item) => [item.value, item.label])
)

/** 온도 하나에서의 값 하나. **문자열로 든다** — 지우는 중인 칸이 0 이 되면 안 된다. */
interface Point {
  value: string
  /** 섭씨. **상온을 298 로 적는 사람은 없다** — 보낼 때 K 로 바꾼다. */
  temperature: string
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
  source: string
  reference: string
  note: string
}

function toDraft(row: DeclaredProperty): Draft {
  // **되돌리는 환산도 서버가 한다.** `value` 가 사람이 적은 단위의 값이다 —
  // 화면이 나눗셈을 하면 그 규칙이 서버와 갈라질 자리가 하나 더 생긴다.
  return {
    item: row.item,
    points: row.points.map((point) => ({
      value: String(Number(point.value.toPrecision(12))),
      // **환산은 표가 한다.** `- 273.15` 를 손으로 적으면 표 바깥에 정본이
      // 하나 더 생기고, 표를 바꾼 날 이 자리만 옛 값을 낸다.
      temperature:
        point.temperature_k == null
          ? ''
          : String(Number(toDisplay(point.temperature_k, 'K', 'temperature').toPrecision(10))),
    })),
    measure: row.scale ?? row.input_unit ?? '',
    isScale: row.scale != null,
    source: row.source,
    reference: row.reference,
    note: row.note ?? '',
  }
}

export function DeclaredPropertiesCard({
  level,
  openItem,
  onOpenChange,
  list = true,
  rows: saved,
  onSave,
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
  /**
   * 창을 열 때의 값. **취소가 되돌릴 곳이다.**
   *
   * 창에서 고치고 저장까지 하는 흐름(A안)이면 「닫기」 가 곧 「버리기」 여야 한다 —
   * 되돌릴 데가 없으면 잘못 고친 것을 손으로 다시 적어야 한다.
   */
  const [snapshot, setSnapshot] = useState<Draft[] | null>(null)
  const editing = openItem !== undefined ? openItem : own
  const setEditing = onOpenChange ?? setOwn

  /** 창을 연다 — 그때의 값을 함께 담아 둔다. */
  function open(item: string) {
    setSnapshot(rows)
    setEditing(item)
  }

  /** 고친 것을 버리고 닫는다. */
  function cancel() {
    if (snapshot) setRows(snapshot)
    setSnapshot(null)
    setEditing(null)
  }

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
    // **더하자마자 편다.** 값을 적으려고 더한 것이므로, 접힌 줄을 다시 눌러
    // 열게 하면 한 걸음이 헛돈다.
    setSnapshot(rows)
    setEditing(item.item)
    setRows((current) => [
      ...current,
      {
        item: item.item,
        points: [{ value: '', temperature: '' }],
        // 척도를 든 항목은 **첫 척도**로 시작한다. 단위는 정본 SI 로.
        measure: item.scales.length > 0 ? item.scales[0] : item.si_unit,
        isScale: item.scales.length > 0,
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

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await onSave(
        rows.map((row) => ({
          item: row.item,
          points: row.points.map((point) => ({
            value: Number(point.value),
            // 화면은 ℃ 로 받고 서버에는 K 로 보낸다 — 상온을 298 로 적는
            // 사람은 없다.
            temperature_k:
              point.temperature === ''
                ? null
                : fromDisplay(Number(point.temperature), 'K', 'temperature'),
          })),
          // **어느 칸으로 보낼지는 줄 자신이 안다.** 항목 목록을 여기서
          // 다시 뒤지면, 목록이 도착하기 전에 저장을 누른 사람이 척도를 단위
          // 자리로 보내게 된다.
          ...(row.isScale ? { scale: row.measure } : { input_unit: row.measure }),
          source: row.source,
          reference: row.reference,
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

  const picker = free.length > 0 && (
    <Select value="" onValueChange={(value) => add(free[Number(value)])}>
      <SelectTrigger size="sm" aria-label="선언 물성 추가" className="h-7 w-40 text-xs">
        <Plus className="size-3.5" />
        <SelectValue placeholder="선언 물성 추가" />
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

          <ErrorNotice error={items.error ?? error} className="mb-3" />

          {known.length === 0 && !items.loading && (
            <p className="text-muted-foreground rounded-md border border-dashed p-3 text-xs">
              {level}에 넣을 수 있는 물성 항목이 없습니다. 기준정보의 <b>물성 항목</b> 축에
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
                            {shown(point.value)} {row.measure}
                            {point.temperature !== '' && (
                              <span className="text-muted-foreground">
                                {' @ '}
                                {shown(point.temperature)} °C
                              </span>
                            )}
                          </div>
                        ))}
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
          <ErrorNotice error={items.error ?? error} />
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
            return (
              <div key={row.item} className="grid grid-cols-12 items-end gap-2">
            <div className="col-span-12 flex justify-end">
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive"
                title={`${row.item} 줄을 지웁니다`}
                onClick={() => {
                  setDirty(true)
                  setEditing(null)
                  setRows((current) => current.filter((_, at) => at !== index))
                }}
              >
                <Trash2 className="size-4" />
                이 항목 지우기
              </Button>
            </div>

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
                값 {row.points.length > 1 && `(온도 ${row.points.length}점)`}
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
                    <span className="text-muted-foreground text-xs">{row.measure}</span>
                    <span className="text-muted-foreground text-xs">@</span>
                    <Input
                      aria-label={
                        row.points.length > 1
                          ? `${row.item} 온도 ${spot + 1}`
                          : `${row.item} 온도`
                      }
                      className="w-28 shrink-0"
                      value={point.temperature}
                      inputMode="decimal"
                      placeholder={row.points.length > 1 ? '필수' : '비우면 상온'}
                      onChange={(event) =>
                        editPoint(index, spot, { temperature: event.target.value })
                      }
                    />
                    <span className="text-muted-foreground text-xs">℃</span>
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
                        ? { ...one, points: [...one.points, { value: '', temperature: '' }] }
                        : one
                    )
                  )
                }}
              >
                <Plus className="size-3.5" />
                온도 추가
              </Button>
              {row.points.length > 1 && (
                // **온도 없는 점이 섞이면 서버가 거절한다.** 누르기 전에
                // 알려 주는 편이 낫다.
                <p className="text-muted-foreground mt-1 text-[11px]">
                  값이 여럿이면 각각 어느 온도의 것인지 적어야 합니다. 표 밖에서는 솔버가
                  끝값을 유지합니다.
                </p>
              )}
            </div>

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
          <DialogFooter>
            {/* **닫기가 곧 버리기다.** 그러니 그렇게 적는다 — 「닫기」 만 있으면
                고친 것이 남는지 사라지는지 눌러 보고서야 안다. */}
            <Button variant="ghost" onClick={cancel} disabled={saving}>
              취소
            </Button>
            <Button
              onClick={async () => {
                await save()
                setSnapshot(null)
                setEditing(null)
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
