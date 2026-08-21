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
  Circle,
  CircleCheck,
  Link2,
  Lock,
  Play,
  Plus,
  Save,
} from 'lucide-react'

import { RecipePicker } from '@/modules/processing/RecipePicker'
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
import { missingSteps } from '@/modules/processing/gaps'
import {
  blockersAt,
  columnsAt,
  flowRows,
  stepSummary,
  insertionIndex,
  outOfOrder,
  vocabularyOf,
} from '@/modules/processing/flow'
import type { Blocker } from '@/modules/processing/flow'
import { testsApi } from '@/modules/tests/api'
import {
  axisLabel,
  display,
  formatScalar,
  fromDisplay,
  toDisplay,
} from '@/shared/units'
import { RightPanel } from '@/shared/layout/RightPanel'
import { useResource } from '@/shared/hooks/useResource'

interface Props {
  testRunId: string
  testTypeKey: string
  curveKey: string | null
  /** 원본 곡선의 채널 키. 기준 열을 고를 때 쓴다. */
  sourceColumns: string[]
  /**
   * 그 채널의 이름·단위. **변수 목록이 `displacement` 를 '변위 (m)' 로 읽게
   * 하려면 필요하다** — 키만 보여 주면 무엇인지 코드를 읽어야 안다.
   */
  sourceChannels?: { key: string; label: string; si_unit: string }[]
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

export function ProcessingPanel({
  testRunId,
  testTypeKey,
  curveKey,
  sourceColumns,
  sourceChannels = [],
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
  /**
   * 펴 둔 단계들. **하나만 펴지게 하지 않는다.**
   *
   * 처음에는 아코디언(한 번에 하나)이었다. 세로 길이는 줄었는데 "무엇으로
   * 설정됐지" 를 확인하려면 **하나하나 열어 봐야** 했다. 그건 접어 둔 뜻이
   * 없다 — 접기는 길이를 줄이려던 것이지 정보를 숨기려던 것이 아니다.
   *
   * 그래서 접힌 줄이 설정을 한 줄로 보여 주고(`stepSummary`), 펴는 것은 **고칠
   * 때**만 한다. 여럿을 나란히 펴 두고 견주는 것도 사람이 정한다.
   */
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set())

  function toggleOpen(index: number) {
    setOpen((current) => {
      const next = new Set(current)
      if (!next.delete(index)) next.add(index)
      return next
    })
  }
  const [savingRecipe, setSavingRecipe] = useState(false)
  /**
   * '돌려 보기' 를 눌러 본 적이 있는가.
   *
   * **누르기 전에는 조용히 있는다.** 단계를 쌓는 동안 아직 안 채운 칸이 붉게
   * 물들어 있으면 그건 경고가 아니라 배경이 되고, 진짜 문제가 났을 때 눈에
   * 안 띈다.
   */
  const [attempted, setAttempted] = useState(false)

  /**
   * 저장한 레시피를 다시 불러온다.
   *
   * **저장만 되고 불러올 수가 없었다.** 배치에는 걸 수 있었지만, 한 건을 열어
   * "지난번 그 순서로 다시" 를 할 방법이 없어서 매번 단계를 처음부터 쌓아야
   * 했다. 저장하는 이유의 절반이 그것인데 빠져 있었다.
   */
  const recipes = useResource(() => processingApi.recipes(testTypeKey), [testTypeKey])

  /**
   * 장비 파일이 준 시편 치수.
   *
   * **파일이 이미 갖고 있다.** Zwick 은 `a0`(두께)·`b0`(폭)을, TA DMA 는
   * `specimen_width`·`specimen_thickness` 를 적어 보낸다. 그런데 자동으로
   * 시편에 넣지 않는 규칙 때문에("사람이 잰 값을 파일이 조용히 바꾸면 안 된다")
   * **채우는 길 자체가 없었다** — 시편 41개 중 치수가 있는 것이 3개뿐이었고,
   * 그래서 처리가 첫 단계에서 막혔다. 덮어쓰기는 여전히 안 한다. 빈 칸만 채운다.
   */
  const dimensions = useResource(() => testsApi.instrumentDimensions(testRunId), [testRunId])
  /** 시편에 아직 없는 것 중 — 파일이 줄 수 있는 것과, 사람이 넣어야 하는 것. */
  const missing = (dimensions.data?.items ?? []).filter((item) => item.current_m === null)
  const fillable = missing.filter((item) => item.value_m !== null)
  const byHand = missing.filter((item) => item.value_m === null)

  async function fill() {
    setError(null)
    try {
      await testsApi.applyInstrumentDimensions(testRunId)
      dimensions.reload()
      await run()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('채우지 못했습니다.'))
    }
  }

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
    // 누른 순간부터 부족한 곳을 붉게 짚는다.
    setAttempted(true)
    if (!steps.length) return null
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
    // 고치는 중에는 짚어 둔 것을 거둔다 — 방금 채운 칸이 계속 붉으면 고쳐도
    // 안 고쳐진 것처럼 보인다. 다시 누르면 다시 본다.
    setAttempted(false)
    // 옵션을 바꾸면 앞의 결과는 더 이상 그 옵션의 결과가 아니다. 남겨 두면
    // 사람이 바뀐 값의 결과라고 읽는다.
    setResult(null)
    setSaved(null)
  }

  /**
   * 순서도에서 켜고 끈다.
   *
   * **끝에 붙이지 않는다.** 탄성계수를 나중에 켰을 때 항복강도 뒤로 가면
   * `@youngs_modulus` 가 안 풀린다 — 자리는 계산이 선언한 `order` 가 안다.
   */
  function toggle(pluginId: string) {
    setResult(null)
    setSaved(null)
    setSteps((current) => {
      if (current.some((step) => step.plugin === pluginId)) {
        return current.filter((step) => step.plugin !== pluginId)
      }
      const at = insertionIndex(current, pluginId, byId)
      const added = { plugin: pluginId, options: defaults(byId.get(pluginId)) }
      return [...current.slice(0, at), added, ...current.slice(at)]
    })
  }

  /** 아직 안 켠 단계를 켜면 돌 수 있는가. 못 돌면 그 이유를 미리 보여 준다. */
  function ifAdded(pluginId: string): Blocker[] {
    const at = insertionIndex(steps, pluginId, byId)
    const next = [
      ...steps.slice(0, at),
      { plugin: pluginId, options: defaults(byId.get(pluginId)) },
      ...steps.slice(at),
    ]
    return blockersAt(next[at], at, next, sourceColumns, byId)
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

  /**
   * **각 단계가 시작될 때 프레임에 있는 열.** 돌려 보기 전에도 안다.
   *
   * 전에는 `result ? result.columns : sourceColumns` 였다. 장비가 준 것은
   * 변위·하중·폭뿐이라, 한 번 돌려 보기 전에는 인장강도 단계의 '변형률 열'
   * 목록이 비어 있었다 — **돌려 보려면 골라야 하고 고르려면 돌려 봐야 하는**
   * 자리였다. 이제 계산이 선언한 `makes_columns` 를 접어서 계산한다.
   */
  const columnsFor = (index: number) => columnsAt(steps, index, sourceColumns, byId)

  /** 지금 구성에서 못 도는 단계와 그 이유. **막지 않고 말한다.** */
  const stepBlockers = useMemo(
    () => steps.map((step, index) => blockersAt(step, index, steps, sourceColumns, byId)),
    [steps, sourceColumns, byId]
  )
  /**
   * 못 돌 것 같은 단계들. **막는 데 쓰지 않는다.**
   *
   * 전에는 이걸로 '돌려 보기' 를 잠갔다. 그런데 **회색 버튼은 이유를 말할
   * 자리가 없다** — 무엇을 고쳐야 하는지 모른 채로 멈춘다. 게다가 이 판정은
   * 계산이 선언한 것에 기댄 추론이라, 선언이 실제와 어긋나면 사람을 가둔다.
   *
   * 그래서 지금은 **누르게 두고, 누르면 어디가 부족한지 가리킨다.** 서버에도
   * 그대로 보낸다 — 우리 추론이 틀렸으면 그냥 돌아가는 것이 맞다.
   */
  const troubled = useMemo(
    () =>
      stepBlockers
        .map((list, index) => ({ index, list }))
        .filter((item) => item.list.length > 0),
    [stepBlockers]
  )
  const scrambled = useMemo(() => outOfOrder(steps, byId), [steps, byId])

  /** 순서도의 줄. 켠 것은 도는 순서대로, 안 켠 것은 켜면 들어갈 자리에. */
  const rows = useMemo(() => flowRows(steps, byId, available), [steps, byId, available])

  /** 지금 구성이 쓰는 이름 전부 — 원본 채널과 각 단계가 만드는 열·값. */
  const vocabulary = useMemo(() => {
    const known = new Map(sourceChannels.map((item) => [item.key, item]))
    const source = sourceColumns.map(
      (key) => known.get(key) ?? { key, label: key, si_unit: '1' }
    )
    return vocabularyOf(steps, source, byId)
  }, [steps, sourceColumns, sourceChannels, byId])

  /**
   * 열 이름 → 그 이름의 뜻. **고르는 자리에서 바로 읽게 한다.**
   *
   * 뜻이 필요한 순간은 목록을 여는 때가 아니라 **열을 고르는 그 순간**이다.
   * 그때 시선은 화면 가운데에 있지 오른쪽 끝에 있지 않다.
   */
  const columnInfo = useMemo(
    () => new Map(vocabulary.columns.map((item) => [item.key, item])),
    [vocabulary]
  )

  /** 지금 구성으로 못 하게 되는 일. 인장에만 뜻이 있다. */
  const gaps = useMemo(
    () => (testTypeKey === 'tensile' ? missingSteps(steps.map((step) => step.plugin)) : []),
    [testTypeKey, steps]
  )

  /** 축과 점을 **같은 단위로** 맞춘다. 하나만 바꾸면 1000배 어긋난 그림이 된다. */
  const shownPoints = useMemo<[number, number][]>(
    () =>
      (result?.points ?? []).map(([x, y]) => [
        toDisplay(x, result?.units[axes.x]),
        toDisplay(y, result?.units[axes.y]),
      ]),
    [result, axes.x, axes.y]
  )

  return (
    <section className="mb-8">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="font-medium">처리</h2>
        <span className="text-muted-foreground text-xs">
          장비가 준 것은 변위·하중입니다. 물성이 되려면 변환이 필요합니다.
        </span>
        <div className="ml-auto flex gap-2">
          {(recipes.data?.length ?? 0) > 0 && (
            /* **드롭다운으로는 못 버틴다.** 레시피는 부서마다·규격마다 쌓이고,
               스무 개만 넘어가도 이름만 늘어놓은 목록에서는 못 찾는다. */
            <RecipePicker
              recipes={recipes.data ?? []}
              action
              className="h-8 w-44 text-sm"
              placeholder="레시피 불러오기"
              ariaLabel="레시피 불러오기"
              onSelect={(recipe) => {
                setSteps((recipe.steps as unknown as RecipeStep[]).map((s) => ({ ...s })))
                setResult(null)
                setSaved(null)
                setNotice(`'${recipe.label}' 을 불러왔습니다. 돌려 보고 저장하세요.`)
              }}
            />
          )}
          {/* **잠그지 않는다.** 회색 버튼은 무엇을 고쳐야 하는지 말할 자리가
              없다 — 누르면 부족한 곳을 짚는다. */}
          <Button size="sm" variant="outline" onClick={run} disabled={busy}>
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
          <p>
            <b>시편 치수가 모자랍니다.</b> 0 이나 기본값으로 채우지 않는 이유는,
            단면적이 틀리면 응력 자릿수가 통째로 어긋나는데 숫자는 그럴듯해
            보이기 때문입니다.
          </p>
          {/* **장비가 이미 준 값이 있으면 그걸 쓴다.** 파일에 폭·두께가 들어
              있는데 사람이 다시 재어 넣게 하는 것은 일이다. */}
          {fillable.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span>이 파일이 준 값:</span>
              {fillable.map((item) => (
                <Badge key={item.field} variant="outline" className="font-mono text-xs">
                  {item.label} {formatScalar(item.value_m ?? 0, 'm')}
                </Badge>
              ))}
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={fill}>
                시편에 채우기
              </Button>
            </div>
          )}
          {/* **파일에 없는 것은 없다고 말한다.** 게이지 길이는 시험기 설정값이라
              적히지 않는 것이 보통인데, 그 말을 안 하면 사람은 '채우기' 를 누르고
              아무 일도 안 일어나는 것을 보게 된다. */}
          {/* 이름 뒤에 조사를 붙이지 않는다 — '게이지 길이 은' 이 된다. 한국어
              조사는 앞말의 받침을 봐야 해서, 이름이 바뀔 때마다 틀린다. */}
          {byHand.length > 0 && (
            <p className="mt-2">
              이 파일에 없는 것: <b>{byHand.map((item) => item.label).join(', ')}</b>{' '}
              — 시험기 설정값이라 사람이 넣어야 합니다. 재료 상세의 시편 기록에
              넣거나, 아래 칸의 <b>직접 넣기</b>로 이번만 쓰세요.
            </p>
          )}
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
            recipes.reload()
            setNotice(
              `레시피 '${label}' 로 저장했습니다 — 시험 목록에서 여러 건에 걸 수 있고, ` +
                `여기서 '레시피 불러오기' 로 다시 꺼낼 수 있습니다.`
            )
          }}
        />
      )}

      {/* **눌렀는데 못 돌 때, 어디를 고쳐야 하는지 여기서 짚는다.**
          전에는 버튼이 그냥 회색이었다 — 회색은 이유를 말할 자리가 없다. */}
      {attempted && troubled.length > 0 && (
        <div className="border-destructive/40 bg-destructive/5 mb-3 rounded-md border p-3 text-sm">
          <p className="mb-1.5">
            <b>아직 못 도는 단계가 {troubled.length}개 있습니다.</b> 서버에도 보냈으니
            그대로 돌아갈 수도 있습니다 — 아래가 화면이 짚은 곳입니다.
          </p>
          <ul className="space-y-1">
            {troubled.map(({ index, list }) => (
              <li key={index} className="flex flex-wrap items-baseline gap-x-1.5">
                <button
                  type="button"
                  className="underline underline-offset-2"
                  onClick={() => {
                    document
                      .getElementById(`step-${index}`)
                      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                  }}
                >
                  {index + 1}단계 {byId.get(steps[index].plugin)?.label ?? steps[index].plugin}
                </button>
                <span className="text-muted-foreground text-xs">
                  {list.map((item) => item.reason).join(' ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {attempted && !steps.length && (
        <div className="border-destructive/40 bg-destructive/5 mb-3 rounded-md border p-3 text-sm">
          <b>켠 단계가 없습니다.</b> 왼쪽 순서도에서 「공칭 응력-변형률」부터 켜세요 —
          장비가 준 것은 변위·하중이라 그 단계가 응력·변형률을 만듭니다.
        </div>
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

      {/* **순서도와 단계가 한 칸이다.** 나눠 두면 같은 목록이 두 칸에 있게
          되고, 가운데만 세로로 길어져 곡선 쪽이 텅 빈다. */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="space-y-2">
          {/* **막지 않는다. 미리 말할 뿐이다.** 공칭까지만 필요한 작업도 정상이다.
              다만 그 사실을 CAE 카드 탭에서 알게 되면 20건을 다시 처리해야 한다 —
              결과는 불변이라 열을 나중에 덧붙일 수 없다. */}
          {steps.length > 0 && gaps.length > 0 && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2.5 text-xs">
              <p className="mb-1 font-medium">이 단계 구성으로는 나중에 할 수 없는 것</p>
              <ul className="space-y-1">
                {gaps.map((gap) => (
                  <li key={gap.plugin} className="text-muted-foreground">
                    <b>{gap.label}</b> 단계가 없습니다 — {gap.lost}.
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="divide-y overflow-hidden rounded-md border">
            <div className="bg-muted/40 flex items-center gap-2 px-2 py-1">
              <p className="text-muted-foreground text-xs">
                위에서 아래로 흐릅니다. <b>켠 것만 돕니다.</b>
              </p>
              {steps.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto h-6 text-xs"
                  onClick={() =>
                    setOpen((current) =>
                      current.size === steps.length
                        ? new Set()
                        : new Set(steps.map((_, index) => index))
                    )
                  }
                >
                  {open.size === steps.length ? '모두 접기' : '모두 펴기'}
                </Button>
              )}
            </div>

            {rows.map((row) => {
              if (row.kind === 'available') {
                const blockers = ifAdded(row.plugin.id)
                const needsFirst = blockers.filter((item) => item.fixedBy)
                const locked = needsFirst.length > 0
                return (
                  <button
                    key={`off-${row.plugin.id}`}
                    type="button"
                    disabled={locked}
                    aria-pressed={false}
                    onClick={() => toggle(row.plugin.id)}
                    className={`flex w-full items-start gap-2 px-2 py-1.5 text-left ${
                      locked ? 'cursor-not-allowed opacity-45' : 'hover:bg-accent/50'
                    }`}
                  >
                    {locked ? (
                      <Lock className="mt-0.5 size-4 shrink-0" />
                    ) : (
                      <Circle className="text-muted-foreground mt-0.5 size-4 shrink-0" />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="text-muted-foreground text-sm">{row.plugin.label}</span>
                      {locked && (
                        <span className="text-muted-foreground mt-0.5 block text-xs">
                          {needsFirst[0].reason}
                        </span>
                      )}
                    </span>
                  </button>
                )
              }

              const { step, index, plugin } = row
              const stage = result?.stages[index]
              const trouble = stepBlockers[index] ?? []
              const isOpen = open.has(index)
              const summary = stepSummary(step, byId)
              return (
                /* **덜 채운 단계는 늘 붉다.** 돌려 보기를 누를 때까지
                   기다리면, 스무 줄을 다 훑고 나서야 어디가 빈지 안다. */
                <div
                  key={`${step.plugin}-${index}`}
                  id={`step-${index}`}
                  className={
                    trouble.length
                      ? `border-destructive border-l-2 ${attempted ? 'bg-destructive/5' : ''}`
                      : ''
                  }
                >
                  <div className="flex items-center gap-2 px-2 py-1.5">
                    <button
                      type="button"
                      aria-pressed
                      aria-label={`${plugin?.label ?? step.plugin} 끄기`}
                      onClick={() => toggle(step.plugin)}
                      className="shrink-0"
                    >
                      <CircleCheck className="text-primary size-4" />
                    </button>
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() => toggleOpen(index)}
                      className="flex min-w-0 flex-1 items-start gap-2 text-left"
                    >
                      <span className="text-muted-foreground mt-0.5 w-3 shrink-0 text-xs tabular-nums">
                        {index + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <span className="truncate text-sm font-medium">
                            {plugin?.label ?? step.plugin}
                          </span>
                          {trouble.length > 0 && (
                            <Badge variant="destructive" className="shrink-0 text-xs">
                              덜 채움
                            </Badge>
                          )}
                          {!plugin && (
                            <Badge variant="destructive" className="shrink-0 text-xs">
                              등록되지 않음
                            </Badge>
                          )}
                        </span>
                        {/* **접힌 줄이 무엇으로 설정됐는지 말한다.** 안 그러면
                            확인하려고 하나하나 열어 봐야 한다. */}
                        {!isOpen &&
                          (trouble.length > 0 ? (
                            /* 빈 줄 대신 **무엇이 없는지**를 적는다. 붉기만 하면
                               열어 봐야 안다. */
                            <span className="text-destructive block truncate text-xs">
                              {trouble[0].reason}
                            </span>
                          ) : (
                            summary && (
                              <span className="text-muted-foreground block truncate text-xs">
                                {summary}
                              </span>
                            )
                          ))}
                      </span>
                      <ChevronDown
                        className={`text-muted-foreground mt-0.5 size-3.5 shrink-0 transition-transform ${
                          isOpen ? 'rotate-180' : ''
                        }`}
                      />
                    </button>
                  </div>

                  {/* **한 번에 하나만 펴진다.** 여섯 단계의 입력칸이 동시에 쌓이면
                      스무 개가 넘고, 그러면 아무것도 안 보인다. */}
                  {isOpen && (
                    <div className="space-y-2 border-t px-2 py-2">
                      {trouble.length > 0 && (
                        <ul className="border-destructive/40 bg-destructive/5 space-y-0.5 rounded-md border p-2 text-xs">
                          {trouble.map((item) => (
                            <li key={item.reason}>
                              {item.reason}
                              {item.fixedBy && (
                                <>
                                  {' '}
                                  <b>{byId.get(item.fixedBy)?.label ?? item.fixedBy}</b> 단계를
                                  먼저 켜세요.
                                </>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}

                      {(plugin?.params ?? []).map((param) => (
                        <ParamField
                          key={param.name}
                          param={param}
                          value={step.options[param.name]}
                          columns={columnsFor(index)}
                          columnInfo={columnInfo}
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
                        <ul className="text-muted-foreground space-y-1 text-xs">
                          {stage.notes.map((note) => (
                            <li key={note} className="border-l-2 pl-2">
                              {note}
                            </li>
                          ))}
                        </ul>
                      )}

                      <div className="flex gap-0.5 pt-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          onClick={() => move(index, -1)}
                          disabled={index === 0}
                        >
                          <ChevronUp className="size-3.5" />
                          위로
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-xs"
                          onClick={() => move(index, 1)}
                          disabled={index === steps.length - 1}
                        >
                          <ChevronDown className="size-3.5" />
                          아래로
                        </Button>
                        {/* 같은 단계를 두 번 쓰는 자리 — 구간을 두 번 자르거나
                            열 둘을 따로 평활하는 경우가 있다. */}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="ml-auto h-7 text-xs"
                          onClick={() => {
                            setSteps((current) => [
                              ...current.slice(0, index + 1),
                              { plugin: step.plugin, options: { ...step.options } },
                              ...current.slice(index + 1),
                            ])
                            setResult(null)
                            setAttempted(false)
                          }}
                        >
                          <Plus className="size-3.5" />
                          한 번 더
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* 손으로 위아래로 옮기면 권장 순서와 어긋날 수 있다. 막지 않는다 —
              그렇게 해야 하는 경우가 있다(진소성변형률을 자른 뒤 다시 정렬). */}
          {scrambled && (
            <p className="text-muted-foreground text-xs">
              단계 순서를 손으로 바꿨습니다. 번호가 실제로 도는 순서입니다.
            </p>
          )}
        </div>

        {/* 좁은 화면에서는 한 칸이라 그림이 단계 밑으로 접힌다. */}
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

              {/* **원본 탭과 같은 단위로 그린다.** 여기만 SI 그대로였다 —
                  같은 곡선이 '원본' 에서는 MPa, '처리' 에서는 Pa 로 보였다.
                  틀린 그림은 아니지만, 두 탭을 오가며 보는 사람은 축이 왜
                  1e8 이 됐는지 먼저 의심하게 된다. */}
              <CurveChart
                points={shownPoints}
                xLabel={axisLabel(axes.x, result.units[axes.x])}
                yLabel={axisLabel(axes.y, result.units[axes.y])}
                height={300}
              />

              {result.scalars.length > 0 && (
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {result.scalars.map((scalar) => (
                    <div key={scalar.key} className="rounded-md border px-3 py-2">
                      <div className="text-muted-foreground text-xs">{scalar.label}</div>
                      <div className="font-mono text-sm">
                        {formatScalar(scalar.value, scalar.si_unit, scalar.dimension)}
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

      {/* **화면 오른쪽 끝에 붙는다.** 이 안(`mx-auto max-w-7xl`)에 두면 본문과
          함께 가운데로 딸려 들어가고 오른쪽 끝에는 여백만 남는다. */}
      {/* **여닫기는 상단 바가 한다.** 화면 오른쪽 끝의 흐린 세로 띠는 아무도
          못 봤다 — 껍데기를 여닫는 단추는 왼쪽 사이드바 토글과 같은 자리에 있다. */}
      <RightPanel label="변수 목록">
        <VariablesSidebar vocabulary={vocabulary} />
      </RightPanel>
    </section>
  )
}

/**
 * 변수 목록 — **이 이름이 무엇인지.**
 *
 * `strain_true_plastic` 만 화면에 뜨면 그게 무엇인지 코드를 읽어야 알게 되고,
 * 그러면 아무도 안 읽는다. 이름·뜻·저장 단위·누가 만드는지를 옆에 놓는다.
 *
 * **목록을 여기 적지 않는다.** 계산이 `Produced` 로 선언한 것을 그대로 보여
 * 준다 — 새 처리를 만들면 여기도 따라온다(D7).
 *
 * 지금 켠 단계가 만드는 것만 보인다. 안 켠 것까지 다 보이면 "있는데 왜 못
 * 고르지" 가 되고, 그건 순서도가 답할 질문이다.
 *
 * ## 창이 아니라 가장자리다
 *
 * 단계의 '변형률 열' 을 고르면서 그 이름의 뜻을 보는 일이다. 창이면 열었다 —
 * 확인하고 — 닫았다 — 고르고 — 다시 여는 것을 반복하게 된다.
 *
 * **여는 손잡이도 여기 있다.** 머리에 버튼을 두면 "저 버튼이 여는 것이 어느
 * 쪽인가" 를 한 번 더 생각해야 한다 — 접혔을 때 오른쪽 가장자리에 남는 띠가
 * 곧 그 자리다. 접어 두는 것이 기본이다: 늘 펴 두면 곡선이 그만큼 좁아지고,
 * 그건 이 화면을 넓힌 이유와 정면으로 부딪힌다.
 */
function VariablesSidebar({ vocabulary }: { vocabulary: ReturnType<typeof vocabularyOf> }) {
  const entry = (item: {
    key: string
    label: string
    si_unit: string
    help?: string | null
    madeBy?: string
  }) => (
    <li key={item.key} className="border-b px-2 py-1.5 last:border-b-0">
      <p className="font-mono text-xs break-all">{item.key}</p>
      <p className="text-sm">
        {item.label}
        {item.si_unit !== '1' && (
          <span className="text-muted-foreground ml-1 text-xs">({item.si_unit})</span>
        )}
      </p>
      {item.help && <p className="text-muted-foreground mt-0.5 text-xs">{item.help}</p>}
      <p className="text-muted-foreground mt-0.5 text-xs italic">{item.madeBy ?? '장비 파일'}</p>
    </li>
  )

  return (
    /* **껍데기의 오른쪽 영역**에 산다. 본문과 따로 스크롤한다 — 단계 목록을
       내리면서 이름의 뜻을 보는 자리라, 같이 굴러가면 쓸 수 없다. */
    <aside className="flex h-full w-64 flex-col border-l">
      <div className="flex shrink-0 items-center border-b px-2 py-2">
        <h3 className="text-sm font-medium">변수 목록</h3>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">

        <p className="text-muted-foreground px-2 py-1.5 text-xs">
          지금 켠 단계가 쓰고 만드는 이름입니다. <b>이름은 계산이 정합니다</b> — 파일이나
          사람이 정하지 않으므로, 다른 시험도 같은 이름이면 같은 뜻입니다.
        </p>

        <p className="bg-muted/50 border-y px-2 py-1 text-xs font-medium">
          열 <span className="text-muted-foreground font-normal">— 곡선의 세로줄</span>
        </p>
        <p className="text-muted-foreground px-2 py-1.5 text-xs">
          저장하면 이 열들이 <b>그대로 파일에 들어갑니다.</b> 결과는 불변이라 나중에 열을
          덧붙일 수 없습니다.
        </p>
        <ul>{vocabulary.columns.map(entry)}</ul>

        {vocabulary.values.length > 0 && (
          <>
            <p className="bg-muted/50 border-y px-2 py-1 text-xs font-medium">
              값 <span className="text-muted-foreground font-normal">— 곡선당 하나</span>
            </p>
            <p className="text-muted-foreground px-2 py-1.5 text-xs">
              뒤 단계가 <code>@이름</code> 으로 가져다 씁니다 — 사람이 옮겨 적으면, 앞을
              다시 계산했을 때 뒤만 옛 값으로 남습니다.
            </p>
            <ul>{vocabulary.values.map(entry)}</ul>
          </>
        )}
      </div>
    </aside>
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
  columnInfo,
  disabled = false,
  onChange,
}: {
  param: StepParam
  value: unknown
  columns: string[]
  /** 열 이름 → 그 이름의 뜻. 고르는 자리에서 바로 읽게 한다. */
  columnInfo: Map<string, { label: string; si_unit: string; help?: string | null }>
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
  // **나누기만 하면 안 된다.** 섭씨는 원점이 달라서 25 °C 를 25 K 로 보내면
  // -248 °C 가 된다. 환산은 `units` 의 짝 함수를 쓴다.
  const toSi = (value: number) => fromDisplay(value, param.unit, param.dimension)
  const fromSi = (value: number) => toDisplay(value, param.unit, param.dimension)

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
                {/* **값은 안 바꾼다.** `linear_regression` 은 레시피 JSON 과
                    결과 스냅샷에 저장되는 계약이라, 한국어로 바꾸면 저장된
                    레시피가 전부 깨진다. 보여 줄 이름만 서버가 따로 준다. */}
                {param.choice_labels?.[choice] ?? choice}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }

  // 열 이름을 받는 칸은 자유 입력보다 목록이 낫다 — 오타 하나가 '열이 없습니다'
  // 로 끝나고, 어떤 이름이 있는지는 화면만 안다.
  //
  // **어느 칸이 열을 받는지는 서버가 말한다**(`ParamSpec.role`). 전에는 여기에
  // `['x','column','strain','stress',...]` 를 적어 뒀는데, 열을 받는 칸을 가진
  // 계산을 새로 만들면 이 목록에도 이름을 더해야 했다 — 안 더하면 자유 입력이
  // 되고, `ParamSpec` 이 곧 화면의 칸이라는 D7 의 약속이 거기서 깨졌다.
  if (param.role === 'column' && columns.length) {
    return (
      <div className={`${rowClass} items-center`} aria-disabled={disabled || undefined}>
        <Label className="text-xs">{param.label}</Label>
        <Select value={String(value ?? '')} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger className="h-8" aria-label={param.label}>
            <SelectValue placeholder="열을 고르세요" />
          </SelectTrigger>
          <SelectContent>
            {/* **이름과 뜻을 같이 낸다.** `strain_true_plastic` 만 있으면 그게
                무엇인지 코드를 읽어야 알고, 뜻이 필요한 순간은 목록을 여는 때가
                아니라 **고르는 이 순간**이다. */}
            {columns.map((column) => {
              const info = columnInfo.get(column)
              return (
                <SelectItem key={column} value={column}>
                  <span className="flex flex-col items-start">
                    <span className="font-mono text-xs">{column}</span>
                    {info && (
                      <span className="text-muted-foreground text-xs">
                        {info.label}
                        {info.si_unit !== '1' && ` (${info.si_unit})`}
                      </span>
                    )}
                  </span>
                </SelectItem>
              )
            })}
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
          /* **상태와 동작이 비슷하게 생기면 안 된다.** 뱃지와 버튼을 나란히
             두었더니 "어느 걸 눌러야 하나" 가 됐다. 지금 무엇을 쓰는지는
             문장으로 말하고, 누를 것은 버튼 하나만 남긴다.
             원문(`@specimen_gauge_length`)을 그대로 보이면 이게 무엇인지
             코드를 읽어야 안다. */
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground flex items-center gap-1 text-xs">
              <Link2 className="size-3" />
              <b className="text-foreground">{referenceLabel(String(value))}</b>를 씁니다
            </span>
            <Button
              size="sm"
              variant="outline"
              className="ml-auto h-7 shrink-0 text-xs"
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
                {/* 이름만 적으면 라벨처럼 보인다. **누르는 것**임을 동사로 말한다. */}
                <Link2 className="size-3" />
                {reference.label} 쓰기
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
