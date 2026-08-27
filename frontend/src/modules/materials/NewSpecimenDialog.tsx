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

        {/* **규격이 치수를 정한다.** 시편을 만들 때 사람이 할 일은 이것 하나다 —
            치수는 규격에서 오고, 시험마다 잰 값은 그 파일에서 온다. */}
        <VocabularyField
          slug="specimen_standard"
          label="시편 규격"
          value={form.standard}
          onChange={(next) => setForm((current) => ({ ...current, standard: next }))}
        />

        {/* **치수를 여기서 안 묻는다.**
         *
         * 실사용에서 나왔다 — *"시편 추가에 왜 실측 추가가 나오지? 시편의 값은
         * 규격의 값으로 하고, 시험에다 두께·폭 같은 걸 넣기로 한 거 아니었어?"*.
         * 맞다. 읽는 순서가 셋이다(v1.118.0):
         *
         *     ① 이 시험이 잰 값     장비 파일의 `a0`·`b0` — 파싱이 담는다
         *     ② 시편에 적힌 값       여기
         *     ③ 규격이 정한 공칭     위에서 고른 규격
         *
         * 그러니 시편을 만들 때 할 일은 **규격을 고르는 것**이고, 치수는 대개
         * 적을 일이 없다. 앞에 내놓으면 사람은 적어야 하는 줄 알고, 그때 적은
         * 값이 규격 공칭과 어긋나면 어느 것이 맞는지 알 수 없게 된다.
         *
         * 그래도 자리는 남긴다 — 치수를 안 주는 장비가 있고, 그 시편만 규격과
         * 다르게 잘린 경우도 있다. 접어 두고 **왜 여는지**를 적는다. */}
        <details className="rounded-md border px-3 py-2">
          <summary className="text-muted-foreground cursor-pointer text-xs">
            이 시편이 규격과 다르면 적으세요 (보통은 비웁니다)
          </summary>
          <p className="text-muted-foreground mt-1.5 text-xs">
            비우면 <b>위에서 고른 규격의 값</b>을 씁니다. 시험 파일이 잰 값이 있으면
            그 시험은 <b>그 값</b>으로 돕니다 — 여기 적은 것보다 먼저입니다.
          </p>
          <div className="mt-2 grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="thickness">두께 ({LENGTH_UNIT})</Label>
              <Input id="thickness" type="number" step="0.01" {...field('thickness')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="width">폭 ({LENGTH_UNIT})</Label>
              <Input id="width" type="number" step="0.01" {...field('width')} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="gauge">게이지 길이 ({LENGTH_UNIT})</Label>
              <Input id="gauge" type="number" step="0.1" {...field('gauge_length')} />
            </div>
          </div>
        </details>

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