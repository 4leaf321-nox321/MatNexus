/**
 * 워크벤치 — **가로지르는 일을 한 자리에서 민다**(ADR 0024).
 *
 * 한 대상에 매달린 일은 그 대상의 화면에 남는다. 시험 하나를 처리하는 것은 시험 상세의
 * 일이고, 시험 스무 건에 같은 레시피를 거는 것이 여기 일이다.
 *
 * ## 무엇을 할지 먼저 고른다
 *
 * 들어오면 워크플로 목록이 뜬다. **그 목록이 곧 「지금 걸려 있는 일」 판**이다 — 새
 * 시나리오는 `workflows.ts` 에 파일 하나로 는다.
 *
 * ## 여기에 도메인이 없다
 *
 * 담고·빼고·어디까지 왔는지 적어 두는 것이 전부다. 실제 일은 각 도메인 화면이 한다 —
 * 이 선이 흐려지면 같은 일을 하는 자리가 둘이 되고, 그때 ADR 0024 의 결정을 다시 봐야
 * 한다.
 *
 * ## 되돌릴 수 없는 일을 대신 누르지 않는다
 *
 * 채택·확정·삭제·이관은 요약을 보이고 **사람이** 누른다. next 를 연타하는 흐름에서 가장
 * 비싼 것이 그것이다 — 확정된 카드는 값을 못 고치고, 그 값으로 해석이 이미 돌았을 수
 * 있다.
 */

import { ArrowRight, Check, Circle, CircleAlert, Layers, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { basketApi } from '@/shared/api/basket'
import type { BasketItem, BasketRun, BasketRunDetail } from '@/shared/api/basket'
import { withJosa } from '@/shared/korean'
import { BundleBar } from '@/modules/fitting/BundleBar'
import { fittingApi } from '@/modules/fitting/api'
import { COLLECT_AT, WORKFLOWS, workflowOf } from '@/modules/workbench/workflows'
import type { StepCheck, Workflow } from '@/modules/workbench/workflows'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

/**
 * 담긴 것 하나로 가는 자리. `null` 이면 링크를 안 건다 — **사라진 것과 카드**가 그렇다
 * (카드는 목록 안에서 펼쳐 보므로 그 카드만의 주소가 없다).
 */
function hrefOf(item: BasketItem): string | null {
  if (item.missing) return null
  if (item.kind === 'test_run') return `/test-runs/${item.target_id}`
  if (item.kind === 'material') return `/materials/${item.target_id}`
  return null
}

const KIND_LABELS: Record<string, string> = {
  test_run: '시험',
  material: '재료',
  card: '카드',
}

export default function WorkbenchPage() {
  const running = useResource(() => basketApi.runs('running'), [])
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
      running.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('작업을 읽지 못했습니다.'))
    }
  }

  if (open) {
    return (
      <RunView
        run={open}
        onBack={() => {
          setOpen(null)
          running.reload()
        }}
        onChanged={() => void reload(open.id)}
        onError={setError}
      />
    )
  }

  return (
    <section>
      <PageHeader
        title="워크벤치"
        description="여러 대상을 가로지르는 일을 한 자리에서 밉니다. 시험 하나·재료 하나에 매달린 일은 그 화면에 그대로 있습니다."
      />

      <ErrorNotice error={running.error ?? error} className="mb-4" />

      {/* **이어서 하기가 먼저다.** 어제 하던 것이 아래에 묻히면 서버에 둔 뜻이 없다. */}
      {(running.data ?? []).length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-medium">이어서 하기</h2>
          <div className="space-y-2">
            {(running.data ?? []).map((run) => (
              <ResumeRow key={run.id} run={run} onOpen={() => void reload(run.id)} />
            ))}
          </div>
        </div>
      )}

      <h2 className="mb-2 text-sm font-medium">무엇을 하시겠습니까</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {WORKFLOWS.map((flow) => (
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
  )
}

function ResumeRow({ run, onOpen }: { run: BasketRun; onOpen: () => void }) {
  const flow = workflowOf(run.workflow_key)
  return (
    <button
      type="button"
      onClick={onOpen}
      className="hover:bg-muted/50 flex w-full flex-wrap items-center gap-2 rounded-md border p-3 text-left"
    >
      <span className="font-medium">{run.title}</span>
      <Badge variant="outline">{flow?.title ?? run.workflow_key}</Badge>
      <span className="text-muted-foreground text-xs">담은 것 {run.item_count}</span>
      {run.owner_name && (
        <span className="text-muted-foreground text-xs">· {run.owner_name}</span>
      )}
      <span className="text-muted-foreground ml-auto text-xs">
        {new Date(run.updated_at).toLocaleString('ko-KR')}
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
      <div className="mb-1 flex items-center gap-2">
        <Layers className="text-muted-foreground size-4" />
        <h3 className="font-medium">{flow.title}</h3>
        <Badge variant="secondary" className="ml-auto text-xs">
          {flow.cadence}
        </Badge>
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
  onError,
}: {
  run: BasketRunDetail
  onBack: () => void
  onChanged: () => void
  onError: (error: Error) => void
}) {
  const flow = workflowOf(run.workflow_key)
  const at = String((run.steps as Record<string, unknown>)?.at ?? flow?.steps[0]?.key ?? '')
  const doneKeys = new Set(
    Array.isArray((run.steps as Record<string, unknown>)?.done)
      ? ((run.steps as Record<string, unknown>).done as string[])
      : []
  )

  async function goTo(key: string, markDone?: string) {
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
  const index = Math.max(
    0,
    steps.findIndex((one) => one.key === at)
  )
  const step = steps[index]
  const cardIds = run.items
    .filter((one) => one.kind === 'card' && !one.missing)
    .map((one) => one.target_id)
  // 판정은 담긴 것으로 한다 — 서버가 세어 준 사실(`facts`)이 그 안에 있다.
  const checks = new Map<string, StepCheck>()
  for (const one of steps) {
    const judged = one.judge?.(run.items)
    if (judged) checks.set(one.key, judged)
  }

  return (
    <section aria-label="작업">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" onClick={onBack}>
          ← 목록
        </Button>
        <h1 className="text-lg font-medium">{run.title}</h1>
        <Badge variant="outline">{flow?.title ?? run.workflow_key}</Badge>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => void finish()}>
          <Check className="size-3.5" />이 작업 끝내기
        </Button>
      </div>

      {/* **정의가 바뀌면 이어서 밀지 않는다.** 반쯤 읽어 미는 것이 더 나쁘다(ADR 0025). */}
      {!flow && (
        <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          이 작업의 워크플로(<code>{run.workflow_key}</code>)를 지금 화면이 모릅니다. 담긴
          것은 그대로 있으니 아래에서 보고, 진행은 새 작업으로 다시 시작하세요.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(220px,280px)_minmax(0,1fr)] lg:items-start">
        <ol className="space-y-1" aria-label="단계">
          {steps.map((one, position) => {
            const done = doneKeys.has(one.key)
            return (
              <li key={one.key}>
                <button
                  type="button"
                  onClick={() => void goTo(one.key)}
                  aria-current={position === index}
                  className={`flex w-full items-start gap-2 rounded-md border p-2 text-left text-xs ${
                    position === index ? 'border-primary bg-muted/50' : ''
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
                    <span className="text-muted-foreground block">{one.what}</span>
                    {/* **표시는 됐는데 실제로는 안 끝난 것**을 조용히 넘기지 않는다. */}
                    {done && checks.get(one.key)?.ok === false && (
                      <span className="block text-amber-600">아직 남았습니다</span>
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

              {/* **담아 둔 것으로 바로 내보낸다.** 카드 목록으로 보내 다시 고르게
                  하면, 담아 둔 값이 그 자리에서 버려진다. 띠는 카드 화면의 것을
                  그대로 세운다 — 여기서 다시 만들면 형식·단위계 안내가 두 벌로 갈린다. */}
              {step.key === 'export' && cardIds.length > 0 && (
                <ExportStep ids={cardIds} onError={onError} />
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
                  적어 두면 그 화면을 사람이 찾아야 한다 — 그러면 안 담는다. */}
              {step.collects && (
                <p className="text-muted-foreground mt-2 text-xs">
                  이 단계에서는 <b>{withJosa(KIND_LABELS[step.collects], '을/를')}</b> 담습니다.{' '}
                  <Link
                    to={COLLECT_AT[step.collects]}
                    className="text-foreground underline underline-offset-2"
                  >
                    {KIND_LABELS[step.collects]} 목록
                  </Link>
                  에서 고른 뒤 「담기」 를 누르면 여기 모입니다.
                </p>
              )}

              <div className="mt-3 flex items-center gap-2">
                {index > 0 && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void goTo(steps[index - 1].key)}
                  >
                    이전
                  </Button>
                )}
                {index < steps.length - 1 && (
                  <Button size="sm" onClick={() => void goTo(steps[index + 1].key, step.key)}>
                    다음: {steps[index + 1].title}
                    <ArrowRight className="size-3.5" />
                  </Button>
                )}
              </div>
            </div>
          )}

          <Basket run={run} onChanged={onChanged} onError={onError} />
        </div>
      </div>
    </section>
  )
}

/**
 * 묶음 내보내기 — **카드 목록의 그 띠를 그대로 세운다**(`BundleBar`).
 *
 * 형식 목록은 서버가 준다. 화면이 적어 두면 새 덱 형식을 붙일 때 두 곳을 고쳐야 한다.
 */
function ExportStep({ ids, onError }: { ids: string[]; onError: (error: Error) => void }) {
  const formats = useResource(() => fittingApi.formats(), [])
  return (
    <BundleBar
      ids={ids}
      formats={formats.data ?? []}
      // 바구니에서 빼는 것은 바구니의 일이다 — 여기서 비우면 담은 기록이 조용히 사라진다.
      onClear={() => {}}
      onError={onError}
    />
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
  onChanged,
  onError,
}: {
  run: BasketRunDetail
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
          아직 담은 것이 없습니다. 시험·재료·카드 목록에서 담으면 여기 모입니다 — 화면을
          오가는 대신 대상이 따라옵니다.
        </p>
      ) : (
        <div className="space-y-1">
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
              {item.detail && <span className="text-muted-foreground">{item.detail}</span>}
              <Button
                size="icon"
                variant="ghost"
                className="ml-auto size-6"
                aria-label={`${item.label} 빼기`}
                onClick={() => void remove(item.id)}
              >
                <X className="size-3" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
