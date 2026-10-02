/**
 * 기본 제공 형식 — **코드로 만든 솔버 덱.** 여기서 고치지 않는다 — 대신 **내릴 수 있다.**
 *
 * 정의 표와 **한 표에 섞지 않는다** — 지울 수 있는 것과 없는 것이 섞이면 지우기가 왜 안
 * 되는지 화면에 안 나온다. 그래도 이 화면에 있어야 한다: 이 화면을 연 사람이 「ANSYS 는
 * 정의 하나뿐」 으로 읽었다(2026-09-27). 솔버 × 물성 모델 서른 개 가까이가 코드에 있는데
 * 여기서는 안 보였다.
 *
 * ## 사용 중단 (ADR 0037)
 *
 * 코드라 화면에서 못 고친다. 틀린 것이 발견되면 고쳐 배포하기까지 공백이 생기고, 그 사이
 * 사람들은 틀린 덱을 계속 받는다. **시스템 관리자가 내린다** — 내려진 형식은 내보내기 메뉴·
 * 카드의 「낼 수 있는 형식」·내려받기에서 빠지고, 이 표에는 사연과 함께 남는다(다시 쓰려면
 * 보여야 한다). 걸고 푼 일은 변경 이력에 남는다.
 *
 * ## 정의판 (ADR 0038 · 0047)
 *
 * 형식마다 그것을 정의로 옮긴 비상용 사본(`<key>_def`)이 꺼진 채로 있다. **내린 줄에서 바로
 * 켠다** — 위 정의 목록 50줄에서 짝을 찾게 하면 그 사이 사람들은 형식 없이 기다린다. 다시 쓸
 * 때는 반대로 정의판을 끄라고 한다(안 끄면 메뉴에 같은 형식이 두 줄 선다).
 */

import { useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import type { BuiltinFormat, ExportProfile } from '@/modules/fitting/api'
import { canEdit } from '@/modules/ownership/access'
import { groupBySolver } from '@/modules/fitting/formatGroups'
import { useAuth } from '@/shared/auth/AuthContext'
import { isSystemAdmin } from '@/shared/auth/roles'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Label } from '@/shared/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'

export function BuiltinFormatsSection({
  twins = {},
  onToggleTwin,
}: {
  /** 형식 key → 그 형식의 정의판. 없으면 정의판 단추를 안 세운다. */
  twins?: Record<string, ExportProfile>
  onToggleTwin?: (twin: ExportProfile) => Promise<void>
} = {}) {
  const { user } = useAuth()
  const admin = isSystemAdmin(user)
  const formats = useResource(() => fittingApi.builtinFormats(), [])
  const [error, setError] = useState<Error | null>(null)
  const [holding, setHolding] = useState<BuiltinFormat | null>(null)
  const groups = groupBySolver(formats.data ?? [])
  const stopped = (formats.data ?? []).filter((one) => one.hold !== null).length

  async function release(item: BuiltinFormat) {
    setError(null)
    const twin = twins[item.key]
    const note = twin?.is_active
      ? `\n\n정의판 '${twin.key}' 이(가) 켜져 있습니다 — 다시 쓰면 메뉴에 같은 형식이 두 줄 서니, 이 줄의 「정의판 끄기」 로 끄세요.`
      : ''
    if (!window.confirm(`${item.label} 을(를) 다시 씁니다. 고친 판이 배포됐나요?${note}`)) return
    try {
      await fittingApi.releaseFormat(item.key)
      formats.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('다시 쓰지 못했습니다.'))
    }
  }

  return (
    <section className="mt-8">
      <h2 className="mb-1 font-medium">기본 제공 형식</h2>
      <p className="text-muted-foreground mb-3 text-sm">
        코드로 만들어져 배포와 함께 옵니다 — 운영 서버에도 그대로 있고, 여기서 고치지 않습니다.
        물성 모델마다 따로 내며, 카드의 <b>내보내기</b> 메뉴에서 고릅니다. 틀린 것이 발견되면
        시스템 관리자가 <b>사용 중단</b>으로 내려 고친 판이 배포될 때까지 메뉴에서 뺍니다.
        {stopped > 0 ? ` 지금 ${stopped}개가 내려져 있습니다.` : null}
      </p>
      {formats.error ? <ErrorNotice error={formats.error} className="mb-4" /> : null}
      {error ? <ErrorNotice error={error} className="mb-4" /> : null}
      {groups.length === 0 && !formats.loading ? (
        <p className="text-muted-foreground rounded-md border border-dashed p-6 text-sm">
          기본 제공 형식을 읽지 못했습니다.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>솔버</TableHead>
              <TableHead>형식</TableHead>
              <TableHead>확장자</TableHead>
              <TableHead>무엇을 쓰나</TableHead>
              <TableHead className="w-28" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {groups.flatMap((group) =>
              group.items.map((item, index) => (
                <TableRow key={item.key}>
                  {/* 솔버 이름은 묶음의 첫 줄에만 — 같은 이름이 여섯 번 서면 표가 읽히지 않는다. */}
                  <TableCell className="font-medium">{index === 0 ? group.solver : null}</TableCell>
                  <TableCell>
                    <span className="flex flex-wrap items-center gap-1.5">
                      {item.label}
                      {item.hold ? <Badge variant="destructive">사용 중단</Badge> : null}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono">.{item.extension}</TableCell>
                  <TableCell>
                    {item.describe}
                    {item.hold ? (
                      // **왜 내렸는지가 같은 줄에 선다.** 쓰는 사람은 「어제 있던 형식이 왜
                      // 없나」 를 여기서 보고, 그때 받은 덱을 다시 받아야 하는지 판단한다.
                      <span className="mt-1 block text-red-700 dark:text-red-400">
                        {item.hold.reason} — {item.hold.held_by_name ?? '?'},{' '}
                        {new Date(item.hold.held_at).toLocaleDateString('ko-KR')}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right">
                    <span className="flex flex-wrap justify-end gap-1">
                      {admin ? (
                        item.hold ? (
                          <Button size="sm" variant="outline" onClick={() => void release(item)}>
                            다시 쓰기
                          </Button>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={() => setHolding(item)}>
                            사용 중단
                          </Button>
                        )
                      ) : null}
                      <TwinButton
                        held={item.hold !== null}
                        twin={twins[item.key]}
                        onToggle={onToggleTwin}
                      />
                    </span>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      )}
      <HoldDialog
        item={holding}
        onClose={() => setHolding(null)}
        onDone={() => {
          setHolding(null)
          formats.reload()
        }}
      />
    </section>
  )
}

function HoldDialog({
  item,
  onClose,
  onDone,
}: {
  item: BuiltinFormat | null
  onClose: () => void
  onDone: () => void
}) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    if (!item) return
    setBusy(true)
    setError(null)
    try {
      await fittingApi.holdFormat(item.key, reason.trim())
      setReason('')
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('내리지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={item !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>기본 형식 사용 중단</DialogTitle>
          <DialogDescription>
            {item?.label} 을(를) 내보내기 메뉴·카드·내려받기에서 뺍니다. 고친 판이 배포되면 다시
            씁니다.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="hold-reason">사유</Label>
          <Textarea
            id="hold-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="예) *MAT_076 의 장기 탄성률이 빠졌다 — 그동안 받은 덱은 다시 받을 것"
          />
          {/* 사유가 내려받기 거절 메시지에 그대로 나온다 — 「틀렸다」 만으로는 받은 사람이
              그때 받은 덱을 다시 받아야 하는지 모른다. */}
          <p className="text-muted-foreground text-xs">
            이 형식을 고르려던 사람에게 그대로 보입니다. 무엇이 틀렸고 이미 받은 덱을 어떻게 할지
            적어 주세요.
          </p>
        </div>
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button
            variant="destructive"
            disabled={busy || reason.trim().length < 2}
            onClick={() => void submit()}
          >
            사용 중단
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 그 형식의 정의판 켜기 · 끄기. **필요한 때만 선다** — 내렸는데 꺼져 있으면 「켜기」, 켜져 있으면
 * 「끄기」(살아 있는 형식과 두 줄이 되는 것을 알린다). 내리지도 켜지도 않았으면 아무것도 없다 —
 * 평소에는 정의판을 만질 일이 없다.
 */
function TwinButton({
  held,
  twin,
  onToggle,
}: {
  held: boolean
  twin: ExportProfile | undefined
  onToggle?: (twin: ExportProfile) => Promise<void>
}) {
  if (!twin || !onToggle || !canEdit(twin.access)) return null
  if (twin.is_active) {
    return (
      <Button
        size="sm"
        variant="ghost"
        title={held ? '대신 쓰는 정의판을 끕니다' : '이 형식이 살아 있어 메뉴에 같은 형식이 두 줄입니다'}
        className={held ? undefined : 'text-amber-700 dark:text-amber-500'}
        onClick={() => void onToggle(twin)}
      >
        정의판 끄기
      </Button>
    )
  }
  if (!held) return null
  return (
    <Button
      size="sm"
      variant="outline"
      title={`${twin.key} 를 켜서 대신 씁니다 — 정의 목록에서 고칠 수 있습니다`}
      onClick={() => void onToggle(twin)}
    >
      정의판 켜기
    </Button>
  )
}
