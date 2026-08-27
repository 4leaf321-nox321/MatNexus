/**
 * 고른 시편의 **칸 하나**를 한 번에 맞춘다.
 *
 * ## 왜 이 둘뿐인가
 *
 * **규격**은 그 시편의 치수 칸을 정한다(ADR 0010). 이관에서 규격이 빈 시편이
 * 무더기로 생겼고, 그때 고칠 길이 시편을 하나씩 여는 것뿐이었다 — 수백 장이면
 * 그것은 길이 아니다.
 *
 * **방향**은 잘못 고른 것을 되돌릴 자리가 필요하다. 지우고 다시 만들면 그 시편의
 * 시험이 함께 사라진다.
 *
 * 치수는 여기 없다. 시편마다 **잰 값**이라 같은 값으로 맞추는 것 자체가 틀렸다 —
 * 열어 두면 스무 장이 같은 두께를 갖게 되고, 그 뒤 응력이 통째로 어긋난다.
 *
 * ## 왜 한 칸인가
 *
 * 여러 칸을 함께 받으면 「안 보낸 것」과 「비운 것」을 구별할 수 없다. 화면도
 * 「지금 무엇을 바꾸는 중인가」를 말하기 어려워지고, 그러면 20건을 바꾸는 단추를
 * 누르는 순간 무슨 일이 일어날지 사람이 확신할 수 없다(시험 일괄 수정과 같다).
 *
 * ## 방향은 이름과 번호를 바꾼다
 *
 * 칸 하나를 갈아 끼우는 일이 아니다. 옮겨 가는 방향에서 번호를 새로 받고 시험
 * 이름까지 따라간다. **그 사실을 미리 말하고, 끝난 뒤에도 무엇이 바뀌었는지
 * 보여 준다** — 방향만 골랐는데 번호까지 달라지는 것은 사람이 예상 못 한다.
 */

import { useEffect, useState } from 'react'

import { ORIENTATIONS, materialsApi } from '@/modules/materials/api'
import type { SpecimenBulkField, SpecimenBulkResult } from '@/modules/materials/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
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
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

/** 고칠 수 있는 칸. **서버의 `field` 목록과 같다.** */
const FIELDS: { key: SpecimenBulkField; label: string; hint: string }[] = [
  {
    key: 'standard',
    label: '시편 규격',
    hint: '이 규격이 그 시편의 치수 칸과 단면적 식을 정합니다.',
  },
  {
    key: 'orientation',
    label: '방향',
    hint: '이름과 번호가 다시 매겨집니다. 번호는 옮겨 가는 방향에서 새로 받습니다.',
  },
]

export function BulkSpecimenDialog({
  open,
  specimenIds,
  onClose,
  onDone,
}: {
  open: boolean
  specimenIds: string[]
  onClose: () => void
  onDone: () => void
}) {
  const [field, setField] = useState<SpecimenBulkField>('standard')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<Error | null>(null)
  const [done, setDone] = useState<SpecimenBulkResult | null>(null)

  // 창을 다시 열면 처음부터. 지난번 값이 남아 있으면 그것을 그대로 거는 사고가 난다.
  useEffect(() => {
    if (open) {
      setField('standard')
      setValue('')
      setFailed(null)
      setDone(null)
    }
  }, [open])

  const chosen = FIELDS.find((one) => one.key === field)!
  // **방향은 못 비운다.** 이름의 한 칸이라 빈 방향인 시편은 있을 수 없다.
  const blocked = field === 'orientation' && value === ''

  async function apply() {
    setBusy(true)
    setFailed(null)
    try {
      const result = await materialsApi.bulkUpdateSpecimens(
        specimenIds,
        field,
        value === '' ? null : value
      )
      setDone(result)
      onDone()
    } catch (error) {
      setFailed(error as Error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>시편 {specimenIds.length}건 일괄 수정</DialogTitle>
          <DialogDescription>
            한 번에 한 칸을 같은 값으로 맞춥니다. 고른 시편 전부에 걸립니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={failed} />

        {done ? (
          <div className="space-y-2 text-sm">
            <p>
              <b>{done.updated}건</b>을 바꿨습니다.
              {/* **조용히 성공으로 세지 않는다.** 20건을 골랐는데 「17건」 이
                  나오면 나머지 셋이 왜 빠졌는지 알 수 있어야 한다. */}
              {done.unchanged > 0 && (
                <span className="text-muted-foreground">
                  {' '}
                  {done.unchanged}건은 이미 그 값이었습니다.
                </span>
              )}
            </p>
            {done.blocked.length > 0 && (
              <p className="text-amber-700 dark:text-amber-500">
                {done.blocked.length}건은 손대지 못했습니다 (권한이 없거나 사라진 시편).
              </p>
            )}
            {/* **번호가 바뀐 것을 보여 준다.** 방향만 골랐는데 이름이 달라지는
                것은 예상 못 하는 일이라, 끝나고 나서도 말해 줘야 한다. */}
            {done.renamed.length > 0 && (
              <div className="rounded-md border p-2">
                <p className="mb-1 text-xs font-medium">이름이 다시 매겨졌습니다</p>
                <ul className="text-muted-foreground space-y-0.5 font-mono text-xs">
                  {done.renamed.slice(0, 8).map((said) => (
                    <li key={said}>{said}</li>
                  ))}
                  {done.renamed.length > 8 && <li>… {done.renamed.length - 8}건 더</li>}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>무엇을</Label>
              <Select
                value={field}
                onValueChange={(next) => {
                  setField(next as SpecimenBulkField)
                  setValue('')
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FIELDS.map((one) => (
                    <SelectItem key={one.key} value={one.key}>
                      {one.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">{chosen.hint}</p>
            </div>

            <div className="space-y-1.5">
              <Label>어떤 값으로</Label>
              {field === 'orientation' ? (
                <Select value={value} onValueChange={setValue}>
                  <SelectTrigger>
                    <SelectValue placeholder="고르세요" />
                  </SelectTrigger>
                  <SelectContent>
                    {ORIENTATIONS.map((one) => (
                      <SelectItem key={one} value={one}>
                        {one}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <>
                  {/* 라벨은 위의 「어떤 값으로」 가 이미 말한다 — 한 번 더
                      적으면 같은 말이 두 줄이 된다. */}
                  <VocabularyField
                    slug="specimen_standard"
                    label=""
                    value={value}
                    onChange={setValue}
                  />
                  {/* **비우면 지운다는 것을 말한다.** 확인만 하려고 창을 열었다
                      무심코 누른 사람이 스무 건을 비운다. */}
                  <p className="text-muted-foreground text-xs">
                    비워 두고 적용하면 <b>규격을 지웁니다.</b> 그러면 그 시편은 치수 칸을
                    잃습니다.
                  </p>
                </>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          {done ? (
            <Button onClick={onClose}>닫기</Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={busy}>
                취소
              </Button>
              <Button onClick={() => void apply()} disabled={busy || blocked}>
                {busy ? '거는 중…' : `${specimenIds.length}건에 걸기`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
