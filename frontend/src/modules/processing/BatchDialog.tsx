/**
 * 배치 적용 — 고른 시험 전부에 같은 단계를.
 *
 * ## 왜 이게 있어야 실데이터가 들어오나
 *
 * 실무는 시편 20~30개다. 하나씩 열어 단계를 맞추고 저장하고 채택하면 그것만으로
 * 하루가 간다. 한 건으로 맞춘 뒤 나머지에 같은 것을 거는 것이 실제 작업 흐름이다.
 *
 * ## 세 걸음이다 — **보고 나서 정한다**(2026-09-11)
 *
 *     ① 무엇을 걸지      저장된 레시피, 또는 방금 맞춘 단계 그대로
 *     ② 미리보기        저장하지 않고 전부 돌려 **전/후를 견준다**
 *     ③ 저장           그때 정한다. 잘못 걸었으면 **되돌린다**
 *
 * *"하나하나 데이터가 중요하니까, 일괄 처리 이후 결과를 비교해서 할지 안 할지
 * 정하는 게 어때"* — 스무 건의 값을 한 번에 바꾸는 일인데, 지금까지는 걸어 본
 * 뒤에야 무엇이 나오는지 알 수 있었다.
 *
 * **미리보기는 저장과 같은 경로로 돈다**(`dry_run`). 따로 만들면 「미리보기는
 * 됐는데 저장은 실패」 가 가능해지고, 그 어긋남은 이미 스무 건을 건 뒤에 드러난다.
 *
 * ## 레시피가 없어도 걸 수 있다
 *
 * 전에는 **저장된 레시피만** 걸 수 있었다. 그런데 레시피 저장은 부서 관리자만
 * 할 수 있어서, 관리자가 아닌 사람은 배치를 아예 못 썼다 — 실측(2026-09-11):
 * 채택된 결과 52건 중 49건이 「레시피 없이」 나왔다. 처리 화면에서 맞춘 단계를
 * 그대로 넘겨받는다(`steps`).
 *
 * ## 부분 실패를 그대로 보여 준다
 *
 * 20건 중 하나가 시편 치수 때문에 막히는 일은 **정상**이다(일괄 등록으로 만든
 * 시편은 치수가 비어 있다). 전체를 되돌리면 19건을 다시 해야 하고, 조용히
 * 건너뛰면 사람은 다 된 줄 안다. 그래서 건별로 보여 주고 실패는 **왜 막혔는지**
 * 까지 적는다.
 *
 * ## 나눠 보낸다
 *
 * 25건씩 잘라 보내고 진행을 센다(`batchRun`). 1000건짜리 요청 하나는 프록시가
 * 끊는 자리이고, 끊기면 어디까지 됐는지 알 방법이 없다.
 */

import { useState } from 'react'
import { AlertTriangle, ArrowRight, Check, Layers, Undo2 } from 'lucide-react'

import { processingApi } from '@/modules/processing/api'
import { changesOf, runInChunks, shifted, undoInChunks } from '@/modules/processing/batchRun'
import type { Change } from '@/modules/processing/batchRun'
import { formatScalar } from '@/shared/units'
import { RecipePicker } from '@/modules/processing/RecipePicker'
import type { BatchItem, BatchOut, RecipeStep } from '@/modules/processing/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'

interface Props {
  testRunIds: string[]
  /** 이 종류의 레시피만 보여 준다. 인장 레시피가 DMA 곡선에 걸리면 실패한다. */
  testTypeKey: string | null
  /**
   * 방금 맞춘 단계 그대로 걸 때. **주면 레시피를 안 고른다** — 레시피 저장은
   * 부서 관리자만 할 수 있어서, 그것을 요구하면 관리자가 아닌 사람은 배치를
   * 아예 못 쓴다.
   */
  steps?: RecipeStep[]
  /** 그 단계가 어디서 왔는지 한 줄. 「이 시험에서 맞춘 단계」 처럼. */
  stepsLabel?: string
  onClose: () => void
  onDone: () => void
}

export function BatchDialog({
  testRunIds,
  testTypeKey,
  steps: given,
  stepsLabel,
  onClose,
  onDone,
}: Props) {
  const recipes = useResource(
    () => (given ? Promise.resolve([]) : processingApi.recipes(testTypeKey ?? undefined)),
    [testTypeKey, Boolean(given)]
  )
  const [recipeKey, setRecipeKey] = useState('')
  const [adopt, setAdopt] = useState(true)
  const [preview, setPreview] = useState<BatchOut | null>(null)
  const [result, setResult] = useState<BatchOut | null>(null)
  const [undone, setUndone] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  /** 몇 건까지 됐나. 30초 동안 스피너만 도는 것과는 다르다. */
  const [progress, setProgress] = useState<[number, number] | null>(null)

  const rows = recipes.data ?? []
  const recipe = rows.find((item) => item.key === recipeKey) ?? null
  const steps = given ?? (recipe?.steps as unknown as RecipeStep[] | undefined) ?? null

  async function go(dryRun: boolean) {
    if (!steps) return
    setBusy(true)
    setError(null)
    setProgress([0, testRunIds.length])
    try {
      const got = await runInChunks(
        { testRunIds, steps, recipeKey: recipe?.key ?? null, adopt, dryRun },
        (done, total) => setProgress([done, total])
      )
      if (dryRun) setPreview(got)
      else {
        setResult(got)
        onDone()
      }
    } catch (caught) {
      const failure = caught instanceof Error ? caught : new Error('돌리지 못했습니다.')
      setError(failure)
      // **여기까지 된 것을 보여 준다.** 끊긴 자리를 모르면 사람은 다시 걸어
      // 같은 것을 두 벌 만든다.
      const partial = (failure as { partial?: BatchOut }).partial
      if (partial && !dryRun) {
        setResult(partial)
        onDone()
      } else if (partial) setPreview(partial)
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  async function undo() {
    if (!result) return
    setBusy(true)
    setError(null)
    try {
      await undoInChunks(
        result.items
          .filter((item) => item.result_id)
          .map((item) => ({
            result_id: item.result_id as string,
            restore_adopted_id: item.previous_adopted_id ?? null,
          })),
        (done, total) => setProgress([done, total])
      )
      setUndone(true)
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('되돌리지 못했습니다.'))
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  const shown = result ?? preview

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            <Layers className="mr-1.5 inline size-4" />
            {testRunIds.length}건에 같은 단계 적용
          </DialogTitle>
          <DialogDescription>
            {result
              ? '저장했습니다. 아래는 시험마다 무엇이 달라졌는지입니다.'
              : preview
                ? '아직 아무것도 저장되지 않았습니다 — 아래를 보고 정하세요.'
                : '먼저 돌려만 보고, 전/후를 견준 뒤에 저장합니다.'}
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={recipes.error ?? error} />

        {undone && (
          <p className="rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
            <b>되돌렸습니다.</b> 만든 결과를 지우고 채택도 원래대로 돌려놓았습니다.
          </p>
        )}

        {progress && (
          <Progress done={progress[0]} total={progress[1]} label={busy ? '도는 중' : ''} />
        )}

        {shown ? (
          <Outcome shown={shown} saved={result !== null} />
        ) : (
          <div className="space-y-3">
            {given ? (
              <div className="rounded-md border p-3 text-sm">
                <b>{stepsLabel ?? '방금 맞춘 단계'}</b>
                <ol className="text-muted-foreground mt-1 space-y-0.5 text-xs">
                  {given.map((step, index) => (
                    <li key={`${step.plugin}-${index}`}>
                      {index + 1}. <span className="font-mono">{step.plugin}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : (
              <div className="space-y-1.5">
                {/* **「레시피」 만 적어 두지 않는다.** 우리 안쪽 말이라, 처음
                    보는 사람은 그것이 무엇인지부터 물어야 한다(2026-09-11
                    지적). 하는 일을 앞에 적고 이름을 괄호에 둔다. */}
                <Label>돌릴 처리 단계 묶음 (레시피)</Label>
                <RecipePicker
                  recipes={rows}
                  value={recipe}
                  className="w-full"
                  placeholder="레시피를 고르세요"
                  ariaLabel="레시피"
                  onSelect={(item) => setRecipeKey(item.key)}
                />
                {!recipes.loading && rows.length === 0 && (
                  <p className="text-muted-foreground text-xs">
                    저장해 둔 단계 묶음이 없습니다. 시험 하나를 열어 <b>처리</b> 탭에서
                    단계를 맞춘 뒤 그 화면의 <b>「이 단계 그대로 여러 건에」</b> 를 쓰면
                    됩니다 — 저장하지 않아도 걸립니다.
                  </p>
                )}
                {recipe && (
                  <ol className="text-muted-foreground space-y-0.5 rounded-md border p-3 text-xs">
                    {(recipe.steps as unknown as RecipeStep[]).map((step, index) => (
                      <li key={`${step.plugin}-${index}`}>
                        {index + 1}. <span className="font-mono">{step.plugin}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={adopt}
                onChange={(event) => setAdopt(event.target.checked)}
              />
              <span>
                저장할 때 <b>바로 채택</b>
                <span className="text-muted-foreground block text-xs">
                  채택된 값이 이 시험의 물성이 되고 요약값 표에 섭니다. 끄면 결과만 저장되고
                  채택은 나중에 건별로 합니다. <b>미리보기는 채택을 건드리지 않습니다.</b>
                </span>
              </span>
            </label>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {result ? '닫기' : '취소'}
          </Button>
          {result ? (
            // **되돌리기는 만든 것을 지우고 채택을 원래대로 돌린다.** 지우기만
            // 하면 원래 있던 값까지 사라져, 배치 걸기 전보다 나쁜 자리가 된다.
            !undone && (
              <Button variant="destructive" onClick={undo} disabled={busy}>
                <Undo2 className="size-3.5" />
                {busy ? '되돌리는 중…' : '되돌리기'}
              </Button>
            )
          ) : preview ? (
            <>
              <Button variant="ghost" onClick={() => setPreview(null)} disabled={busy}>
                단계 다시 선택
              </Button>
              <Button onClick={() => go(false)} disabled={busy || preview.succeeded === 0}>
                {busy ? '저장하는 중…' : `${preview.succeeded}건 저장`}
              </Button>
            </>
          ) : (
            <Button onClick={() => go(true)} disabled={busy || !steps}>
              <ArrowRight className="size-3.5" />
              {busy ? '돌려 보는 중…' : `${testRunIds.length}건 미리보기`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 진행. **건수로 센다** — 조각 수로 세면 사람이 못 읽는다. */
function Progress({ done, total, label }: { done: number; total: number; label: string }) {
  const percent = total === 0 ? 0 : Math.round((done / total) * 100)
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground flex items-center justify-between text-xs">
        <span>{label}</span>
        <span className="tabular-nums">
          {done}/{total}건
        </span>
      </div>
      <div className="bg-muted h-1.5 overflow-hidden rounded-full">
        <div className="bg-primary h-full transition-all" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

/**
 * 결과 — **바뀐 것이 위에 온다.**
 *
 * 스무 줄이 다 「똑같음」 인데 그 사이에 한 줄만 크게 달라졌다면, 그 한 줄이
 * 사람이 봐야 할 전부다. 차례가 그것을 대신 골라 준다.
 */
function Outcome({ shown, saved }: { shown: BatchOut; saved: boolean }) {
  const items = [...shown.items].sort((a, b) => rank(a) - rank(b))
  const moved = shown.items.filter((one) => one.status === 'ok' && shifted(one)).length

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge className="bg-emerald-600 hover:bg-emerald-600">
          {saved ? '저장' : '성공'} {shown.succeeded}
        </Badge>
        {shown.failed > 0 && <Badge variant="destructive">실패 {shown.failed}</Badge>}
        {moved > 0 && (
          <Badge variant="outline" className="border-amber-500/60 text-amber-700">
            값이 달라진 것 {moved}
          </Badge>
        )}
        <span className="text-muted-foreground text-xs">요청 {shown.requested}건</span>
      </div>

      <div className="max-h-[22rem] space-y-1 overflow-y-auto">
        {items.map((item) => (
          <Row key={item.test_run_id} item={item} />
        ))}
      </div>

      {shown.failed > 0 && (
        <p className="text-muted-foreground text-xs">
          실패한 건은 <b>아무것도 저장되지 않았습니다.</b> 이유를 고친 뒤 그 건들만 다시
          고르면 됩니다 — 성공한 것을 다시 돌릴 필요는 없습니다.
        </p>
      )}
    </div>
  )
}

function rank(item: BatchItem): number {
  if (item.status === 'failed') return 0
  return shifted(item) ? 1 : 2
}

function Row({ item }: { item: BatchItem }) {
  const changes = changesOf(item).slice(0, 4)
  return (
    <div
      className={`rounded-md border px-3 py-2 text-xs ${
        item.status === 'failed' ? 'border-destructive/40 bg-destructive/5' : ''
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {item.status === 'ok' ? (
          <Check className="size-3.5 text-emerald-600" />
        ) : (
          <AlertTriangle className="text-destructive size-3.5" />
        )}
        <span className="font-mono">{item.record_name}</span>
        {item.adopted && (
          <Badge variant="outline" className="text-xs">
            채택됨
          </Badge>
        )}
        {item.status === 'ok' && !shifted(item) && (
          <span className="text-muted-foreground">값이 거의 같습니다</span>
        )}
      </div>

      {/* **전 → 후를 나란히.** 「그래서 뭐가 달라지나」 가 이 표의 전부다. */}
      {changes.length > 0 && (
        <div className="mt-1.5 grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
          {changes.map((one) => (
            <Diff key={one.key} change={one} />
          ))}
        </div>
      )}

      {item.error && <p className="text-destructive mt-1 whitespace-pre-wrap">{item.error}</p>}
    </div>
  )
}

function Diff({ change }: { change: Change }) {
  const loud = change.ratio !== null && Math.abs(change.ratio) >= 0.01
  const show = (value: number | null) =>
    value === null ? '—' : formatScalar(value, change.unit, change.dimension ?? undefined)
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-muted-foreground min-w-24 truncate">{change.label}</span>
      <span className="text-muted-foreground font-mono tabular-nums">{show(change.before)}</span>
      <ArrowRight className="size-3 shrink-0 opacity-50" />
      <span className="font-mono tabular-nums">{show(change.after)}</span>
      {change.ratio !== null && (
        <span
          className={`tabular-nums ${loud ? 'font-medium text-amber-700 dark:text-amber-500' : 'text-muted-foreground'}`}
        >
          {change.ratio > 0 ? '+' : ''}
          {(change.ratio * 100).toFixed(1)}%
        </span>
      )}
    </div>
  )
}
