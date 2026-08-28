/**
 * 내 정보 — **표시 이름만 바꾼다.**
 *
 * 아이디(로그인 식별자)는 여기서 못 바꾼다. 본인이 바꾸면 감사 기록·알림·자료
 * 이관이 가리키는 대상이 흔들린다 — 그것은 관리자의 일이다.
 *
 * 만든 이유는 소박하다. 관리자가 계정을 만들 때 정한 이름이 그대로 가는데,
 * **오타 하나를 고치려고 DB 를 직접 만지는 일**이 실제로 생긴다.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, api } from '@/shared/api/client'
import { AccessTokens } from '@/shared/components/AccessTokens'
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
  /** 지금 값. 열 때마다 이것으로 채운다. */
  email: string
  displayName: string
  onClose: () => void
  onSaved: () => void
}

export function ProfileDialog({ open, email, displayName, onClose, onSaved }: Props) {
  const [name, setName] = useState(displayName)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setName(displayName)
      setFailure(null)
    }
  }, [open, displayName])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (name.trim().length === 0) {
      setFailure('이름을 입력하세요.')
      return
    }
    setBusy(true)
    setFailure(null)
    try {
      await api.patch('/auth/me', { display_name: name.trim() })
      onSaved()
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '서버에 연결하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>내 정보</DialogTitle>
          <DialogDescription>
            표시 이름은 목록·이력·알림에 그대로 나타납니다.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="profile-email">아이디</Label>
            {/* **읽기 전용이다.** 로그인 식별자라 본인이 바꾸면 기록이 가리키는
                대상이 흔들린다. 왜 못 바꾸는지 화면이 말한다. */}
            <Input id="profile-email" value={email} disabled />
            <p className="text-muted-foreground text-xs">
              아이디는 바꿀 수 없습니다 — 필요하면 시스템 관리자에게 요청하세요.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="profile-name">표시 이름</Label>
            <Input
              id="profile-name"
              value={name}
              autoFocus
              onChange={(event) => setName(event.target.value)}
            />
          </div>

          {failure && <p className="text-destructive text-sm">{failure}</p>}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy || name.trim() === displayName}>
              저장
            </Button>
          </DialogFooter>
        </form>

        {/* **장비가 들어오는 열쇠.** 장비 PC 의 수집 에이전트가 이 토큰으로 온다.
            발급은 여기서, 어느 부서에 붙었는지는 장비 커넥터 화면에서 본다. */}
        <section className="mt-4 border-t pt-4">
          <h3 className="mb-2 text-sm font-semibold">액세스 토큰</h3>
          <AccessTokens />
        </section>
      </DialogContent>
    </Dialog>
  )
}
