/**
 * 처리 패널 — 단계를 쌓고, **저장 전에** 결과를 보고, 근거와 함께 저장한다.
 *
 * ## 왜 미리보기가 먼저인가
 *
 * 처리가 잘못되면 곡선이 조용히 이상해진다. 오류가 아니라 **그럴듯한 다른
 * 곡선**이 나오고, 그것으로 적합한 물성이 그대로 해석에 들어간다. 형식
 * 프로파일에서 같은 판단을 했다(ADR 0005) — 저장하기 전에 돌려 볼 수 있어야 한다.
 *
 * ## 왜 근거를 값 옆에 붙이는가
 *
 * "탄성계수 205 GPa" 만 있으면 반년 뒤 그 값을 설명할 수 없다. 어느 구간의 몇
 * 점을 무슨 방법으로 쟀는지가 함께 있어야 한다. 서버가 단계마다 `notes` 를
 * 만들어 주므로 화면은 **버리지 않고 보여 주기만** 하면 된다.
 *
 * ## 폼을 여기서 그리지 않는다
 *
 * 입력 칸은 서버의 `ParamSpec` 에서 온다. 목록을 여기에 적으면 계산을 추가할
 * 때 두 곳을 고쳐야 하고, 그러면 한 곳을 빠뜨린다 — 새 물성 하나가 파일 2~3개로
 * 끝나야 한다는 원칙(D7)이 프론트에서 깨지는 자리가 정확히 여기다.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  BookMarked,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  Link2,
  Play,
  Plus,
  Save,
  Trash2,
} from 'lucide-react'

import { CurveChart } from '@/modules/tests/CurveChart'
import {
  REFERENCE_FOR,
  isReference,
  isUsed,
  processingApi,
  referenceLabel,
} from '@/modules/processing/api'
import type {
  ProcessingPreview,
  ProcessingStep,
  RecipeStep,
  StepParam,
} from '@/modules/processing/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Badge } from '@/shared/components/ui/badge'
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
import { display } from '@/modules/tests/units'
import { useResource } from '@/shared/hooks/useResource'

interface Props {
  testRunId: string
  testTypeKey: string
  curveKey: string | null
  /** 원본 곡선의 채널 키. 기준 열을 고를 때 쓴다. */
  sourceColumns: string[]
  /** 관리자인 부서. 비어 있으면 '레시피로 저장' 을 감춘다 — 서버가 거절한다. */
  managedWorkspaces?: { slug: string; name: string }[]
}

/**
 * 인장을 처음 여는 사람이 바로 돌려 볼 수 있는 순서.
 *
 * **기본값을 두는 이유:** 빈 화면에서 단계를 하나씩 고르라고 하면, 무엇을 어떤
 * 순서로 놓아야 하는지 아는 사람만 쓸 수 있다. 정렬이 왜 필요한지는 보간이
 * 정렬을 전제한다는 것을 알아야 나오는 판단이다.
 *
 * 치수는 `@` 참조로 둔다 — 시편 기록에 있으면 그대로 돌고, 없으면 "시편 기록에
 * 그 값이 있는지 확인하세요" 로 실패한다. 0 을 채워 조용히 틀리는 것보다 낫다.
 */
const TENSILE_STARTER: RecipeStep[] = [
  {
    plugin: 'tensile.engineering',
    options: { gauge_length: '@specimen_gauge_length', area: '@specimen_area' },
  },
  {
    plugin: 'curve.sort_unique',
    options: { x: 'strain_engineering', duplicate_policy: 'mean' },
  },
  {
    plugin: 'tensile.elastic_modulus',
    options: { method: 'linear_regression', minimum_strain: 0.0005, maximum_strain: 0.0025 },
  },
  {
    plugin: 'tensile.proof_stress',
    options: { youngs_modulus: '@youngs_modulus', offset_strain: 0.002 },
  },
  { plugin: 'tensile.strength', options: {} },
  { plugin: 'tensile.necking_candidate', options: {} },
]

/** `ParamSpec` 의 기본값. 화면과 서버가 같은 값을 보게 하는 유일한 출처다. */
function defaults(plugin: ProcessingStep | undefined): Record<string, unknown> {
  const options: Record<string, unknown> = {}
  for (const param of plugin?.params ?? []) {
    if (param.default !== null && param.default !== undefined) options[param.name] = param.default
  }
  return options
}

function formatScalar(value: number, unit: string): string {
  if (unit === 'Pa') {
    return Math.abs(value) >= 1e9
      ? `${(value / 1e9).toPrecision(4)} GPa`
      : `${(value / 1e6).toPrecision(4)} MPa`
  }
  if (unit === '1') return Number(value.toPrecision(5)).toString()
  return `${Number(value.toPrecision(5))} ${unit}`
}

export function ProcessingPanel({
  testRunId,
  testTypeKey,
  curveKey,
  sourceColumns,
  managedWorkspaces = [],
}: Props) {
  const catalog = useResource(() => processingApi.steps(testTypeKey), [testTypeKey])
  const [steps, setSteps] = useState<RecipeStep[]>([])
  const [result, setResult] = useState<ProcessingPreview | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [axes, setAxes] = useState<{ x: string; y: string }>({
    x: 'strain_engineering',
    y: 'stress_engineering',
  })
  const [open, setOpen] = useState<number | null>(null)
  const [savingRecipe, setSavingRecipe] = useState(false)

  const available = catalog.data ?? []
  const byId = useMemo(
    () => new Map(available.map((step) => [step.id, step])),
    [available]
  )

  useEffect(() => {
    // 인장이면 바로 돌려 볼 수 있는 순서를 깔아 둔다. 다른 종류는 빈 상태에서
    // 시작한다 — 아직 그 종류의 표준 순서를 우리가 모른다.
    //
    // **기본값은 여기서 채운다.** 서버도 생략된 옵션에 기본값을 쓰지만, 화면이
    // 빈 칸을 보여 주면 사람은 "설정 안 됨" 으로 읽는다. 실제로 '변위 열' 이
    // '열을 고르세요' 로 비어 보였는데 서버는 displacement 로 잘 돌고 있었다 —
    // 화면과 서버가 서로 다른 것을 아는 상태다.
    if (!available.length) return
    setSteps(
      testTypeKey === 'tensile'
        ? TENSILE_STARTER.map((step) => ({
            ...step,
            options: { ...defaults(byId.get(step.plugin)), ...step.options },
          }))
        : []
    )
    setResult(null)
    setSaved(null)
  }, [testTypeKey, curveKey, available.length, byId])

  async function run(): Promise<ProcessingPreview | null> {
    setBusy(true)
    setError(null)
    setSaved(null)
    setNotice(null)
    try {
      const preview = await processingApi.preview(
        { test_run_id: testRunId, source_curve_key: curveKey, steps },
        axes
      )
      setResult(preview)
      return preview
    } catch (caught) {
      setResult(null)
      setError(caught instanceof Error ? caught : new Error('처리하지 못했습니다.'))
      return null
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const stored = await processingApi.save({
        test_run_id: testRunId,
        source_curve_key: curveKey,
        steps,
      })
      setSaved(stored.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function update(index: number, options: Record<string, unknown>) {
    setSteps((current) =>
      current.map((step, at) => (at === index ? { ...step, options } : step))
    )
    // 옵션을 바꾸면 앞의 결과는 더 이상 그 옵션의 결과가 아니다. 남겨 두면
    // 사람이 바뀐 값의 결과라고 읽는다.
    setResult(null)
    setSaved(null)
  }

  function move(index: number, delta: number) {
    const target = index + delta
    if (target < 0 || target >= steps.length) return
    setSteps((current) => {
      const next = [...current]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
    setResult(null)
  }

  const columns = result ? result.columns : sourceColumns

  return (
    <section className="mb-8">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">처리</h2>
        <span className="text-muted-foreground text-xs">
          장비가 준 것은 변위·하중입니다. 물성이 되려면 변환이 필요합니다.
        </span>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" onClick={run} disabled={busy || !steps.length}>
            <Play className="size-3.5" />
            돌려 보기
          </Button>
          <Button size="sm" onClick={save} disabled={busy || !result}>
            <Save className="size-3.5" />
            결과 저장
          </Button>
          {/* **레시피가 없으면 배치를 걸 수 없다.** 한 건으로 단계를 맞춘 뒤
              나머지 20건에 같은 것을 거는 것이 실제 작업 흐름인데, 그 '같은 것'
              에 이름을 붙일 자리가 여기 말고 없었다 — 레시피 테이블은 있는데
              화면에서 만들 길이 없었다. */}
          {managedWorkspaces.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setSavingRecipe(true)}
              disabled={busy || !steps.length}
            >
              <BookMarked className="size-3.5" />
              레시피로 저장
            </Button>
          )}
        </div>
      </div>

      <ErrorNotice error={catalog.error ?? error} className="mb-3" />

      {/* **막다른 길을 만들지 않는다.** 일괄 등록으로 만든 시편은 치수가 비어
          있는 것이 정상이라 이 실패는 자주 난다. 서버 메시지는 "시편 기록을
          확인하세요" 인데, 이 화면에서 갈 곳이 없으면 사람은 멈춘다. */}
      {error && /specimen_/.test(error.message) && (
        <div className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
          <b>시편에 치수가 없습니다.</b> 두 가지 중 하나를 하세요 — 시편 기록에
          게이지 길이·폭·두께를 채우거나, 아래 칸의 <b>직접 입력</b>을 눌러 이번만
          숫자를 넣으세요. <span className="text-muted-foreground">
            치수를 0 이나 기본값으로 채우지 않는 이유: 단면적이 틀리면 응력 자릿수가
            통째로 어긋나는데 숫자는 그럴듯해 보입니다.
          </span>
        </div>
      )}

      {savingRecipe && (
        <SaveRecipeDialog
          steps={steps}
          testTypeKey={testTypeKey}
          workspaces={managedWorkspaces}
          onClose={() => setSavingRecipe(false)}
          onSaved={(label) => {
            setSavingRecipe(false)
            setNotice(`레시피 '${label}' 로 저장했습니다 — 시험 목록에서 여러 건에 걸 수 있습니다.`)
          }}
        />
      )}

      {(saved || notice) && (
        <div className="mb-3 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
          {notice ?? (
            <>
              결과를 저장했습니다. <b>저장된 결과는 바뀌지 않습니다</b> — 단계를 고쳐
              다시 저장하면 새 결과가 생기고, 예전 결과는 그때의 단계를 그대로 갖고
              있습니다. <b>결과</b> 탭에서 채택하면 이 시험의 물성이 됩니다.
            </>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <div className="space-y-2">
          {steps.length === 0 && (
            <p className="text-muted-foreground rounded-md border py-8 text-center text-xs">
              <FlaskConical className="mx-auto mb-2 size-5 opacity-50" />
              단계를 더해 주세요.
            </p>
          )}

          {steps.map((step, index) => {
            const plugin = byId.get(step.plugin)
            const stage = result?.stages[index]
            return (
              <div key={`${step.plugin}-${index}`} className="rounded-md border">
                <div className="flex items-center gap-2 border-b px-3 py-2">
                  <span className="text-muted-foreground font-mono text-xs">{index + 1}</span>
                  <span className="text-sm font-medium">{plugin?.label ?? step.plugin}</span>
                  {!plugin && (
                    <Badge variant="destructive" className="text-xs">
                      등록되지 않음
                    </Badge>
                  )}
                  <div className="ml-auto flex gap-0.5">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      onClick={() => move(index, -1)}
                      disabled={index === 0}
                      aria-label="위로"
                    >
                      <ChevronUp className="size-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      onClick={() => move(index, 1)}
                      disabled={index === steps.length - 1}
                      aria-label="아래로"
                    >
                      <ChevronDown className="size-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      onClick={() => {
                        setSteps((current) => current.filter((_, at) => at !== index))
                        setResult(null)
                      }}
                      aria-label="지우기"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>

                <div className="space-y-2 px-3 py-2">
                  {(plugin?.params ?? []).map((param) => (
                    <ParamField
                      key={param.name}
                      param={param}
                      value={step.options[param.name]}
                      columns={columns}
                      /* **안 쓰는 칸은 잠근다.** 탄성계수를 구간으로 재는데
                         '직접 입력' 이 살아 있으면, 거기 넣은 숫자가 무시된다는
                         것을 알 방법이 없다 — 값을 넣었는데 아무 일도 안
                         일어나는 것이 가장 나쁘다. 지우지 않고 잠그는 이유는
                         그 칸이 있다는 것 자체가 정보이기 때문이다. */
                      disabled={!isUsed(param, step.options)}
                      onChange={(value) =>
                        update(index, { ...step.options, [param.name]: value })
                      }
                    />
                  ))}

                  {/* **근거는 접어 두되 버리지 않는다.** 값 옆에 없으면 반년 뒤
                      그 값을 설명할 수 없다. */}
                  {stage && stage.notes.length > 0 && (
                    <div className="pt-1">
                      <button
                        type="button"
                        className="text-muted-foreground text-xs underline-offset-2 hover:underline"
                        onClick={() => setOpen(open === index ? null : index)}
                      >
                        근거 {stage.notes.length}줄 {open === index ? '접기' : '보기'} ·{' '}
                        {stage.row_count.toLocaleString('ko-KR')}행
                      </button>
                      {open === index && (
                        <ul className="text-muted-foreground mt-1 space-y-1 text-xs">
                          {stage.notes.map((note) => (
                            <li key={note} className="border-l-2 pl-2">
                              {note}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}

          <AddStep
            available={available}
            onAdd={(id) => {
              setSteps((current) => [...current, { plugin: id, options: defaults(byId.get(id)) }])
              setResult(null)
            }}
          />
        </div>

        <div>
          {result ? (
            <>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                {(['x', 'y'] as const).map((axis) => (
                  <div key={axis} className="flex items-center gap-1">
                    <span className="text-muted-foreground text-xs">{axis}</span>
                    <Select
                      value={axes[axis]}
                      onValueChange={(value) => {
                        const next = { ...axes, [axis]: value }
                        setAxes(next)
                        void processingApi
                          .preview(
                            { test_run_id: testRunId, source_curve_key: curveKey, steps },
                            next
                          )
                          .then(setResult)
                          .catch(() => undefined)
                      }}
                    >
                      <SelectTrigger className="h-8 w-48" aria-label={`${axis}축`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {result.columns.map((column) => (
                          <SelectItem key={column} value={column}>
                            {column}
                            {result.units[column] && result.units[column] !== '1'
                              ? ` (${result.units[column]})`
                              : ''}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
                <span className="text-muted-foreground ml-auto text-xs">
                  {result.source_row_count.toLocaleString('ko-KR')}행 →{' '}
                  {result.row_count.toLocaleString('ko-KR')}행
                </span>
              </div>

              <CurveChart
                points={result.points}
                xLabel={`${axes.x}${
                  result.units[axes.x] && result.units[axes.x] !== '1'
                    ? ` (${result.units[axes.x]})`
                    : ''
                }`}
                yLabel={`${axes.y}${
                  result.units[axes.y] && result.units[axes.y] !== '1'
                    ? ` (${result.units[axes.y]})`
                    : ''
                }`}
                height={300}
              />

              {result.scalars.length > 0 && (
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {result.scalars.map((scalar) => (
                    <div key={scalar.key} className="rounded-md border px-3 py-2">
                      <div className="text-muted-foreground text-xs">{scalar.label}</div>
                      <div className="font-mono text-sm">
                        {formatScalar(scalar.value, scalar.si_unit)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="text-muted-foreground rounded-md border py-16 text-center text-sm">
              <Play className="mx-auto mb-2 size-5 opacity-50" />
              아직 돌리지 않았습니다.
              <p className="mx-auto mt-2 max-w-sm text-xs">
                <b>돌려 보기</b>는 아무것도 저장하지 않습니다. 처리가 잘못되면 곡선이
                오류 없이 그럴듯한 다른 모양이 되는데, 저장한 뒤에는 찾기 어렵습니다.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function AddStep({
  available,
  onAdd,
}: {
  available: ProcessingStep[]
  onAdd: (id: string) => void
}) {
  return (
    <Select value="" onValueChange={onAdd}>
      <SelectTrigger className="h-9 w-full" aria-label="단계 더하기">
        <span className="text-muted-foreground flex items-center gap-1.5 text-sm">
          <Plus className="size-3.5" />
          단계 더하기
        </span>
      </SelectTrigger>
      <SelectContent>
        {available.map((step) => (
          <SelectItem key={step.id} value={step.id}>
            {step.label}
            <span className="text-muted-foreground ml-2 font-mono text-xs">{step.id}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/**
 * 입력 칸 하나. **서버의 `ParamSpec` 이 모양을 정한다.**
 *
 * 참조(`@…`)를 값과 같은 칸에서 다루는 이유: 사람은 "게이지 길이" 하나를 정할
 * 뿐이고, 그것이 시편에서 오는지 손으로 넣는지가 다른 개념일 이유가 없다.
 */
function ParamField({
  param,
  value,
  columns,
  disabled = false,
  onChange,
}: {
  param: StepParam
  value: unknown
  columns: string[]
  disabled?: boolean
  onChange: (value: unknown) => void
}) {
  const referenced = isReference(value)

  /**
   * **저장은 SI, 화면은 실무 단위.** CAE 는 길이를 mm 로 쓴다 — `0.05` 를 치라고
   * 하면 사람이 `50` 을 치고, 그러면 1000배 틀린 곡선이 조용히 나온다. 재료
   * 화면의 시편 폼은 이미 mm 로 받고 있어서 앱 안에서 단위가 갈려 있기도 했다.
   *
   * 환산표는 `modules/tests/units` 하나뿐이다 — 곡선 축도 같은 것을 쓴다.
   */
  const shown = display(param.unit, param.dimension)
  const numeric = param.type === 'float' || param.type === 'int'
  /** 잠금은 **세 갈래 모두**에 붙는다. 숫자 칸에만 붙이면, 조건이 걸린 칸이
   *  나중에 choice 로 바뀌었을 때 조용히 안 잠긴다. */
  const rowClass = `grid grid-cols-[9rem_1fr] gap-2 ${
    disabled ? 'pointer-events-none opacity-40' : ''
  }`
  const toSi = (value: number) => value / shown.factor
  const fromSi = (value: number) => value * shown.factor

  /** 타이핑 중인 글자. 확정된 값과 나눠 두지 않으면 소수점이 지워진다. */
  const [draft, setDraft] = useState<string | null>(null)
  const text =
    draft ??
    (value === null || value === undefined
      ? ''
      : numeric
        ? String(Number((fromSi(Number(value))).toPrecision(12)))
        : String(value))

  if (param.type === 'choice') {
    return (
      <div className={`${rowClass} items-center`} aria-disabled={disabled || undefined}>
        <Label className="text-xs">{param.label}</Label>
        <Select value={String(value ?? '')} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger className="h-8" aria-label={param.label}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {param.choices.map((choice) => (
              <SelectItem key={choice} value={choice}>
                {choice}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }

  // 열 이름을 받는 칸(`x`·`column`·`strain`·`stress`)은 자유 입력보다 목록이 낫다 —
  // 오타 하나가 '열이 없습니다' 로 끝나고, 어떤 이름이 있는지는 화면만 안다.
  const isColumn = ['x', 'column', 'strain', 'stress', 'displacement', 'force'].includes(
    param.name
  )
  if (isColumn && columns.length) {
    return (
      <div className={`${rowClass} items-center`} aria-disabled={disabled || undefined}>
        <Label className="text-xs">{param.label}</Label>
        <Select value={String(value ?? '')} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger className="h-8" aria-label={param.label}>
            <SelectValue placeholder="열을 고르세요" />
          </SelectTrigger>
          <SelectContent>
            {columns.map((column) => (
              <SelectItem key={column} value={column}>
                {column}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }

  // **칸마다 최대 하나다.** 단위로 고르면 '게이지 길이' 에 폭·두께까지 붙는다.
  const reference = REFERENCE_FOR[param.name]

  return (
    <div className={`${rowClass} items-start`} aria-disabled={disabled || undefined}>
      <Label className="pt-1.5 text-xs">
        {param.label}
        {shown.unit && <span className="text-muted-foreground ml-1">({shown.unit})</span>}
      </Label>
      <div className="space-y-1">
        {referenced ? (
          <div className="flex items-center gap-2">
            {/* 원문(`@specimen_gauge_length`)을 그대로 보이면 사람은 이게
                무엇인지 코드를 읽어야 안다. */}
            <Badge variant="secondary" className="gap-1 text-xs">
              <Link2 className="size-3" />
              {referenceLabel(String(value))}
            </Badge>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => onChange(param.default ?? null)}
            >
              직접 넣기
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            {/* **`type="number"` 를 쓰지 않는다.** 값이 상태에 매여 있는데
                `Number("0.")` 이 `0` 이라, 소수점을 찍는 순간 되돌아가 지워졌다 —
                12.12 를 칠 수가 없었다. 글자는 그대로 두고 숫자로 읽히는
                동안에만 위로 올린다. */}
            <Input
              className="h-8"
              inputMode={numeric ? 'decimal' : 'text'}
              value={text}
              onChange={(event) => {
                const raw = event.target.value
                setDraft(raw)
                if (raw === '' || raw === '-') return onChange(null)
                if (!numeric) return onChange(raw)
                const parsed = Number(raw)
                // '0.' · '1e' 처럼 아직 숫자가 아닌 중간 상태는 올리지 않는다.
                if (Number.isFinite(parsed)) onChange(toSi(parsed))
              }}
              onBlur={() => setDraft(null)}
              aria-label={param.label}
            />
            {reference && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 shrink-0 text-xs"
                title={`${reference.label} 을 그때그때 가져다 씁니다. 손으로 옮겨 적으면 원본이 바뀌었을 때 어긋납니다.`}
                onClick={() => onChange(`@${reference.key}`)}
              >
                <Link2 className="size-3" />
                {reference.label}
              </Button>
            )}
          </div>
        )}
        {param.help && <p className="text-muted-foreground text-xs">{param.help}</p>}
      </div>
    </div>
  )
}

/**
 * 지금 단계를 레시피로 저장한다.
 *
 * **레시피 없이는 배치를 걸 수 없다.** 한 건으로 단계를 맞춘 뒤 나머지 20건에
 * 같은 것을 거는 것이 실제 작업 흐름인데, 그 '같은 것' 에 이름을 붙이는 자리가
 * 여기 말고 없었다 — 레시피 테이블은 진작 있었는데 화면에서 만들 길이 없었다.
 */
function SaveRecipeDialog({
  steps,
  testTypeKey,
  workspaces,
  onClose,
  onSaved,
}: {
  steps: RecipeStep[]
  testTypeKey: string
  workspaces: { slug: string; name: string }[]
  onClose: () => void
  onSaved: (label: string) => void
}) {
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [owner, setOwner] = useState(workspaces[0]?.slug ?? '')
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await processingApi.createRecipe({
        key,
        label,
        description: null,
        test_type_key: testTypeKey,
        steps: steps as unknown as Record<string, never>[],
        is_active: true,
        owner_workspace_slug: owner || null,
      })
      onSaved(label)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>레시피로 저장</DialogTitle>
          <DialogDescription>
            지금 {steps.length}단계를 이름 붙여 저장합니다. 저장하면 시험 목록에서 여러
            건을 골라 한 번에 걸 수 있습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="recipe-key">키</Label>
            <Input
              id="recipe-key"
              value={key}
              placeholder="tensile_standard"
              onChange={(event) =>
                setKey(event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))
              }
            />
            <p className="text-muted-foreground text-xs">
              소문자·숫자·밑줄. <b>부서 안에서만 유일하면 됩니다</b> — 같은 인장이라도
              부서마다 따르는 규격이 다르므로, 다른 부서가 같은 이름을 써도 됩니다.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="recipe-label">이름</Label>
            <Input
              id="recipe-label"
              value={label}
              placeholder="인장 표준 (사내규격)"
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="recipe-owner">누구 것</Label>
            <Select value={owner} onValueChange={setOwner}>
              <SelectTrigger id="recipe-owner">
                <SelectValue placeholder="부서를 고르세요" />
              </SelectTrigger>
              <SelectContent>
                {workspaces.map((workspace) => (
                  <SelectItem key={workspace.slug} value={workspace.slug}>
                    {workspace.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={save} disabled={busy || !key || !label || !owner}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
