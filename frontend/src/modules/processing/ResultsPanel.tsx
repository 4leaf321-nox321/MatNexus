/**
 * 처리 결과 목록 — 시도들과 **그중 채택된 하나.**
 *
 * ## 왜 채택이 필요한가
 *
 * 탄성계수를 회귀로도 재 보고 현으로도 재 보고, 네킹 후보로 잘라도 보는 것이
 * 정상 작업이다. 그래서 결과는 여러 벌 쌓인다. 그런데 통계·비교·내보내기는
 * **시험당 값 하나**가 필요하다. 저장된 것이 전부 동등하면 "이 시험의
 * 항복강도는 얼마인가" 에 답할 수가 없다(ADR 0007).
 *
 * 그렇다고 "저장 = 확정" 으로 하면 시행착오를 남길 수 없어 방법 간 비교가
 * 불가능해지고, "최신이 곧 대표" 로 하면 실험 삼아 마지막에 돌린 것이 대표가
 * 된다 — 조용히 틀리는 그 계열이다.
 *
 * ## 이 화면이 답해야 하는 것
 *
 * "이 값이 무엇으로 나왔나." 그래서 채택된 결과의 **단계와 근거**를 펼쳐 볼 수
 * 있어야 한다. 결과는 그때의 단계를 통째로 스냅샷하고 있으므로, 레시피가
 * 나중에 바뀌어도 여기 적힌 것은 그대로다.
 */

import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, Star } from 'lucide-react'

import { processingApi } from '@/modules/processing/api'
import { formatScalar } from '@/shared/units'
import type { ProcessingResult } from '@/modules/processing/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

const when = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

interface Props {
  testRunId: string
  /** 채택이 바뀌면 요약값 표가 달라진다 — 상위가 다시 읽게 알린다. */
  onAdoptChange?: () => void
}

export function ResultsPanel({ testRunId, onAdoptChange }: Props) {
  const results = useResource(() => processingApi.results(testRunId), [testRunId])
  const [error, setError] = useState<Error | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const rows = results.data ?? []

  async function toggle(item: ProcessingResult) {
    setBusy(true)
    setError(null)
    try {
      if (item.is_adopted) await processingApi.unadopt(item.id)
      else await processingApi.adopt(item.id)
      results.reload()
      onAdoptChange?.()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('바꾸지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <ErrorNotice error={results.error ?? error} className="mb-3" />

      {!results.loading && rows.length === 0 ? (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          저장된 처리 결과가 없습니다.
          <p className="mx-auto mt-2 max-w-md text-xs">
            <b>처리</b> 탭에서 단계를 돌려 보고 결과를 저장하세요. 저장된 결과 중
            하나를 <b>채택</b>하면 그 값이 이 시험의 물성이 되고, 요약값 표에
            장비 값과 나란히 섭니다.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((item) => {
            const expanded = open === item.id
            return (
              <div
                key={item.id}
                className={`rounded-md border ${item.is_adopted ? 'border-emerald-500/50' : ''}`}
              >
                <div className="flex flex-wrap items-center gap-2 px-3 py-2">
                  <button
                    type="button"
                    className="text-muted-foreground"
                    onClick={() => setOpen(expanded ? null : item.id)}
                    aria-label={expanded ? '접기' : '펼치기'}
                  >
                    {expanded ? (
                      <ChevronDown className="size-4" />
                    ) : (
                      <ChevronRight className="size-4" />
                    )}
                  </button>
                  {item.is_adopted && (
                    <Badge className="gap-1 bg-emerald-600 hover:bg-emerald-600">
                      <Star className="size-3" />
                      채택됨
                    </Badge>
                  )}
                  <span className="text-muted-foreground text-xs">
                    {when(item.created_at)}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {item.steps.length}단계 · {item.row_count.toLocaleString('ko-KR')}행
                  </span>
                  {item.recipe_label && (
                    <Badge variant="outline" className="text-xs">
                      {item.recipe_label}
                    </Badge>
                  )}

                  <div className="ml-auto flex items-center gap-3">
                    {/* 목록 줄에서 핵심 값이 바로 보여야 비교가 된다. */}
                    {item.scalars
                      .filter((s) => ['youngs_modulus', 'proof_stress'].includes(s.key))
                      .map((scalar) => (
                        <span key={scalar.key} className="font-mono text-xs">
                          {scalar.key === 'youngs_modulus' ? 'E' : 'YS'}{' '}
                          {formatScalar(scalar.value, scalar.si_unit, scalar.dimension)}
                        </span>
                      ))}
                    <Button
                      size="sm"
                      variant={item.is_adopted ? 'outline' : 'default'}
                      disabled={busy}
                      onClick={() => toggle(item)}
                    >
                      {item.is_adopted ? '채택 거두기' : <><Check className="size-3.5" />채택</>}
                    </Button>
                  </div>
                </div>

                {expanded && (
                  <div className="space-y-3 border-t px-3 py-3">
                    {item.scalars.length > 0 && (
                      <div className="grid gap-2 sm:grid-cols-3">
                        {item.scalars.map((scalar) => (
                          <div key={scalar.key} className="rounded-md border px-2 py-1.5">
                            <div className="text-muted-foreground text-xs">{scalar.label}</div>
                            <div className="font-mono text-xs">
                              {formatScalar(scalar.value, scalar.si_unit, scalar.dimension)}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* **이 값이 무엇으로 나왔나.** 스냅샷이라 레시피가 나중에
                        바뀌어도 여기 적힌 것은 그대로다. */}
                    <ol className="space-y-1.5">
                      {item.stages.map((stage, index) => (
                        <li key={`${stage.plugin}-${index}`} className="text-xs">
                          <span className="text-muted-foreground font-mono">
                            {index + 1}.
                          </span>{' '}
                          <span className="font-medium">{stage.label}</span>
                          <span className="text-muted-foreground ml-1 font-mono">
                            v{stage.version}
                          </span>
                          {stage.notes.map((note) => (
                            <p key={note} className="text-muted-foreground ml-4 border-l pl-2">
                              {note}
                            </p>
                          ))}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <p className="text-muted-foreground mt-4 text-xs">
        결과는 <b>바뀌지 않습니다.</b> 단계를 고쳐 다시 저장하면 새 결과가 생기고,
        예전 결과는 그때의 단계를 그대로 갖고 있습니다. <b>채택</b>은 그중 무엇이
        이 시험의 물성인지를 정하는 것이고, 채택된 값만 요약값 표·통계·내보내기로
        갑니다.
      </p>
    </section>
  )
}
