/**
 * 재료를 찾아 시료 하나를 고른다 — 새 의뢰와 「시료 잇기」 가 같은 부품을 쓴다.
 *
 * 두 단계다: 재료 검색(이름·등급) → 그 재료의 시료. 시료가 없는 재료를 고르면 재료
 * 상세로 안내한다 — 시료는 재료 화면에서 만든다(시편·시험이 거기 딸린다).
 */

import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { Material, Sample } from '@/modules/materials/api'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'

export function SamplePicker({
  sample,
  onChange,
  presetMaterialId,
  presetSampleId,
  idPrefix = 'commission',
}: {
  sample: Sample | null
  onChange: (next: Sample | null) => void
  /** `?material=` 로 왔을 때 미리 고른 재료. */
  presetMaterialId?: string | null
  /** `?sample=` 로 왔을 때 미리 고른 시료. */
  presetSampleId?: string | null
  idPrefix?: string
}) {
  const [material, setMaterial] = useState<Material | null>(null)

  useEffect(() => {
    if (!presetMaterialId) return
    materialsApi
      .get(presetMaterialId)
      .then((found) => setMaterial(found))
      .catch(() => undefined)
  }, [presetMaterialId])

  const samples = useResource(
    () => (material ? materialsApi.samples(material.id) : Promise.resolve<Sample[]>([])),
    [material?.id]
  )
  useEffect(() => {
    if (!presetSampleId || !samples.data) return
    const found = samples.data.find((one) => one.id === presetSampleId)
    if (found) onChange(found)
    // onChange 는 부르는 쪽의 setState 라 안정적이다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetSampleId, samples.data])

  return (
    <>
      <MaterialPicker
        idPrefix={idPrefix}
        value={material}
        onChange={(next) => {
          setMaterial(next)
          onChange(null)
        }}
      />
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-sample`}>시료</Label>
        <select
          id={`${idPrefix}-sample`}
          className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
          disabled={!material}
          value={sample?.id ?? ''}
          onChange={(event) =>
            onChange(samples.data?.find((one) => one.id === event.target.value) ?? null)
          }
        >
          <option value="">{material ? '— 시료 선택 —' : '재료를 먼저 고르세요'}</option>
          {(samples.data ?? []).map((one) => (
            <option key={one.id} value={one.id}>
              {one.record_name}
              {one.lot_no ? ` · ${one.lot_no}` : ''}
            </option>
          ))}
        </select>
        {material && samples.data?.length === 0 && (
          <p className="text-muted-foreground text-xs">
            이 재료에 시료가 없습니다 —{' '}
            <Link to={`/materials/${material.id}`} className="underline">
              재료 상세
            </Link>
            에서 시료를 먼저 등록하세요.
          </p>
        )}
      </div>
    </>
  )
}

/** 재료 찾기 — 이름·등급으로 검색해 하나 고른다. */
function MaterialPicker({
  idPrefix,
  value,
  onChange,
}: {
  idPrefix: string
  value: Material | null
  onChange: (next: Material | null) => void
}) {
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const found = useResource(
    () => (q ? materialsApi.list({ q, limit: 20 }) : Promise.resolve(null)),
    [q]
  )

  return (
    <div className="space-y-1.5">
      <Label htmlFor={`${idPrefix}-material`}>재료</Label>
      {value ? (
        <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <span className="font-medium">{value.record_name}</span>
          <span className="text-muted-foreground">{value.grade}</span>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => {
              onChange(null)
              setQ('')
              setTyped('')
            }}
          >
            다시 선택
          </Button>
        </div>
      ) : (
        <>
          <form
            className="relative"
            onSubmit={(event) => {
              event.preventDefault()
              setQ(typed.trim())
            }}
          >
            <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
            <Input
              id={`${idPrefix}-material`}
              className="pl-8"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="재료 이름·등급으로 검색 후 Enter"
            />
          </form>
          {found.data && (
            <ul className="max-h-48 overflow-y-auto rounded-md border text-sm" aria-label="재료 후보">
              {found.data.items.length === 0 && (
                <li className="text-muted-foreground px-3 py-2">맞는 재료가 없습니다.</li>
              )}
              {found.data.items.map((one) => (
                <li key={one.id}>
                  <button
                    type="button"
                    className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left"
                    onClick={() => onChange(one)}
                  >
                    <span className="font-medium">{one.record_name}</span>
                    <span className="text-muted-foreground">
                      {one.family} · {one.grade}
                    </span>
                    <span className="text-muted-foreground ml-auto tabular-nums">시료 {one.sample_count}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
