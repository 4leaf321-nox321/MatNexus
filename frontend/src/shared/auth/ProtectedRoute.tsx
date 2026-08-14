/**
 * 인증 가드.
 *
 * 두 가지를 강제한다.
 *   1. 로그인하지 않았으면 로그인 화면으로 보내되, **원래 가려던 곳을 기억**한다.
 *      기억하지 않으면 링크로 받은 주소가 로그인 후 홈으로 흘러가 버린다.
 *   2. `must_change_password` 면 다른 화면을 못 쓰게 한다. 시드 비밀번호가 그대로
 *      남는 사고를 막는 것이 이 플래그의 존재 이유인데, 우회 가능하면 무의미하다.
 */

import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/shared/auth/AuthContext'

export function ProtectedRoute() {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="text-muted-foreground flex h-svh items-center justify-center text-sm">
        확인 중…
      </div>
    )
  }

  if (status === 'anonymous' || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (user.must_change_password && location.pathname !== '/force-password-change') {
    return <Navigate to="/force-password-change" replace />
  }

  return <Outlet />
}
