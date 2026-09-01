/**
 * 인증 상태.
 *
 * 새로고침하면 메모리의 access 토큰이 사라지므로, 앱이 뜰 때 refresh 쿠키로 한 번
 * 갱신을 시도한다. 성공하면 로그인 상태가 유지되고 실패하면 익명이다 — 사용자
 * 눈에는 "로그인이 유지되는" 것으로 보인다.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { api, session } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type CurrentUser = components['schemas']['UserOut']
type LoginResponse = components['schemas']['LoginResponse']

type Status = 'loading' | 'authenticated' | 'anonymous'

interface AuthContextValue {
  status: Status
  user: CurrentUser | null
  login: (email: string, password: string) => Promise<CurrentUser>
  logout: () => Promise<void>
  /** 비밀번호 변경 등으로 사용자 정보가 바뀐 뒤 다시 읽는다. */
  reload: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<CurrentUser | null>(null)

  const clear = useCallback(() => {
    session.setToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  // 앱 기동 시 1회 — 쿠키가 살아 있으면 세션을 되살린다.
  useEffect(() => {
    let cancelled = false
    session.onLost(clear)

    api
      .post<LoginResponse>('/auth/refresh')
      .then((body) => {
        if (cancelled) return
        session.setToken(body.access_token)
        setUser(body.user)
        setStatus('authenticated')
      })
      .catch(() => {
        if (!cancelled) clear()
      })

    return () => {
      cancelled = true
      session.onLost(null)
    }
  }, [clear])

  const login = useCallback(async (email: string, password: string) => {
    const body = await api.post<LoginResponse>('/auth/login', { email, password })
    session.setToken(body.access_token)
    setUser(body.user)
    setStatus('authenticated')
    return body.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      clear()
    }
  }, [clear])

  const reload = useCallback(async () => {
    const me = await api.get<CurrentUser>('/auth/me')
    setUser(me)
  }, [])

  const value = useMemo(
    () => ({ status, user, login, logout, reload }),
    [status, user, login, logout, reload],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth 는 AuthProvider 안에서만 쓸 수 있습니다')
  return value
}

/**
 * 로그인 정보를 **있으면 쓰고 없으면 넘어간다.**
 *
 * `useAuth` 가 던지는 것은 옳다 — 로그인해야 보이는 화면이 제공자 밖에 있으면 그것은
 * 조립 실수다. 다만 **곁들이 위젯**은 다르다: 「담기」 처럼 여러 화면에 얹히는 것이
 * 로그인 정보를 쓰는 순간, 그 단추를 품은 화면 전부가 제공자를 요구하게 된다. 실제로
 * 카드·시험 목록의 시험이 그것으로 깨졌다 — 화면의 잘못이 아니라 위젯이 옮긴 짐이다.
 *
 * 없을 때 무엇으로 대신할지는 부르는 쪽이 정한다.
 */
export function useMaybeAuth(): AuthContextValue | null {
  return useContext(AuthContext) ?? null
}
