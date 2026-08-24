/**
 * Prony 적합에서 물성 카드로 — **만들어 둔 형식에 닿는 자리.**
 *
 * `abaqus_viscoelastic` 은 v1.14.0 에 등록됐는데 거기로 가는 카드가 없었다.
 * 파일에서 마스터커브까지, 마스터커브에서 Prony 까지는 도는데 그 계수를 담을
 * 카드를 만들 길이 없어서 **한 번도 불릴 수 없는 렌더러**였다.
 *
 * ## 푸아송비를 여기서 받는다
 *
 * `*ELASTIC` 은 값 두 개를 받는 키워드라 하나를 비울 수 없는데 **DMA 는
 * 푸아송비를 재지 않는다.** 재료에 적혀 있으면 서버가 물려받고, 없으면 여기서
 * 받는다. 그래도 없으면 카드는 만들어지되 Abaqus 덱은 못 낸다 — 0.3 으로
 * 채우면 그것이 측정값인지 덱만 봐서는 알 수 없다.
 */

import { useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import type { PronyFit } from '@/modules/viscoelastic/api'
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

export function ViscoelasticCardDialog({
  fit,
  suggestedLabel,
  onClose,
  onDone,
}: {
  fit: PronyFit
  suggestedLabel: string
  onClose: () => void
  onDone: () => void
}) {
  const [label, setLabel] = useState(suggestedLabel)
  const [poisson, setPoisson] = useState('')
  const [density, setDensity] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await fittingApi.createViscoelastic({
        prony_fit_id: fit.id,
        label,
        // **빈 칸은 안 보낸다.** 0 을 보내면 그것이 잰 값인지 알 수 없다.
        poisson_ratio: poisson.trim() ? Number(poisson) : null,
        density: density.trim() ? Number(density) : null,
        note: note.trim() || null,
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('카드를 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>물성 카드 만들기</DialogTitle>
          <DialogDescription>
            이 적합의 계수 {fit.terms.length}항이 카드가 됩니다. <b>시편 한 건</b>의
            마스터커브에서 나온 값이라, 재료의 대푯값이 아니라 그 시편의 값이라는 사실이
            카드와 덱에 적힙니다.
          </DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="vc-label">이름</Label>
            <Input
              id="vc-label"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="vc-poisson">푸아송비</Label>
              <Input
                id="vc-poisson"
                value={poisson}
                placeholder="비우면 재료에서"
                onChange={(event) => setPoisson(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="vc-density">밀도 (kg/m³)</Label>
              <Input
                id="vc-density"
                value={density}
                placeholder="비우면 재료에서"
                onChange={(event) => setDensity(event.target.value)}
              />
            </div>
          </div>
          {/* **DMA 는 푸아송비를 재지 않는다.** 없으면 없는 채로 둔다. */}
          <p className="text-muted-foreground text-xs">
            DMA 는 푸아송비와 밀도를 재지 않습니다. 재료·시료에 있으면 그것을 쓰고,
            아무 데도 없으면 <b>빈 채로 둡니다</b> — 그 카드로는 Abaqus 덱을 낼 수
            없다고 그때 짚어 줍니다. 0.3 으로 채우면 그것이 잰 값인지 덱만 봐서는
            알 수 없습니다.
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="vc-note">메모</Label>
            <Input id="vc-note" value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            닫기
          </Button>
          <Button onClick={() => void save()} disabled={busy || !label.trim()}>
            만들기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
