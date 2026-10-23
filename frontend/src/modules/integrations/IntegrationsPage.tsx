/**
 * 외부 연동 — **바깥 시스템에 닿는 주소와 토큰을 시스템 관리자가 화면에서 넣는다**(2026-10-23).
 *
 * `.env` 에 두면 서버 파일을 고치고 서비스를 다시 띄워야 바뀐다. 지금은 TestScope 하나 —
 * 보유 장비 · 교정의 정본이다.
 *
 * ## 토큰은 다시 보이지 않는다
 *
 * 서버는 봉인해 두고 「설정됨」 만 말한다. 그래서 토큰 칸은 늘 비어 있고, **비운 채 저장하면
 * 그대로 둔다** — 빈 칸을 「지우기」 로 읽으면 주소만 고쳐도 토큰이 사라진다. 지우기는 따로
 * 누른다.
 *
 * ## 주소가 둘인 까닭
 *
 * 서버끼리는 같은 기계라 `127.0.0.1` 로 닿지만, 사람의 브라우저는 그 주소로 TestScope 화면을
 * 못 연다. 링크에 쓸 화면 주소를 따로 받는다(비우면 API 주소에서 `/api` 를 뗀 것).
 */

import { useState } from 'react'
import type { FormEvent } from 'react'

import { integrationsApi } from '@/modules/integrations/api'
import type { Integration, IntegrationCheck } from '@/modules/integrations/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'

function when(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString('ko-KR') : ''
}

export default function IntegrationsPage() {
  const list = useResource(() => integrationsApi.list(), [])
  return (
    <div className="space-y-4">
      <PageHeader
        title="외부 연동"
        description="바깥 시스템에 닿는 주소와 토큰입니다. 토큰은 암호화해 두고 다시 보여 주지 않습니다."
      />
      <ErrorNotice error={list.error} />
      {list.data?.map((one) => (
        <ConnectionForm key={one.system} initial={one} />
      ))}
    </div>
  )
}

/** 한 시스템의 칸 — 처음 읽은 값으로 시작하고, 저장하면 서버가 돌려준 값을 따른다. */
function ConnectionForm({ initial }: { initial: Integration }) {
  const [shown, setShown] = useState(initial)
  const [baseUrl, setBaseUrl] = useState(initial.base_url)
  const [webUrl, setWebUrl] = useState(initial.web_url)
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<Error | null>(null)
  const [checked, setChecked] = useState<IntegrationCheck | null>(null)

  async function save(body: { clear_token?: boolean } = {}) {
    setBusy(true)
    setFailed(null)
    setChecked(null)
    try {
      const saved = await integrationsApi.save(shown.system, {
        base_url: baseUrl,
        web_url: webUrl,
        // 빈 칸은 「그대로」 다 — null 로 보낸다.
        token: token.trim() || null,
        clear_token: body.clear_token ?? false,
      })
      setShown(saved)
      setBaseUrl(saved.base_url)
      setWebUrl(saved.web_url)
      setToken('')
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function check() {
    setBusy(true)
    setFailed(null)
    try {
      // 목록을 다시 읽지 않는다 — 고치다 만 칸이 저장된 값으로 되돌아간다.
      setChecked(await integrationsApi.check(shown.system))
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('확인하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void save()
  }

  const id = (name: string) => `${shown.system}-${name}`
  const tokenState = !shown.has_token
    ? '없음'
    : shown.token_readable
      ? `설정됨 · ${when(shown.token_set_at)}`
      : '이 서버가 풀지 못함 — 다시 넣으세요'
  // 방금 누른 확인이 있으면 그것, 없으면 저장된 지난 확인(주소 · 토큰을 바꾸면 서버가 지운다).
  const lastCheck = checked
    ? { ok: checked.ok, message: checked.message, at: checked.checked_at }
    : { ok: shown.check_ok, message: shown.check_message, at: shown.checked_at }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-md border p-4" aria-label={shown.label}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">{shown.label}</h2>
        {shown.updated_by && (
          <span className="text-muted-foreground text-xs">
            {shown.updated_by} · {when(shown.updated_at)}
          </span>
        )}
      </div>
      <p className="text-muted-foreground text-sm">
        보유 장비 · 교정 · 기종 사양의 정본입니다. TestScope 에서 <b>읽기(read)</b> 범위만 준 개인
        토큰을 발급해 넣습니다. 그 토큰 주인이 볼 수 있는 부서의 장비만 보입니다.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor={id('base')}>API 주소</Label>
          <Input
            id={id('base')}
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="http://testscope-서버:8020/api"
          />
          <p className="text-muted-foreground text-xs">
            이 서버가 부르는 주소. 같은 서버면 127.0.0.1 — 끝의 /api 는 없으면 붙입니다.
          </p>
        </div>
        <div className="space-y-1">
          <Label htmlFor={id('web')}>화면 주소(링크용)</Label>
          <Input
            id={id('web')}
            value={webUrl}
            onChange={(event) => setWebUrl(event.target.value)}
            placeholder={shown.link_url || 'http://testscope-서버:8020'}
          />
          <p className="text-muted-foreground text-xs">
            사람이 브라우저로 여는 주소. 비우면 API 주소에서 /api 를 뗀 것을 씁니다.
          </p>
        </div>
        <div className="space-y-1 md:col-span-2">
          <Label htmlFor={id('token')}>읽기 토큰</Label>
          <Input
            id={id('token')}
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder={shown.has_token ? '바꿀 때만 넣으세요' : 'TestScope 개인 토큰'}
          />
          <p className="text-muted-foreground text-xs">지금: {tokenState}</p>
        </div>
      </div>

      <ErrorNotice error={failed} />
      <CheckLine {...lastCheck} />

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={busy}>
          저장
        </Button>
        <Button type="button" variant="outline" disabled={busy} onClick={() => void check()}>
          연결 확인
        </Button>
        {shown.has_token && (
          <Button
            type="button"
            variant="ghost"
            disabled={busy}
            onClick={() => void save({ clear_token: true })}
          >
            토큰 지우기
          </Button>
        )}
      </div>
    </form>
  )
}

function CheckLine({
  ok,
  message,
  at,
}: {
  ok: boolean | null | undefined
  message: string | null | undefined
  at: string | null | undefined
}) {
  if (!message) return null
  return (
    <p
      role="status"
      className={`rounded-md border p-2 text-sm ${ok ? 'border-emerald-300 text-emerald-700' : 'border-amber-300 text-amber-700'}`}
    >
      {ok ? '✓ ' : '✕ '}
      {message}
      {at && <span className="text-muted-foreground ml-2 text-xs">{when(at)}</span>}
    </p>
  )
}
