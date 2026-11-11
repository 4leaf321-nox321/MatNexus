/**
 * 고른 계정 → 메일 받는 사람 칸에 붙일 한 줄 (2026-11-11).
 *
 * 아이디가 곧 회사 메일 주소다(가입은 허용 도메인으로만 받고, 도메인을 안 치면 붙여 준다 —
 * `signup_domain.complete_email`). 다만 **관리자가 직접 만든 계정은 `admin` 처럼 `@` 없는 아이디일
 * 수 있고**, 지운 계정의 아이디는 `…#deleted-…` 로 풀려 있다 — 둘은 메일이 안 가므로 빼고, 뺐다고
 * 말한다(빠진 줄 모르면 그 사람만 메일을 못 받는다).
 *
 * 구분은 `; ` — 아웃룩 · 사내 메일이 받는 사람 칸에서 그대로 나눈다(아이디 내보내기도 `;`).
 */

import type { Account } from '@/modules/accounts/api'

export const SEPARATOR = '; '

export interface MailAddresses {
  addresses: string[]
  /** 메일이 안 가서 뺀 계정 — 이름과 까닭. */
  skipped: { name: string; why: string }[]
  text: string
}

/** 메일 주소 꼴 — `@` 앞뒤에 글자가 있고 공백이 없다. 이 정도면 받는 사람 칸이 알아본다. */
function looksLikeAddress(value: string): boolean {
  return /^[^\s@]+@[^\s@]+$/.test(value)
}

export function mailAddresses(accounts: Account[]): MailAddresses {
  const addresses: string[] = []
  const skipped: MailAddresses['skipped'] = []
  const seen = new Set<string>()
  for (const account of accounts) {
    const name = account.display_name || account.email
    if (account.deleted_at) {
      skipped.push({ name, why: '삭제된 계정' })
      continue
    }
    const address = account.email.trim()
    if (!looksLikeAddress(address)) {
      skipped.push({ name, why: `메일 주소가 아닌 아이디(${address})` })
      continue
    }
    const key = address.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    addresses.push(address)
  }
  return { addresses, skipped, text: addresses.join(SEPARATOR) }
}
