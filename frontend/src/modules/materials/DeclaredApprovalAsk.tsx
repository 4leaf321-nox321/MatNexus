/**
 * 승인을 기다리는 선언 값을 자료 관리자에게 **부탁한다**(2026-10-15).
 *
 * 승인은 자료 관리자만 한다(ADR 0049). 전에는 「승인 대기 값」 화면을 열어 보지 않으면 자료
 * 관리자는 몰랐고, 값을 적은 사람은 누구에게 말해야 할지 몰랐다. 부탁은 알림뿐이다 — 값도
 * 상태도 안 바뀐다.
 *
 * **여기서 세는 것은 재료 쪽 값뿐이다.** 서버는 시료(밀시트) 값까지 세어 알린다 — 밀시트는
 * 승인해도 등급이 안 올라 거의 기다리지 않는다. 판정(승인 전 · 승인하면 등급이 오름)은 서버
 * `declared_approval.waiting` 과 같다: 서버가 준 `tier_if_approved` 로 견준다.
 */

import { Send } from 'lucide-react'
import { useState } from 'react'

import { materialsApi } from '@/modules/materials/api'
import type { DeclaredProperty, Material } from '@/modules/materials/api'
import { AskDialog, askedMessage } from '@/shared/components/AskDialog'
import { Button } from '@/shared/components/ui/button'

/** 승인을 기다리는 줄 수 — 승인 전이고, 승인하면 등급이 오르는 것. */
export function waitingCount(rows: DeclaredProperty[]): number {
  return rows.filter((row) => {
    const tier = row.quality_tier ?? 4
    return !row.approval && (row.tier_if_approved ?? tier) < tier
  }).length
}

export function DeclaredApprovalAsk({ material }: { material: Material }) {
  const [open, setOpen] = useState(false)
  const count = waitingCount(material.declared_properties)
  if (count === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed px-3 py-2 text-xs">
      <span>
        승인을 기다리는 값 <b>{count}건</b> — 자료 관리자가 근거 문서와 대조해 승인하면 등급이
        오릅니다.
      </span>
      <Button size="sm" variant="outline" className="ml-auto" onClick={() => setOpen(true)}>
        <Send className="size-3.5" />
        승인 요청
      </Button>
      <AskDialog
        open={open}
        title={`「${material.record_name}」 선언 값 승인 요청`}
        body={
          <>
            승인을 기다리는 값을 자료 관리자에게 알립니다. 시료(밀시트) 값도 함께 셉니다.
          </>
        }
        onSend={async (note) => {
          const result = await materialsApi.requestDeclaredApproval(material.id, note)
          return `승인 대기 ${result.pending}건 — ${askedMessage(result.notified)}`
        }}
        onClose={() => setOpen(false)}
      />
    </div>
  )
}
