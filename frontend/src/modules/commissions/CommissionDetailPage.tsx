/**
 * 측정 의뢰 한 건 — **항목·시험·이력·옮기기.**
 *
 * 위는 무엇을 왜 재 달라는 것인지, 가운데는 항목마다 어떤 시험이 붙었고 결과가 채택됐는지,
 * 아래는 누가 언제 무슨 말로 상태를 옮겼는지. 단추는 **서버가 말한 것만** 선다 —
 * 어느 쪽(낸 사람·받는 부서)인지, 지금 어디로 갈 수 있는지, 말이 필요한지는 `side` ·
 * `allowed` · `note_required` 가 준다. 화면이 규칙을 외우면 서버와 어긋나는 날이 온다.
 *
 * 시험을 붙이는 것은 받는 쪽이다(`can_link`). 후보는 같은 시료·같은 종류의 아직 안 붙은
 * 시험 — 서버가 골라 준다. 붙으면 「접수」 는 저절로 「시험 중」 이 된다.
 */

import { useState } from 'react'
import { ArrowLeft, Link2, Pencil, Trash2, Unlink } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Progress, StatusBadge } from '@/modules/commissions/CommissionsPage'
import {
  ItemsEditor,
  deliverableLabel,
  draftFromItem,
  itemReady,
  toPayload,
} from '@/modules/commissions/ItemsEditor'
import type { ItemDraft } from '@/modules/commissions/ItemsEditor'
import { SamplePicker } from '@/modules/commissions/SamplePicker'
import { STATUS_TONES, commissionsApi } from '@/modules/commissions/api'
import type { CommissionDetail, CommissionEvent, CommissionItem } from '@/modules/commissions/api'
import { fittingApi } from '@/modules/fitting/api'
import type { BlockSpec } from '@/modules/fitting/api'
import type { Sample } from '@/modules/materials/api'
import { testsApi } from '@/modules/tests/api'
import type { TestType } from '@/modules/tests/api'
import { workspacesApi } from '@/modules/workspaces/api'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Stamp } from '@/shared/components/Stamp'
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
import { display, toDisplay } from '@/shared/units'

const TEXTAREA =
  'border-input bg-transparent focus-visible:ring-ring w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none'

export default function CommissionDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const item = useResource(() => commissionsApi.get(id), [id])
  const testTypes = useResource(() => testsApi.types(), [])
  const blocks = useResource(() => fittingApi.blocks(), [])
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const detail = item.data

  async function act(work: () => Promise<unknown>, fallback: string) {
    setBusy(true)
    setError(null)
    try {
      await work()
      item.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(fallback))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <Link
        to="/commissions"
        className="text-muted-foreground hover:text-foreground mb-3 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" />
        측정 의뢰 목록
      </Link>

      <ErrorNotice error={item.error ?? error} className="mb-4" />

      {detail && (
        <>
          <header className="mb-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground tabular-nums">#{detail.seq}</span>
              <h1 className="text-xl font-semibold">{detail.title}</h1>
              <StatusBadge item={detail} />
              {detail.priority === 'urgent' && (
                <Badge variant="destructive">{detail.priority_label}</Badge>
              )}
              {detail.can_edit && (
                <div className="ml-auto flex shrink-0 gap-1">
                  <Button size="sm" variant="ghost" aria-label="편집" onClick={() => setEditing(true)}>
                    <Pencil className="size-3.5" />
                    편집
                  </Button>
                  {detail.status === 'draft' && (
                    <Button size="sm" variant="ghost" aria-label="삭제" onClick={() => setDeleting(true)}>
                      <Trash2 className="size-3.5" />
                      삭제
                    </Button>
                  )}
                </div>
              )}
            </div>
            <p className="text-muted-foreground mt-1 text-sm">
              {detail.created_by ?? '알 수 없음'} · <Stamp at={detail.created_at} /> ·{' '}
              {detail.requester_workspace.name} → {detail.lab_workspace.name}
              {detail.due_on && <> · 기한 {detail.due_on}</>}
            </p>
          </header>

          <section className="mb-6 grid gap-4 rounded-md border p-4 sm:grid-cols-[1fr_auto]">
            <div className="space-y-3">
              <div>
                <h2 className="text-muted-foreground mb-1 text-xs font-medium">목적</h2>
                <p className="whitespace-pre-wrap">{detail.purpose}</p>
              </div>
              <div>
                <h2 className="text-muted-foreground mb-1 text-xs font-medium">
                  {detail.sample ? '시료' : '새 재료 — 시료 미등록'}
                </h2>
                {detail.sample ? (
                  <p>
                    <Link to={`/materials/${detail.sample.material_id}`} className="font-medium hover:underline">
                      {detail.sample.record_name}
                    </Link>{' '}
                    <span className="text-muted-foreground">· {detail.sample.material_name}</span>
                  </p>
                ) : (
                  <p className="whitespace-pre-wrap">{detail.material_hint}</p>
                )}
                {/* 시료가 이어진 뒤에도 「무엇을 달라고 했는지」 는 남는다. */}
                {detail.sample && detail.material_hint && (
                  <p className="text-muted-foreground mt-1 text-sm">의뢰 당시: {detail.material_hint}</p>
                )}
                {/* **받는 쪽이 재료·시료를 등록한 뒤 잇는다.** 시료가 없으면 시험을 못 붙인다. */}
                {!detail.sample && detail.can_resolve && (
                  <AttachSample
                    busy={busy}
                    onAttach={(sampleId) =>
                      act(() => commissionsApi.attachSample(detail.id, sampleId), '시료를 잇지 못했습니다.')
                    }
                  />
                )}
                {!detail.sample && !detail.can_resolve && (
                  <p className="text-muted-foreground mt-1 text-xs">
                    받는 부서가 접수한 뒤 재료·시료를 등록해 이 의뢰에 잇습니다.
                  </p>
                )}
                {detail.sample_plan && (
                  <p className="text-muted-foreground mt-1 whitespace-pre-wrap text-sm">{detail.sample_plan}</p>
                )}
              </div>
            </div>
            <div className="min-w-48 space-y-2 text-sm">
              <div>
                <span className="text-muted-foreground block text-xs">진행</span>
                <Progress progress={detail.progress} />
              </div>
              <div>
                <span className="text-muted-foreground block text-xs">담당자</span>
                {detail.can_assign ? (
                  <select
                    aria-label="담당자"
                    className="border-input bg-background h-8 rounded-md border px-2 text-sm"
                    value={detail.assignee?.id ?? ''}
                    disabled={busy}
                    onChange={(event) =>
                      act(
                        () => commissionsApi.assign(detail.id, event.target.value || null),
                        '담당자를 정하지 못했습니다.'
                      )
                    }
                  >
                    <option value="">— 미정 —</option>
                    {(detail.assignees ?? []).map((one) => (
                      <option key={one.id} value={one.id}>
                        {one.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span>{detail.assignee?.name ?? '미정'}</span>
                )}
              </div>
            </div>
          </section>

          <section className="mb-6">
            <h2 className="mb-2 font-medium">항목</h2>
            <div className="space-y-3">
              {detail.items.map((one) => (
                <ItemCard
                  key={one.id}
                  detail={detail}
                  item={one}
                  testType={testTypes.data?.find((type) => type.key === one.test_type_key)}
                  blocks={blocks.data ?? []}
                  busy={busy}
                  onLink={(runId) =>
                    act(() => commissionsApi.linkRun(detail.id, one.id, runId), '시험을 붙이지 못했습니다.')
                  }
                  onUnlink={(runId) =>
                    act(() => commissionsApi.unlinkRun(detail.id, one.id, runId), '연결을 풀지 못했습니다.')
                  }
                  testTypes={testTypes.data ?? []}
                  onResolve={(key) =>
                    act(() => commissionsApi.resolveItem(detail.id, one.id, key), '종류를 정하지 못했습니다.')
                  }
                />
              ))}
            </div>
          </section>

          <section className="mb-6">
            <h2 className="mb-2 font-medium">이력</h2>
            <Timeline events={detail.events} />
          </section>

          <ActionBox
            detail={detail}
            onDone={() => {
              setError(null)
              item.reload()
            }}
          />

          {editing && (
            <EditDialog
              detail={detail}
              testTypes={testTypes.data ?? []}
              blocks={blocks.data ?? []}
              onClose={() => setEditing(false)}
              onDone={() => {
                setEditing(false)
                item.reload()
              }}
            />
          )}

          <ConfirmDialog
            open={deleting}
            title="작성 중인 의뢰를 지웁니다"
            busy={busy}
            body={
              <>
                <b>
                  #{detail.seq} {detail.title}
                </b>{' '}
                이 항목 {detail.items.length}건과 함께 사라집니다. 아직 낸 것이 아니라 받는 부서는 모릅니다.
              </>
            }
            onClose={() => setDeleting(false)}
            onConfirm={() =>
              act(async () => {
                await commissionsApi.remove(detail.id)
                navigate('/commissions')
              }, '지우지 못했습니다.')
            }
          />
        </>
      )}
    </div>
  )
}

/** 조건을 사람 단위로 — 입력 단위(`input_units`)가 있으면 그것으로, 없으면 정의의 표시 단위로. */
function conditionText(item: CommissionItem, testType: TestType | undefined): string {
  const parts: string[] = []
  for (const field of testType?.conditions ?? []) {
    const raw = item.conditions[field.key]
    if (raw === undefined || raw === null || raw === '') continue
    if (typeof raw === 'number' && field.si_unit) {
      const { unit } = display(field.si_unit, field.dimension)
      const shown = toDisplay(raw, field.si_unit, field.dimension)
      parts.push(`${field.label} ${Number(shown.toPrecision(6))}${unit ? ` ${unit}` : ''}`)
    } else {
      parts.push(`${field.label} ${String(raw)}`)
    }
  }
  if (parts.length === 0 && Object.keys(item.conditions).length > 0) {
    // 정의를 아직 못 읽었으면 키 그대로라도 보인다 — 빈 칸보다 낫다.
    return Object.entries(item.conditions)
      .map(([key, value]) => `${key} ${String(value)}`)
      .join(' · ')
  }
  return parts.join(' · ')
}

function ItemCard({
  detail,
  item,
  testType,
  blocks,
  busy,
  onLink,
  onUnlink,
  testTypes,
  onResolve,
}: {
  detail: CommissionDetail
  item: CommissionItem
  testType: TestType | undefined
  blocks: BlockSpec[]
  busy: boolean
  onLink: (runId: string) => void
  onUnlink: (runId: string) => void
  testTypes: TestType[]
  onResolve: (testTypeKey: string) => void
}) {
  const [picked, setPicked] = useState('')
  const [pickedType, setPickedType] = useState('')
  const candidates = item.candidates ?? []
  const conditions = conditionText(item, testType)
  const done = item.done >= item.count

  return (
    <div className="rounded-md border p-3" aria-label={`${item.position + 1}번 항목`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground tabular-nums">{item.position + 1}.</span>
        {item.test_type_label ? (
          <span className="font-medium">{item.test_type_label}</span>
        ) : (
          <Badge variant="outline" className={STATUS_TONES.on_hold}>
            시험 종류 미정
          </Badge>
        )}
        {item.property_hint && <span className="font-medium">{item.property_hint}</span>}
        {item.orientations.length > 0 && (
          <span className="text-muted-foreground">{item.orientations.join('·')}</span>
        )}
        <span className="text-muted-foreground">× {item.count}</span>
        <Badge variant="outline">{deliverableLabel(item.deliverable, blocks)}</Badge>
        <span className={`ml-auto tabular-nums ${done ? 'text-emerald-700 dark:text-emerald-300' : ''}`}>
          채택 {item.done}/{item.count}
        </span>
      </div>
      {conditions && <p className="text-muted-foreground mt-1 text-sm">{conditions}</p>}
      {item.note && <p className="mt-1 text-sm">{item.note}</p>}
      {/* **종류 미정은 받는 쪽이 정한다.** 정해져야 시험을 붙일 수 있다. */}
      {!item.test_type_key && detail.can_resolve && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <select
            aria-label={`${item.position + 1}번 항목의 시험 종류 정하기`}
            className="border-input bg-background h-8 rounded-md border px-2 text-sm"
            value={pickedType}
            onChange={(event) => setPickedType(event.target.value)}
          >
            <option value="">— 무슨 시험으로 잴지 —</option>
            {testTypes.map((one) => (
              <option key={one.key} value={one.key}>
                {one.label}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || !pickedType}
            onClick={() => {
              onResolve(pickedType)
              setPickedType('')
            }}
          >
            종류 정하기
          </Button>
        </div>
      )}

      {(item.runs.length > 0 || (detail.can_link && item.test_type_key && detail.sample)) && (
        <div className="mt-2 border-t pt-2">
          {item.runs.length > 0 && (
            <ul className="space-y-1 text-sm" aria-label={`${item.position + 1}번 항목의 시험`}>
              {item.runs.map((run) => (
                <li key={run.id} className="flex items-center gap-2">
                  <Link to={`/test-runs/${run.id}`} className="hover:underline">
                    {run.record_name}
                  </Link>
                  {run.adopted ? (
                    <Badge variant="outline" className={STATUS_TONES.delivered}>
                      채택
                    </Badge>
                  ) : (
                    <Badge variant="secondary">채택 전</Badge>
                  )}
                  {detail.can_link && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="ml-auto size-7"
                      aria-label={`${run.record_name} 연결 해제`}
                      title="연결을 풉니다 — 시험은 남습니다"
                      disabled={busy}
                      onClick={() => onUnlink(run.id)}
                    >
                      <Unlink className="size-3.5" />
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {detail.can_link && item.test_type_key && detail.sample && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <select
                aria-label={`${item.position + 1}번 항목에 붙일 시험`}
                className="border-input bg-background h-8 rounded-md border px-2 text-sm"
                value={picked}
                onChange={(event) => setPicked(event.target.value)}
              >
                <option value="">
                  {candidates.length > 0
                    ? '— 붙일 시험 (같은 시료·같은 종류) —'
                    : '붙일 시험 없음 — 이 시료에 시험을 등록하세요'}
                </option>
                {candidates.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.record_name}
                    {run.adopted ? ' · 채택' : ''}
                  </option>
                ))}
              </select>
              <Button size="sm" variant="outline" disabled={busy || !picked} onClick={() => {
                onLink(picked)
                setPicked('')
              }}>
                <Link2 className="size-3.5" />
                붙이기
              </Button>
              {detail.sample && (
                <Link
                  to={`/materials/${detail.sample.material_id}`}
                  className="text-muted-foreground ml-auto text-xs hover:underline"
                >
                  재료 상세에서 시편·시험 등록 →
                </Link>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Timeline({ events }: { events: CommissionEvent[] }) {
  return (
    <ol className="space-y-2" aria-label="이력">
      {events.map((one) => {
        const moved = one.from_status !== one.to_status
        const registered = one.from_status === null
        return (
          <li key={one.id} className="flex gap-3 rounded-md border p-3">
            <div className="text-muted-foreground w-36 shrink-0">
              <Stamp at={one.at} />
              <p className="mt-0.5 truncate">{one.by ?? '알 수 없음'}</p>
            </div>
            <div className="min-w-0 flex-1">
              {registered ? (
                <Badge variant="outline" className={STATUS_TONES[one.to_status] ?? ''}>
                  등록 · {one.to_status_label}
                </Badge>
              ) : moved ? (
                <Badge variant="outline" className={STATUS_TONES[one.to_status] ?? ''}>
                  {one.to_status_label} 로 옮김
                </Badge>
              ) : (
                <Badge variant="secondary">기록</Badge>
              )}
              {one.note && <p className="mt-1.5 whitespace-pre-wrap">{one.note}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** 옮기거나 말을 보탠다. 단추는 서버가 말한 것만, 말이 필요한 곳은 말 없이는 안 눌린다. */
function ActionBox({ detail, onDone }: { detail: CommissionDetail; onDone: () => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const trimmed = note.trim()

  async function send(status: string | null) {
    setBusy(true)
    setError(null)
    try {
      await commissionsApi.event(detail.id, { status, note: trimmed || null })
      setNote('')
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('보내지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-md border p-4">
      <Label htmlFor="commission-note" className="mb-1.5 block">
        댓글 등록
      </Label>
      <textarea
        id="commission-note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={3}
        className={TEXTAREA}
        placeholder={
          detail.allowed.length > 0
            ? '언제쯤인지, 왜인지, 어디서 보는지 — 상태를 옮길 때 함께 남습니다.'
            : '덧붙일 말을 남깁니다. 상태는 받는 부서와 낸 사람이 옮깁니다.'
        }
      />
      <ErrorNotice error={error} className="mt-2" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {detail.allowed.map((status) => {
          const needs = detail.note_required.includes(status)
          return (
            <Button
              key={status}
              size="sm"
              variant={
                status === 'delivered' || status === 'closed' || status === 'submitted' ? 'default' : 'outline'
              }
              disabled={busy || (needs && !trimmed)}
              title={needs && !trimmed ? '말을 적어야 옮길 수 있습니다' : undefined}
              onClick={() => send(status)}
            >
              {detail.allowed_labels[status] ?? status}
            </Button>
          )
        })}
        <Button size="sm" variant="ghost" className="ml-auto" disabled={busy || !trimmed} onClick={() => send(null)}>
          말만 남기기
        </Button>
      </div>
    </section>
  )
}

/** 낸 것을 고친다 — 작성 중·접수 대기에서. 항목은 표 한 장으로 통째로 바뀐다. */
function EditDialog({
  detail,
  testTypes,
  blocks,
  onClose,
  onDone,
}: {
  detail: CommissionDetail
  testTypes: TestType[]
  blocks: BlockSpec[]
  onClose: () => void
  onDone: () => void
}) {
  const [title, setTitle] = useState(detail.title)
  const [purpose, setPurpose] = useState(detail.purpose)
  const [samplePlan, setSamplePlan] = useState(detail.sample_plan ?? '')
  const [dueOn, setDueOn] = useState(detail.due_on ?? '')
  const [priority, setPriority] = useState(detail.priority)
  const [lab, setLab] = useState(detail.lab_workspace.slug)
  const [materialHint, setMaterialHint] = useState(detail.material_hint ?? '')
  const [items, setItems] = useState<ItemDraft[]>(() =>
    detail.items.map((one) =>
      draftFromItem(one, testTypes.find((type) => type.key === one.test_type_key))
    )
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const labs = useResource(() => workspacesApi.options(), [])

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await commissionsApi.update(detail.id, {
        title: title.trim(),
        purpose: purpose.trim(),
        sample_plan: samplePlan.trim() || null,
        due_on: dueOn || null,
        priority,
        lab_workspace_slug: lab,
        material_hint: detail.sample ? detail.material_hint : materialHint.trim() || null,
        items: items.map((one) =>
          toPayload(one, testTypes.find((type) => type.key === one.test_type_key))
        ),
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('고치지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>의뢰 편집</DialogTitle>
          <DialogDescription>
            접수되기 전까지만 고칠 수 있습니다. 항목은 표 전체가 바뀝니다.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="edit-title">제목</Label>
            <Input id="edit-title" value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-purpose">목적</Label>
            <textarea id="edit-purpose" className={TEXTAREA} rows={3} value={purpose} onChange={(event) => setPurpose(event.target.value)} />
          </div>
          {!detail.sample && (
            <div className="space-y-1.5">
              <Label htmlFor="edit-material-hint">새 재료 — 무엇인지</Label>
              <textarea id="edit-material-hint" className={TEXTAREA} rows={2} value={materialHint} onChange={(event) => setMaterialHint(event.target.value)} />
            </div>
          )}
          <ItemsEditor items={items} onChange={setItems} testTypes={testTypes} blocks={blocks} />
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-3">
              <Label htmlFor="edit-plan">시료 전달</Label>
              <textarea id="edit-plan" className={TEXTAREA} rows={2} value={samplePlan} onChange={(event) => setSamplePlan(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-due">희망 기한</Label>
              <Input id="edit-due" type="date" value={dueOn} onChange={(event) => setDueOn(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-priority">우선순위</Label>
              <select id="edit-priority" className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm" value={priority} onChange={(event) => setPriority(event.target.value)}>
                <option value="normal">보통</option>
                <option value="urgent">급함</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-lab">받는 부서</Label>
              <select id="edit-lab" className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm" value={lab} onChange={(event) => setLab(event.target.value)}>
                {(labs.data ?? [{ slug: detail.lab_workspace.slug, path: detail.lab_workspace.name }]).map((one) => (
                  <option key={one.slug} value={one.slug}>
                    {one.path}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button
            disabled={
              busy ||
              !title.trim() ||
              !purpose.trim() ||
              (!detail.sample && !materialHint.trim()) ||
              !items.every(itemReady)
            }
            onClick={save}
          >
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 새 재료 의뢰에 등록된 시료를 잇는다 — 받는 쪽. 재료·시료는 재료 화면에서 먼저 만든다. */
function AttachSample({
  busy,
  onAttach,
}: {
  busy: boolean
  onAttach: (sampleId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [sample, setSample] = useState<Sample | null>(null)
  if (!open) {
    return (
      <Button size="sm" variant="outline" className="mt-2" onClick={() => setOpen(true)}>
        시료 잇기
      </Button>
    )
  }
  return (
    <div className="mt-2 grid gap-3 rounded-md border p-3 sm:grid-cols-2" aria-label="시료 잇기">
      <SamplePicker sample={sample} onChange={setSample} idPrefix="attach" />
      <div className="flex items-end gap-2 sm:col-span-2">
        <Button
          size="sm"
          disabled={busy || !sample}
          onClick={() => {
            if (sample) onAttach(sample.id)
            setOpen(false)
          }}
        >
          이 시료로 잇기
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          취소
        </Button>
        <Link to="/materials" className="text-muted-foreground ml-auto text-xs hover:underline">
          재료가 없으면 재료 목록에서 먼저 등록 →
        </Link>
      </div>
    </div>
  )
}
