/**
 * 내 정보 — **팝업이 아니라 자리가 있는 화면.**
 *
 * 처음에는 상단 메뉴의 팝업(ProfileDialog)이었다. 액세스 토큰까지 여기 붙자
 * 팝업이 하는 일이 「이름 고치기」 를 넘었고, 목록·발급·폐기를 팝업 안에서 하는
 * 것은 좁았다 — 왼쪽 「내 활동」 아래의 화면으로 옮겼다(실사용 요청, 2026-08-29).
 * 상단 메뉴의 「내 정보」 는 이제 여기로 온다.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, api } from '@/shared/api/client'
import { useAuth } from '@/shared/auth/AuthContext'
import { AccessTokens } from '@/shared/components/AccessTokens'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { ChangePasswordDialog } from '@/shared/layout/ChangePasswordDialog'

export default function ProfilePage() {
  const { user, reload, logout } = useAuth()
  const [name, setName] = useState(user?.display_name ?? '')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)

  // 계정은 뒤늦게 풀린다 — 첫 렌더에서 user 가 없을 수 있다.
  useEffect(() => {
    setName(user?.display_name ?? '')
  }, [user?.display_name])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (name.trim().length === 0) {
      setFailure('이름을 입력하세요.')
      return
    }
    setBusy(true)
    setFailure(null)
    setSaved(false)
    try {
      await api.patch('/auth/me', { display_name: name.trim() })
      // 상단 바가 바로 새 이름을 보여야 한다 — 저장했는데 안 바뀌면 실패로 읽힌다.
      await reload()
      setSaved(true)
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '서버에 연결하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title="내 정보" description="이름·비밀번호·액세스 토큰을 여기서 관리합니다." />

      <form onSubmit={submit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="profile-email">아이디</Label>
          {/* **읽기 전용이다.** 로그인 식별자라 본인이 바꾸면 기록이 가리키는
              대상이 흔들린다. 왜 못 바꾸는지 화면이 말한다. */}
          <Input id="profile-email" value={user?.email ?? ''} disabled />
          <p className="text-muted-foreground text-xs">
            아이디는 바꿀 수 없습니다 — 필요하면 시스템 관리자에게 요청하세요.
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="profile-name">표시 이름</Label>
          <Input
            id="profile-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>

        {failure && <p className="text-destructive text-sm">{failure}</p>}
        {saved && <p className="text-sm text-emerald-700">저장했습니다.</p>}

        <div className="flex gap-2">
          <Button type="submit" disabled={busy || name.trim() === (user?.display_name ?? '')}>
            저장
          </Button>
          <Button type="button" variant="outline" onClick={() => setChangingPassword(true)}>
            비밀번호 변경
          </Button>
        </div>
      </form>

      {/* **장비가 들어오는 열쇠.** 장비 PC 의 수집 에이전트가 이 토큰으로 온다.
          발급은 여기서, 어느 부서에 붙었는지는 장비 커넥터 화면에서 본다. */}
      <section className="mt-8 border-t pt-4">
        <h2 className="mb-2 text-sm font-semibold">액세스 토큰</h2>
        <AccessTokens />
      </section>

      <ChangePasswordDialog
        open={changingPassword}
        onClose={() => setChangingPassword(false)}
        onChanged={async () => {
          // 바꾸고 나면 서버가 세션을 전부 끊는다 — 클라이언트 상태도 맞춘다.
          setChangingPassword(false)
          await logout()
        }}
      />
    </div>
  )
}
