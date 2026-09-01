/**
 * 고른 카드를 **한 묶음으로** 내보내는 띠 (ADR 0024 ②).
 *
 * 해석 하나에 재료가 여럿 들어간다. 지금까지는 카드를 한 장씩 내려받아 사람이 폴더에
 * 모았고, **그 묶음이 무엇이었는지는 아무 데도 안 남았다.** 해석자가 물을 것은
 * 하나다 — 「내가 받은 이 덱이 그때 그 카드가 맞나」.
 *
 * ## 고른 것이 없으면 안 뜬다
 *
 * 늘 떠 있으면 목록 아래가 항상 가려진다. 담긴 것이 정하는 것은 워크벤치의 바구니와
 * 같은 규칙이다.
 *
 * ## 형식과 단위계를 여기서 고른다
 *
 * 낱장 내보내기와 **같은 목록**을 쓴다. 화면이 형식을 적어 두면 새 덱 형식을 붙일
 * 때 두 곳을 고쳐야 한다 — 이 저장소가 반복해 내린 판단이다.
 */

import { FileDown, X } from 'lucide-react'
import { useState } from 'react'

import { fittingApi } from '@/modules/fitting/api'
import type { ExportFormat } from '@/modules/fitting/api'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

export function BundleBar({
  ids,
  formats,
  onClear,
  onError,
}: {
  ids: string[]
  formats: ExportFormat[]
  onClear: () => void
  onError: (error: Error) => void
}) {
  const systems = useResource(() => fittingApi.unitSystems(), [])
  const [chosen, setChosen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const available = systems.data ?? []
  // 고르기 전에는 서버가 기본이라고 말한 것. **화면이 'si' 를 적어 두지 않는다.**
  const system =
    available.find((one) => one.key === chosen) ??
    available.find((one) => one.is_default) ??
    available[0] ??
    null

  if (ids.length === 0) return null

  async function send(format: ExportFormat) {
    if (!system) return
    setBusy(true)
    try {
      await fittingApi.downloadBundle(ids, format, system)
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('묶음을 내보내지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="bg-background sticky bottom-0 z-10 mt-3 flex flex-wrap items-center gap-2 rounded-md border p-3"
      aria-label="묶음 내보내기"
    >
      <span className="text-sm font-medium">{ids.length}장 골랐습니다</span>

      <div className="flex items-center gap-1">
        {available.map((one) => (
          <button
            key={one.key}
            type="button"
            aria-pressed={system?.key === one.key}
            className={`rounded-md border px-2 py-1 text-xs ${
              system?.key === one.key ? 'bg-primary text-primary-foreground' : ''
            }`}
            onClick={() => setChosen(one.key)}
          >
            {one.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {formats.map((format) => (
          <Button
            key={format.key}
            size="sm"
            variant="outline"
            disabled={busy || system === null}
            onClick={() => void send(format)}
          >
            <FileDown className="size-3.5" />
            {format.label}
          </Button>
        ))}
      </div>

      {/* **묶음에 무엇이 들어가는지 미리 말한다.** 압축을 풀고 나서 알면 늦다. */}
      <span className="text-muted-foreground text-xs">
        덱 파일과 함께 <code>manifest.json</code>·<code>SHA256SUMS</code> 가 들어갑니다 —
        받은 쪽이 「그때 그 카드가 맞나」 를 검산할 수 있습니다. 초안이 섞였으면 그 사실도
        적힙니다.
      </span>

      <Button size="sm" variant="ghost" className="ml-auto" onClick={onClear}>
        <X className="size-3.5" />
        고른 것 비우기
      </Button>
    </div>
  )
}
