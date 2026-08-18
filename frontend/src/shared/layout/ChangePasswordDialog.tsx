/**
 * 내 비밀번호 바꾸기 — **스스로 바꿀 자리가 없었다.**
 *
 * `/auth/change-password` 는 처음부터 있었는데 부르는 화면이 강제 변경 페이지
 * 하나뿐이었다. 그래서 자기 비밀번호를 바꾸려면 **관리자에게 재설정을 부탁해
 * 임시 비밀번호를 받고, 그걸로 로그인해 강제 변경 화면을 거치는** 길밖에
 * 없었다. 관리자 자신은 그 길조차 없다.
 *
 * 설치 현장에서 "비밀번호 바꾸는 기능이 안 보인다" 로 드러났다.
 *
 * 길이 하한을 두지 않는다. 10자를 요구했더니 기관 규칙과 어긋나 사람이 화면을
 * 우회해 스크립트로 바꿨고, **그 경로가 오히려 강제 변경 상태를 되돌려** 놓아
 * 로그인이 되풀이에 갇혔다. 규칙이 우회를 만들면 규칙이 지키려던 것을 잃는다.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, api } from '@/shared/api/client'
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

interface Props {
  open: boolean
  onClose: () => void
  /** 바꾸고 나면 서버가 모든 세션을 끊는다 — 껍데기가 로그인 화면으로 보낸다. */
  onChanged: () => void
}

export function ChangePasswordDialog({ open, onClose, onChanged }: Props) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setCurrent('')
      setNext('')
      setConfirm('')
      setFailure(null)
    }
  }, [open])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (next !== confirm) {
      setFailure('새 비밀번호가 서로 다릅니다.')
      return
    }
    if (next.length === 0) {
      setFailure('새 비밀번호를 입력하세요.')
      return
    }

    setBusy(true)
    setFailure(null)
    try {
      await api.post('/auth/change-password', {
        current_password: current,
        new_password: next,
      })
      onChanged()
    } catch (error) {
      // 서버가 이유를 준다 — "현재 비밀번호가 올바르지 않습니다" 같은 것.
      setFailure(error instanceof ApiError ? error.message : '서버에 연결하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>비밀번호 변경</DialogTitle>
          <DialogDescription>
            바꾸고 나면 <b>모든 기기에서 로그아웃</b>됩니다 — 바꾸는 이유가 유출일 수
            있기 때문입니다. 새 비밀번호로 다시 로그인하세요.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="pw-current">현재 비밀번호</Label>
            <Input
              id="pw-current"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pw-next">새 비밀번호</Label>
            <Input
              id="pw-next"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">이전과 다른 값이어야 합니다</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pw-confirm">새 비밀번호 확인</Label>
            <Input
              id="pw-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </div>

          {failure && <p className="text-destructive text-sm">{failure}</p>}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy || !current || !next}>
              바꾸기
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
