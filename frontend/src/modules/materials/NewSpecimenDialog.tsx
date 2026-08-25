/**
 * 시편 추가 — **재료 화면과 시험 등록 화면이 같은 폼을 쓴다.**
 *
 * `NewSampleDialog`·`NewMaterialDialog` 와 같은 이유로 재료 모듈에 있다.
 * 만드는 대상이 재료 계층이라, 시험 화면이 자기 안에 다시 구현하면 두 곳의
 * 규칙이 갈라진다.
 */

import { useState } from 'react'

import { LENGTH_UNIT, ORIENTATIONS, materialsApi } from '@/modules/materials/api'
import type { Specimen } from '@/modules/materials/api'
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
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'

/** 방향은 자를 때 정해진다. `NA` 는 방향이 뜻 없는 시험용. */

export function NewSpecimenDialog({
  sampleId,
  open,
  onClose,
  onDone,
}: {
  sampleId: string
  open: boolean
  onClose: () => void
  /** **만든 시편을 넘긴다.** 부른 쪽이 곧바로 고를 수 있어야 한다. */
  onDone: (specimen: Specimen) => void
}) {
  const [orientation, setOrientation] = useState<string>('MD')
  const [form, setForm] = useState({ standard: '', thickness: '', width: '', gauge_length: '' })
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      const created = await materialsApi.createSpecimen(sampleId, {
        orientation,
        standard: form.standard || null,
        thickness: form.thickness === '' ? null : Number(form.thickness),
        width: form.width === '' ? null : Number(form.width),
        gauge_length: form.gauge_length === '' ? null : Number(form.gauge_length),
        length_unit: LENGTH_UNIT,
      })
      setForm({ standard: '', thickness: '', width: '', gauge_length: '' })
      onDone(created)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('등록에 실패했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>시편 추가</DialogTitle>
          <DialogDescription>
            방향은 자를 때 정해집니다. 번호는 방향별로 이어서 붙습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label>방향</Label>
          <div className="flex gap-2">
            {ORIENTATIONS.map((value) => (
              <Button
                key={value}
                type="button"
                size="sm"
                variant={orientation === value ? 'default' : 'outline'}
                onClick={() => setOrientation(value)}
              >
                {value}
              </Button>
            ))}
          </div>
        </div>

        {/* **규격이 치수를 정한다.** 그래서 치수 위에 둔다 — 아래 세 칸이
            어디서 나온 값인지가 이 한 줄이다. 장비 파일에는 없어서 사람이
            넣어야 하는 값이기도 하다. */}
        <VocabularyField
          slug="specimen_standard"
          label="시편 규격"
          value={form.standard}
          onChange={(next) => setForm((current) => ({ ...current, standard: next }))}
        />

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="thickness">실측 두께 (mm)</Label>
            <Input id="thickness" type="number" step="0.01" {...field('thickness')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="width">실측 폭 (mm)</Label>
            <Input id="width" type="number" step="0.01" {...field('width')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gauge">게이지 길이 (mm)</Label>
            <Input id="gauge" type="number" step="0.1" {...field('gauge_length')} />
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving}>
            추가
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}