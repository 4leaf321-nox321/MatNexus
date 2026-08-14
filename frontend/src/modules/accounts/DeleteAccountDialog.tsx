/**
 * 계정 삭제 — 미리보기 후 결정.
 *
 * **무엇이 딸려 있는지 먼저 보여 준다.** "지웠더니 데이터가 사라졌다"를 막는 것은
 * 확인 문구가 아니라 목록이다. 소유 자료는 다른 사람에게 넘길 수 있고, 넘기지
 * 않으면 소유자 참조가 지워진 계정을 계속 가리킨다.
 */

import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'

import { accountsApi } from '@/modules/accounts/api'
import type { Account, Reference } from '@/modules/accounts/api'
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
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

const NO_TRANSFER = '__none__'

interface DeleteAccountDialogProps {
  account: Account | null
  candidates: Account[]
  onClose: () => void
  onDeleted: (summary: string) => void
}

export function DeleteAccountDialog({
  account,
  candidates,
  onClose,
  onDeleted,
}: DeleteAccountDialogProps) {
  const [refs, setRefs] = useState<Reference[] | null>(null)
  const [transferTo, setTransferTo] = useState(NO_TRANSFER)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!account) return
    setRefs(null)
    setError(null)
    setTransferTo(NO_TRANSFER)
    accountsApi
      .dependents(account.id)
      .then(setRefs)
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught : new Error('조회에 실패했습니다.')),
      )
  }, [account])

  async function submit() {
    if (!account) return
    setBusy(true)
    setError(null)
    try {
      const result = await accountsApi.remove(
        account.id,
        transferTo === NO_TRANSFER ? null : transferTo,
      )
      const moved = result.transferred
        .map((ref) => `${ref.label} ${ref.count}건`)
        .join(', ')
      onDeleted(moved ? `${account.email} 삭제 — 넘긴 자료: ${moved}` : `${account.email} 삭제`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('삭제에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={account !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Trash2 className="size-4" />
            계정 삭제
          </DialogTitle>
          <DialogDescription>
            {account?.display_name} ({account?.email}) 의 접근을 끊습니다. 계정 기록 자체는 남아
            "누가 만든 데이터인가"를 잃지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <p className="mb-1.5 text-sm font-medium">이 계정에 딸린 것</p>
            {refs === null && <p className="text-muted-foreground text-sm">확인 중…</p>}
            {refs?.length === 0 && (
              <p className="text-muted-foreground text-sm">딸린 자료가 없습니다.</p>
            )}
            {refs && refs.length > 0 && (
              <ul className="text-muted-foreground space-y-1 text-sm">
                {refs.map((ref) => (
                  <li key={`${ref.table}.${ref.column}`} className="flex justify-between">
                    <span>{ref.label}</span>
                    <span className="font-mono text-xs">
                      {ref.count}건
                      {ref.on_delete === 'CASCADE' && ' · 함께 삭제'}
                      {ref.on_delete === 'SET NULL' && ' · 참조만 해제'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="transfer-to">소유 자료 승계</Label>
            <Select value={transferTo} onValueChange={setTransferTo}>
              <SelectTrigger id="transfer-to" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_TRANSFER}>넘기지 않음</SelectItem>
                {candidates.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.display_name} ({item.email})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-muted-foreground text-xs">
              넘기지 않으면 그 사람이 등록한 자료의 소유자가 삭제된 계정으로 남습니다.
            </p>
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button variant="destructive" disabled={busy} onClick={submit}>
            삭제
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
