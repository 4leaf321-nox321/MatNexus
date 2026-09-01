/**
 * 글로벌 피팅 — **시편 여럿의 데이터를 한 번에 적합한다**(ADR 0020).
 *
 * ## 이름을 두 번 고쳤다
 *
 * 처음에는 「묶음」·「새로 묶기」 였다. 코드 안에서는 그것이 맞다 — `registry` 의
 * 갈래 이름이 `grouping` 이다. **그런데 화면에서 「묶는다」 는 무엇을 하는지 안
 * 알려 준다** — 파일을 묶는지 목록을 묶는지 알 수 없다.
 *
 * 다음에 「통합 적합」 으로 바꿨는데 그것도 안 와닿았다. 번역어라 처음 보는 사람이
 * 무슨 계산인지 못 짚는다.
 *
 * **「글로벌 피팅」 은 실무에서 그대로 쓰는 말이다.** DMA·점탄성에서 여러 데이터
 * 세트를 동시에 적합하는 것을 global fitting 이라 부른다.
 *
 * **「전역 적합」 은 안 된다** — 이 시스템에서 「전역」 은 이미 전역 재료·전역
 * 프로파일(부서를 안 가리는 것)이라는 뜻으로 쓰고 있어 겹친다.
 *
 * ## 왜 물성 탭인가
 *
 * 묶음은 「이 재료가 이렇게 거동한다」 를 만드는 일이다. 시료·시편 탭은 무엇이
 * 있나를, CAE 카드 탭은 해석에 뭘 넣나를 답한다 — 그 사이가 여기다.
 *
 * **제 화면을 따로 두지 않았다.** 묶는 자리가 둘이 되면 어느 쪽이 진짜인지 알 수
 * 없다(시험 탭을 없앤 것과 같은 판단).
 *
 * ## 고른 것과 쓴 것을 나란히 보인다
 *
 * 대표를 고르면 셋을 골라도 하나만 쓴다. 그 차이가 안 보이면 「셋을 묶었다」 가
 * 거짓말이 된다 — 서버가 둘을 따로 주는 이유가 그것이다.
 *
 * ## 방법 목록을 화면이 안 적는다
 *
 * `/groups/kinds` 가 고를 값과 설명까지 준다. 화면이 적어 두면 새 물성을 붙일 때
 * 화면도 고쳐야 하고, 그러면 확장이 아니다(D7).
 */

import { useState } from 'react'
import { Layers } from 'lucide-react'

import { groupsApi } from '@/modules/materials/api.groups'
import { masterCurveGap } from '@/shared/masterCurveGap'
import type { GroupResult, GroupingSpec } from '@/modules/materials/api.groups'
import { testsApi } from '@/modules/tests/api'
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
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'
import { useRowSelection } from '@/shared/hooks/useRowSelection'
import { formatScalar } from '@/shared/units'

/** 값 한 줄. 단위는 **서버가 준 것**을 쓴다(라벨에 손으로 안 적는다). */
function Value({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="font-mono text-sm tabular-nums">
        {unit === '1' ? value.toPrecision(4) : formatScalar(value, unit, undefined)}
      </dd>
    </div>
  )
}

function GroupCard({ row, spec }: { row: GroupResult; spec?: GroupingSpec }) {
  const units = new Map((spec?.makes_values ?? []).map((one) => [one.key, one]))
  const method = String(row.options?.method ?? row.detail?.method ?? '')
  const terms = (row.detail?.terms as { relaxation_time_s: number }[] | undefined) ?? []

  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{spec?.label ?? row.plugin_id}</Badge>
        {method && <Badge>{method}</Badge>}
        <span className="text-muted-foreground text-xs">
          {/* **고른 것과 쓴 것을 나란히.** 대표를 고르면 셋 중 하나만 쓴다. */}
          고른 {row.members.length}건 · 쓴 {row.used.length}건
          {terms.length > 0 && ` · ${terms.length}항`}
        </span>
        <span className="text-muted-foreground ml-auto text-xs">
          {new Date(row.created_at).toLocaleString('ko-KR')}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        {Object.entries(row.values).map(([key, value]) => (
          <Value
            key={key}
            label={units.get(key)?.label ?? key}
            value={value}
            unit={units.get(key)?.si_unit ?? '1'}
          />
        ))}
      </dl>

      <p className="text-muted-foreground mt-2 font-mono text-xs break-all">
        {row.used.join(' · ')}
      </p>

      {/* **감수한 것을 적는다.** 조건이 조금씩 다른 것을 묶는 일이라, 무엇을
          넘겼는지가 남아야 한다. */}
      {row.warnings.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {row.warnings.map((said) => (
            <li key={said} className="text-xs text-amber-700 dark:text-amber-500">
              {said}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function GroupsPanel({
  materialId,
  appliesTo,
  list = true,
}: {
  materialId: string
  /**
   * 이 시험종류에 쓸 수 있는 방법만. 안 주면 전부.
   *
   * **묶는 방법은 시험종류마다 다르다** — `viscoelastic.prony_group` 은 DMA 에만
   * 붙고 인장에는 쓸 방법이 아예 없다.
   */
  appliesTo?: string
  /**
   * 만든 결과 목록도 여기서 보일까.
   *
   * 재료 화면에서는 **끈다** — 묶음 결과는 물성이고, 물성 표가 `[묶음]` 배지로
   * 이미 보인다. 두 곳에 두면 어느 쪽이 진짜인지 묻게 된다.
   *
   * 끄면 **단추 하나만** 남는다. 그것이 물성 상자 머리에 앉는다.
   */
  list?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState('')
  const [options, setOptions] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<Error | null>(null)

  const kinds = useResource(() => groupsApi.kinds(appliesTo), [appliesTo])
  const rows = useResource(() => groupsApi.ofMaterial(materialId), [materialId])
  // 적합에 쓸 후보는 **채택까지 끝난 것**이 아니라 읽힌 것 전부다 — 마스터커브는
  // 채택과 무관하게 만든다.
  const runs = useResource(
    () => testsApi.runs({ material_id: materialId, status: 'parsed', limit: 200 }),
    [materialId]
  )

  const specs = kinds.data ?? []
  const chosen = specs.find((one) => one.id === kind) ?? specs[0]

  /**
   * 이 계산에 **쓸 수 있는 시험만.**
   *
   * 전에는 그 재료의 읽힌 시험 전부였다 — Prony 를 맞추려는데 인장 시험도 목록에
   * 떴고, 고르면 계산이 거절했다. **누르기 전에 알 수 있는 것을 눌러 보고 알게
   * 하지 않는다.**
   *
   * **시험종류만으로는 모자란다.** 온도 스윕과 변형률 스윕이 둘 다 `dma_sweep`
   * 인데, 마스터커브는 온도 스윕에서만 나온다 — 변형률 스윕은 **애초에 만들 수
   * 없는** 것이라 종류로 거르면 그대로 남는다. 그래서 마스터커브 수를 함께 본다.
   */
  const kindMatched = (runs.data?.items ?? []).filter(
    (run) =>
      !chosen || chosen.applies_to.length === 0 || chosen.applies_to.includes(run.test_type_key)
  )
  const candidates = kindMatched.filter((run) => (run.master_curve_count ?? 0) > 0)
  // **Shift 로 범위를 고른다.** 온도 여섯 단이면 여섯 번 누르게 된다.
  const selection = useRowSelection(candidates.map((run) => run.id))
  const picked = selection.picked
  /**
   * 종류는 맞는데 마스터커브가 없어 빠진 것. **왜 안 뜨는지 말하려고 센다.**
   *
   * 「겹칠 수 있는데 안 한 것」 과 「겹칠 수 없는 것」 을 가른다 — 변형률 스윕까지
   * 「만들면 쓸 수 있다」 고 적으면 할 수 없는 일을 시키는 셈이다.
   */
  const gap = masterCurveGap(kindMatched, [])

  /** 지금 고른 적합 방법. **쓰이지 않는 칸을 숨기는 데 쓴다.** */
  const method =
    options.method ??
    String(chosen?.params.find((one) => one.name === 'method')?.default ?? '')

  async function create() {
    if (!chosen) return
    setBusy(true)
    setFailed(null)
    try {
      await groupsApi.create({
        plugin_id: chosen.id,
        run_ids: [...picked],
        options: Object.fromEntries(
          Object.entries(options)
            .filter(([, value]) => value !== '')
            // 숫자 칸은 숫자로 보낸다 — 서버가 `int` 를 기대한다.
            .map(([key, value]) => [
              key,
              chosen.params.find((one) => one.name === key)?.type === 'int'
                ? Number(value)
                : value,
            ])
        ),
      })
      setOpen(false)
      selection.clear()
      rows.reload()
    } catch (error) {
      setFailed(error as Error)
    } finally {
      setBusy(false)
    }
  }

  // **쓸 방법이 없으면 자리를 안 차지한다.** 인장만 하는 재료에서 「묶음」 이라는
  // 말이 뜨면 그것이 무엇인지 매번 묻게 된다.
  if (!kinds.loading && specs.length === 0) return null

  /**
   * 무엇을 만드는 계산인지 — **누르기 전에 알아야 한다.**
   *
   * 「글로벌 피팅」 만으로는 그 결과가 무슨 물성인지 모른다. 방법마다 만드는 값이
   * 정해져 있고(`makes_values`), 그 목록이 곧 「이걸 누르면 무엇이 생기나」 다.
   *
   * **화면이 값 이름을 적어 두지 않는다** — 서버가 준다. 새 방법이 붙어도 여기는
   * 안 고친다.
   */
  const hint = specs
    .map((spec) => {
      const makes = spec.makes_values.map((one) => one.label).join(' · ')
      return `${spec.label}\n  ${makes || '값 없음'}`
    })
    .join('\n\n')

  const trigger = (
    <Button
      size="sm"
      variant="outline"
      className="h-7 text-xs"
      title={hint}
      onClick={() => {
        setKind(specs[0]?.id ?? '')
        setOptions({})
        setOpen(true)
      }}
    >
      <Layers className="size-3.5" />
      글로벌 피팅
    </Button>
  )

  return (
    <section className={list ? 'space-y-3' : undefined}>
      {list ? (
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium">글로벌 피팅</h3>
          <span className="text-muted-foreground text-xs">
            시편 여럿의 데이터를 한 번에 적합합니다
          </span>
          <span className="ml-auto">{trigger}</span>
        </div>
      ) : (
        trigger
      )}

      {list && <ErrorNotice error={rows.error ?? kinds.error} />}

      {list && !rows.loading && (rows.data ?? []).length === 0 && (
        <p className="text-muted-foreground rounded-md border py-8 text-center text-sm">
          아직 적합한 것이 없습니다.
        </p>
      )}

      {list && (
        <div className="space-y-2">
          {(rows.data ?? []).map((row) => (
            <GroupCard key={row.id} row={row} spec={specs.find((s) => s.id === row.plugin_id)} />
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={(next) => !next && setOpen(false)}>
        {/* **넓게 연다.** 왼쪽에서 방법을 정하고 오른쪽에서 시편을 고른다 —
            세로로 이어 붙이면 방법을 고르고 스크롤해 내려가 시편을 고르는 동안
            무엇을 고른 방법이었는지 화면에서 사라진다. */}
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>글로벌 피팅</DialogTitle>
            {/* **무엇을 하는지가 아니라 언제 쓰는지를 적는다.** 계산의 정의는
                방법을 고른 뒤 그 설명이 말한다 — 그리고 「한 번에 적합」 은 세
                방법 중 하나(pooled)의 설명이라 여기 적으면 나머지에는 틀린 말이
                된다. */}
            <DialogDescription>
              <b>시편마다 마스터커브가 하나씩 나오는데, 해석에 넣을 계수는 한
              벌이어야 합니다.</b> 그 여럿을 하나로 만드는 자리입니다 —{' '}
              <b>인장의 통계 묶음에 해당합니다.</b>
              <br />
              다만 <b>계수를 그냥 평균 낼 수는 없습니다.</b> 시편마다 완화시간(τ)도 항
              수도 다르게 맞춰져서, E₁ 끼리 더하면 서로 다른 시간의 계수를 더하는 셈이
              됩니다. 그래서 <b>묶는 방법</b>을 아래에서 고릅니다.
              <br />
              시편이 하나뿐이면 안 해도 됩니다 — 그 마스터커브의 계수를 그대로 씁니다.
            </DialogDescription>
          </DialogHeader>

          <ErrorNotice error={failed} />

          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>무엇을 구하나</Label>
                <select
                  aria-label="적합 계산"
                  className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                  value={chosen?.id ?? ''}
                  onChange={(event) => {
                    setKind(event.target.value)
                    setOptions({})
                  }}
                >
                  {specs.map((one) => (
                    <option key={one.id} value={one.id}>
                      {one.label}
                    </option>
                  ))}
                </select>
                {/* **무엇이 나오는지 먼저 말한다.** 「Prony 글로벌 피팅」 만으로는
                    그 결과가 무슨 물성인지 모른다. */}
                {chosen && (
                  <p className="text-muted-foreground text-xs">
                    {chosen.makes_values.map((one) => one.label).join(' · ')}
                  </p>
                )}
              </div>

              {/* **고를 값도 서버가 준다.** 화면이 적어 두면 새 방법이 생겨도 안 보인다. */}
              {(chosen?.params ?? []).map((param) => {
                const choices = param.choices ?? []
                const value = options[param.name] ?? String(param.default ?? '')

                // **쓰이지 않는 칸은 숨긴다.** 「대표 시편」 은 그 방법을 골랐을
                // 때만 뜻이 있고, 늘 보이면 무엇을 적어야 하는지 매번 생각하게 된다.
                if (param.name === 'representative' && method !== 'representative') {
                  return null
                }

                if (param.name === 'representative') {
                  return (
                    <div key={param.name} className="space-y-1.5">
                      <Label>{param.label}</Label>
                      <select
                        aria-label={param.label}
                        className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                        value={value}
                        onChange={(event) =>
                          setOptions((now) => ({ ...now, [param.name]: event.target.value }))
                        }
                      >
                        {/* **이름을 손으로 적게 하지 않는다.** 고른 시편 중에서 고른다. */}
                        <option value="">자동 — 잔차가 가장 작은 시편</option>
                        {candidates
                          .filter((run) => picked.has(run.id))
                          .map((run) => (
                            <option key={run.id} value={run.record_name}>
                              {run.record_name}
                            </option>
                          ))}
                      </select>
                      <p className="text-muted-foreground text-xs">{param.help}</p>
                    </div>
                  )
                }

                if (param.name === 'terms') {
                  return (
                    <div key={param.name} className="space-y-1.5">
                      <Label>{param.label}</Label>
                      <select
                        aria-label={param.label}
                        className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                        value={value}
                        onChange={(event) =>
                          setOptions((now) => ({ ...now, [param.name]: event.target.value }))
                        }
                      >
                        {/* **0 을 「자동」 이라고 적는다.** 숫자 0 은 「항이 없다」 로
                            읽히는데 실제로는 「알아서 고르라」 는 뜻이다. */}
                        <option value="0">자동 — BIC 가 고름</option>
                        {[2, 3, 4, 5, 6, 7, 8].map((one) => (
                          <option key={one} value={String(one)}>
                            {one}항
                          </option>
                        ))}
                      </select>
                      <p className="text-muted-foreground text-xs">{param.help}</p>
                    </div>
                  )
                }

                return (
                  <div key={param.name} className="space-y-1.5">
                    <Label>{param.label}</Label>
                    {choices.length > 0 ? (
                      <select
                        aria-label={param.label}
                        className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                        value={value}
                        onChange={(event) =>
                          setOptions((now) => ({ ...now, [param.name]: event.target.value }))
                        }
                      >
                        {choices.map((one) => (
                          // **원래 값도 괄호로 적는다.** 논문·문서·결과 스냅샷에는
                          // `pooled` 로 남으므로, 사람 말만 보이면 그 둘을 잇지
                          // 못한다 — 남이 쓴 설정을 그대로 재현하려면 값을 알아야 한다.
                          //
                          // **추천은 서버가 정한 기본값이다.** 화면이 따로 적어 두면
                          // 새 방법이 붙을 때 그 판단이 여기 남아 낡는다.
                          <option key={one} value={one}>
                            {param.choice_labels?.[one]
                              ? `${param.choice_labels[one]} (${one})`
                              : one}
                            {one === String(param.default ?? '') ? ' · 추천' : ''}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        aria-label={param.label}
                        value={options[param.name] ?? ''}
                        placeholder={String(param.default ?? '')}
                        onChange={(event) =>
                          setOptions((now) => ({ ...now, [param.name]: event.target.value }))
                        }
                      />
                    )}
                    {/* **고른 것의 설명만 보인다.** 셋을 한 줄에 이어 적으면 지금
                        무엇을 고른 것인지 눈으로 찾아야 한다. */}
                    {param.choice_help?.[value] ? (
                      <p className="text-muted-foreground bg-muted/50 rounded-md p-2 text-xs">
                        {param.choice_help[value]}
                      </p>
                    ) : param.help ? (
                      <p className="text-muted-foreground text-xs">{param.help}</p>
                    ) : null}
                  </div>
                )
              })}
            </div>

            <div className="space-y-1.5">
              <Label>어느 시편으로 ({picked.size}건 고름)</Label>
              <div className="max-h-80 space-y-1 overflow-y-auto rounded-md border p-2">
                {candidates.map((run) => (
                  <label
                    key={run.id}
                    className="hover:bg-muted/50 flex items-center gap-2 rounded px-1 py-0.5 text-sm"
                  >
                    <input
                      type="checkbox"
                      aria-label={`${run.record_name} 고르기`}
                      checked={picked.has(run.id)}
                      // **`onClick` 이다.** `onChange` 에는 shiftKey 가 안 실린다.
                      onClick={(event) => selection.toggle(run.id, event)}
                      onChange={() => {}}
                    />
                    <span className="font-mono text-xs">{run.record_name}</span>
                    <span className="text-muted-foreground text-xs">{run.orientation}</span>
                  </label>
                ))}
                {candidates.length === 0 && (
                  <p className="text-muted-foreground p-2 text-xs">
                    이 계산에 쓸 수 있는 시험이 없습니다.
                  </p>
                )}
              </div>
              {/* **왜 이것만 뜨는지 말한다.** 아무 말 없이 걸러 두면 「내 시험이 왜
                  없지」 가 된다. 그리고 마스터커브 유무는 여기서 못 보므로 미리 알린다. */}
              {/* **왜 이것만 뜨는지 말한다.** 아무 말 없이 걸러 두면 「내 시험이
                  왜 없지」 가 된다. 그리고 **몇 건이 왜 빠졌는지**가 다음 할 일을
                  가리킨다 — 마스터커브를 만들면 그것도 쓸 수 있다. */}
              <p className="text-muted-foreground text-xs">
                마스터커브가 있는 시험만 보입니다.
                {gap.pending > 0 &&
                  ` ${gap.pending}건은 아직 안 겹쳐서 빠졌습니다 — 그 시험의 점탄성 탭에서 겹치면 쓸 수 있습니다.`}
                {gap.cannot > 0 &&
                  ` ${gap.cannot}건은 온도가 한 단이라 겹칠 수 없습니다(변형률 스윕).`}
                {gap.unknown > 0 && ` ${gap.unknown}건은 온도 단 수를 아직 안 세었습니다.`}
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>
              취소
            </Button>
            <Button onClick={() => void create()} disabled={busy || picked.size < 2}>
              {busy ? '적합 중…' : `시편 ${picked.size}건 적합`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
