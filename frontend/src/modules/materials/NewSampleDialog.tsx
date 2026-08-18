/**
 * 시료 추가 — **재료 화면과 시험 등록 화면이 같은 폼을 쓴다.**
 *
 * 이 컴포넌트가 재료 모듈에 있는 이유는 `SpecimenPicker` 와 같다. 만드는 대상이
 * 재료 계층이므로 규칙도 여기 있어야 한다. 시험 모듈이 자기 안에 시료 폼을 다시
 * 그리면 **두 폼이 갈라진다** — 한쪽에만 필드가 늘거나, 단위를 한쪽만 명시하는
 * 식으로. 밀도의 단위가 그런 종류의 사고가 나기 가장 좋은 자리다.
 *
 * 시험 데이터를 올리다가도 시료를 만들 수 있어야 하는 이유: **파일이 오는 순간이
 * 시료를 처음 아는 순간이기도 하다.** "새로 받은 판에서 자른 시편들" 을 올리는데
 * 시료를 먼저 등록하러 다른 화면에 다녀오게 하면, 시편에서 없앤 왕복이 시료에
 * 그대로 남는다.
 */

import { useState } from 'react'

import { DENSITY_UNIT, materialsApi } from '@/modules/materials/api'
import type { Sample } from '@/modules/materials/api'
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
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const EMPTY = {
  lot_no: '',
  manufacturer: '',
  primary_vendor: '',
  production_date: '',
  density: '',
}

interface Props {
  materialId: string | null
  open: boolean
  onClose: () => void
  onCreated: (sample: Sample) => void
}

export function NewSampleDialog({ materialId, open, onClose, onCreated }: Props) {
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  function field(key: keyof typeof EMPTY) {
    return {
      value: form[key],
      onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
        setForm((current) => ({ ...current, [key]: event.target.value })),
    }
  }

  async function submit() {
    if (!materialId) return
    setSaving(true)
    setError(null)
    try {
      const created = await materialsApi.createSample(materialId, {
        lot_no: form.lot_no || null,
        manufacturer: form.manufacturer || null,
        primary_vendor: form.primary_vendor || null,
        production_date: form.production_date || null,
        density: form.density === '' ? null : Number(form.density),
        // **단위를 항상 명시해 보낸다.** 생략 가능하게 두면 "이 값이 kg/m³ 였나
        // tonne/mm³ 였나" 를 나중에 아무도 답할 수 없다.
        density_unit: DENSITY_UNIT,
      })
      setForm(EMPTY)
      onCreated(created)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('시료를 만들지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>시료 추가</DialogTitle>
          <DialogDescription>
            이름은 재료별 일련번호로 자동 부여됩니다. 로트번호는 나중에 채워도 이름이
            바뀌지 않습니다 — 이름이 바뀌면 옛 보고서가 다른 것을 가리킵니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="sample-lot">로트번호 (선택)</Label>
            <Input id="sample-lot" placeholder="L240612" {...field('lot_no')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sample-production">생산일 (선택)</Label>
            <Input id="sample-production" type="date" {...field('production_date')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sample-manufacturer">제조사</Label>
            <Input id="sample-manufacturer" {...field('manufacturer')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sample-vendor">주 벤더</Label>
            <Input id="sample-vendor" {...field('primary_vendor')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sample-density">밀도 (kg/m³, 이 로트 실측)</Label>
            <Input
              id="sample-density"
              type="number"
              step="1"
              placeholder="7850"
              {...field('density')}
            />
          </div>
        </div>

        <p className="text-muted-foreground text-xs">
          전부 선택 사항입니다. 로트를 관리하지 않는 경우가 있어 비워 두어도 시료는
          만들어집니다. <b>밀도는 이 로트에서 잰 값</b>일 때만 넣으세요 — 카드가
          재료의 공칭값보다 이쪽을 먼저 씁니다. 푸아송비는 로트마다 달라지는 값이
          아니라 <b>재료</b>에 있습니다.
        </p>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving || !materialId}>
            추가
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
