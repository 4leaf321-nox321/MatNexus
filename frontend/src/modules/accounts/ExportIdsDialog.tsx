/**
 * 아이디 내보내기 — 가입한 사람의 아이디를 `id1;id2;…` 한 줄로.
 *
 * 메일 수신자 칸이나 다른 시스템의 계정 등록에 붙여 넣는 용도(2026-09-15). **서버가
 * 전부 모은다** — 목록은 한 쪽 100 개라 화면이 이어 붙이면 101 번째부터 조용히 빠진다.
 * 기본은 활성 계정만 — 승인 대기·정지된 사람은 「가입한 사람」 이 아니다.
 */

import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { accountsApi } from '@/modules/accounts/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { useResource } from '@/shared/hooks/useResource'
import { copyText } from '@/shared/lib/clipboard'

export function ExportIdsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [includeInactive, setIncludeInactive] = useState(false)
  const [copied, setCopied] = useState(false)
  const ids = useResource(
    () => (open ? accountsApi.ids(includeInactive) : Promise.resolve(null)),
    [open, includeInactive]
  )

  async function copy() {
    if (!ids.data) return
    if (await copyText(ids.data.text)) {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>아이디 내보내기</DialogTitle>
          <DialogDescription>
            가입한 사람의 아이디를 <code>;</code> 로 이어 한 줄로 냅니다 — 메일 수신자 칸이나 다른
            시스템의 계정 등록에 그대로 붙여 넣습니다.
          </DialogDescription>
        </DialogHeader>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(event) => setIncludeInactive(event.target.checked)}
          />
          승인 대기·정지 계정도 포함
        </label>

        <ErrorNotice error={ids.error} />

        <textarea
          readOnly
          aria-label="아이디 목록"
          rows={6}
          className="border-input bg-muted/40 w-full rounded-md border px-3 py-2 font-mono text-sm"
          value={ids.data?.text ?? (ids.loading ? '모으는 중…' : '')}
          onFocus={(event) => event.currentTarget.select()}
        />
        <p className="text-muted-foreground text-xs">
          {ids.data ? `${ids.data.count}명 · 아이디순` : ''}
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button disabled={!ids.data || ids.data.count === 0} onClick={copy}>
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied ? '복사됨' : '복사'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
