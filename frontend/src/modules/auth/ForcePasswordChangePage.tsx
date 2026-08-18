/**
 * 최초 로그인 시 비밀번호 강제 변경.
 *
 * 초기 관리자 계정과 세트로 필수다 — 시드 비밀번호가 그대로 남는 것이 폐쇄망
 * 설치에서 가장 흔한 사고다(비교표 B-계정 항목).
 *
 * 변경에 성공하면 서버가 모든 세션을 끊으므로 다시 로그인해야 한다. 그 편이
 * 안전하고, 사용자에게도 "바뀌었다"는 신호가 분명하다.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { AlertCircle, KeyRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { ApiError, api } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

export default function ForcePasswordChangePage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

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
      await api.post('/auth/change-password', { current_password: current, new_password: next })
      await logout() // 서버가 이미 세션을 끊었다 — 클라이언트 상태도 맞춘다
      navigate('/login', { replace: true })
    } catch (error) {
      setFailure(
        error instanceof ApiError ? error.message : '서버에 연결하지 못했습니다.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="size-5" />
            비밀번호 변경
          </CardTitle>
          <CardDescription>
            {user?.email} — 처음 로그인했습니다. 비밀번호를 바꿔야 계속할 수 있습니다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="current">현재 비밀번호</Label>
              <Input
                id="current"
                type="password"
                autoComplete="current-password"
                required
                autoFocus
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="next">새 비밀번호</Label>
              <Input
                id="next"
                type="password"
                autoComplete="new-password"
                required
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
              <p className="text-muted-foreground text-xs">이전과 다른 값이어야 합니다</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirm">새 비밀번호 확인</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>

            {failure && (
              <div className="border-destructive/40 bg-destructive/5 text-destructive flex items-start gap-2 rounded-md border p-3 text-sm">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <span>{failure}</span>
              </div>
            )}

            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? '변경 중…' : '변경하고 다시 로그인'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
