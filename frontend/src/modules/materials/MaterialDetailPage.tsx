/**
 * 재료 상세 — 시료와 시편.
 *
 * 계층이 화면에 그대로 보여야 한다. 재료(규격) 아래 시료(실물 한 덩이), 그 아래
 * 시편(잘라낸 조각). **방향은 시편에 있다** — 자를 때 정해지기 때문이고, 그래야
 * 같은 시료의 MD/TD/DD 를 묶어 r값·이방성 파라미터를 구할 수 있다(ADR 0004).
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight, FlaskConical, Globe2, Layers, Plus } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { DENSITY_UNIT, LENGTH_UNIT, materialsApi } from '@/modules/materials/api'
import type { Sample } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'

const ORIENTATIONS = ['MD', 'TD', 'DD', 'NA'] as const

export default function MaterialDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const material = useResource(() => materialsApi.get(id), [id])
  const samples = useResource(() => materialsApi.samples(id), [id])
  const [addingSample, setAddingSample] = useState(false)
  const [deleteError, setDeleteError] = useState<Error | null>(null)

  const item = material.data

  async function removeMaterial() {
    setDeleteError(null)
    try {
      await materialsApi.remove(id)
      navigate('/materials')
    } catch (caught) {
      // 서버가 "시료 N건이 남아 있어 지울 수 없습니다" 를 이유와 함께 준다.
      setDeleteError(caught instanceof Error ? caught : new Error('삭제에 실패했습니다.'))
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={item?.record_name ?? '재료'}
        description={item?.alias ?? undefined}
        actions={
          <Button variant="outline" onClick={removeMaterial}>
            삭제
          </Button>
        }
      />

      <ErrorNotice error={material.error ?? deleteError} className="mb-4" />

      {item && (
        <dl className="mb-8 grid grid-cols-2 gap-x-6 gap-y-3 rounded-md border p-4 text-sm sm:grid-cols-4">
          <Field label="Family" value={item.family} />
          <Field label="Category" value={item.category} />
          <Field label="Grade" value={item.grade} />
          <Field label="Details" value={item.details ?? '—'} />
          <Field
            label="스펙 두께"
            value={
              item.spec_thickness == null
                ? '—'
                : `${item.spec_thickness} ${item.spec_thickness_unit}`
            }
          />
          <Field
            label="소속"
            value={
              item.is_global ? (
                <Badge variant="outline" className="gap-1">
                  <Globe2 className="size-3" />
                  전역
                </Badge>
              ) : (
                (item.owner_workspace_name ?? '—')
              )
            }
          />
          <Field label="시료" value={`${item.sample_count}건`} />
          <Field
            label="등록"
            value={new Date(item.created_at).toLocaleDateString('ko-KR')}
          />
        </dl>
      )}

      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-medium">
          <Layers className="size-4" />
          시료
        </h2>
        <Button size="sm" variant="secondary" onClick={() => setAddingSample(true)}>
          <Plus className="size-4" />
          시료 추가
        </Button>
      </div>

      <ErrorNotice error={samples.error} className="mb-4" />

      {!samples.loading && (samples.data ?? []).length === 0 && (
        <div className="text-muted-foreground rounded-md border py-10 text-center text-sm">
          시료가 없습니다. 시험을 등록하려면 시료와 시편이 먼저 있어야 합니다.
        </div>
      )}

      <ul className="space-y-2">
        {(samples.data ?? []).map((sample) => (
          <SampleRow key={sample.id} sample={sample} onChanged={() => samples.reload()} />
        ))}
      </ul>

      <AddSampleDialog
        materialId={id}
        open={addingSample}
        onClose={() => setAddingSample(false)}
        onDone={() => {
          setAddingSample(false)
          samples.reload()
          material.reload()
        }}
      />
    </div>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  )
}

function SampleRow({ sample, onChanged }: { sample: Sample; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const specimens = useResource(
    () => (open ? materialsApi.specimens(sample.id) : Promise.resolve([])),
    [open, sample.id]
  )

  return (
    <li className="rounded-md border">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="hover:bg-muted/40 flex w-full items-center gap-3 p-3 text-left"
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <span className="font-mono text-xs">{sample.record_name}</span>
        {sample.lot_no && <Badge variant="outline">로트 {sample.lot_no}</Badge>}
        <span className="text-muted-foreground ml-auto text-sm">
          시편 {sample.specimen_count}
        </span>
      </button>

      {open && (
        <div className="border-t p-3">
          <dl className="mb-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <Field label="제조사" value={sample.manufacturer ?? '—'} />
            <Field label="벤더" value={sample.primary_vendor ?? '—'} />
            <Field label="생산일" value={sample.production_date ?? '—'} />
            <Field
              label="밀도"
              value={
                sample.density == null ? '—' : `${sample.density} ${sample.density_unit}`
              }
            />
          </dl>

          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm font-medium">
              <FlaskConical className="size-3.5" />
              시편
            </span>
            <Button size="sm" variant="ghost" onClick={() => setAdding(true)}>
              <Plus className="size-3.5" />
              시편 추가
            </Button>
          </div>

          <ErrorNotice error={specimens.error} className="mb-2" />

          {(specimens.data ?? []).length === 0 ? (
            <p className="text-muted-foreground py-4 text-center text-sm">시편이 없습니다.</p>
          ) : (
            <ul className="divide-y">
              {(specimens.data ?? []).map((specimen) => (
                <li key={specimen.id} className="flex items-center gap-3 py-2 text-sm">
                  <Badge variant="secondary">{specimen.orientation}</Badge>
                  <span className="font-mono text-xs">{specimen.record_name}</span>
                  <span className="text-muted-foreground ml-auto tabular-nums">
                    {[specimen.thickness, specimen.width, specimen.gauge_length]
                      .map((value) => (value == null ? '—' : value))
                      .join(' × ')}{' '}
                    {specimen.length_unit}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <AddSpecimenDialog
            sampleId={sample.id}
            open={adding}
            onClose={() => setAdding(false)}
            onDone={() => {
              setAdding(false)
              specimens.reload()
              onChanged()
            }}
          />
        </div>
      )}
    </li>
  )
}

function AddSampleDialog({
  materialId,
  open,
  onClose,
  onDone,
}: {
  materialId: string
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [form, setForm] = useState({
    lot_no: '',
    manufacturer: '',
    primary_vendor: '',
    production_date: '',
    density: '',
    poisson_ratio: '',
  })
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      await materialsApi.createSample(materialId, {
        lot_no: form.lot_no || null,
        manufacturer: form.manufacturer || null,
        primary_vendor: form.primary_vendor || null,
        production_date: form.production_date || null,
        density: form.density === '' ? null : Number(form.density),
        density_unit: DENSITY_UNIT,
        poisson_ratio: form.poisson_ratio === '' ? null : Number(form.poisson_ratio),
      })
      setForm({
        lot_no: '',
        manufacturer: '',
        primary_vendor: '',
        production_date: '',
        density: '',
        poisson_ratio: '',
      })
      onDone()
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
      <DialogContent>
        <DialogHeader>
          <DialogTitle>시료 추가</DialogTitle>
          <DialogDescription>
            이름은 재료별 일련번호로 자동 부여됩니다. 로트번호는 나중에 채워도 이름이
            바뀌지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="lot">로트번호 (선택)</Label>
            <Input id="lot" placeholder="L240612" {...field('lot_no')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="production">생산일 (선택)</Label>
            <Input id="production" type="date" {...field('production_date')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="manufacturer">제조사</Label>
            <Input id="manufacturer" {...field('manufacturer')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="vendor">주 벤더</Label>
            <Input id="vendor" {...field('primary_vendor')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="density">밀도 (kg/m³)</Label>
            <Input id="density" type="number" step="1" placeholder="7850" {...field('density')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="poisson">포아송비</Label>
            <Input
              id="poisson"
              type="number"
              step="0.01"
              placeholder="0.3"
              {...field('poisson_ratio')}
            />
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

function AddSpecimenDialog({
  sampleId,
  open,
  onClose,
  onDone,
}: {
  sampleId: string
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [orientation, setOrientation] = useState<string>('MD')
  const [form, setForm] = useState({ thickness: '', width: '', gauge_length: '' })
  const [error, setError] = useState<Error | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      await materialsApi.createSpecimen(sampleId, {
        orientation,
        thickness: form.thickness === '' ? null : Number(form.thickness),
        width: form.width === '' ? null : Number(form.width),
        gauge_length: form.gauge_length === '' ? null : Number(form.gauge_length),
        length_unit: LENGTH_UNIT,
      })
      setForm({ thickness: '', width: '', gauge_length: '' })
      onDone()
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
      <DialogContent>
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
