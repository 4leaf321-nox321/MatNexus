/**
 * 배치 적용 — 고른 시험 전부에 같은 레시피를.
 *
 * ## 왜 이게 있어야 실데이터가 들어오나
 *
 * 실무는 시편 20~30개다. 하나씩 열어 단계를 맞추고 저장하고 채택하면 그것만으로
 * 하루가 간다. 한 건으로 맞춘 뒤 나머지에 같은 것을 거는 것이 실제 작업 흐름이다.
 *
 * ## 부분 실패를 그대로 보여 준다
 *
 * 20건 중 하나가 시편 치수 때문에 막히는 일은 **정상**이다(일괄 등록으로 만든
 * 시편은 치수가 비어 있다). 그때
 *
 *   - 전체를 되돌리면 19건을 다시 해야 하고,
 *   - 조용히 건너뛰면 사람은 다 된 줄 안다.
 *
 * 그래서 건별 결과를 표로 보여 주고, 실패는 **왜 막혔는지까지** 적는다. 이유는
 * 건마다 다르다 — 치수가 없는 것, 탄성 구간에 점이 없는 것이 한 배치에 섞인다.
 */

import { useState } from 'react'
import { AlertTriangle, Check, Layers } from 'lucide-react'

import { processingApi } from '@/modules/processing/api'
import { formatScalar } from '@/modules/tests/units'
import { RecipePicker } from '@/modules/processing/RecipePicker'
import type { BatchOut, RecipeStep } from '@/modules/processing/api'
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
  onClose: () => void
  onDone: () => void
}

export function BatchDialog({ testRunIds, testTypeKey, onClose, onDone }: Props) {
  const recipes = useResource(
    () => processingApi.recipes(testTypeKey ?? undefined),
    [testTypeKey],
  )
  const [recipeKey, setRecipeKey] = useState('')
  const [adopt, setAdopt] = useState(true)
  const [result, setResult] = useState<BatchOut | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  const rows = recipes.data ?? []
  const recipe = rows.find((item) => item.key === recipeKey) ?? null

  async function run() {
    if (!recipe) return
    setBusy(true)
    setError(null)
    try {
      setResult(
        await processingApi.batch({
          test_run_ids: testRunIds,
          steps: recipe.steps as unknown as RecipeStep[],
          recipe_key: recipe.key,
          adopt,
        }),
      )
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('돌리지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            <Layers className="mr-1.5 inline size-4" />
            {testRunIds.length}건에 레시피 적용
          </DialogTitle>
          <DialogDescription>
            고른 시험 전부에 같은 단계를 겁니다. 결과는 시험마다 하나씩 저장됩니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={recipes.error ?? error} />

        {result ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge className="bg-emerald-600 hover:bg-emerald-600">
                성공 {result.succeeded}
              </Badge>
              {result.failed > 0 && <Badge variant="destructive">실패 {result.failed}</Badge>}
              <span className="text-muted-foreground text-xs">요청 {result.requested}건</span>
            </div>

            <div className="space-y-1">
              {result.items.map((item) => (
                <div
                  key={item.test_run_id}
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
                    <span className="text-muted-foreground ml-auto flex gap-3">
                      {item.scalars
                        .filter((s) => ['youngs_modulus', 'proof_stress'].includes(s.key))
                        .map((s) => (
                          <span key={s.key} className="font-mono">
                            {s.key === 'youngs_modulus' ? 'E' : 'YS'}{' '}
                            {formatScalar(s.value, s.si_unit, s.dimension)}
                          </span>
                        ))}
                    </span>
                  </div>
                  {/* **왜 막혔는지가 건별로 있어야** 무엇을 고칠지 안다. */}
                  {item.error && (
                    <p className="text-destructive mt-1 whitespace-pre-wrap">{item.error}</p>
                  )}
                </div>
              ))}
            </div>

            {result.failed > 0 && (
              <p className="text-muted-foreground text-xs">
                실패한 건은 <b>아무것도 저장되지 않았습니다.</b> 이유를 고친 뒤 그 건들만 다시
                고르면 됩니다 — 성공한 것을 다시 돌릴 필요는 없습니다.
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>레시피</Label>
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
                  이 시험 종류의 레시피가 없습니다. 시험 하나를 열어 <b>처리</b> 탭에서 단계를
                  맞춘 뒤 <b>레시피로 저장</b>하세요 — 그것이 여기 나옵니다.
                </p>
              )}
            </div>

            {recipe && (
              <ol className="text-muted-foreground space-y-0.5 rounded-md border p-3 text-xs">
                {(recipe.steps as unknown as RecipeStep[]).map((step, index) => (
                  <li key={`${step.plugin}-${index}`}>
                    {index + 1}. <span className="font-mono">{step.plugin}</span>
                  </li>
                ))}
              </ol>
            )}

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={adopt}
                onChange={(event) => setAdopt(event.target.checked)}
              />
              <span>
                성공한 것을 <b>바로 채택</b>
                <span className="text-muted-foreground block text-xs">
                  채택된 값이 이 시험의 물성이 되고 요약값 표에 섭니다. 끄면 결과만 저장되고
                  채택은 나중에 건별로 합니다.
                </span>
              </span>
            </label>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {result ? '닫기' : '취소'}
          </Button>
          {!result && (
            <Button onClick={run} disabled={busy || !recipe}>
              {busy ? '돌리는 중…' : `${testRunIds.length}건 돌리기`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
