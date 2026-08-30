/**
 * 점탄성 — 겹치고, 계수를 맞추고, 근거를 본다.
 *
 * ## 이 화면이 답해야 하는 것
 *
 * "이 재료의 점탄성 계수는 얼마인가" 하나로 보이지만 실제로는 셋이다.
 *
 *   1. **어느 온도로 겹쳤나** — 마스터커브는 기준 온도 하나에서만 유효하다
 *   2. **그 모델이 이 재료에 맞나** — 맞춘 이동인자와 실제로 겹쳐 본 값이
 *      벌어지면 WLF 가 이 온도 범위에 안 맞는다는 뜻이다
 *   3. **몇 항이 맞나** — 항을 늘리면 잔차는 언제나 준다. 그래서 후보를 나란히
 *      본다(경화식 맞춰 보기와 같은 판단)
 *
 * 셋을 다 보여 주지 않으면 사람은 마지막 숫자만 베껴 간다.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { CurveChart } from '@/modules/tests/CurveChart'
import { viscoelasticApi } from '@/modules/viscoelastic/api'
import type {
  ImportableCurve,
  MasterCurve,
  MasterCurvePoints,
  PronyCandidate,
  PronyFit,
  Sweep,
} from '@/modules/viscoelastic/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { ViscoelasticCardDialog } from '@/modules/viscoelastic/ViscoelasticCardDialog'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { display, formatScalar, fromDisplay } from '@/shared/units'
import { useResource } from '@/shared/hooks/useResource'

/** 맞춘 값이 관측값과 이만큼 벌어지면 눈에 띄게 표시한다(로그 자릿수). */
const DRIFT_LIMIT = 0.5

const METHODS = [
  { key: 'wlf', label: 'WLF', hint: '유리 전이 위. 고분자에서 가장 흔하다' },
  { key: 'arrhenius', label: 'Arrhenius', hint: '유리 전이 아래처럼 WLF 가 안 맞는 구간' },
  { key: 'manual', label: '장비 값', hint: '장비가 계산해 준 이동인자를 그대로 쓴다' },
] as const

type Method = (typeof METHODS)[number]['key']

/**
 * 온도·탄성률을 사람이 읽는 글자로. **환산은 표가 한다.**
 *
 * 전에는 이 파일이 `kelvin - 273.15` 와 `value / 1e6` 을 손으로 적고 있었다.
 * `formatScalar` 의 머리말이 「같은 코드가 세 번 복제돼 있었다」 고 적어 두고
 * 그것을 모았는데, **여기가 네 번째였다** — 모으는 자리에 안 들어와 있었다.
 *
 * 표 바깥에 환산이 하나라도 남으면 표를 바꾼 날 그 자리만 옛 값을 낸다.
 */
function celsius(kelvin: number): string {
  return formatScalar(kelvin, 'K', 'temperature')
}

function si(value: number): string {
  return Number.isFinite(value) ? formatScalar(value, 'Pa') : '—'
}

/**
 * 단계 머리 — **순서가 있다는 것을 화면이 말한다.**
 *
 * 블록 셋을 세로로 이어 놨을 뿐이라 겹치기 → 맞추기 → 카드가 순서라는 것이 안
 * 보였다. 장비 파일 정의가 `①②③` 로 같은 일을 한다 — 화면 언어를 맞춘다.
 */
function Step({ n, title, done }: { n: string; title: string; done?: boolean }) {
  return (
    <h2 className="mb-1 flex items-center gap-2 font-medium">
      <span className="text-muted-foreground">{n}</span>
      {title}
      {/* **끝난 것에만 표시한다.** 「안 함」 배지를 달면 아직 할 필요가 없는
          단계까지 미완으로 보여 재촉하는 화면이 된다. */}
      {done && (
        <Badge variant="secondary" className="text-xs">
          됨
        </Badge>
      )}
    </h2>
  )
}

export function ViscoelasticPanel({ testRunId }: { testRunId: string }) {
  const sweeps = useResource(() => viscoelasticApi.sweeps(testRunId), [testRunId])
  const [curves, setCurves] = useState<MasterCurve[]>([])
  const [selected, setSelected] = useState<MasterCurve | null>(null)
  const [method, setMethod] = useState<Method>('wlf')
  const [reference, setReference] = useState<number | null>(null)
  const [manual, setManual] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const reload = useCallback(async () => {
    const found = await viscoelasticApi.masterCurves(testRunId)
    setCurves(found)
    setSelected((current) => found.find((item) => item.id === current?.id) ?? found[0] ?? null)
  }, [testRunId])

  useEffect(() => {
    void reload().catch((caught: unknown) =>
      setError(caught instanceof Error ? caught : new Error('불러오지 못했습니다.'))
    )
  }, [reload])

  // **기준 온도의 기본값은 가장 높은 온도다.** 실무에서 상온이나 사용 온도를
  // 기준으로 잡는 일이 많은데, 그 자리에 있을 확률이 가장 높다.
  const options = useMemo(() => sweeps.data?.items ?? [], [sweeps.data])
  useEffect(() => {
    if (reference === null && options.length) {
      setReference(Math.max(...options.map((item) => item.temperature_k)))
    }
  }, [options, reference])

  async function makePrimary(curve: MasterCurve) {
    setError(null)
    try {
      await viscoelasticApi.setPrimary(curve.id)
      await reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('대표를 옮기지 못했습니다.'))
    }
  }

  async function build() {
    if (reference === null) return
    setBusy(true)
    setError(null)
    try {
      const created = await viscoelasticApi.createMasterCurve(testRunId, {
        reference_temperature_k: reference,
        method,
        manual_shifts: method === 'manual' ? manualShifts(options, reference, manual) : undefined,
      })
      await reload()
      // **방금 만든 것을 보여 준다.** 안 그러면 이미 고른 곡선이 그대로 남아,
      // 눌렀는데 버튼 하나 늘어난 것 말고는 아무 일도 안 일어난 것처럼 보인다.
      setSelected(created)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('겹치지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-6">
      <ErrorNotice error={sweeps.error ?? error} />

      {/* **인장과 무엇이 대응하는지 적는다.** 같은 구조에 다른 이름이 붙어 있는데
          그 사실이 어디에도 없어서, 「점탄성은 왜 채택이 없나」 가 반복됐다. */}
      <p className="text-muted-foreground rounded-md border p-3 text-sm">
        온도를 <b>가로질러</b> 겹친 것이 여기 삽니다. 인장의 <b>「채택」 자리에 있는 것이
        마스터커브</b>이고 — 이 시험의 대표 곡선입니다 — <b>카드로 만들어야</b> CAE 덱에
        나갑니다. 「결과」 탭의 값(Tg 등)과는 <b>선행 관계가 없습니다.</b>
      </p>

      <div>
        <Step n="①" title="겹치기" done={curves.length > 0} />
        <p className="text-muted-foreground mb-3 text-sm">
          한 온도에서는 좁은 주파수 창만 잽니다. 온도를 바꿔 잰 것을 밀어 겹치면 훨씬 넓은 곡선이
          됩니다 — <strong>그 곡선은 고른 기준 온도에서만 유효합니다.</strong>
        </p>

        {/* **왜 버튼이 꺼져 있는지 말한다.** 온도 한 단만 잰 DMA 도 있고, 그때
            겹치기는 할 수 있는 일이 아니다 — 꺼진 버튼만 두면 고장으로 읽힌다. */}
        {!sweeps.loading && options.length < 2 && (
          <p className="text-muted-foreground mb-3 rounded-md border p-4 text-sm">
            {options.length === 0
              ? '겹칠 스윕이 없습니다. 저장 탄성률과 온도가 있는 곡선이 필요합니다.'
              : '온도가 한 단뿐이라 겹칠 것이 없습니다. 마스터커브는 온도가 다른 스윕이 둘 이상 있어야 만들 수 있습니다.'}
          </p>
        )}

        {sweeps.data?.warnings.length ? (
          <ul className="text-muted-foreground mb-3 space-y-0.5 text-xs">
            {sweeps.data.warnings.map((note) => (
              <li key={note}>· {note}</li>
            ))}
          </ul>
        ) : null}

        <div className="mb-3 space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Label className="w-20 shrink-0 text-xs">기준 온도</Label>
            {/* **잰 온도만 보여 준다.** 입력칸에 숫자를 치게 두면 없는 온도를
                적고 나서 오류를 본다 — 서버가 거절하는 것이 맞지만, 고를 수
                없는 것을 고르게 두는 화면이 먼저 잘못이다. */}
            {options.map((item) => (
              <Button
                key={item.curve_key}
                size="sm"
                variant={reference === item.temperature_k ? 'default' : 'outline'}
                className="h-7 text-xs"
                onClick={() => setReference(item.temperature_k)}
              >
                {celsius(item.temperature_k)}
              </Button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <Label className="w-20 shrink-0 text-xs">방법</Label>
            {METHODS.map((item) => (
              <Button
                key={item.key}
                size="sm"
                variant={method === item.key ? 'default' : 'outline'}
                className="h-7 text-xs"
                title={item.hint}
                onClick={() => setMethod(item.key)}
              >
                {item.label}
              </Button>
            ))}
            <Button
              size="sm"
              className="ml-auto h-7 text-xs"
              disabled={busy || reference === null || options.length < 2}
              onClick={() => void build()}
            >
              겹치기
            </Button>
          </div>

          {method === 'manual' && reference !== null && (
            <ManualShifts
              options={options}
              reference={reference}
              values={manual}
              onChange={setManual}
            />
          )}
        </div>

        {curves.length > 1 && (
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <Label className="w-20 shrink-0 text-xs">만든 것</Label>
              {/* **고치지 않고 새로 만든다.** 기준 온도를 바꾼 곡선이 둘 다 남아야
                  어느 계수가 어디서 나왔는지 되짚을 수 있다(ADR 0007). */}
              {curves.map((item) => (
                <Button
                  key={item.id}
                  size="sm"
                  variant={selected?.id === item.id ? 'secondary' : 'ghost'}
                  className="h-7 text-xs"
                  onClick={() => setSelected(item)}
                >
                  {celsius(item.reference_temperature_k)} · {item.method}
                  {item.is_primary && (
                    <Badge variant="secondary" className="ml-1 text-[10px]">
                      대표
                    </Badge>
                  )}
                </Button>
              ))}
            </div>
            {/* **재료로 나가는 것은 대표 하나다.** 전에는 「가장 최근 것」 이 말없이
                쓰였다 — 하나 더 만든 순간 재료 쪽 계산이 바뀌는데 그 전환이 화면
                어디에도 없었다. 처리 결과의 「채택」 과 같은 자리다. */}
            <p className="text-muted-foreground pl-20 text-xs">
              재료의 <b>글로벌 피팅</b>은 <b>대표</b> 하나를 읽습니다.
              {selected && !selected.is_primary && (
                <>
                  {' '}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => void makePrimary(selected)}
                  >
                    고른 것을 대표로
                  </button>
                </>
              )}
            </p>
          </div>
        )}
      </div>

      <FromEquipment
        testRunId={testRunId}
        onImported={(made) => {
          void reload()
          setSelected(made)
        }}
      />

      {selected && <MasterCurveView curve={selected} />}
    </section>
  )
}

/**
 * **장비가 이미 겹쳐 준 곡선**을 마스터커브로 등록한다.
 *
 * TA TRIOS 같은 장비는 시간-온도 중첩을 제 소프트웨어에서 하고 마스터커브를 함께
 * 내보낸다. 장비 파일 정의가 그 표를 「장비가 계산해 준 표」 로 읽어 두지만,
 * **그것만으로는 Prony 도 글로벌 피팅도 못 썼다** — `MasterCurve` 행이 아니라서다.
 * 만드는 길이 「온도별 스윕을 겹친다」 하나뿐이었고, 그런 파일에는 겹칠 원본이
 * 아예 없는 일도 많다.
 *
 * ## 왜 못 쓰는 표까지 보이나
 *
 * `derived` 에는 마스터커브만 오는 것이 아니다 — 이동인자 표(`TTS - shift
 * factors`)가 같은 칸에 들어온다. 걸러 버리면 「내 파일에 있는 그 표가 왜 안
 * 보이지」 가 되고, 그냥 두면 골라 놓고 나서야 거절을 본다. **둘 다 보이되 왜 못
 * 쓰는지 적는다.**
 *
 * ## 기준 온도는 사람이 적는다
 *
 * 표 이름에 있는 일이 많지만 장비마다 다르다. 짐작해 채우면 **틀린 온도의 곡선이
 * 조용히 다른 온도의 해석에 쓰인다** — 그래서 이름에서 읽은 숫자는 힌트로만 보이고
 * 칸은 비워 둔다.
 *
 * 아무것도 없으면 이 블록 자체가 안 뜬다. 장비가 계산해 준 표가 없는 시험이
 * 대부분이고, 늘 보이면 「이건 뭐지」 가 하나 는다.
 */
function FromEquipment({
  testRunId,
  onImported,
}: {
  testRunId: string
  onImported: (made: MasterCurve) => void
}) {
  const found = useResource(() => viscoelasticApi.importableCurves(testRunId), [testRunId])
  const [picked, setPicked] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<Error | null>(null)

  const items = useMemo(() => found.data ?? [], [found.data])
  const usable = useMemo(() => items.filter((one) => one.usable), [items])

  // **하나뿐이면 골라 둔다.** 고를 것이 없는데 고르라고 두면 한 번 더 눌러야 한다.
  useEffect(() => {
    if (picked === null && usable.length === 1) setPicked(usable[0].curve_key)
  }, [picked, usable])

  if (items.length === 0) return null

  const unit = display('K', 'temperature').unit
  const typed = Number(text)
  const ready = picked !== null && text.trim() !== '' && Number.isFinite(typed)

  async function run() {
    if (picked === null || !ready) return
    setBusy(true)
    setFailed(null)
    try {
      const made = await viscoelasticApi.importMasterCurve(testRunId, {
        curve_key: picked,
        reference_temperature_k: fromDisplay(typed, 'K', 'temperature'),
      })
      onImported(made)
      setText('')
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('가져오지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div aria-label="장비가 만든 마스터커브">
      <Step n="①" title="장비가 만든 마스터커브 가져오기 (겹치기 대신)" />
      <p className="text-muted-foreground mb-3 text-sm">
        장비가 제 소프트웨어에서 겹쳐 준 곡선을 그대로 받습니다.{' '}
        <strong>다시 겹치지 않습니다</strong> — 장비가 쓴 이동인자를 이 시스템은 모르고, 다시
        겹치면 다른 곡선이 나오는데 둘 다 그럴듯합니다.
      </p>

      <ErrorNotice error={found.error ?? failed} />

      <div className="space-y-1">
        {items.map((one) => (
          <ImportRow
            key={one.curve_key}
            curve={one}
            chosen={picked === one.curve_key}
            onChoose={() => setPicked(one.curve_key)}
          />
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Label className="w-20 shrink-0 text-xs" htmlFor="imported-reference">
          기준 온도
        </Label>
        {/* **사람이 적는다.** 짐작해 채우면 틀린 온도가 그대로 굳는다. */}
        <Input
          id="imported-reference"
          className="h-7 w-28 text-xs"
          value={text}
          placeholder={unit}
          onChange={(event) => setText(event.target.value)}
        />
        <span className="text-muted-foreground text-xs">{unit}</span>
        <Button
          size="sm"
          className="ml-auto h-7 text-xs"
          disabled={busy || !ready}
          onClick={() => void run()}
        >
          {busy ? '가져오는 중…' : '가져오기'}
        </Button>
      </div>
      {picked !== null && !ready && (
        <p className="text-muted-foreground mt-1 text-xs">
          이 곡선이 어느 온도의 것인지 적어야 등록합니다. 표 이름이나 시험 보고서에 있습니다.
        </p>
      )}
    </div>
  )
}

/** 표 이름에 적힌 온도. `TTS - master curve (20.0 °C)` 같은 것을 찾는다. */
const NAMED_TEMPERATURE = /(-?\d+(?:\.\d+)?)\s*°?\s*C\b/

function ImportRow({
  curve,
  chosen,
  onChoose,
}: {
  curve: ImportableCurve
  chosen: boolean
  onChoose: () => void
}) {
  const name = curve.label ?? curve.curve_key
  const hinted = NAMED_TEMPERATURE.exec(name)?.[1] ?? null

  return (
    <button
      type="button"
      aria-label={`${name} 고르기`}
      disabled={!curve.usable}
      onClick={onChoose}
      className={`w-full rounded-md border p-2 text-left text-xs disabled:opacity-60 ${
        chosen ? 'border-primary bg-muted/50' : ''
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono">{name}</span>
        <span className="text-muted-foreground">{curve.row_count}점</span>
        {/* **이름에서 읽은 숫자는 힌트일 뿐이다.** 자동으로 채우면 장비가 다른
            뜻으로 적은 숫자가 기준 온도로 굳는다. */}
        {curve.usable && hinted !== null && (
          <span className="text-muted-foreground">이름에 적힌 온도: {hinted}</span>
        )}
      </div>
      {/* **왜 못 쓰는지 적는다.** 이동인자 표가 같은 칸에 들어온다. */}
      {curve.note && <p className="text-muted-foreground mt-0.5">{curve.note}</p>}
    </button>
  )
}

/**
 * 장비가 준 이동인자를 받는 칸.
 *
 * **비워 두면 0 으로 보낸다** — 0 은 "안 민다" 는 뜻이라 그 온도의 스윕이 기준
 * 자리에 그대로 겹친다. 결과를 보면 안 채웠다는 것이 바로 보인다. 그럴듯한
 * 값을 대신 지어 넣는 것보다 이 편이 낫다.
 *
 * 기준 온도는 정의상 log a_T = 0 이라 고칠 수 없게 잠근다.
 */
function ManualShifts({
  options,
  reference,
  values,
  onChange,
}: {
  options: Sweep[]
  reference: number
  values: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  const ordered = [...options].sort((a, b) => a.temperature_k - b.temperature_k)
  return (
    <div className="flex flex-wrap items-start gap-1.5">
      <Label className="mt-1.5 w-20 shrink-0 text-xs">log a_T</Label>
      <div className="flex flex-wrap gap-2">
        {ordered.map((item) => {
          const key = String(item.temperature_k)
          const isReference = item.temperature_k === reference
          return (
            <div key={item.curve_key} className="w-24">
              <Input
                aria-label={`${celsius(item.temperature_k)} log a_T`}
                inputMode="decimal"
                className="h-7 text-xs"
                value={isReference ? '0' : (values[key] ?? '')}
                disabled={isReference}
                onChange={(event) => onChange({ ...values, [key]: event.target.value })}
              />
              <p className="text-muted-foreground mt-0.5 text-center text-xs">
                {celsius(item.temperature_k)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** 입력칸의 문자열을 서버가 받는 모양(온도 문자열 → 숫자)으로. */
function manualShifts(
  options: Sweep[],
  reference: number,
  values: Record<string, string>
): Record<string, number> {
  const shifts: Record<string, number> = {}
  for (const item of options) {
    const key = String(item.temperature_k)
    const raw = (item.temperature_k === reference ? '0' : (values[key] ?? '')).trim()
    const parsed = Number(raw)
    shifts[key] = raw === '' || !Number.isFinite(parsed) ? 0 : parsed
  }
  return shifts
}

function MasterCurveView({ curve }: { curve: MasterCurve }) {
  const points = useResource<MasterCurvePoints>(() => viscoelasticApi.points(curve.id), [curve.id])
  const [fits, setFits] = useState<PronyFit[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const reload = useCallback(async () => {
    setFits(await viscoelasticApi.pronyFits(curve.id))
  }, [curve.id])

  useEffect(() => {
    void reload().catch(() => setFits([]))
  }, [reload])

  async function fit(terms?: number) {
    setBusy(true)
    setError(null)
    try {
      await viscoelasticApi.fitProny(curve.id, terms ? { terms } : {})
      await reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('맞추지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const chart = useMemo<[number, number][]>(() => {
    const frequency = points.data?.frequency ?? []
    const storage = points.data?.storage_modulus ?? []
    const pairs: [number, number][] = []
    frequency.forEach((x, index) => {
      const y = storage[index]
      // 로그 축에는 0 과 음수의 자리가 없다. 서버는 빈 칸을 null 로 보낸다.
      if (x != null && y != null && x > 0 && y > 0) pairs.push([x, y])
    })
    return pairs
  }, [points.data])

  const latest = fits[0]

  return (
    /**
     * **곡선을 오른쪽에 두고 숫자를 왼쪽에 둔다** — 곡선 탭·처리 탭과 같은 4:6 이다.
     * 세로로 이어 붙이면 곡선이 화면 하나를 통째로 먹고, 이동인자와 Prony 후보를
     * 보려면 곡선이 화면 밖으로 나간다 — **둘을 견주는 것이 이 화면의 일인데** 그
     * 둘을 동시에 못 본다.
     */
    <div className="grid gap-6 2xl:grid-cols-[minmax(0,4fr)_minmax(0,6fr)] 2xl:items-start">
      {/* 곡선은 DOM 에서 먼저 둔다 — 좁은 화면에서는 곡선부터 보는 것이 맞다. */}
      <div className="min-w-0 2xl:sticky 2xl:top-4 2xl:order-2">
        {/* 축이 둘 다 로그다. 선형으로 그리면 점 대부분이 왼쪽 끝에 뭉친다. */}
        <CurveChart
          points={chart}
          xLabel="환산 주파수 (Hz)"
          yLabel="저장 탄성률 (Pa)"
          logX
          logY
          height={320}
        />
      </div>

      <div className="min-w-0 space-y-6 2xl:order-1">
        <div>
          <div className="mb-2 flex flex-wrap items-baseline gap-2">
            <h3 className="font-medium">마스터커브</h3>
            <span className="text-muted-foreground text-xs">
              {celsius(curve.reference_temperature_k)} 기준 · {curve.method} ·{' '}
              {curve.minimum_frequency_hz.toExponential(2)} ~{' '}
              {curve.maximum_frequency_hz.toExponential(2)} Hz
            </span>
            {Object.entries(curve.parameters).map(([key, value]) => (
              <Badge key={key} variant="outline" className="text-xs">
                {key} {Number(value).toPrecision(4)}
              </Badge>
            ))}
          </div>

          {curve.notes.length > 0 && (
            <ul className="text-muted-foreground space-y-0.5 text-xs">
              {curve.notes.map((note) => (
                <li key={note}>· {note}</li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="mb-1 font-medium">이동인자</h3>
          <p className="text-muted-foreground mb-2 text-sm">
            <strong>맞춘 값과 실제로 겹쳐 본 값을 나란히 봅니다.</strong> 둘이 벌어지면 그 모델이 이
            재료·이 온도 범위에 안 맞는다는 뜻이고, 그 판단은 사람이 합니다.
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>온도</TableHead>
                <TableHead className="text-right">log a_T (맞춤)</TableHead>
                <TableHead className="text-right">log a_T (관측)</TableHead>
                <TableHead className="text-right">차이</TableHead>
                <TableHead>출처</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {curve.shifts.map((shift) => {
                const drift = shift.residual ?? null
                const loud = drift !== null && Math.abs(drift) > DRIFT_LIMIT
                return (
                  <TableRow key={shift.temperature_k}>
                    <TableCell>{celsius(shift.temperature_k)}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {shift.log10_a_t.toFixed(3)}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-right font-mono tabular-nums">
                      {shift.observed_log10_a_t?.toFixed(3) ?? '—'}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono tabular-nums ${loud ? 'text-destructive font-medium' : 'text-muted-foreground'}`}
                    >
                      {drift === null ? '—' : `${drift > 0 ? '+' : ''}${drift.toFixed(3)}`}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">{shift.source}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>

        <div>
          <div className="mb-1 flex items-center gap-2">
            <h3 className="flex items-center gap-2 font-medium">
              <span className="text-muted-foreground">②</span>
              Prony 계수 맞추기
              {latest && (
                <Badge variant="secondary" className="text-xs">
                  됨
                </Badge>
              )}
            </h3>
            <Button
              size="sm"
              className="ml-auto h-7 text-xs"
              disabled={busy}
              onClick={() => void fit()}
            >
              맞추기
            </Button>
          </div>
          <p className="text-muted-foreground mb-2 text-sm">
            항을 늘리면 잔차는 <strong>언제나</strong> 줄어듭니다 — 그래서 후보를 나란히 두고 BIC 로
            고릅니다. 고른 것이 마음에 안 들면 항 수를 직접 정하세요.
          </p>

          <ErrorNotice error={error} className="mb-2" />

          {latest ? (
            <PronyView
              fit={latest}
              busy={busy}
              onPick={(terms) => void fit(terms)}
              // **기준 온도가 이름에 든다.** 같은 재료의 카드가 여럿이면 어느
              // 온도의 것인지가 이름에서 보여야 한다.
              cardLabel={`점탄성 ${celsius(curve.reference_temperature_k)}`}
            />
          ) : (
            <p className="text-muted-foreground rounded-md border p-6 text-center text-sm">
              아직 맞춘 계수가 없습니다.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function PronyView({
  fit,
  busy,
  onPick,
  cardLabel,
}: {
  fit: PronyFit
  busy: boolean
  onPick: (terms: number) => void
  /** 카드 이름의 첫 제안. 재료·시편에서 온다. */
  cardLabel: string
}) {
  const best = fit.terms.length
  const [making, setMaking] = useState(false)
  const [made, setMade] = useState(false)
  return (
    <div className="space-y-3">
      {making && (
        <ViscoelasticCardDialog
          fit={fit}
          suggestedLabel={cardLabel}
          onClose={() => setMaking(false)}
          onDone={() => {
            setMaking(false)
            setMade(true)
          }}
        />
      )}
      {fit.at_bound.length > 0 && (
        <p className="text-destructive text-sm">
          완화시간 {fit.at_bound.map((value) => value.toExponential(2)).join(', ')} 초가 관측 범위
          경계에 붙었습니다 — <strong>데이터가 정하지 못한 값입니다.</strong> 그 계수는 관측 밖을
          외삽하고 있습니다.
        </p>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>항 수</TableHead>
            <TableHead className="text-right">BIC</TableHead>
            <TableHead className="text-right">잔차</TableHead>
            <TableHead className="text-right">순간 탄성률</TableHead>
            <TableHead className="text-right">평형 탄성률</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...fit.candidates]
            .sort((a, b) => a.term_count - b.term_count)
            .map((item: PronyCandidate) => (
              <TableRow
                key={item.term_count}
                className={item.term_count === best ? 'bg-muted/40' : ''}
              >
                <TableCell className="font-medium">
                  {item.term_count}
                  {item.term_count === best && (
                    <Badge variant="secondary" className="ml-1.5 text-xs">
                      고름
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {item.bic.toFixed(1)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {item.normalized_rmse.toExponential(2)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {si(item.instantaneous_pa)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {si(item.equilibrium_pa)}
                </TableCell>
                <TableCell className="text-right">
                  {item.term_count !== best && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-xs"
                      disabled={busy}
                      onClick={() => onPick(item.term_count)}
                    >
                      이걸로
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
        </TableBody>
      </Table>

      <div>
        <p className="mb-1 text-sm font-medium">고른 계수 ({best}항)</p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>완화시간 (s)</TableHead>
              <TableHead className="text-right">탄성률</TableHead>
              <TableHead className="text-right">g = E/E₀</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {fit.terms.map((term) => (
              <TableRow key={term.relaxation_time_s}>
                <TableCell className="font-mono tabular-nums">
                  {term.relaxation_time_s.toExponential(3)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {si(term.modulus_pa)}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {(term.modulus_pa / fit.instantaneous_pa).toFixed(4)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="text-muted-foreground mt-1 text-xs">
          Abaqus <code>*VISCOELASTIC, TIME=PRONY</code> 는 마지막 칸(g)을 받습니다.
        </p>
      </div>

      {/* **계수만으로는 해석에 못 들어간다.** 여기서 카드가 되어야 덱이 나온다 —
          형식은 진작 있었는데 거기로 가는 길이 없었다. */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground text-sm">③</span>
        <Button size="sm" onClick={() => setMaking(true)} disabled={busy}>
          이 계수로 물성 카드 만들기
        </Button>
        {made ? (
          <span className="text-muted-foreground text-xs">
            만들었습니다 — 재료 상세의 「CAE 카드」 에서 덱을 받습니다.
          </span>
        ) : (
          // **여기가 끝점이다.** 계수는 카드가 되어야 나가고, 시편 여럿을 한 벌로
          // 묶는 것은 이 자리가 아니라 재료의 글로벌 피팅이다.
          <span className="text-muted-foreground text-xs">
            카드가 되어야 덱이 나갑니다. 시편 여럿을 한 벌로 묶으려면 재료 화면의{' '}
            <b>글로벌 피팅</b> 을 쓰세요.
          </span>
        )}
      </div>
    </div>
  )
}
