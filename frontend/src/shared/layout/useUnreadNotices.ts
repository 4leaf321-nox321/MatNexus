/**
 * 안 읽은 공지 수 — 사이드바의 「공지 · VOC」 옆에 단다(2026-09-24).
 *
 * 알림 종(`NotificationBell`)과 같은 판단이다. **숫자 하나만** 주기적으로 묻는다 — 목록을
 * 통째로 받아 세면 사람이 늘수록 서버가 그만큼 일한다. 공지는 알림보다 드물어 1분마다 묻는다.
 *
 * **읽으면 곧바로 다시 센다**(`NOTICES_READ`). 주기만 기다리면 공지를 읽고 나왔는데 수가 1분
 * 동안 그대로다. 화면을 옮길 때도 센다 — 다른 탭에서 읽은 것이 여기 반영되는 자리다.
 */

import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { NOTICES_READ, noticesApi } from '@/modules/notices/api'

const POLL_MS = 60_000

export function useUnreadNotices(): number {
  const [unread, setUnread] = useState(0)
  const location = useLocation()

  useEffect(() => {
    let cancelled = false
    const check = () => {
      noticesApi
        .unreadCount()
        .then((result) => {
          if (!cancelled) setUnread(result.unread)
        })
        .catch(() => {
          // 수는 부가 정보다. 실패해도 메뉴를 방해하지 않는다.
        })
    }

    check()
    const timer = setInterval(check, POLL_MS)
    window.addEventListener(NOTICES_READ, check)
    return () => {
      cancelled = true
      clearInterval(timer)
      window.removeEventListener(NOTICES_READ, check)
    }
  }, [location.pathname])

  return unread
}
