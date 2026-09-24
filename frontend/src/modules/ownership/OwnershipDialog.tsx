/**
 * 누가 고치나 — **등록자와 편집을 받은 부서를 보고, 넘긴다**(ADR 0035).
 *
 * 자료를 고치는 사람은 넷이다: 시스템 관리자 · 자료 관리자 · 그 자료의 등록자 · 그
 * 자료에 편집을 받은 부서의 멤버. 소속 부서는 권한을 정하지 않는다 — 전에는 그랬고,
 * 잠긴 이유를 사람이 알아낼 길이 없었다. 그래서 이 창은 **지금 누가 고치는지**를 먼저
 * 보이고, 넘길 수 있는 사람(등록자와 관리자)에게만 바꾸는 칸을 연다.
 *
 * **안 바꾼 칸은 안 보낸다.** 등록자만 넘기려다 부서 부여가 함께 사라지면 안 된다 —
 * 서버도 「안 보낸 것」 과 「비운 것」 을 가른다.
 */

import { Loader2, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'

import { ownershipApi } from '@/modules/ownership/api'
import type {
  OwnedKind,
  OwnershipChange,
  OwnershipResult,
  Person,
} from '@/modules/ownership/api'
import { workspacesApi } from '@/modules/workspaces/api'
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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

/** 편집 부서를 어떻게 할까 — 안 건드림 / 이 부서에 / 부여 걷기. */
type SpaceMode = 'keep' | 'set' | 'clear'

const KIND_LABELS: Record<OwnedKind, string> = {
  material: '재료',
  sample: '시료',
  specimen: '시편',
  test_run: '시험',
  property_card: '카드',
  group_result: '묶음',
  // 정의와 장비도 사람이 고친다(ADR 0035 3단계) — 아래로 딸린 것은 없다.
  test_type: '시험 정의',
  format_profile: '장비 파일 정의',
  recipe: '레시피',
  export_profile: '해석용 물성 정의',
  equipment: '장비',
}

export function OwnershipDialog({
  kind,
  id,
  onClose,
  onChanged,
}: {
  kind: OwnedKind
  id: string
  onClose: () => void
  /** 넘긴 뒤 부르는 쪽이 자기 목록을 다시 읽게 한다. */
  onChanged?: () => void
}) {
  const current = useResource(() => ownershipApi.get(kind, id), [kind, id])
  const workspaces = useResource(() => workspacesApi.options(), [])

  const [query, setQuery] = useState('')
  const [people, setPeople] = useState<Person[]>([])
  const [person, setPerson] = useState<Person | null>(null)
  const [mode, setMode] = useState<SpaceMode>('keep')
  const [space, setSpace] = useState<string | null>(null)
  const [children, setChildren] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [done, setDone] = useState<OwnershipResult | null>(null)

  // **사람은 이름으로 찾는다.** 계정 목록은 시스템 관리자 것이라, 등록자가 넘길 사람을
  // 고를 길이 따로 필요했다(`/ownership/people`). 치는 동안 매번 부르지 않게 조금 기다린다.
  useEffect(() => {
    const text = query.trim()
    if (!text) {
      setPeople([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(() => {
      ownershipApi
        .people(text)
        .then((found) => {
          if (!cancelled) setPeople(found)
        })
        .catch(() => {
          if (!cancelled) setPeople([])
        })
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [query])

  const info = current.data
  const access = info?.access
  const ready =
    person !== null || mode === 'clear' || (mode === 'set' && space !== null)

  async function save() {
    if (!info) return
    const body: OwnershipChange = { include_children: children }
    if (person) body.registrant_id = person.id
    if (mode === 'set' && space) body.edit_workspace_slug = space
    if (mode === 'clear') body.edit_workspace_slug = null
    setBusy(true)
    setError(null)
    try {
      setDone(await ownershipApi.change(kind, id, body))
      current.reload()
      onChanged?.()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('넘기지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>누가 고치나 — {info?.name ?? KIND_LABELS[kind]}</DialogTitle>
          <DialogDescription>
            등록자와 편집을 받은 부서, 그리고 자료 관리자가 고칩니다. 소속 부서는 권한을
            정하지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={current.error ?? error} />
        {current.loading && !info && (
          <p className="text-muted-foreground flex items-center gap-2 text-sm">
            <Loader2 className="size-4 animate-spin" /> 불러오는 중…
          </p>
        )}

        {access && (
          <dl className="grid grid-cols-[6rem_1fr] gap-y-1 text-sm">
            <dt className="text-muted-foreground">등록자</dt>
            <dd>{access.registrant ?? '없음 — 관리자만 고칩니다'}</dd>
            <dt className="text-muted-foreground">편집 부서</dt>
            <dd>{access.edit_workspace ?? '없음 — 등록자와 자료 관리자만'}</dd>
            <dt className="text-muted-foreground">나는</dt>
            <dd>{access.can_edit ? '고칠 수 있습니다' : access.reason}</dd>
          </dl>
        )}

        {done && (
          <div className="space-y-1 rounded-md border p-3 text-sm">
            <p>{done.changed}건을 넘겼습니다.</p>
            {done.skipped.length > 0 && (
              <>
                <p className="text-muted-foreground">
                  건너뛴 것 {done.skipped.length}건 — 남이 붙인 것은 그 사람이 넘깁니다:
                </p>
                <ul className="max-h-40 list-disc overflow-y-auto pl-5">
                  {done.skipped.map((one, at) => (
                    <li key={`${one.kind}-${at}`}>
                      {KIND_LABELS[one.kind]} {one.name} — {one.reason}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        {access && !access.can_hand_over && (
          <p className="text-muted-foreground text-sm">
            등록자와 자료 관리자만 넘길 수 있습니다. 편집을 받은 부서 사람은 고칠 수는 있어도
            권한을 옮기지는 못합니다.
          </p>
        )}

        {access?.can_hand_over && !done && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="ownership-person">등록자 넘기기</Label>
              {person ? (
                <div className="flex items-center gap-2 text-sm">
                  <UserRound className="size-4" />
                  {person.display_name}
                  {person.workspace && (
                    <span className="text-muted-foreground">· {person.workspace}</span>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => setPerson(null)}>
                    바꾸지 않음
                  </Button>
                </div>
              ) : (
                <>
                  <Input
                    id="ownership-person"
                    value={query}
                    placeholder="이름으로 찾기"
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  {people.length > 0 && (
                    <ul className="max-h-40 overflow-y-auto rounded-md border">
                      {people.map((one) => (
                        <li key={one.id}>
                          <button
                            type="button"
                            className="hover:bg-muted w-full px-3 py-1.5 text-left text-sm"
                            onClick={() => {
                              setPerson(one)
                              setQuery('')
                            }}
                          >
                            {one.display_name}
                            {one.workspace && (
                              <span className="text-muted-foreground"> · {one.workspace}</span>
                            )}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              <p className="text-muted-foreground text-xs">
                넘기면 지금 등록자는 더 못 고칩니다(편집 부서 사람이면 계속 고칩니다).
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>편집 부서</Label>
              <div className="flex flex-wrap gap-3 text-sm">
                {(
                  [
                    ['keep', '그대로'],
                    ['set', '이 부서에 준다'],
                    ['clear', '부여 걷기'],
                  ] as const
                ).map(([value, label]) => (
                  <label key={value} className="flex items-center gap-1.5">
                    <input
                      type="radio"
                      name="ownership-space"
                      checked={mode === value}
                      onChange={() => setMode(value)}
                    />
                    {label}
                  </label>
                ))}
              </div>
              {mode === 'set' && (
                <WorkspacePicker
                  workspaces={workspaces.data ?? []}
                  value={space}
                  onChange={setSpace}
                  excludeArchived
                />
              )}
            </div>

            {info && info.children.length > 0 && (
              <div className="space-y-1.5">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={children}
                    onChange={(event) => setChildren(event.target.checked)}
                  />
                  아래에 딸린 것도 함께
                </label>
                <p className="text-muted-foreground text-xs">
                  {info.children
                    .map(
                      (one) =>
                        `${one.label} ${one.total}건` +
                        (one.changeable < one.total ? `(내가 넘길 것 ${one.changeable})` : '')
                    )
                    .join(' · ')}
                  {' — '}남이 붙인 것은 건너뜁니다.
                </p>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          {access?.can_hand_over && !done && (
            <Button onClick={() => void save()} disabled={busy || !ready}>
              {busy && <Loader2 className="size-4 animate-spin" />}
              넘기기
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
