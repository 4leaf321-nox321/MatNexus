/**
 * 워크벤치 — **업무 단위로 한 자리에서 민다**(ADR 0024 · 0058).
 *
 * 한 대상에 매달린 일은 그 대상의 화면에 남는다. 시험 하나를 처리하는 것은 시험 상세의
 * 일이고, 시험 스무 건에 같은 레시피를 걸고 견주어 채택하는 것이 여기 일이다.
 *
 * ## 무엇을 할지 먼저 고른다 — 묶음별로
 *
 * 들어오면 업무 목록이 묶음(시험 데이터 · 물성 카드 · 해석 덱 · 장비 · 형식)으로 선다. **그
 * 목록이 곧 「무엇을 할 수 있나」 판**이다 — 새 업무는 `workflows.ts` 에 정의 하나로 는다.
 *
 * ## 전용 화면도 도메인의 것이다
 *
 * 업무가 전용 화면을 가질 수 있다(ADR 0058) — 채택 검토대 · 한번에 처리 · 카드 패널. 그 화면은
 * 도메인 모듈에 살고 여기서는 끼우기만 한다(`views.tsx`). 이 선이 흐려지면 같은 일을 하는
 * 자리가 둘이 되고, 그때 ADR 0024 의 결정을 다시 봐야 한다.
 *
 * ## 되돌릴 수 없는 일을 대신 누르지 않는다
 *
 * 채택·확정·삭제·이관은 요약을 보이고 **사람이** 누른다. next 를 연타하는 흐름에서 가장
 * 비싼 것이 그것이다 — 확정된 카드는 값을 못 고치고, 그 값으로 해석이 이미 돌았을 수
 * 있다. 채택 검토대도 누르기 전에 무엇이 바뀌는지 세어 보인다.
 */

import { ArrowRight, Check, Circle, CircleAlert, Layers, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { basketApi } from '@/shared/api/basket'
import type { BasketItem, BasketRun, BasketRunDetail } from '@/shared/api/basket'
import { withJosa } from '@/shared/korean'
import { StepViewHost } from '@/modules/workbench/views'
import {
  COLLECT_AT,
  LEGACY_KEYS,
  WORKFLOW_GROUPS,
  hasView,
  stepKeyOf,
  workflowOf,
  workflowsIn,
} from '@/modules/workbench/workflows'
import type { StepCheck, Workflow } from '@/modules/workbench/workflows'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

/**
 * 담긴 것 하나로 가는 자리. `null` 이면 링크를 안 건다 — 사라진 것이 그렇다.
 *
 * **카드는 자기 주소가 없다.** 카드 상세 화면이 따로 없고 재료의 「CAE 카드」 탭에서
 * 펼쳐 본다 — 그래서 그 재료로 데려간다. 링크를 안 걸어 두면 「이름을 적고 그리로
 * 데려간다」 고 해 놓고 카드만 못 가는데, 확정 훑기는 담긴 것이 전부 카드다.
 */
function hrefOf(item: BasketItem): string | null {
  if (item.missing) return null
  if (item.kind === 'test_run') return `/test-runs/${item.target_id}`
  if (item.kind === 'material') return `/materials/${item.target_id}`
  if (item.kind === 'card' && item.material_id) return `/materials/${item.material_id}?tab=cards`
  return null
}

const KIND_LABELS: Record<string, string> = {
  test_run: '시험',
  material: '재료',
  card: '카드',
}

export default function WorkbenchPage() {
  // **기본은 내가 이어 할 것.** 남의 부서 작업은 「모든 부서」 로 넓혀 본다 — 보기는
  // 전원이지만(ADR 0035 3단계) 「계속」 에 섞이면 이어 할 것이 안 보인다.
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const running = useResource(() => basketApi.runs('running', scope), [scope])
  const [open, setOpen] = useState<BasketRunDetail | null>(null)
  const [error, setError] = useState<Error | null>(null)
  // **담고 나서 돌아오면 그 작업이 열려야 한다.** 목록으로 떨어뜨리면 방금 담은
  // 작업을 사람이 다시 골라야 하고, 진행 중인 것이 여럿이면 어느 것이었는지 헷갈린다.
  const [params, setParams] = useSearchParams()
  const asked = params.get('run')

  useEffect(() => {
    if (!asked || open?.id === asked) return
    void reload(asked)
    // 주소는 한 번 쓰고 지운다 — 남겨 두면 목록으로 나가려 할 때 다시 열린다.
    setParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked])

  async function reload(id: string) {
    try {
      setOpen(await basketApi.run(id))
      // 다시 읽혔으면 앞의 실패는 지난 일이다.
      setError(null)
      running.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('작업을 읽지 못했습니다.'))
    }
  }

  if (open) {
    return (
      <>
        {/* **연 작업 안에서도 오류가 보인다**(2026-10-04). 전에는 오류 표시가 목록 쪽에만 있어,
            진행 적기 · 끝내기가 실패해도 목록으로 돌아가기 전에는 아무것도 안 떴다. */}
        <ErrorNotice error={error} className="mb-4" />
        <RunView
          run={open}
          onBack={() => {
            setOpen(null)
            setError(null)
            running.reload()
          }}
          onChanged={() => void reload(open.id)}
          onOpen={(made) => {
            setOpen(made)
            setError(null)
            running.reload()
          }}
          onError={setError}
        />
      </>
    )
  }

  return (
    <section>
      <PageHeader
        title="워크벤치"
        description="여러 대상을 가로지르는 일을 업무 단위로 한 자리에서 밉니다. 시험 하나·재료 하나에 매달린 일은 그 화면에 그대로 있습니다."
      />

      <ErrorNotice error={running.error ?? error} className="mb-4" />

      {/* **업무 목록은 왼쪽, 이어 할 것은 오른쪽 열**(2026-10-04 지적). 전에는 「계속」 이 업무
          목록 위에 쌓여서, 하는 일이 많아질수록 새 일을 시작할 카드가 아래로 밀려 찾기 어려웠다.
          오른쪽 열은 제 안에서만 스크롤한다 — 몇 건이 쌓이든 왼쪽 목록의 자리는 그대로다. */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)] lg:items-start">
        <div className="min-w-0">
          <h2 className="mb-3 text-sm font-medium">무엇을 하시겠습니까</h2>
          {/* **비슷한 업무는 묶어 세운다** — 업무가 늘어도 어디서 찾을지가 그대로다. */}
          <div className="space-y-6">
            {WORKFLOW_GROUPS.map((group) => (
              <section key={group.key} aria-label={group.title}>
                <div className="mb-2 flex flex-wrap items-baseline gap-2">
                  <h3 className="font-medium">{group.title}</h3>
                  <span className="text-muted-foreground text-xs">{group.what}</span>
                </div>
                <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
                  {workflowsIn(group.key).map((flow) => (
                    <StartCard
                      key={flow.key}
                      flow={flow}
                      onStarted={(made) => {
                        setOpen(made)
                        running.reload()
                      }}
                      onError={setError}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>

        {/* **이어서 하기는 늘 보인다** — 어제 하던 것이 묻히면 서버에 둔 뜻이 없다. 좁은 화면에서는
            위로 올라오되 높이를 묶어, 업무 목록을 밀어내지 않는다. */}
        <aside
          aria-label="계속"
          className="order-first rounded-md border p-3 lg:sticky lg:top-24 lg:order-none"
        >
          <div className="mb-2 flex flex-wrap items-center gap-1">
            <h2 className="mr-auto text-sm font-medium">
              계속
              {running.data && running.data.length > 0 && (
                <span className="text-muted-foreground ml-1.5 font-normal">
                  {running.data.length}
                </span>
              )}
            </h2>
            <Button
              size="sm"
              variant={scope === 'mine' ? 'secondary' : 'ghost'}
              aria-pressed={scope === 'mine'}
              onClick={() => setScope('mine')}
            >
              우리 부서
            </Button>
            <Button
              size="sm"
              variant={scope === 'all' ? 'secondary' : 'ghost'}
              aria-pressed={scope === 'all'}
              onClick={() => setScope('all')}
            >
              모든 부서
            </Button>
          </div>
          {running.data && running.data.length === 0 ? (
            <p className="text-muted-foreground py-4 text-center text-sm">
              {scope === 'mine'
                ? '이어 할 작업이 없습니다. 왼쪽에서 업무를 골라 시작하세요.'
                : '진행 중인 작업이 없습니다.'}
            </p>
          ) : (
            <div className="max-h-72 space-y-2 overflow-y-auto lg:max-h-[calc(100vh-12rem)]">
              {(running.data ?? []).map((run) => (
                <ResumeRow key={run.id} run={run} onOpen={() => void reload(run.id)} />
              ))}
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}

function ResumeRow({ run, onOpen }: { run: BasketRun; onOpen: () => void }) {
  const flow = workflowOf(run.workflow_key)
  return (
    // 좁은 열에 서므로 **두 줄로** — 이름과 업무가 먼저, 담은 수 · 사람 · 때가 아래.
    <button
      type="button"
      onClick={onOpen}
      className="hover:bg-muted/50 flex w-full flex-col items-start gap-1 rounded-md border p-2.5 text-left"
    >
      <span className="w-full truncate font-medium" title={run.title}>
        {run.title}
      </span>
      <Badge variant="outline" className="max-w-full truncate">
        {flow?.title ?? run.workflow_key}
      </Badge>
      <span className="text-muted-foreground flex w-full flex-wrap gap-x-1.5 text-xs">
        <span>담은 것 {run.item_count}</span>
        {run.owner_name && <span>· {run.owner_name}</span>}
        <span className="ml-auto">{new Date(run.updated_at).toLocaleString('ko-KR')}</span>
      </span>
    </button>
  )
}

function StartCard({
  flow,
  onStarted,
  onError,
}: {
  flow: Workflow
  onStarted: (run: BasketRunDetail) => void
  onError: (error: Error) => void
}) {
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

  async function start() {
    setBusy(true)
    try {
      // **이름은 사람이 짓는다.** 「작업 3」 같은 이름이면 목록에서 어제 것을 못 찾는다.
      onStarted(
        await basketApi.create({
          workflow_key: flow.key,
          title: title.trim() || `${flow.title} ${new Date().toLocaleDateString('ko-KR')}`,
        })
      )
      setTitle('')
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('시작하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col rounded-md border p-3">
      <div className="mb-1 flex items-start gap-2">
        <Layers className="text-muted-foreground mt-0.5 size-4 shrink-0" />
        <h4 className="font-medium">{flow.title}</h4>
        <span className="ml-auto flex shrink-0 gap-1">
          {/* **전용 화면인지 미리 말한다.** 안내형은 다른 화면으로 데려가고, 전용은 여기서
              끝난다 — 고르기 전에 알아야 시간을 잴 수 있다. */}
          <Badge variant={hasView(flow) ? 'default' : 'outline'} className="text-xs">
            {hasView(flow) ? '전용 화면' : '안내'}
          </Badge>
          <Badge variant="secondary" className="text-xs">
            {flow.cadence}
          </Badge>
        </span>
      </div>
      <p className="text-muted-foreground mb-2 text-xs">{flow.when}</p>

      {/* **몇 단계인지 미리 보인다.** 시작하고 나서 알면 되돌리는 값이 든다. */}
      <ol className="text-muted-foreground mb-3 space-y-0.5 text-xs">
        {flow.steps.map((step, index) => (
          <li key={step.key}>
            {index + 1}. {step.title}
          </li>
        ))}
      </ol>

      <div className="mt-auto flex items-center gap-2">
        <Input
          className="h-8 text-xs"
          value={title}
          placeholder="이름 (예: EPDM 도어씰 2026-09)"
          aria-label={`${flow.title} 작업 이름`}
          onChange={(event) => setTitle(event.target.value)}
        />
        <Button size="sm" disabled={busy} onClick={() => void start()}>
          <Plus className="size-3.5" />
          시작
        </Button>
      </div>
    </div>
  )
}

function RunView({
  run,
  onBack,
  onChanged,
  onOpen,
  onError,
}: {
  run: BasketRunDetail
  onBack: () => void
  onChanged: () => void
  /** 다른 작업을 연다 — 다음 업무로 이어 갈 때. */
  onOpen: (run: BasketRunDetail) => void
  onError: (error: Error) => void
}) {
  const flow = workflowOf(run.workflow_key)
  /**
   * **이 작업을 이어 할 수 있나** — 그 부서 사람 · 시작한 사람 · 자료 관리자(ADR 0035 3단계).
   * 아니면 읽기로 연다: 단계는 둘러보되 서버에 적지 않고, 담기·빼기·끝내기를 막는다.
   */
  const writable = run.access?.can_edit ?? true
  const [peek, setPeek] = useState<string | null>(null)
  const saved = String((run.steps as Record<string, unknown>)?.at ?? '')
  // **옛 단계 이름은 지금 단계로 옮긴다**(`formerly`) — 업무를 합치며 단계가 줄어도 이어 하던
  // 작업이 1단계로 되돌아가지 않게.
  const at = (!writable && peek) || (flow && saved ? stepKeyOf(flow, saved) : saved) || ''
  const doneKeys = new Set(
    (Array.isArray((run.steps as Record<string, unknown>)?.done)
      ? ((run.steps as Record<string, unknown>).done as string[])
      : []
    ).map((key) => (flow ? stepKeyOf(flow, key) : key))
  )

  async function goTo(key: string, markDone?: string) {
    // 읽기로 연 작업은 **둘러보기만** 한다 — 남의 작업의 진행을 옮기지 않는다.
    if (!writable) {
      setPeek(key)
      return
    }
    try {
      const done = markDone ? [...new Set([...doneKeys, markDone])] : [...doneKeys]
      await basketApi.patch(run.id, { steps: { ...(run.steps ?? {}), at: key, done } })
      onChanged()
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('진행을 적지 못했습니다.'))
    }
  }

  async function finish() {
    try {
      await basketApi.patch(run.id, { status: 'finished' })
      onBack()
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('끝내지 못했습니다.'))
    }
  }

  const steps = flow?.steps ?? []
  const found = at === '' ? 0 : steps.findIndex((one) => one.key === at)
  const index = Math.max(0, found)
  // **모르는 단계로 조용히 옮기지 않는다.** 단계 이름이 바뀐 뒤 이어서 연 작업이
  // 아무 말 없이 1단계로 되돌아오면, 사람은 자기가 잘못 눌렀다고 여긴다.
  const movedBack = flow !== undefined && at !== '' && found < 0
  const step = steps[index]
  const renamed = run.workflow_key in LEGACY_KEYS
  // 판정은 담긴 것으로 한다 — 서버가 세어 준 사실(`facts`)이 그 안에 있다.
  const checks = new Map<string, StepCheck>()
  for (const one of steps) {
    const judged = one.judge?.(run.items)
    if (judged) checks.set(one.key, judged)
  }
  const next = flow?.next ? workflowOf(flow.next) : undefined

  return (
    <section aria-label="작업">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" onClick={onBack}>
          ← 목록
        </Button>
        <h1 className="text-lg font-medium">{run.title}</h1>
        <Badge variant="outline">{flow?.title ?? run.workflow_key}</Badge>
        {writable && (
          <Button size="sm" variant="outline" className="ml-auto" onClick={() => void finish()}>
            <Check className="size-3.5" />이 작업 끝내기
          </Button>
        )}
      </div>

      {!writable && (
        <div className="text-muted-foreground mb-4 rounded-md border border-dashed p-3 text-sm">
          읽기만 됩니다 — {run.access?.reason ?? '이 작업은 그 부서가 이어 합니다.'}
        </div>
      )}

      {/* **정의가 바뀌면 이어서 밀지 않는다.** 반쯤 읽어 미는 것이 더 나쁘다(ADR 0025). */}
      {!flow && (
        <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          이 작업의 워크플로(<code>{run.workflow_key}</code>)를 지금 화면이 모릅니다. 담긴
          것은 그대로 있으니 아래에서 보고, 진행은 새 작업으로 다시 시작하세요.
        </div>
      )}

      {flow && renamed && (
        <p className="text-muted-foreground mb-4 text-xs">
          이 작업은 예전 업무 이름(<code>{run.workflow_key}</code>)으로 시작했습니다 — 지금은
          「{flow.title}」 로 엽니다(ADR 0058). 담긴 것과 진행은 그대로입니다.
        </p>
      )}

      {movedBack && (
        <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          저장된 단계(<code>{at}</code>)를 지금 화면이 모릅니다 — 단계 구성이 바뀌었습니다.
          담긴 것은 그대로이니 처음 단계부터 다시 보세요.
        </div>
      )}

      {/* **단계를 가로로** — 전용 화면이 폭을 써야 한다(채택 검토대는 표와 곡선을 나란히 둔다). */}
      <ol className="mb-4 flex flex-wrap gap-2" aria-label="단계">
        {steps.map((one, position) => {
          const done = doneKeys.has(one.key)
          return (
            <li key={one.key}>
              <button
                type="button"
                onClick={() => void goTo(one.key)}
                aria-current={position === index}
                className={`flex items-start gap-1.5 rounded-md border px-2.5 py-1.5 text-left text-sm ${
                  position === index ? 'border-primary bg-muted/50' : 'hover:bg-muted/30'
                }`}
              >
                {done ? (
                  <Check className="mt-0.5 size-3.5 text-emerald-600" />
                ) : (
                  <Circle className="text-muted-foreground mt-0.5 size-3.5" />
                )}
                <span>
                  <span className="font-medium">
                    {position + 1}. {one.title}
                  </span>
                  {/* **표시는 됐는데 실제로는 안 끝난 것**을 조용히 넘기지 않는다. */}
                  {done && checks.get(one.key)?.ok === false && (
                    <span className="block text-xs text-amber-600">아직 남았습니다</span>
                  )}
                </span>
              </button>
            </li>
          )
        })}
      </ol>

      <div className="min-w-0 space-y-4">
        {step && (
          <div className="rounded-md border p-3">
            <h2 className="mb-1 font-medium">
              {index + 1}. {step.title}
            </h2>
            <p className="text-muted-foreground mb-3 text-sm">{step.what}</p>

            {checks.has(step.key) && <StepStatus check={checks.get(step.key)!} />}

            {/* **여기서 한다** — 도메인 화면을 그 자리에 세운다(ADR 0058). */}
            {step.view && (
              <div className="mb-3">
                <StepViewHost
                  view={step.view}
                  run={run}
                  writable={writable}
                  onChanged={onChanged}
                  onError={onError}
                />
              </div>
            )}

            {/* **일은 그 도메인 화면이 한다.** 여기서 복제하면 두 벌이 갈린다. */}
            {step.where && (
              <Button size="sm" variant="outline" asChild>
                <Link to={step.where}>
                  {/* **어디로 가는지 적는다.** 「그 화면으로」 는 누르기 전에는 모른다. */}
                  {step.whereLabel ?? '그 화면으로'} <ArrowRight className="size-3.5" />
                </Link>
              </Button>
            )}

            {/* **담는 자리로 데려간다.** 「담는 단추는 그 목록 화면에 있습니다」 만
                적어 두면 그 화면을 사람이 찾아야 한다 — 그러면 안 담는다. 전용 화면이
                있으면 거기서 담으므로 안 적는다. */}
            {step.collects && !step.view && (
              <p className="text-muted-foreground mt-2 text-xs">
                이 단계에서는 <b>{withJosa(KIND_LABELS[step.collects], '을/를')}</b> 담습니다.{' '}
                <Link
                  to={COLLECT_AT[step.collects]}
                  className="text-foreground underline underline-offset-2"
                >
                  {KIND_LABELS[step.collects]} 목록
                </Link>
                에서 고른 뒤 「추가」 를 누르면 여기 모입니다.
              </p>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {index > 0 && (
                <Button size="sm" variant="ghost" onClick={() => void goTo(steps[index - 1].key)}>
                  이전
                </Button>
              )}
              {index < steps.length - 1 && (
                <Button size="sm" onClick={() => void goTo(steps[index + 1].key, step.key)}>
                  다음: {steps[index + 1].title}
                  <ArrowRight className="size-3.5" />
                </Button>
              )}
              {index === steps.length - 1 && next && writable && (
                <HandOff run={run} next={next} onOpen={onOpen} onError={onError} />
              )}
            </div>
          </div>
        )}

        <Basket run={run} writable={writable} onChanged={onChanged} onError={onError} />
      </div>
    </section>
  )
}

/**
 * 다음 업무로 — **담은 것을 그대로 가져간다.** 올린 시험을 처리로 넘길 때 다시 고르게 하면
 * 고른 것이 그 자리에서 버려진다. 이 작업은 끝낸다고 적는다 — 「계속」 에 같은 시험을 든
 * 작업이 둘 서면 어느 쪽을 이어 할지 헷갈린다.
 */
function HandOff({
  run,
  next,
  onOpen,
  onError,
}: {
  run: BasketRunDetail
  next: Workflow
  onOpen: (run: BasketRunDetail) => void
  onError: (error: Error) => void
}) {
  const [busy, setBusy] = useState(false)

  async function go() {
    setBusy(true)
    try {
      const made = await basketApi.create({ workflow_key: next.key, title: run.title })
      const live = run.items.filter((one) => !one.missing)
      for (const kind of ['test_run', 'material', 'card'] as const) {
        const targets = live.filter((one) => one.kind === kind).map((one) => one.target_id)
        if (targets.length > 0) await basketApi.add(made.id, kind, targets)
      }
      await basketApi.patch(run.id, { status: 'finished' })
      onOpen(await basketApi.run(made.id))
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('다음 업무를 시작하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button size="sm" disabled={busy} onClick={() => void go()}>
      이 작업을 끝내고 「{next.title}」 로 이어 하기
      <ArrowRight className="size-3.5" />
    </Button>
  )
}

function StepStatus({ check }: { check: StepCheck }) {
  return (
    <div
      className={`mb-3 rounded-md border p-2 text-sm ${
        check.ok ? 'border-emerald-600/40 bg-emerald-500/5' : 'border-amber-500/40 bg-amber-500/5'
      }`}
      aria-label="이 단계 상태"
    >
      <span className="flex items-start gap-2">
        {check.ok ? (
          <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" />
        ) : (
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />
        )}
        <span>{check.say}</span>
      </span>
      {/* **이름을 적고, 그리로 데려간다.** 세기만 하면 어느 것인지 찾으러 다녀야 한다. */}
      {check.blocking && check.blocking.length > 0 && (
        <span className="mt-2 flex flex-wrap gap-1">
          {check.blocking.map((item) => {
            const href = hrefOf(item)
            return href ? (
              <Link
                key={item.id}
                to={href}
                className="bg-muted rounded px-1.5 py-0.5 text-xs underline underline-offset-2"
              >
                {item.label}
              </Link>
            ) : (
              <span key={item.id} className="bg-muted rounded px-1.5 py-0.5 text-xs">
                {item.label}
              </span>
            )
          })}
        </span>
      )}
      {check.go && (
        <span className="mt-2 block">
          <Button size="sm" variant="outline" asChild>
            <Link to={check.go.href}>
              {check.go.label} <ArrowRight className="size-3.5" />
            </Link>
          </Button>
        </span>
      )}
    </div>
  )
}

function Basket({
  run,
  writable,
  onChanged,
  onError,
}: {
  run: BasketRunDetail
  /** 뺄 수 있나 — 남의 부서 작업은 읽기로 연다(ADR 0035 3단계). */
  writable: boolean
  onChanged: () => void
  onError: (error: Error) => void
}) {
  async function remove(itemId: string) {
    try {
      await basketApi.remove(run.id, itemId)
      onChanged()
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('빼지 못했습니다.'))
    }
  }

  return (
    <div className="rounded-md border p-3" aria-label="바구니">
      <h2 className="mb-2 font-medium">바구니 {run.items.length}</h2>

      {run.items.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          아직 담은 것이 없습니다. 위 단계의 화면이나 시험·재료·카드 목록에서 담으면 여기
          모입니다 — 화면을 오가는 대신 대상이 따라옵니다.
        </p>
      ) : (
        // 담은 것이 수백이어도 단계 화면을 밀어내지 않게 높이를 묶는다.
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {run.items.map((item) => (
            <div key={item.id} className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="outline" className="text-[10px]">
                {KIND_LABELS[item.kind] ?? item.kind}
              </Badge>
              {/* **사라진 것도 줄을 지킨다.** 조용히 빠지면 「여덟이 왜 일곱이지」 가
                  된다(ADR 0025). */}
              {/* 담아 둔 것을 열어 보는 길. 사라진 것은 갈 데가 없다. */}
              {hrefOf(item) ? (
                <Link to={hrefOf(item)!} className="font-mono underline underline-offset-2">
                  {item.label}
                </Link>
              ) : (
                <span className={item.missing ? 'text-muted-foreground italic' : 'font-mono'}>
                  {item.label}
                </span>
              )}
              {item.kind === 'test_run' && item.material_label && (
                <span className="text-muted-foreground">{item.material_label}</span>
              )}
              {item.detail && <span className="text-muted-foreground">{item.detail}</span>}
              {writable && (
                <Button
                  size="icon"
                  variant="ghost"
                  className="ml-auto size-6"
                  aria-label={`${item.label} 제거`}
                  onClick={() => void remove(item.id)}
                >
                  <X className="size-3" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
