/**
 * 재료 등록 — **목록에서도, 시험 등록 화면에서도 같은 폼을 쓴다.**
 *
 * `NewSampleDialog` 와 같은 이유로 재료 모듈에 있다. 만드는 대상이 재료라,
 * 시험 화면이 자기 안에 다시 구현하면 두 곳의 규칙이 갈라진다.
 *
 * 파일로 뺀 이유는 실사용에서 나왔다. 「시험 등록」이 재료·시료·시편을 **고르기만**
 * 해서, 새 판을 받아 시편을 뜬 사람이 *"재료 상세에서 먼저 만드세요"* 를 보고
 * 다른 화면에 다녀와야 했다. **파일이 오는 순간이 그 셋을 처음 아는 순간이다.**
 */

import { useEffect, useState } from 'react'

import { DENSITY_UNIT, LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import type { Material, NamePreview } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
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
import type { ApiError } from '@/shared/api/client'

const EMPTY = {
  family: 'Metal',
  category: 'Steel',
  grade: '',
  details: '',
  spec_thickness: '',
  applied_product: '',
  applied_part: '',
  density: '',
  poisson_ratio: '',
  alias: '',
}

export function NewMaterialDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  /** **만든 재료를 넘긴다.** 부른 쪽이 곧바로 고를 수 있어야 한다 —
   * 다시 목록을 받아 찾게 하면 방금 만든 것이 안 보이는 순간이 생긴다. */
  onDone: (material: Material) => void
}) {
  const [form, setForm] = useState(EMPTY)
  const [preview, setPreview] = useState<NamePreview | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [saving, setSaving] = useState(false)

  const thickness = form.spec_thickness === '' ? null : Number(form.spec_thickness)

  // 입력하는 동안 서버에 이름을 물어본다. 잠깐 기다렸다 보내는 이유는, 글자마다
  // 요청하면 목록 화면 하나가 서버를 두드리는 꼴이 되기 때문이다.
  useEffect(() => {
    if (!open) return
    const timer = setTimeout(() => {
      materialsApi
        .previewName({
          grade: form.grade || null,
          details: form.details || null,
          spec_thickness: thickness,
          spec_thickness_unit: LENGTH_UNIT,
        })
        .then(setPreview)
        .catch(() => setPreview(null))
    }, 250)
    return () => clearTimeout(timer)
  }, [open, form.grade, form.details, thickness])

  useEffect(() => {
    if (open) {
      setForm(EMPTY)
      setPreview(null)
      setError(null)
    }
  }, [open])

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      const created = await materialsApi.create({
        family: form.family,
        category: form.category,
        grade: form.grade,
        details: form.details || null,
        spec_thickness: thickness,
        spec_thickness_unit: LENGTH_UNIT,
        applied_product: form.applied_product || null,
        applied_part: form.applied_part || null,
        density: form.density === '' ? null : Number(form.density),
        density_unit: DENSITY_UNIT,
        poisson_ratio: form.poisson_ratio === '' ? null : Number(form.poisson_ratio),
        alias: form.alias || null,
      })
      onDone(created)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('등록에 실패했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const field = (key: keyof typeof EMPTY) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>재료 등록</DialogTitle>
          <DialogDescription>
            이름은 입력한 값에서 자동으로 만들어집니다. 부르기 쉬운 이름은 별칭에 넣으세요.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <VocabularyField
            slug="family"
            label="Family"
            value={form.family}
            onChange={(next) => setForm((current) => ({ ...current, family: next }))}
          />
          <VocabularyField
            slug="category"
            label="Category"
            value={form.category}
            parentValue={form.family}
            onChange={(next) => setForm((current) => ({ ...current, category: next }))}
          />
          <VocabularyField
            slug="grade"
            label="Grade"
            value={form.grade}
            parentValue={form.category}
            onChange={(next) => setForm((current) => ({ ...current, grade: next }))}
          />
          <div className="space-y-1.5">
            <Label htmlFor="details">Details</Label>
            <Input id="details" placeholder="MDOI (같은 규격 구분용)" {...field('details')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="thickness">스펙 두께 (mm)</Label>
            <Input id="thickness" type="number" step="0.01" placeholder="1.0" {...field('spec_thickness')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="alias">별칭 (선택)</Label>
            <Input id="alias" placeholder="도어 이너 강판" {...field('alias')} />
          </div>
          {/* CAE 물성. **여기 없으면 카드를 만들 때 막힌다** — 그때 되돌아와
              채우는 것보다 아는 값이면 지금 넣는 편이 싸다. 비워도 등록된다. */}
          <VocabularyField
            slug="product"
            label="적용 제품 (선택)"
            value={form.applied_product}
            onChange={(next) => setForm((current) => ({ ...current, applied_product: next }))}
          />
          <VocabularyField
            slug="part"
            label="적용 부위 (선택)"
            value={form.applied_part}
            onChange={(next) => setForm((current) => ({ ...current, applied_part: next }))}
          />
          <div className="space-y-1.5">
            <Label htmlFor="density">밀도 (kg/m³, 선택)</Label>
            <Input id="density" type="number" step="1" placeholder="7850" {...field('density')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="poisson">푸아송비 (선택)</Label>
            <Input id="poisson" type="number" step="0.01" placeholder="0.3" {...field('poisson_ratio')} />
          </div>
        </div>

        <div className="bg-muted/40 rounded-md border p-3">
          <p className="text-muted-foreground mb-1 text-xs">이름 (자동)</p>
          <p className="font-mono text-sm">{preview?.record_name ?? '—'}</p>
          {preview?.taken && (
            <p className="text-destructive mt-1 text-xs">
              같은 이름의 재료가 이미 있습니다. Details 로 구분하세요.
            </p>
          )}
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving || !form.grade || preview?.taken}>
            등록
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
