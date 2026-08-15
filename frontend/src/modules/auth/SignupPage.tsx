/**
 * 가입 신청.
 *
 * 신청은 누구나 할 수 있지만 **승인 전에는 로그인할 수 없다**. 그 사실을 신청
 * 직후에 분명히 말해 주지 않으면, 로그인해 보고 "계정이 안 된다"고 문의가 온다.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { CheckCircle2, UserPlus } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import { accountsApi } from '@/modules/accounts/api'
import { workspacesApi } from '@/modules/workspaces/api'
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { useResource } from '@/shared/hooks/useResource'

const MIN_PASSWORD = 10

export default function SignupPage() {
  const navigate = useNavigate()
  const workspaces = useResource(() => workspacesApi.options(), [])

  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [workspaceSlug, setWorkspaceSlug] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [done, setDone] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (password !== confirm) {
      setError(new Error('비밀번호가 서로 다릅니다.'))
      return
    }
    if (password.length < MIN_PASSWORD) {
      setError(new Error(`비밀번호는 ${MIN_PASSWORD}자 이상이어야 합니다.`))
      return
    }
    if (!workspaceSlug) {
      setError(new Error('소속 부서를 선택하세요.'))
      return
    }

    setBusy(true)
    setError(null)
    try {
      await accountsApi.signup({
        email,
        password,
        display_name: displayName,
        workspace_slug: workspaceSlug,
      })
      setDone(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('신청에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="bg-background flex min-h-svh items-center justify-center p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="size-5 text-emerald-600" />
              신청이 접수되었습니다
            </CardTitle>
            <CardDescription>
              관리자가 승인하면 로그인할 수 있습니다. 승인 전에는 로그인되지 않습니다.
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Button className="w-full" onClick={() => navigate('/login', { replace: true })}>
              로그인 화면으로
            </Button>
          </CardFooter>
        </Card>
      </div>
    )
  }

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <UserPlus className="size-5" />
            가입 신청
          </CardTitle>
          <CardDescription>관리자 승인 후 사용할 수 있습니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">아이디</Label>
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
              <Label htmlFor="display-name">이름</Label>
              <Input
                id="display-name"
                required
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label>소속 부서</Label>
              {/* 경로를 보여 주는 선택기. **가입 화면이 이게 가장 절실하다** —
                  신청자는 조직도를 모르는 채로 고르는데, `품질팀` 이 둘이면
                  이름만으로는 어느 본부 소속인지 알 수 없다. */}
              <WorkspacePicker
                workspaces={workspaces.data ?? []}
                value={workspaceSlug}
                onChange={setWorkspaceSlug}
                placeholder="부서를 선택하세요"
                className="w-full"
                emptyLabel="선택할 수 있는 부서가 없습니다"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">비밀번호</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <p className="text-muted-foreground text-xs">{MIN_PASSWORD}자 이상</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm">비밀번호 확인</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>

            <ErrorNotice error={error ?? workspaces.error} />

            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? '신청 중…' : '신청하기'}
            </Button>
          </form>
        </CardContent>
        <CardFooter>
          <p className="text-muted-foreground w-full text-center text-sm">
            이미 계정이 있으신가요?{' '}
            <Link to="/login" className="text-foreground underline underline-offset-4">
              로그인
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
