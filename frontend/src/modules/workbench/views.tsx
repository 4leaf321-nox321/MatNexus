/**
 * 단계에 끼우는 전용 화면 — **조립만 한다**(ADR 0058).
 *
 * 화면은 도메인 모듈의 것이다: 시험 골라 담기는 시험 모듈, 한번에 처리 · 채택 검토대는 처리
 * 모듈, 카드 패널 · 준비도 · BOM 덱 · 묶음 내보내기는 카드 모듈. 여기는 **바구니에 담긴 것을
 * 그 화면이 받는 모양으로 건네고**, 그 화면이 담으면 바구니에 적는 것까지만 한다.
 *
 * 도메인 화면은 워크벤치를 모른다 — 시험 id 목록 · 재료 id 를 받을 뿐이다. 거꾸로 되면 도메인이
 * 워크벤치를 알게 되고, 그때부터 워크벤치를 떼어 낼 수 없다(ADR 0024).
 *
 * 화면은 늦게 읽는다(`lazy`). 워크벤치 홈은 목록뿐인데, 카드 패널 · 곡선 그림까지 한 번에 받으면
 * 첫 화면이 그만큼 늦다.
 */

import { Suspense, lazy } from 'react'

import { basketApi } from '@/shared/api/basket'
import type { BasketItem, BasketRunDetail, ItemKind } from '@/shared/api/basket'
import type { StepView } from '@/modules/workbench/workflows'
import { useResource } from '@/shared/hooks/useResource'
import { fittingApi } from '@/modules/fitting/api'

const RunCollector = lazy(() =>
  import('@/modules/tests/RunCollector').then((one) => ({ default: one.RunCollector }))
)
const BatchByType = lazy(() =>
  import('@/modules/processing/BatchPanel').then((one) => ({ default: one.BatchByType }))
)
const AdoptionBoard = lazy(() =>
  import('@/modules/processing/AdoptionBoard').then((one) => ({ default: one.AdoptionBoard }))
)
const CardMaterialPick = lazy(() =>
  import('@/modules/fitting/CardMaker').then((one) => ({ default: one.CardMaterialPick }))
)
const DeckReadinessTable = lazy(() =>
  import('@/modules/fitting/DeckReadinessTable').then((one) => ({
    default: one.DeckReadinessTable,
  }))
)
const FittingPanel = lazy(() =>
  import('@/modules/fitting/FittingPanel').then((one) => ({ default: one.FittingPanel }))
)
const BomDeck = lazy(() =>
  import('@/modules/fitting/BomDeckPage').then((one) => ({ default: one.BomDeck }))
)
const BundleBar = lazy(() =>
  import('@/modules/fitting/BundleBar').then((one) => ({ default: one.BundleBar }))
)

export interface ViewProps {
  view: StepView
  run: BasketRunDetail
  /** 이 작업을 이어 할 수 있나 — 아니면 담지 않는다(ADR 0035 3단계). */
  writable: boolean
  onChanged: () => void
  onError: (error: Error) => void
}

/** 살아 있는 것의 id. 사라진 것은 건네지 않는다 — 그것은 바구니의 줄이 이미 말한다. */
function ids(items: BasketItem[], kind: ItemKind): string[] {
  return items.filter((one) => one.kind === kind && !one.missing).map((one) => one.target_id)
}

/**
 * 카드를 만들 재료 — **담은 재료가 먼저**, 없으면 담은 시험의 재료(옛 점탄성 작업이 그렇다).
 * 여럿이면 첫 것이다(그 업무의 판정이 그렇게 말한다).
 */
function materialOf(items: BasketItem[]): { id: string; label: string } | null {
  const material = items.find((one) => one.kind === 'material' && !one.missing)
  if (material) return { id: material.target_id, label: material.label }
  return null
}

function suggestedMaterials(items: BasketItem[]): { id: string; label: string }[] {
  const seen = new Map<string, string>()
  for (const one of items) {
    if (one.kind === 'test_run' && !one.missing && one.material_id) {
      seen.set(one.material_id, one.material_label ?? one.material_id)
    }
  }
  return [...seen.entries()].map(([id, label]) => ({ id, label }))
}

export function StepViewHost(props: ViewProps) {
  return (
    <Suspense fallback={<p className="text-muted-foreground text-sm">화면을 읽는 중…</p>}>
      <ViewBody {...props} />
    </Suspense>
  )
}

function ViewBody({ view, run, writable, onChanged, onError }: ViewProps) {
  const runs = ids(run.items, 'test_run')

  async function add(kind: ItemKind, targets: string[]) {
    await basketApi.add(run.id, kind, targets)
    onChanged()
  }

  switch (view.kind) {
    case 'runs':
      return (
        <RunCollector
          processing={view.processing}
          taken={runs}
          disabled={!writable}
          onPick={(picked) => add('test_run', picked)}
        />
      )
    case 'batch':
      return <BatchByType testRunIds={runs} onDone={onChanged} />
    case 'adopt':
      return <AdoptionBoard testRunIds={runs} onChanged={onChanged} />
    case 'material': {
      const current = materialOf(run.items)
      return (
        <CardMaterialPick
          current={current}
          suggested={suggestedMaterials(run.items)}
          disabled={!writable}
          onPick={async (materialId) => {
            // **이 업무는 재료 하나다** — 바꾸면 앞의 재료를 빼고 담는다. 둘이 담겨 있으면 뒤
            // 단계가 어느 재료의 카드를 보이는지 사람이 헤아려야 한다.
            for (const one of run.items) {
              if (one.kind === 'material' && one.target_id !== materialId) {
                await basketApi.remove(run.id, one.id)
              }
            }
            if (current?.id !== materialId) await basketApi.add(run.id, 'material', [materialId])
            onChanged()
          }}
        />
      )
    }
    case 'readiness':
    case 'cards': {
      const current = materialOf(run.items) ?? suggestedMaterials(run.items)[0] ?? null
      if (!current) {
        return (
          <p className="text-muted-foreground rounded-md border border-dashed p-6 text-center text-sm">
            앞 단계에서 재료를 고르면 여기 섭니다.
          </p>
        )
      }
      return view.kind === 'readiness' ? (
        <DeckReadinessTable materialId={current.id} />
      ) : (
        <FittingPanel materialId={current.id} />
      )
    }
    case 'bom':
      return <BomDeck />
    case 'bundle':
      return <BundleStep ids={ids(run.items, 'card')} onError={onError} />
  }
}

/**
 * 묶음 내보내기 — **카드 목록의 그 띠를 그대로 세운다**(`BundleBar`).
 *
 * 형식 목록은 서버가 준다. 화면이 적어 두면 새 덱 형식을 붙일 때 두 곳을 고쳐야 한다.
 */
function BundleStep({ ids: cards, onError }: { ids: string[]; onError: (error: Error) => void }) {
  const formats = useResource(() => fittingApi.formats(), [])
  if (cards.length === 0) {
    return (
      <p className="text-muted-foreground rounded-md border border-dashed p-6 text-center text-sm">
        담은 카드가 없습니다. 앞 단계에서 카드를 담으면 여기서 한 번에 받습니다.
      </p>
    )
  }
  // 「고른 것 비우기」 를 안 그린다. 여기서 고른 것은 바구니이고, 바구니에서 빼는 것은 아래
  // 바구니의 일이다 — 눌러도 아무 일이 없는 단추를 두면 사람은 「기능이 고장났다」 로 읽는다.
  return <BundleBar ids={cards} formats={formats.data ?? []} onError={onError} />
}
