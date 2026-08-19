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
 *
 * 위 주석이 '재료 화면 vs 시험 화면' 의 갈라짐을 막았는데, **'추가 vs 수정' 은
 * 못 봤다** — 추가는 5개, 수정은 11개였다. 필드는 이제 `SampleFields` 에 한 벌만
 * 있다.
 */

import { useState } from 'react'

import { DENSITY_UNIT, materialsApi } from '@/modules/materials/api'
import type { Sample } from '@/modules/materials/api'
import { EMPTY_SAMPLE, SampleFields, samplePayload } from '@/modules/materials/SampleFields'
import type { SampleForm } from '@/modules/materials/SampleFields'
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

interface Props {
  materialId: string | null
  open: boolean
  onClose: () => void
  onCreated: (sample: Sample) => void
}

export function NewSampleDialog({ materialId, open, onClose, onCreated }: Props) {
  const [form, setForm] = useState<SampleForm>(EMPTY_SAMPLE)
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    if (!materialId) return
    setSaving(true)
    setError(null)
    try {
      const created = await materialsApi.createSample(
        materialId,
        samplePayload(form, DENSITY_UNIT)
      )
      setForm(EMPTY_SAMPLE)
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

        <SampleFields
          idPrefix="new-sample"
          form={form}
          onChange={(key, value) => setForm((current) => ({ ...current, [key]: value }))}
        />

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
