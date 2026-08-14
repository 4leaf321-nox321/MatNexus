/**
 * 헤더의 알림 벨.
 *
 * 30초마다 읽지 않은 개수만 확인한다. 목록 전체를 주기적으로 받아 오면 사람이
 * 늘수록 서버가 그만큼 일하는데, 배지에 필요한 것은 숫자 하나다.
 */

import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

import { notificationsApi } from '@/modules/notifications/api'
import { Button } from '@/shared/components/ui/button'

const POLL_MS = 30_000

export function NotificationBell() {
  const [unread, setUnread] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    let cancelled = false

    const check = () => {
      notificationsApi
        .unreadCount()
        .then((result) => {
          if (!cancelled) setUnread(result.unread)
        })
        .catch(() => {
          // 배지는 부가 정보다. 실패해도 화면을 방해하지 않는다.
        })
    }

    check()
    const timer = setInterval(check, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
    // 알림 화면을 다녀오면 다시 센다 — 읽고 나왔는데 배지가 남아 있으면 이상하다.
  }, [location.pathname])

  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative"
      onClick={() => navigate('/notifications')}
      aria-label={unread > 0 ? `알림 ${unread}건` : '알림'}
    >
      <Bell className="size-4" />
      {unread > 0 && (
        <span className="bg-primary text-primary-foreground absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full text-[10px] font-medium">
          {unread > 9 ? '9+' : unread}
        </span>
      )}
    </Button>
  )
}
