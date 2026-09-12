/**
 * 알림함.
 *
 * 알림은 **무엇을 해야 하는지**로 이어져야 한다. 그래서 링크가 있으면 항목
 * 전체를 누를 수 있게 하고, 누르면 읽음 처리와 이동을 함께 한다.
 *
 * 아래에 **끄고 켜는 자리**가 있다(2026-09-12). VOC 알림이 붙으면서 모든 계정이
 * 알림을 받게 됐다 — 끌 길이 없으면 알림은 소음이 되고, 소음이 되면 진짜 알림도
 * 안 읽는다. 받을 수 있는 사건만 보인다(역할이 정한다).
 */

import { Bell, CheckCheck, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { notificationsApi } from '@/modules/notifications/api'
import type { Notification, NotificationRule } from '@/modules/notifications/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

function formatWhen(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function RuleSettings() {
  const rules = useResource(() => notificationsApi.rules(), [])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)

  async function toggle(rule: NotificationRule) {
    setBusy(rule.event_kind)
    setError(null)
    try {
      await notificationsApi.setRule(rule.event_kind, !rule.enabled)
      rules.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('바꾸지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  const rows = rules.data ?? []
  if (rows.length === 0 && !rules.error) return null
  return (
    <section className="mt-10 space-y-3" aria-label="알림 설정">
      <div>
        <h2 className="text-base font-semibold">어떤 알림을 받을까</h2>
        <p className="text-muted-foreground text-sm">
          끄면 그 일은 나에게 안 옵니다. 다른 사람은 그대로입니다.
        </p>
      </div>
      <ErrorNotice error={rules.error ?? error} />
      <ul className="divide-y rounded-md border">
        {rows.map((rule) => (
          <li key={rule.event_kind} className="flex items-center gap-3 px-3 py-2">
            <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={rule.enabled}
                disabled={busy === rule.event_kind}
                onChange={() => toggle(rule)}
                aria-label={rule.label}
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{rule.label}</span>
                <span className="text-muted-foreground block text-xs">{rule.description}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const notifications = useResource(() => notificationsApi.list(), [])

  async function open(item: Notification) {
    if (item.read_at === null) {
      await notificationsApi.read(item.id)
      notifications.reload()
    }
    if (item.link) navigate(item.link)
  }

  const rows = notifications.data ?? []
  const unread = rows.filter((item) => item.read_at === null).length

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="알림"
        description={unread > 0 ? `읽지 않은 알림 ${unread}건` : '새 알림이 없습니다.'}
        actions={
          unread > 0 && (
            <Button
              variant="outline"
              onClick={async () => {
                await notificationsApi.readAll()
                notifications.reload()
              }}
            >
              <CheckCheck className="size-4" />
              모두 읽음
            </Button>
          )
        }
      />

      <ErrorNotice error={notifications.error} className="mb-4" />

      {notifications.loading && (
        <div className="text-muted-foreground py-12 text-center">
          <Loader2 className="mx-auto size-4 animate-spin" />
        </div>
      )}

      {!notifications.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <Bell className="mx-auto mb-2 size-5 opacity-50" />
          알림이 없습니다.
        </div>
      )}

      <ul className="space-y-2">
        {rows.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => open(item)}
              className={`hover:bg-accent/50 flex w-full items-start gap-3 rounded-md border p-3 text-left transition-colors ${
                item.read_at === null ? 'bg-accent/20' : ''
              }`}
            >
              <span
                className={`mt-1.5 size-2 shrink-0 rounded-full ${
                  item.read_at === null ? 'bg-primary' : 'bg-transparent'
                }`}
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">{item.title}</span>
                {item.body && (
                  <span className="text-muted-foreground mt-0.5 block text-sm">{item.body}</span>
                )}
              </span>
              <span className="text-muted-foreground shrink-0 text-xs">
                {formatWhen(item.created_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <RuleSettings />
    </div>
  )
}
