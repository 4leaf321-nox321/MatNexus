/**
 * 지금 어느 영역에 서 있는가 — 재료 물성인가 복합 물성인가.
 *
 * **주소가 정한다.** `/composite` 아래면 복합 물성이고, 재료·시편·시험 같은
 * 재료 쪽 주소면 재료 물성이다. 둘 다 아닌 공용 화면(알림·기준정보·관리)에서는
 * **마지막에 서 있던 영역**을 유지한다 — 알림을 보러 갔다가 사이드바가 다른
 * 세계로 바뀌어 있으면 사람이 「내가 어디 있었더라」 를 묻는다.
 *
 * 저장은 브라우저에만 한다(localStorage). 서버가 알 일이 아니다 — 이것은 권한도
 * 데이터도 아니고 「어느 메뉴를 펼쳐 두었나」 다.
 */

import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import type { NavRealm } from '@/shared/layout/navigation'

export const REALM_STORAGE_KEY = 'mnx.realm'

/** 재료 물성 쪽이라고 확실히 말할 수 있는 주소. 여기 없는 주소는 공용이다. */
const MATERIAL_PATHS = [
  /^\/materials(\/|$)/,
  /^\/specimens(\/|$)/,
  /^\/tests(\/|$)/,
  /^\/test-runs(\/|$)/,
  /^\/cards(\/|$)/,
  /^\/compare(\/|$)/,
  // 부서 홈과 부서 시험 목록·일괄 등록. 워크벤치·멤버는 공용이다.
  /^\/w\/[^/]+$/,
  /^\/w\/[^/]+\/tests(\/|$)/,
]

export function realmOf(pathname: string, stored: NavRealm | null): NavRealm {
  if (pathname === '/composite' || pathname.startsWith('/composite/')) return 'composite'
  if (MATERIAL_PATHS.some((one) => one.test(pathname))) return 'material'
  return stored ?? 'material'
}

export function readStoredRealm(): NavRealm | null {
  try {
    const raw = window.localStorage.getItem(REALM_STORAGE_KEY)
    return raw === 'material' || raw === 'composite' ? raw : null
  } catch {
    // 사생활 보호 창이나 저장을 막은 브라우저. 기억 못 할 뿐 화면은 멀쩡해야 한다.
    return null
  }
}

export function rememberRealm(realm: NavRealm): void {
  try {
    window.localStorage.setItem(REALM_STORAGE_KEY, realm)
  } catch {
    // 위와 같다.
  }
}

/** 지금 영역. 주소가 바뀌면 따라 바뀌고, 정해진 영역은 기억해 둔다. */
export function useRealm(): NavRealm {
  const { pathname } = useLocation()
  const realm = realmOf(pathname, readStoredRealm())
  useEffect(() => {
    rememberRealm(realm)
  }, [realm])
  return realm
}
