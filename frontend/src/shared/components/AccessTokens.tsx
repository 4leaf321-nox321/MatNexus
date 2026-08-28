/**
 * 개인 액세스 토큰 — **발급·목록·폐기.**
 *
 * 장비 PC 의 수집 에이전트(MatPylon)가 이 토큰으로 온다. 지금까지는 API 로만
 * 발급할 수 있었다 — 마법사가 토큰을 요구하는데 PowerShell 을 열게 할 수는 없다.
 *
 * ## 평문은 한 번만
 *
 * 서버가 해시만 저장하므로 토큰 평문은 발급 응답에서 **딱 한 번** 보인다.
 * `SecretOnceDialog` 가 그것을 말한다. 잃어버리면 새로 발급한다.
 *
 * ## 왜 shared 에 있나
 *
 * 내 프로필(껍데기)과 장비 커넥터 화면(모듈) 둘이 쓴다. 모듈끼리 직접 부르지
 * 않으므로, 둘이 같아야 하는 것을 여기 둔다. 토큰은 로그인과 같은 층의 일이라
 * 도메인(재료·시험)이 아니다 — `shared/api/client` 가 세션을 들고 있는 것과 같다.
 */

import { useState } from 'react'

import { ApiError, api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { SecretOnceDialog } from '@/shared/components/SecretOnceDialog'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'
import { stamp } from '@/shared/lib/datetime'

type Pat = components['schemas']['PatOut']
type PatCreated = components['schemas']['PatCreateResponse']

export const tokensApi = {
  list: () => api.get<Pat[]>('/auth/tokens'),
  create: (name: string) => api.post<PatCreated>('/auth/tokens', { name }),
  revoke: (id: string) => api.delete<void>(`/auth/tokens/${id}`),
}

export function AccessTokens({ compact = false }: { compact?: boolean }) {
  const { data, error, loading, reload } = useResource(() => tokensApi.list(), [])
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<ApiError | Error | null>(null)
  const [issued, setIssued] = useState<PatCreated | null>(null)

  async function issue() {
    const label = name.trim()
    if (!label) return
    setBusy(true)
    setFailed(null)
    try {
      const made = await tokensApi.create(label)
      setIssued(made)
      setName('')
      reload()
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  async function revoke(row: Pat) {
    if (
      !window.confirm(
        `'${row.name}' 토큰을 폐기합니다. 이 토큰으로 붙어 있던 장비는 더 못 보냅니다.`
      )
    ) {
      return
    }
    setBusy(true)
    setFailed(null)
    try {
      await tokensApi.revoke(row.id)
      reload()
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  const rows = (data ?? []).filter((row) => !row.revoked_at)

  return (
    <div className="space-y-3">
      <ErrorNotice error={error ?? failed} />
      <div className="flex gap-2">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="용도 (예: 인장기-1 MatPylon)"
          aria-label="토큰 이름"
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              issue()
            }
          }}
        />
        <Button type="button" onClick={issue} disabled={busy || name.trim().length === 0}>
          발급
        </Button>
      </div>
      {!compact && (
        <p className="text-muted-foreground text-xs">
          토큰은 <strong>내 계정의 권한</strong>으로 움직입니다. 장비를 붙일 부서의 구성원이어야 그
          부서에 파일을 넣을 수 있습니다. 평문은 발급 직후 한 번만 보입니다.
        </p>
      )}

      {loading && !data && <p className="text-muted-foreground text-sm">불러오는 중…</p>}
      {data && rows.length === 0 && (
        <p className="text-muted-foreground text-sm">살아 있는 토큰이 없습니다.</p>
      )}
      {rows.length > 0 && (
        <ul className="divide-y rounded-md border text-sm">
          {rows.map((row) => (
            <li key={row.id} className="flex items-center justify-between gap-2 px-3 py-2">
              <div className="min-w-0">
                <div className="font-medium">{row.name}</div>
                <div className="text-muted-foreground text-xs">
                  <code className="font-mono">{row.prefix}…</code> · 발급 {stamp(row.created_at)}
                  {row.last_used_at ? ` · 마지막 사용 ${stamp(row.last_used_at)}` : ' · 아직 안 씀'}
                  {row.expires_at ? ` · 만료 ${stamp(row.expires_at)}` : ''}
                </div>
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => revoke(row)}
              >
                폐기
              </Button>
            </li>
          ))}
        </ul>
      )}

      <SecretOnceDialog
        open={issued !== null}
        onClose={() => setIssued(null)}
        title="액세스 토큰이 발급되었습니다"
        description="이 값은 다시 볼 수 없습니다. 지금 복사해 MatPylon 마법사에 붙여 넣으세요."
        secret={issued?.token ?? ''}
        subject={issued?.pat.name}
      />
    </div>
  )
}
