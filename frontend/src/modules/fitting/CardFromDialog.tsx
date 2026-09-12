/**
 * 「이것으로 카드 만들기」 대화상자 — **묻지 않고 만드는 단추는 없다.**
 *
 * 실사용(2026-09-05): 선형탄성구간(LVE) 카드·속도 의존 카드가 단추 하나로 바로 만들어졌다. 누른
 * 사람은 아무 설명 없이 화면이 바뀌는 것을 봤고, 누를 때마다 같은 초안이 하나씩
 * 쌓여 여덟 장이 됐다. 점탄성 카드는 이미 대화상자를 거치는데(이름·푸아송비·밀도·
 * 메모), 둘만 달랐다.
 *
 * 그래서 셋이 같은 대화상자를 쓴다. 무엇이 실리는지(`preview`)를 먼저 보이고, 이름을
 * 확인시키고, 만든 뒤에는 **그 재료의 CAE 카드 탭**으로 간다 — 전역 카드 목록으로
 * 보내면 방금 만든 것이 어느 것인지 찾아야 한다.
 */

import { useState } from 'react'
import type { ReactNode } from 'react'

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
import { InheritedFields, densityToSi } from '@/modules/fitting/InheritedFields'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 대화상자가 모아 주는 값. **빈 칸은 `null`** — 0 을 보내면 그것이 잰 값인지 알 수 없다. */
export interface CardFromValues {
  label: string
  poisson_ratio: number | null
  density: number | null
  note: string | null
  /** `declaredOption` 을 준 대화상자만 싣는다. 재료에 적어 둔 값(열물성)을 함께 실을지. */
  include_declared?: boolean
}

export function CardFromDialog({
  materialId,
  title,
  description,
  preview,
  suggestedLabel,
  existingDrafts = 0,
  declaredOption,
  onSubmit,
  onClose,
  onDone,
}: {
  /**
   * 「재료 기본 정보 함께 싣기」 확인란. 주면 보이고 기본으로 켜진다 — 선형탄성구간
   * 카드 한 장으로 열응력 해석까지 돌게 비열·열전도율이 따라온다(2026-09-05).
   */
  declaredOption?: {
    label: string
    help: ReactNode
    /** 켜면 실제로 따라오는 것. 무엇이 실리는지 모른 채 켜게 하지 않는다. */
    carried?: ReactNode
  }
  /** 비워 둔 푸아송비·밀도가 어디서 올지 물어볼 재료. */
  materialId: string
  title: string
  description: ReactNode
  /** 이 카드에 실리는 값들. 만들기 전에 보여 준다. */
  preview?: ReactNode
  suggestedLabel: string
  /** 같은 자리에 이미 있는 초안 수. 막지 않고 말만 한다 — 조건을 바꿔 다시 만드는 것은 정상이다. */
  existingDrafts?: number
  onSubmit: (values: CardFromValues) => Promise<PropertyCard>
  onClose: () => void
  onDone: (card: PropertyCard) => void
}) {
  const [label, setLabel] = useState(suggestedLabel)
  const [poisson, setPoisson] = useState('')
  const [density, setDensity] = useState('')
  const [note, setNote] = useState('')
  const [includeDeclared, setIncludeDeclared] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const card = await onSubmit({
        label: label.trim(),
        poisson_ratio: poisson.trim() ? Number(poisson) : null,
        density: densityToSi(density),
        note: note.trim() || null,
        ...(declaredOption ? { include_declared: includeDeclared } : {}),
      })
      onDone(card)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('카드를 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <ErrorNotice error={error} />

        {preview && (
          <div className="bg-muted/50 rounded-md border p-3 text-sm">
            <p className="text-muted-foreground mb-1 text-xs">이 카드에 실리는 것</p>
            {preview}
          </div>
        )}

        {existingDrafts > 0 && (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400">
            같은 자리에 초안 {existingDrafts}장이 이미 있습니다. 조건을 바꿔 다시 만드는 것이
            아니면 그것을 쓰세요 — 같은 초안이 쌓이면 어느 것을 확정할지 골라야 합니다.
          </p>
        )}

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="cf-label">이름</Label>
            <Input id="cf-label" value={label} onChange={(event) => setLabel(event.target.value)} />
          </div>

          {/* **비우면 무엇이 오는지 보인다.** 「비우면 재료에서」 만으로는 그 값이
              무엇인지 모른 채 비우게 된다(2026-09-05). */}
          <InheritedFields
            materialId={materialId}
            idPrefix="cf"
            poisson={poisson}
            density={density}
            onPoisson={setPoisson}
            onDensity={setDensity}
          />

          {declaredOption && (
            <label className="flex items-start gap-2 rounded-md border p-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                aria-label={declaredOption.label}
                checked={includeDeclared}
                onChange={(event) => setIncludeDeclared(event.target.checked)}
              />
              <span>
                <span className="font-medium">{declaredOption.label}</span>
                <span className="text-muted-foreground block text-xs">{declaredOption.help}</span>
                {declaredOption.carried && (
                  <span className="mt-1 block text-xs">{declaredOption.carried}</span>
                )}
              </span>
            </label>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="cf-note">메모</Label>
            <Input id="cf-note" value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            닫기
          </Button>
          <Button onClick={() => void save()} disabled={busy || !label.trim()}>
            {busy ? '만드는 중…' : '생성'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
