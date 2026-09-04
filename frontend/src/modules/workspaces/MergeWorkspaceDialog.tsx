/**
 * 부서 합치기 — **무엇이 옮겨지는지 보고 누른다.**
 *
 * 자료가 매달린 부서는 지울 수 없다(그것이 맞다). 조직 개편으로 두 팀이 한 팀이
 * 되거나, 잘못 만든 부서에 자료가 먼저 쌓였을 때 이 창으로 옮긴다 — 기준정보의
 * 병합과 같은 무늬다.
 *
 * 대상을 고르면 **옮겨질 것의 목록**(표·건수)을 먼저 보여 준다. 서버의 삭제 검사와
 * 같은 자료다 — 미리보기와 실제 이동이 같은 눈으로 세어야 「미리보기엔 없더니」 가
 * 없다. 원본은 지워지지 않고 보관된다.
 */

import { Loader2, Merge } from 'lucide-react'
import { useEffect, useState } from 'react'

import { workspacesApi } from '@/modules/workspaces/api'
import type { Reference, Workspace } from '@/modules/workspaces/api'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

export function MergeWorkspaceDialog({
  workspace,
  candidates,
  onClose,
  onDone,
}: {
  /** 원본 — 이 부서의 자료가 옮겨지고, 이 부서는 보관된다. */
  workspace: Workspace | null
  /** 대상 후보(활성 부서 전체). 원본과 그 하위는 서버가 거절하지만 목록에서도 뺀다. */
  candidates: Workspace[]
  onClose: () => void
  onDone: () => void
}) {
  const [target, setTarget] = useState('')
  const [references, setReferences] = useState<Reference[] | null>(null)
  const [moved, setMoved] = useState<Reference[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    setTarget('')
    setReferences(null)
    setMoved(null)
    setError(null)
    if (!workspace) return
    let alive = true
    // 무엇이 옮겨질지 — 삭제 검사와 같은 목록이다.
    void workspacesApi
      .references(workspace.slug)
      .then((rows) => alive && setReferences(rows))
      .catch((caught) =>
        alive ? setError(caught instanceof Error ? caught : new Error('읽지 못했습니다.')) : null
      )
    return () => {
      alive = false
    }
  }, [workspace])

  async function run() {
    if (!workspace || !target) return
    setBusy(true)
    setError(null)
    try {
      setMoved(await workspacesApi.merge(workspace.slug, target))
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('합치지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const total = (references ?? []).reduce((sum, one) => sum + one.count, 0)
  const options = candidates.filter(
    (one) => one.slug !== workspace?.slug && one.is_active
  )

  return (
    <Dialog open={workspace !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>「{workspace?.name}」 을 다른 부서로 합치기</DialogTitle>
          <DialogDescription>
            이 부서의 자료가 전부 대상 부서 소속이 되고, 멤버도 옮겨 갑니다(양쪽에 다
            있던 사람은 한 명으로 — 관리자는 관리자로 남습니다). 이 부서는 빈 채로
            보관되며, 그 뒤에 지울 수 있습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <ErrorNotice error={error} />

          {moved ? (
            <p className="text-sm">
              <b className="text-emerald-700 dark:text-emerald-500">옮겼습니다.</b>{' '}
              {moved.reduce((sum, one) => sum + one.count, 0).toLocaleString('ko-KR')}건이 대상
              부서 소속이 됐습니다. 「{workspace?.name}」 은 보관되었습니다.
            </p>
          ) : (
            <>
              {/* **옮겨질 것을 이름과 수로 보여 준다.** 총계만 적으면 「그 안에
                  뭐가 있는데」 를 사람이 확인할 길이 없다. */}
              {references && references.length > 0 && (
                <div className="rounded-md border p-2 text-xs">
                  <p className="mb-1 font-medium">
                    옮겨질 자료 {total.toLocaleString('ko-KR')}건
                  </p>
                  {references.map((one) => (
                    <p key={`${one.table}.${one.column}`} className="text-muted-foreground">
                      {one.label ?? one.table} · {one.count.toLocaleString('ko-KR')}건
                    </p>
                  ))}
                </div>
              )}
              {references && references.length === 0 && (
                <p className="text-muted-foreground text-xs">
                  이 부서에 매달린 자료가 없습니다 — 합칠 것 없이 바로 지워도 되는
                  상태입니다.
                </p>
              )}

              <Select value={target} onValueChange={setTarget}>
                <SelectTrigger aria-label="합칠 대상 부서">
                  <SelectValue placeholder="어느 부서로 합칠까요" />
                </SelectTrigger>
                <SelectContent>
                  {options.map((one) => (
                    <SelectItem key={one.slug} value={one.slug}>
                      {one.name}
                      <span className="text-muted-foreground ml-1 text-xs">({one.slug})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            {moved ? '닫기' : '취소'}
          </Button>
          {!moved && (
            <Button onClick={() => void run()} disabled={busy || !target}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Merge className="size-4" />}
              {total > 0 ? `${total.toLocaleString('ko-KR')}건을 옮기고 합치기` : '합치기'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
