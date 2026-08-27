/**
 * 대표 소속 정하기 — **이 사람이 로그인해서 처음 서는 부서.**
 *
 * 이 값이 없으면 로그인이 `memberships[0]`, 즉 **이름 순 첫 부서**로 떨어진다
 * (`routes/router.tsx` 의 `HomeRedirect`). 부서 하나뿐인 사람에게는 그것이
 * 맞지만, 시스템 관리자처럼 여러 부서에 든 사람은 매번 엉뚱한 곳에 서고 부서를
 * 손으로 바꿔야 했다. 그 순서를 정하는 것은 사람이지 가나다순이 아니다.
 *
 * **고를 수 있는 것은 그 사람의 부서뿐이다.** 멤버가 아닌 부서를 주면 그 사람은
 * 로그인해서 자기가 못 보는 부서에 서고, 목록이 비어 보인다 — 데이터가 없는
 * 것과 구별이 안 된다. 서버도 같은 것을 막지만(`MNX-ACCOUNTS-0014`), 고를 수
 * 없는 것을 보여 주고 나서 거절하는 것은 화면의 일이 아니다.
 */

import { useState } from 'react'

import { accountsApi } from '@/modules/accounts/api'
import type { Account } from '@/modules/accounts/api'
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import type { PickableWorkspace } from '@/modules/workspaces/WorkspacePicker'
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

interface Props {
  account: Account
  /** 전체 부서 목록. 이 안에서 그 사람의 멤버십만 골라 쓴다. */
  workspaces: PickableWorkspace[]
  onClose: () => void
  onSaved: (message: string) => void
}

export function HomeWorkspaceDialog({ account, workspaces, onClose, onSaved }: Props) {
  const [slug, setSlug] = useState<string | null>(account.home_workspace_slug)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const mine = workspaces.filter((item) => account.memberships.includes(item.slug))

  async function save() {
    if (!slug) return
    setBusy(true)
    setError(null)
    try {
      await accountsApi.setHomeWorkspace(account.id, slug)
      const name = mine.find((item) => item.slug === slug)?.name ?? slug
      onSaved(`${account.display_name} 의 대표 소속을 ${name} 으로 정했습니다.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('정하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{account.display_name} — 대표 소속</DialogTitle>
          <DialogDescription>
            이 사람이 <b>로그인해서 처음 서는 부서</b>입니다. 안 정하면 이름 순 첫 부서로
            떨어집니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <WorkspacePicker
          workspaces={mine}
          value={slug}
          onChange={setSlug}
          placeholder="부서 고르기"
          emptyLabel="이 사람은 아직 어느 부서에도 없습니다"
          className="w-full"
        />

        {/* **여기서 부서를 「추가」 할 수 없다는 것을 말한다.** 목록에 없는 부서를
            찾다가 이 창을 닫고 다른 데를 뒤지게 두면 안 된다. */}
        <p className="text-muted-foreground text-xs">
          이 사람이 속한 부서만 나옵니다. 다른 부서로 옮기려면 <b>부서 멤버</b> 화면에서
          멤버로 먼저 넣으세요 — 여기서 겸하면 대표 소속을 정하는 일이 권한을 주는 일이
          됩니다.
        </p>

        {/* 본인이 지금 로그인해 있으면 이번 화면은 안 바뀐다. 그것을 미리 말한다 —
            안 그러면 "안 먹혔다" 로 읽고 한 번 더 누른다. */}
        <p className="text-muted-foreground text-xs">
          바뀐 자리는 그 사람이 <b>다음에 로그인할 때</b>부터 보입니다.
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button
            disabled={busy || !slug || slug === account.home_workspace_slug}
            onClick={() => void save()}
          >
            정하기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
