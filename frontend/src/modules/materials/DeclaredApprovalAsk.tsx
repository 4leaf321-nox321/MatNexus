/**
 * 승인을 기다리는 선언 값을 자료 관리자에게 **부탁한다**(2026-10-15).
 *
 * 승인은 자료 관리자만 한다(ADR 0049). 전에는 「승인 대기 값」 화면을 열어 보지 않으면 자료
 * 관리자는 몰랐고, 값을 적은 사람은 누구에게 말해야 할지 몰랐다. 부탁은 알림과 기록 한 줄이다 —
 * 값도 상태도 안 바뀐다.
 *
 * **수는 서버가 센다**(2026-10-16). 전에는 화면이 재료 쪽 값만 세어 「1건」 이라는데 서버는 시료 ·
 * 밀시트까지 세어 「2건」 을 알렸다. **하루 한 번** — 지난 요청이 하루 안이면 누가 언제 했는지
 * 보이고 단추를 잠근다(서버도 막는다).
 */

import { Send } from 'lucide-react'
import { useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type { ApprovalAskStatus, Material } from '@/modules/materials/api'
import { AskDialog, askedMessage } from '@/shared/components/AskDialog'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

/** 지난 요청 — 「앨리스 · AI(MCP) 경유 · 2026. 10. 16.」 */
function lastAsked(status: ApprovalAskStatus): string | null {
  const last = status.last
  if (!last) return null
  return [
    last.by_name,
    last.via ? `${last.via} 경유` : null,
    new Date(last.at).toLocaleDateString('ko-KR'),
  ]
    .filter(Boolean)
    .join(' · ')
}

export function DeclaredApprovalAsk({ material }: { material: Material }) {
  const [open, setOpen] = useState(false)
  const status = useResource(() => materialsApi.declaredApprovalStatus(material.id), [material.id])
  const now = status.data
  if (!now || now.pending === 0) return null
  const locked = now.next_allowed_at !== null && now.next_allowed_at !== undefined
  const who = lastAsked(now)
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed px-3 py-2 text-xs">
      <span>
        승인을 기다리는 값 <b>{now.pending}건</b> — 자료 관리자가 근거 문서와 대조해 승인하면
        등급이 오릅니다.
        {who && <span className="text-muted-foreground ml-1">(요청함 · {who})</span>}
      </span>
      <Button
        size="sm"
        variant="outline"
        className="ml-auto"
        disabled={locked}
        title={
          locked
            ? '하루 안에 이미 승인을 요청했습니다 — 같은 부탁은 하루에 한 번입니다.'
            : '자료 관리자에게 승인을 요청합니다.'
        }
        onClick={() => setOpen(true)}
      >
        <Send className="size-3.5" />
        승인 요청
      </Button>
      <AskDialog
        open={open}
        title={`「${material.record_name}」 선언 값 승인 요청`}
        body={
          <>
            승인을 기다리는 값(재료와 시료) <b>{now.pending}건</b>을 자료 관리자에게 알립니다. 같은
            재료는 하루에 한 번입니다.
          </>
        }
        onSend={async (note) => {
          const result = await materialsApi.requestDeclaredApproval(material.id, note)
          status.reload()
          return `승인 대기 ${result.pending}건 — ${askedMessage(result.notified)}`
        }}
        onClose={() => setOpen(false)}
      />
    </div>
  )
}
