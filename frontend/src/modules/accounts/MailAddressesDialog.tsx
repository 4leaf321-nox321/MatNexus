/**
 * 메일 주소 복사 — **고른 계정의 주소를 한 줄로 보여 주고, 「복사」 를 누르면 그 자리에서 복사한다**
 * (2026-11-11).
 *
 * ## 운영 서버가 HTTP 라서
 *
 * 보안 컨텍스트(https · localhost)가 아니면 브라우저의 클립보드 API 가 없거나 거절한다. 그래서 복사는
 * `shared/lib/clipboard` 의 숨은 칸 + `execCommand('copy')` 로 가는데, 이 길은 **누른 그 순간**에만
 * 된다 — 누르고 나서 서버에 묻고 복사하면 조용히 빈 것이 복사된다. 주소는 이미 표에 있으므로(목록을
 * 끝까지 받아 둔다) 여기서는 아무것도 기다리지 않고 바로 복사한다.
 *
 * 그래도 막는 브라우저가 있다 — 주소를 글로 보여 주고, 막혔으면 그렇다고 말해 사람이 골라서 Ctrl+C
 * 로 복사하게 한다(공지 · VOC 복사와 같은 짜임).
 */

import { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'

import type { Account } from '@/modules/accounts/api'
import { mailAddresses } from '@/modules/accounts/mailAddresses'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { copyText } from '@/shared/lib/clipboard'

/** 열릴 때만 그린다(`AccountsAdminPage`) — 지난번 복사 결과가 남지 않는다. */
export function MailAddressesDialog({
  accounts,
  onClose,
}: {
  accounts: Account[]
  onClose: () => void
}) {
  const made = useMemo(() => mailAddresses(accounts), [accounts])
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  async function copy() {
    if (!made.text) return
    // **기다리지 않고 바로** — 누른 그 순간이어야 HTTP 에서도 복사된다.
    const ok = await copyText(made.text)
    setCopied(ok ? 'yes' : 'no')
    if (ok) window.setTimeout(() => setCopied(null), 2000)
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>메일 주소 복사</DialogTitle>
          <DialogDescription>
            고른 계정의 메일 주소를 <code>;</code> 로 이어 한 줄로 냅니다 — 메일의 받는 사람 칸에
            그대로 붙여 넣으세요.
          </DialogDescription>
        </DialogHeader>

        <textarea
          readOnly
          aria-label="메일 주소"
          rows={6}
          className="border-input bg-muted/40 w-full rounded-md border px-3 py-2 font-mono text-sm"
          value={made.text}
          // 눌러서 전부 고른다 — 복사가 막힌 브라우저에서 사람이 직접 복사하는 길이다.
          onFocus={(event) => event.currentTarget.select()}
        />
        <p className="text-sm" role="status">
          {made.addresses.length.toLocaleString('ko-KR')}명
          {made.skipped.length > 0 &&
            ` — ${made.skipped.length.toLocaleString('ko-KR')}명은 메일이 안 가서 뺐습니다: ` +
              made.skipped
                .slice(0, 5)
                .map((one) => `${one.name}(${one.why})`)
                .join(', ') +
              (made.skipped.length > 5 ? ' …' : '')}
        </p>
        {copied === 'no' && (
          <p className="text-destructive text-sm" role="alert">
            브라우저가 복사를 막았습니다 — 위 칸을 눌러 전부 고른 뒤 Ctrl+C 로 복사하세요.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button onClick={() => void copy()} disabled={!made.text}>
            {copied === 'yes' ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied === 'yes' ? '복사했습니다' : '복사'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
