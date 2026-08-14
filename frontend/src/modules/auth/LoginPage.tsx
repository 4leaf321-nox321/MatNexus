/**
 * 로그인 화면.
 *
 * 65는 로그인 화면 자체가 없어(#215 미착수) 사내 배포가 성립하지 않았다.
 * 인증 방식이 나중에 SSO로 바뀌더라도 이 화면은 남는다 — OIDC도 시작점·콜백·
 * 실패 표시가 필요하고, LDAP 직접 바인딩이면 폼이 오히려 필수다.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { AlertCircle, LogIn } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

interface FailureInfo {
  message: string
  code: string
  requestId?: string
}

interface LocationState {
  from?: { pathname: string }
}

export default function LoginPage() {
  const { status, user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<FailureInfo | null>(null)

  // 이미 로그인된 상태로 /login 에 오면 되돌려 보낸다.
  const from = (location.state as LocationState | null)?.from?.pathname ?? '/'
  useEffect(() => {
    if (status === 'authenticated' && user && !user.must_change_password) {
      navigate(from, { replace: true })
    }
  }, [status, user, from, navigate])

  if (status === 'authenticated' && user?.must_change_password) {
    return <Navigate to="/force-password-change" replace />
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setFailure(null)
    try {
      const me = await login(email, password)
      navigate(me.must_change_password ? '/force-password-change' : from, { replace: true })
    } catch (error) {
      if (error instanceof ApiError) {
        setFailure({ message: error.message, code: error.code, requestId: error.requestId })
      } else {
        setFailure({ message: '서버에 연결하지 못했습니다.', code: 'MNX-CLIENT-0000' })
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>MatNexus</CardTitle>
          <CardDescription>물성 관리 시스템에 로그인합니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">아이디</Label>
              {/* type="email" 을 쓰지 않는다 — 관리자 계정은 `admin` 처럼 이메일
                  형식이 아닌 아이디를 쓰는 경우가 많은데, 브라우저가 그것을
                  제출 단계에서 막아 로그인 자체가 불가능해진다. 서버도 같은
                  이유로 EmailStr 검증을 쓰지 않는다(ADR 0002). */}
              <Input
                id="email"
                type="text"
                autoComplete="username"
                placeholder="이메일 또는 아이디"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">비밀번호</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {failure && (
              <div className="border-destructive/40 bg-destructive/5 text-destructive flex items-start gap-2 rounded-md border p-3 text-sm">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <div className="min-w-0">
                  <p>{failure.message}</p>
                  <p className="mt-1 font-mono text-xs opacity-70">
                    {failure.code}
                    {failure.requestId ? ` · ${failure.requestId}` : ''}
                  </p>
                </div>
              </div>
            )}

            <Button type="submit" className="w-full" disabled={busy}>
              <LogIn className="size-4" />
              {busy ? '확인 중…' : '로그인'}
            </Button>
          </form>
        </CardContent>
        <CardFooter>
          <p className="text-muted-foreground w-full text-center text-sm">
            계정이 없으신가요?{' '}
            <Link to="/signup" className="text-foreground underline underline-offset-4">
              가입 신청
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
