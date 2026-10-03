/**
 * 고유 번호 — 재료 `M-` · 시료 `S-` · 시편 `P-` · 시험 `T-`(ADR 0043). **누르면 복사한다.**
 *
 * 이름(`SECC_MDOI_1.0__01__MD_01__TEN_01`)은 밑줄로 엮여 길고, 재료 개명 · 다른 두께로 옮기기에
 * 따라 바뀐다. 말 · 메신저 · 라벨로 전할 때는 번호를 쓴다 — 그래서 번호가 **보여야 하고**,
 * 옮겨 적는 수고가 없어야 한다. 전에는 재료 번호가 제목 옆에 흐린 글씨로만 있어서 「번호가
 * 화면에 안 나온다」 는 말을 들었다(2026-09-30).
 *
 * 표 칸에는 이것을 안 쓴다 — 표는 「번호」 열에 글자로 둔다(줄마다 단추가 서면 표가 시끄럽다).
 */

import { useEffect, useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { copyText } from '@/shared/lib/clipboard'
import { cn } from '@/shared/lib/utils'

export function CodeChip({ code, className }: { code: string | null | undefined; className?: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(timer)
  }, [copied])
  if (!code) return null

  return (
    <button
      type="button"
      aria-label={`번호 ${code} 복사`}
      title={
        copied
          ? '복사했습니다'
          : `${code} — 누르면 복사합니다. 이름이 바뀌어도 이 번호는 안 바뀝니다.`
      }
      className={cn(
        'border-border bg-background hover:bg-muted inline-flex items-center gap-1 rounded border px-1.5 py-0.5 align-middle font-mono text-xs font-medium tabular-nums transition-colors',
        className
      )}
      onClick={(event) => {
        // 링크 · 펼침 줄 안에 설 수 있다 — 누른 것이 그쪽으로 새지 않게.
        event.preventDefault()
        event.stopPropagation()
        // **`navigator.clipboard` 를 바로 부르지 않는다**(2026-10-04). 사내 http 주소에서는 그
        // 객체가 없어 아무 일도 안 일어났다 — 되돌아 갈 길을 가진 `copyText` 를 쓴다. 막혔으면
        // 「복사했습니다」 를 안 띄운다(번호는 화면에 그대로 있다).
        void copyText(code).then((ok) => {
          if (ok) setCopied(true)
        })
      }}
    >
      {code}
      {copied ? (
        <Check className="size-3 text-emerald-600" aria-hidden />
      ) : (
        <Copy className="size-3 opacity-50" aria-hidden />
      )}
    </button>
  )
}
