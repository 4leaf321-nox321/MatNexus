/**
 * 「물성 카드 하나 만들기」 의 첫 걸음 — **카드를 만들 재료 하나를 고른다**(ADR 0058).
 *
 * 카드는 재료의 것이다(재료 상세의 「CAE 카드」 탭). 워크벤치에서 그 업무를 하려면 먼저 어느
 * 재료인지가 정해져야 하고, 그 뒤의 준비도 · 카드 패널은 재료 화면의 것을 그대로 세운다 — 따로
 * 만들면 카드를 만드는 자리가 둘이 되고, 그중 하나만 고쳐지는 날이 온다.
 *
 * **담은 시험의 재료를 먼저 권한다.** 옛 「DMA 한 벌로 점탄성 계수 내기」 작업은 시험을 담았다 —
 * 그 작업을 이 업무로 이어 열면 재료를 다시 찾게 하지 않는다.
 */

import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { Material } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'

export interface MaterialRef {
  id: string
  label: string
}

export function CardMaterialPick({
  current,
  suggested,
  disabled = false,
  onPick,
}: {
  current: MaterialRef | null
  /** 담은 시험의 재료 — 그 재료로 바로 하자고 권한다. */
  suggested: MaterialRef[]
  disabled?: boolean
  onPick: (materialId: string) => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function pick(id: string) {
    setBusy(true)
    setError(null)
    try {
      await onPick(id)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('고르지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const others = suggested.filter((one) => one.id !== current?.id)

  return (
    <section aria-label="재료 고르기" className="space-y-2">
      <ErrorNotice error={error} />
      {current ? (
        <p className="text-sm">
          카드를 만들 재료:{' '}
          <Link
            to={`/materials/${current.id}?tab=cards`}
            className="font-medium underline underline-offset-2"
          >
            {current.label}
          </Link>
        </p>
      ) : (
        <p className="text-muted-foreground text-sm">아직 고른 재료가 없습니다.</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <MaterialPicker
          value={null}
          action
          disabled={disabled || busy}
          placeholder={current ? '다른 재료로 바꾸기' : '재료 고르기'}
          ariaLabel="카드를 만들 재료"
          className="w-72"
          onSelect={(material: Material) => void pick(material.id)}
        />
        {others.map((one) => (
          <Button
            key={one.id}
            size="sm"
            variant="outline"
            disabled={disabled || busy}
            onClick={() => void pick(one.id)}
          >
            담은 시험의 재료: {one.label} <ArrowRight className="size-3.5" />
          </Button>
        ))}
      </div>
    </section>
  )
}
