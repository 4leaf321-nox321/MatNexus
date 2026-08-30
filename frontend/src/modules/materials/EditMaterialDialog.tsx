/**
 * 재료 수정 — **이름이 따라 바뀐다는 것을 먼저 보여 준다.**
 *
 * Grade·Details·스펙 두께는 이름을 만드는 값이라, 고치면 `SECC_MDOI_1.0` 이
 * 달라지고 **그 아래 시료·시편·시험 이름이 전부 따라 바뀐다**(ADR 0004 —
 * 이름은 참조 키가 아니라 표시라서 다시 계산해 덮는다).
 *
 * 그것이 이 설계의 값이다. 기존 앱은 이름이 곧 식별자여서 재료 이름을 고칠
 * 방법 자체가 없었다. 다만 **모르고 누르면 놀란다** — 시편 11개와 시험 11건의
 * 이름이 한꺼번에 달라지므로, 새 이름과 영향 범위를 저장 전에 적는다.
 *
 * 별칭·메모는 이름에 안 들어간다. 부르기 쉬운 이름을 자주 바꾸는 것이 자연스러운데
 * 그때마다 하위가 흔들리면 안 되기 때문이다.
 */

import { display } from '@/shared/units'
import { useEffect, useState } from 'react'
import { ArrowRight } from 'lucide-react'

import { DENSITY_UNIT, LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import { VocabularyField } from '@/modules/vocabulary/VocabularyField'
import { VocabularyMultiField } from '@/modules/vocabulary/VocabularyMultiField'
import type { Material, NamePreview } from '@/modules/materials/api'
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

interface Props {
  material: Material
  open: boolean
  onClose: () => void
  onDone: () => void
}

function initial(material: Material) {
  return {
    family: material.family,
    category: material.category,
    grade: material.grade,
    details: material.details ?? '',
    // **문자열로 들고 있는다.** 숫자 입력을 제어 컴포넌트로 두면 `Number('0.')`
    // 이 0 이 되어 소수점을 찍는 순간 지워진다 — 처리 옵션에서 겪은 것과 같다.
    spec_thickness: material.spec_thickness == null ? '' : String(material.spec_thickness),
    density: material.density == null ? '' : String(material.density),
    poisson_ratio: material.poisson_ratio == null ? '' : String(material.poisson_ratio),
    alias: material.alias ?? '',
    note: material.note ?? '',
  }
}

/** 밀도를 보여 줄 기호. **표가 정한다** — 손으로 적으면 표만 바뀌었을 때 어긋난다. */
const DENSITY_SYMBOL = display('kg/m3').unit

export function EditMaterialDialog({ material, open, onClose, onDone }: Props) {
  const [form, setForm] = useState(() => initial(material))
  const [products, setProducts] = useState<string[]>(material.applied_products ?? [])
  const [parts, setParts] = useState<string[]>(material.applied_parts ?? [])
  const [preview, setPreview] = useState<NamePreview | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  const thickness = form.spec_thickness === '' ? null : Number(form.spec_thickness)

  useEffect(() => {
    if (open) {
      setForm(initial(material))
      setProducts(material.applied_products ?? [])
      setParts(material.applied_parts ?? [])
      setPreview(null)
      setError(null)
    }
  }, [open, material])

  // 등록 폼과 같은 규칙 — 서버가 이름을 만드는 유일한 곳이다. 화면이 규칙을
  // 다시 구현하면 두 구현이 갈라지고, 그때 보여 준 이름과 저장된 이름이 달라진다.
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

  const field = (key: keyof ReturnType<typeof initial>) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value })),
  })

  const renamed = preview != null && preview.record_name !== material.record_name
  // 자기 이름을 그대로 두는 것은 중복이 아니다. 서버도 자신을 빼고 검사한다.
  const conflict = renamed && preview.taken

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      await materialsApi.update(material.id, {
        family: form.family,
        category: form.category,
        grade: form.grade,
        details: form.details || null,
        spec_thickness: thickness,
        spec_thickness_unit: LENGTH_UNIT,
        applied_products: products,
        applied_parts: parts,
        density: form.density === '' ? null : Number(form.density),
        density_unit: DENSITY_UNIT,
        poisson_ratio: form.poisson_ratio === '' ? null : Number(form.poisson_ratio),
        alias: form.alias || null,
        note: form.note || null,
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('수정에 실패했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>재료 수정</DialogTitle>
          <DialogDescription>
            Grade·Details·두께를 고치면 이름이 다시 만들어집니다. 별칭과 메모는 이름에
            들어가지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          {/* **분류는 사슬이다.** Family 를 고르면 Category 가, Category 를
              고르면 Grade 가 그 아래로 좁혀진다(ADR 0010). */}
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
            <Label htmlFor="edit-details">Details</Label>
            <Input id="edit-details" placeholder="같은 규격 구분용" {...field('details')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-thickness">스펙 두께 ({LENGTH_UNIT})</Label>
            <Input id="edit-thickness" inputMode="decimal" {...field('spec_thickness')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-alias">별칭 (선택)</Label>
            <Input id="edit-alias" {...field('alias')} />
          </div>
        </div>

        {/* **여기가 이 값들의 자리다.**
            푸아송비는 로트마다 달라지는 값이 아니고, 인장시험이 주지도 않는다 —
            문헌값이 재료 등급에 붙는다. 시료에 두었더니 로트 5개에 0.3 을 다섯
            번 적어야 했고, 그중 하나만 0.28 로 고쳐지는 일이 생겼다.

            밀도는 여기가 '공칭' 이다. 로트에서 잰 값이 있으면 시료에 넣고,
            카드는 그쪽을 먼저 쓴다. */}
        {/* **용도는 재료의 성질이다.** 시료에 있었을 때는 "도어 이너용 재료가
            뭐가 있나" 를 물으려면 로트를 전부 뒤져야 했고, 같은 재료의 로트
            다섯 개에 같은 용도를 다섯 번 적어야 했다. */}
        <div className="grid grid-cols-2 gap-3">
          {/* **여러 개 고를 수 있다**(v1.89.0). 한 재료가 여러 제품에 들어간다. */}
          <VocabularyMultiField
            slug="product"
            label="적용 제품"
            values={products}
            onChange={setProducts}
          />
          <VocabularyMultiField
            slug="part"
            label="적용 파트"
            values={parts}
            onChange={setParts}
          />
        </div>

        <div className="rounded-md border p-3">
          <p className="mb-2 text-sm font-medium">CAE 물성</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="edit-density">밀도 ({DENSITY_SYMBOL}, 공칭)</Label>
              <Input
                id="edit-density"
                inputMode="decimal"
                placeholder="7.85e-9"
                {...field('density')}
              />
              <p className="text-muted-foreground text-xs">
                로트에서 잰 값은 시료에 넣습니다 — 카드는 그쪽을 먼저 씁니다.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-poisson">푸아송비</Label>
              <Input
                id="edit-poisson"
                inputMode="decimal"
                placeholder="0.3"
                {...field('poisson_ratio')}
              />
              <p className="text-muted-foreground text-xs">
                인장시험은 이 값을 주지 않습니다. 대개 문헌값입니다.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="edit-note">메모 (선택)</Label>
          <Input id="edit-note" {...field('note')} />
        </div>

        <div className="bg-muted/40 rounded-md border p-3">
          <p className="text-muted-foreground mb-1 text-xs">이름 (자동)</p>
          {renamed ? (
            <p className="flex flex-wrap items-center gap-2 font-mono text-sm">
              <span className="text-muted-foreground line-through">
                {material.record_name}
              </span>
              <ArrowRight className="size-3.5" />
              <span>{preview.record_name}</span>
            </p>
          ) : (
            <p className="font-mono text-sm">{preview?.record_name ?? material.record_name}</p>
          )}

          {conflict && (
            <p className="text-destructive mt-1 text-xs">
              같은 이름의 재료가 이미 있습니다. Details 로 구분하세요.
            </p>
          )}

          {/* **모르고 누르면 놀란다.** 시편과 시험 이름이 한꺼번에 달라진다. */}
          {renamed && !conflict && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-500">
              이름이 바뀌면 이 재료의 <b>시료 {material.sample_count}건과 그 아래 시편·시험
              이름이 전부 따라 바뀝니다.</b> 저장된 값과 곡선은 그대로입니다 — 이름은
              표시일 뿐 참조 키가 아닙니다.
            </p>
          )}
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving || !form.grade || conflict}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
