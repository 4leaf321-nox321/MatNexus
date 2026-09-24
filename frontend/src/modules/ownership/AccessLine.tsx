/**
 * 「누가 고치나」 한 줄 — 등록자 · 편집 부서, 그리고 **못 고치면 누구에게 물을지**.
 *
 * 전에는 잠긴 이유가 소속에 숨어 있었고, 사람은 단추를 눌러 403 을 받고서야 알았다
 * (ADR 0035). 이 줄이 누르기 전에 같은 말을 한다. 「권한」 을 누르면 넘기는 창이 열린다.
 */

import { Lock, Users } from 'lucide-react'
import { useState } from 'react'

import type { EditAccess, OwnedKind } from '@/modules/ownership/api'
import { OwnershipDialog } from '@/modules/ownership/OwnershipDialog'
import { Button } from '@/shared/components/ui/button'

export function AccessLine({
  kind,
  id,
  access,
  onChanged,
}: {
  kind: OwnedKind
  id: string
  access: EditAccess | null | undefined
  onChanged?: () => void
}) {
  const [open, setOpen] = useState(false)
  if (!access) return null
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {!access.can_edit && (
        <span className="flex items-center gap-1" title={access.reason ?? undefined}>
          <Lock className="size-3.5" />
          읽기 전용
        </span>
      )}
      <span>
        등록자 {access.registrant ?? '없음'} · 편집 부서 {access.edit_workspace ?? '없음'}
      </span>
      {!access.can_edit && access.reason && <span>— {access.reason}</span>}
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        <Users className="size-3.5" />
        권한
      </Button>
      {open && (
        <OwnershipDialog
          kind={kind}
          id={id}
          onClose={() => setOpen(false)}
          onChanged={onChanged}
        />
      )}
    </div>
  )
}
