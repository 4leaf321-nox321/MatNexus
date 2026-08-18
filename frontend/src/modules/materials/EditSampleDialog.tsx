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
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

interface Props {
  sample: Sample
  open: boolean
  onClose: () => void
  onSaved: () => void
}

/** 숫자는 문자열로 들고 있는다 — `Number('0.')` 이 0 이 되어 소수점이 지워진다. */
function initial(sample: Sample) {
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

  const field = (key: keyof ReturnType<typeof initial>) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setFailure(null)
    try {
      await materialsApi.updateSample(sample.id, {
        // 빈 칸은 `null` 로 보낸다 — 지운 것과 안 건드린 것을 구분해야 한다.
        // 다만 밀도는 다르다: 0 을 보내면 "쟀는데 0" 이 되므로 아예 안 보낸다.
        lot_no: form.lot_no || null,
        alias: form.alias || null,
        manufacturer: form.manufacturer || null,
        distributor: form.distributor || null,
        primary_vendor: form.primary_vendor || null,
        sales_type: form.sales_type || null,
        applied_product: form.applied_product || null,
        applied_part: form.applied_part || null,
        production_date: form.production_date || null,
        density: form.density === '' ? null : Number(form.density),
        density_unit: DENSITY_UNIT,
        note: form.note || null,
      })
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
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="es-lot">로트 번호</Label>
              <Input id="es-lot" {...field('lot_no')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-alias">별칭</Label>
              <Input id="es-alias" {...field('alias')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-maker">제조사</Label>
              <Input id="es-maker" {...field('manufacturer')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-dist">유통사</Label>
              <Input id="es-dist" {...field('distributor')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-vendor">주 벤더</Label>
              <Input id="es-vendor" {...field('primary_vendor')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-sales">판매 유형</Label>
              <Input id="es-sales" {...field('sales_type')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-product">적용 제품</Label>
              <Input id="es-product" {...field('applied_product')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-part">적용 부위</Label>
              <Input id="es-part" {...field('applied_part')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-date">생산일</Label>
              <Input id="es-date" type="date" {...field('production_date')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="es-density">밀도 (kg/m³)</Label>
              <Input id="es-density" inputMode="decimal" placeholder="이 로트 실측" {...field('density')} />
            </div>
          </div>

          {/* **어느 자리에 무엇을 적는지가 결과를 바꾼다.** 여기 적은 값은
              재료의 공칭값을 이기고 카드로 들어간다. */}
          <p className="text-muted-foreground text-xs">
            밀도는 <b>이 로트에서 잰 값</b>일 때만 넣으세요 — 카드가 재료의 공칭값보다
            이쪽을 먼저 씁니다. 푸아송비는 로트마다 달라지는 값이 아니라 <b>재료</b>에
            있습니다.
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="es-note">메모</Label>
            <Input id="es-note" {...field('note')} />
          </div>

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
