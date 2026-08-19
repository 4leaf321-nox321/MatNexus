/**
 * 시료 고치기.
 *
 * **재료와 시편에는 수정이 있는데 시료만 없었다.** 로트 번호를 잘못 적었거나
 * 밀도를 나중에 재면 고칠 길이 없어, 시료를 지우고 다시 만들어야 했다 —
 * 그런데 시편이 달린 시료는 서버가 삭제를 막는다. 막다른 길이었다.
 *
 * 번호(`seq_no`)는 여기서 안 바꾼다. 그것이 시료 이름을 만들고 이름은 시편과
 * 시험까지 따라 내려간다(ADR 0004).
 *
 * 밀도는 **이 로트에서 잰 값**일 때만 넣는다. 재료의 공칭값과 다른 자리이고,
 * 카드는 이쪽을 먼저 쓴다 — 관례값을 여기 적으면 그것이 실측인 척하게 된다.
 * 푸아송비는 여기 없다. 로트마다 달라지는 값이 아니라 재료에 있다.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { DENSITY_UNIT, materialsApi } from '@/modules/materials/api'
import type { Sample } from '@/modules/materials/api'
import { SampleFields, samplePayload } from '@/modules/materials/SampleFields'
import type { SampleForm } from '@/modules/materials/SampleFields'
import { ApiError } from '@/shared/api/client'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

interface Props {
  sample: Sample
  open: boolean
  onClose: () => void
  onSaved: () => void
}

/** 숫자는 문자열로 들고 있는다 — `Number('0.')` 이 0 이 되어 소수점이 지워진다. */
function initial(sample: Sample): SampleForm {
  return {
    lot_no: sample.lot_no ?? '',
    alias: sample.alias ?? '',
    manufacturer: sample.manufacturer ?? '',
    distributor: sample.distributor ?? '',
    primary_vendor: sample.primary_vendor ?? '',
    sales_type: sample.sales_type ?? '',
    applied_product: sample.applied_product ?? '',
    applied_part: sample.applied_part ?? '',
    production_date: sample.production_date ?? '',
    density: sample.density == null ? '' : String(sample.density),
    note: sample.note ?? '',
  }
}

export function EditSampleDialog({ sample, open, onClose, onSaved }: Props) {
  const [form, setForm] = useState(() => initial(sample))
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setForm(initial(sample))
      setFailure(null)
    }
  }, [open, sample])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setFailure(null)
    try {
      // 빈 칸은 `null` 로 간다 — 지운 것과 안 건드린 것을 구분해야 한다.
      // 변환은 추가 창과 **같은 함수**를 쓴다.
      await materialsApi.updateSample(sample.id, samplePayload(form, DENSITY_UNIT))
      onSaved()
    } catch (error) {
      setFailure(error instanceof ApiError ? error.message : '저장하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>시료 수정</DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {sample.record_name}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-3">
          <SampleFields
            idPrefix="edit-sample"
            form={form}
            onChange={(key, value) => setForm((current) => ({ ...current, [key]: value }))}
          />

          {failure && <p className="text-destructive text-sm">{failure}</p>}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
              취소
            </Button>
            <Button type="submit" disabled={busy}>
              저장
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
