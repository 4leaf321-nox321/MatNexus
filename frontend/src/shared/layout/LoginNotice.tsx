/**
 * 로그인 직후 **한 번** 보이는 안내 — 「아이디에 @samsung.com 이 붙었습니다」.
 *
 * 로그인 화면은 성공하면 바로 떠나므로 거기서는 못 보여 준다. 응답의 `notice` 를
 * `sessionStorage` 에 놓아 두고(`AuthContext`), 껍데기가 뜨면서 읽고 지운다 —
 * 닫으면 다시 안 뜨고, 새로고침해도 안 뜬다.
 */

import { Info, X } from 'lucide-react'
import { useState } from 'react'

import { LOGIN_NOTICE_KEY } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/components/ui/button'

function take(): string | null {
  try {
    const found = sessionStorage.getItem(LOGIN_NOTICE_KEY)
    if (found) sessionStorage.removeItem(LOGIN_NOTICE_KEY)
    return found
  } catch {
    return null
  }
}

export function LoginNotice() {
  const [notice, setNotice] = useState<string | null>(take)
  if (!notice) return null
  return (
    <div
      role="status"
      className="flex items-start gap-2 border-b border-sky-200 bg-sky-50 px-4 py-2 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100"
    >
      <Info className="mt-0.5 size-4 shrink-0" />
      <span className="flex-1">{notice}</span>
      <Button
        size="sm"
        variant="ghost"
        className="h-6 px-1"
        aria-label="안내 닫기"
        onClick={() => setNotice(null)}
      >
        <X className="size-4" />
      </Button>
    </div>
  )
}
