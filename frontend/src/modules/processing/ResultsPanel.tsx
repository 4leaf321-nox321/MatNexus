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

import { useMemo, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Star } from 'lucide-react'

import { processingApi } from '@/modules/processing/api'
import { CurveChart } from '@/modules/tests/CurveChart'
import { axisLabel, formatScalar, toDisplay } from '@/shared/units'
import type { ProcessingResult } from '@/modules/processing/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
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

  /**
   * **채택이 진응력 없는 결과에 걸려 있는가.**
   *
   * 실측: 단계를 고쳐 다시 처리해 놓고 채택을 안 옮겨서, CAE 카드 탭에서
   * "strain_true_plastic 열이 없습니다" 를 봤다. 목록에는 '4단계 · 18행' 과
   * '5단계 · 18행' 이 나란히 있어 어느 쪽이 그 열을 가졌는지 알 수가 없었다.
   * 고르는 자리에서 안 보이면 세 화면 뒤에서 오류로 만난다.
   */
  const adopted = rows.find((item) => item.is_adopted)
  const trueStressElsewhere =
    adopted !== undefined &&
    !adopted.columns.includes('stress_true') &&
    rows.some((item) => !item.is_adopted && item.columns.includes('stress_true'))

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

      {trueStressElsewhere && (
        <div className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          <b>채택된 결과에 진응력 열이 없습니다.</b> 아래에 진응력을 포함한 결과가
          따로 있습니다 — 그것을 채택해야 CAE 카드를 만들 수 있습니다. 다시 처리만
          하고 채택을 옮기지 않으면 예전 결과가 그대로 쓰입니다.
        </div>
      )}

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
                  {/* **고르는 자리에서 보여야 한다.** '4단계' 와 '5단계' 만으로는
                      어느 쪽이 CAE 카드를 만들 수 있는지 알 수 없다. */}
                  {item.columns.includes('stress_true') && (
                    <Badge variant="outline" className="text-xs">
                      진응력 포함
                    </Badge>
                  )}
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
                  <div className="grid gap-4 border-t px-3 py-3 2xl:grid-cols-[minmax(300px,420px)_minmax(0,1fr)] 2xl:items-start">
                    {/* **곡선을 오른쪽에, 읽는 값을 왼쪽에.** 채택은 이 곡선을
                        물성으로 삼는 결정인데, 세로로 쌓으면 곡선을 보고 스크롤을
                        내려 숫자를 보고 다시 올라와야 한다 — 「이 곡선에서 이 값이
                        나오는 게 맞나」 가 채택 직전에 하는 질문이다.

                        좁은 화면에서는 한 열로 돌아가고 그때는 **곡선이 먼저다**
                        (`order`) — 무엇을 계산했는지 보고 나서 숫자를 본다. */}
                    <div className="space-y-3 2xl:order-1">
                      {/* 칸이 좁아 두 열이면 한 줄에 하나꼴로 늘어졌다. 값은
                          짧고(숫자+단위) 이름도 짧아 셋이 들어간다. */}
                      {item.scalars.length > 0 && (
                        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
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

                    <div className="2xl:order-2 2xl:sticky 2xl:top-28">
                      <ResultCurve resultId={item.id} />
                    </div>
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

/**
 * 저장된 결과의 곡선.
 *
 * **처리 탭에서는 보이던 그림이 결과 탭에서는 없었다.** 값과 근거만 있고 곡선은
 * 파일에 있었다 — 처리한 사람이 정작 자기가 저장한 곡선을 볼 수 없었다. 채택은
 * "이 곡선을 이 시험의 물성으로 삼는다" 는 결정인데, 그 곡선을 안 보고 눌러야
 * 했다.
 *
 * **축 목록이 곧 레시피가 한 일이다.** 진응력 축이 목록에 없다면 레시피에
 * '진응력·진소성변형률' 단계가 없는 것이다. 그래서 없을 때는 그 사실을 적는다 —
 * 빈 선택지를 보고 스스로 알아내야 하면 그건 알려 준 것이 아니다.
 */
function ResultCurve({ resultId }: { resultId: string }) {
  const [axes, setAxes] = useState<{ x: string; y: string } | null>(null)
  const curve = useResource(
    () => processingApi.curve(resultId, axes ?? undefined),
    [resultId, axes?.x, axes?.y]
  )
  const data = curve.data

  // 축과 점을 **같은 단위로** 맞춘다. 하나만 바꾸면 1000배 어긋난 그림이 된다.
  const points = useMemo<[number, number][]>(
    () =>
      (data?.points ?? []).map(([x, y]) => [
        toDisplay(x, data?.units[data.x]),
        toDisplay(y, data?.units[data.y]),
      ]),
    [data]
  )

  if (curve.error) return <ErrorNotice error={curve.error} />
  if (!data) return <p className="text-muted-foreground text-xs">곡선을 읽는 중…</p>

  const hasTrue = data.columns.includes('stress_true')

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {(['x', 'y'] as const).map((axis) => (
          <div key={axis} className="flex items-center gap-1">
            <span className="text-muted-foreground text-xs">{axis}</span>
            <Select
              value={data[axis]}
              onValueChange={(value) => setAxes({ ...{ x: data.x, y: data.y }, [axis]: value })}
            >
              <SelectTrigger className="h-8 w-52" aria-label={`${axis}축`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.columns.map((column) => (
                  <SelectItem key={column} value={column}>
                    {column}
                    {data.units[column] && data.units[column] !== '1'
                      ? ` (${data.units[column]})`
                      : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ))}
        <span className="text-muted-foreground ml-auto text-xs">
          {data.row_count.toLocaleString('ko-KR')}행
        </span>
      </div>

      <CurveChart
        points={points}
        xLabel={axisLabel(data.x, data.units[data.x])}
        yLabel={axisLabel(data.y, data.units[data.y])}
        // **2열로 가면서 세로가 남았다.** 곡선이 오른쪽 한 칸을 통째로 쓰는데
        // 280 은 왼쪽 목록보다 훨씬 짧아, 채택 직전에 봐야 할 모양이 작게 눌린다.
        height={420}
      />

      {!hasTrue && (
        // **없는 것을 없다고 말한다.** 축 목록에 진응력이 안 보이는 이유를
        // 사람이 추론해야 하면 알려 준 것이 아니다.
        <p className="text-muted-foreground mt-2 text-xs">
          진응력·진소성변형률 축이 없습니다 — 이 결과를 만든 레시피에{' '}
          <b>진응력·진소성변형률</b> 단계가 없기 때문입니다. 그 단계를 넣고 다시
          처리하면 축 목록에 나타나고, CAE 카드도 그 열에서 만듭니다.
        </p>
      )}
    </div>
  )
}
