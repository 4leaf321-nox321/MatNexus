/**
 * 적어 둔 값만으로 카드 만들기 — **시험이 하나도 없는 재료의 길**(ADR 0016).
 *
 * 경화 카드는 대표 곡선에서 나온다. 시험이 없으면 그 길이 아예 없는데, 탄성계수·
 * 열물성은 인장시험이 주지 않는 값이다 — 그 재료의 선언 물성은 갈 데가 없었다.
 *
 * ## 모달이 얇은 이유
 *
 * 여기서 정할 것이 거의 없다. **값은 이미 재료에 적혀 있다** — 물성 탭에서
 * 적었고, 이 모달은 그것을 카드로 굳힐 뿐이다. 푸아송비·밀도만 덮어쓸 수 있게
 * 두는 것은 경화 카드 저장 모달과 같은 이유다: 재료에 없을 때 여기서 한 번
 * 넣고 지나갈 수 있어야 한다.
 *
 * **무엇이 실릴지 먼저 보인다.** 저장을 누른 뒤에 "적어 둔 물성이 없습니다" 를
 * 보는 것은 늦다 — 서버도 막지만, 막힌다는 것을 누르기 전에 알아야 한다.
 */

import { useEffect, useMemo, useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import type { PropertyCard } from '@/modules/fitting/api'
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
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

export function DeclaredCardDialog({
  materialId,
  open,
  onClose,
  onSaved,
}: {
  materialId: string
  open: boolean
  onClose: () => void
  onSaved: (card: PropertyCard) => void
}) {
  // 열 때마다 다시 읽는다. **물성 탭에서 값을 채우고 돌아오는 것이 정상
  // 흐름이다** — 캐시해 두면 방금 적은 값이 여기 안 뜬다.
  //
  // **재료를 직접 읽지 않는다.** 무엇이 실리는지는 카드를 만드는 계산이 안다 —
  // 화면이 선언 물성을 보고 나름대로 판정하면 "실린다" 고 한 값이 안 실리는
  // 일이 생기고, 그때 사람은 이 화면을 믿을 근거를 잃는다.
  const found = useResource(
    () => (open ? fittingApi.declaredPreview(materialId) : Promise.resolve(null)),
    [materialId, open]
  )
  const rows = found.data?.values ?? []
  const blocks = found.data?.blocks ?? []

  // **단위를 화면에 박지 않는다.** 블록 선언이 값마다 저장 단위를 들고 있다 —
  // 새 물성이 붙어도 여기는 안 고친다(`CardBlocks` 와 같은 규칙).
  const specs = useResource(() => fittingApi.blocks(), [])
  const unitOf = useMemo(() => {
    const table = new Map<string, string | null>()
    for (const spec of specs.data ?? []) {
      for (const one of spec.produces) table.set(one.key, one.si_unit)
    }
    return (key: string) => table.get(key) ?? null
  }, [specs.data])

  const [label, setLabel] = useState('')
  const [poisson, setPoisson] = useState('')
  const [density, setDensity] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (open) {
      setLabel('문헌값')
      setPoisson('')
      setDensity('')
      setNote('')
      setError(null)
    }
  }, [open])

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const card = await fittingApi.createDeclaredCard({
        material_id: materialId,
        label,
        poisson_ratio: poisson === '' ? null : Number(poisson),
        density: density === '' ? null : Number(density),
        note: note || null,
      })
      onSaved(card)
      onClose()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('만들지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>적어 둔 값으로 카드 만들기</DialogTitle>
          <DialogDescription>
            시험에서 나온 값이 하나도 안 들어갑니다. 재료의 <b>물성</b> 탭에 적어 둔 값만
            싣고, 덱에는 「사람이 적은 값」이라고 근거 문서와 함께 나갑니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={found.error ?? specs.error ?? error} />

        {/* **무엇이 실릴지 먼저 보인다.** 저장을 누른 뒤에 "없습니다" 를 보는
            것은 늦다. */}
        <div className="rounded-md border p-3 text-sm">
          <div className="text-muted-foreground mb-1 text-xs">실릴 값</div>
          {blocks.length === 0 && !found.loading ? (
            <p className="text-muted-foreground text-xs">
              적어 둔 물성이 없습니다. 재료의 <b>물성</b> 탭에서 먼저 채우세요 — 값이 없는
              카드는 목록에서 「이 재료는 물성이 있다」고 말하게 됩니다.
            </p>
          ) : (
            <ul className="space-y-0.5">
              {rows.map((row) => (
                <li key={row.key} className="tabular-nums">
                  {row.label} <b>{formatScalar(row.value ?? 0, unitOf(row.key))}</b>
                  {/* **어디서 온 값인지 함께 본다.** 시료 실측 밀도와 문헌
                      탄성계수가 한 카드에 섞여 들어간다. */}
                  <span className="text-muted-foreground ml-2 text-xs">{row.detail}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label htmlFor="declared-label" className="mb-1">
              카드 이름
            </Label>
            <Input
              id="declared-label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="declared-poisson" className="mb-1">
              푸아송비
            </Label>
            {/* 재료에 있으면 비워 둔다 — 두 곳에 적으면 어느 쪽이 맞는지
                판정할 근거가 없다. */}
            <Input
              id="declared-poisson"
              value={poisson}
              inputMode="decimal"
              placeholder="재료에 있으면 비워 두세요"
              onChange={(event) => setPoisson(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="declared-density" className="mb-1">
              밀도 (kg/m³)
            </Label>
            <Input
              id="declared-density"
              value={density}
              inputMode="decimal"
              placeholder="시료·재료에 있으면 비워 두세요"
              onChange={(event) => setDensity(event.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="declared-note" className="mb-1">
              메모
            </Label>
            <Input
              id="declared-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button onClick={save} disabled={saving || !label || blocks.length === 0}>
            {saving ? '만드는 중…' : '만들기'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
