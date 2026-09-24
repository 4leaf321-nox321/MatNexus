/**
 * 「JSON 내보내기」 — **단위계를 먼저 고르고 받는다**(ADR 0036).
 *
 * 재료·문헌 내보내기는 해석 연동으로 나가는 파일이다. 전에는 계를 고를 자리가 없었고,
 * 재료 파일은 「SI 그대로」 라고 적어 두고 밀도만 tonne/mm3 였다 — 받는 쪽이 전부 SI 로
 * 읽을 뻔했다(2026-09-24). 이제 파일은 고른 계 하나로 나가고 기본은 해석이 쓰는
 * mm·N·tonne 이다.
 *
 * 카드 내보내기 메뉴(`fitting/ExportMenu`)와 같은 순서다 — 계를 먼저 한 번 고르고, 그
 * 아래에서 받는다. 고른 계는 받기 전에 **파일 이름으로** 보인다. 같은 폴더에 두 계가
 * 섞여도 열지 않고 가려지게 하려는 것이라, 서버가 파일 머리에 적는 것과 같은 키를 쓴다.
 */

import { useState } from 'react'
import { Download } from 'lucide-react'

import { chosenSystem, unitSystemsApi } from '@/shared/api/unitSystems'
import type { UnitSystem } from '@/shared/api/unitSystems'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { useResource } from '@/shared/hooks/useResource'

export function ExportJsonMenu({
  stem,
  busy,
  onExport,
}: {
  /** 파일 이름의 앞부분 — 뒤에 `_<계>.json` 이 붙는다. */
  stem: string
  busy: boolean
  onExport: (system: UnitSystem, filename: string) => void
}) {
  const systems = useResource(() => unitSystemsApi.list(), [])
  const [chosen, setChosen] = useState<string | null>(null)
  const available = systems.data ?? []
  const system = chosenSystem(available, chosen)
  const filename = system ? `${stem}_${system.key}.json` : null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={busy}>
          <Download className="size-4" />
          {busy ? '내보내는 중…' : 'JSON 내보내기'}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="font-normal">
          <p className="text-xs font-medium">값의 단위계</p>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {available.map((one) => (
              <button
                key={one.key}
                type="button"
                className={`rounded-md border px-2 py-1 text-xs ${
                  system?.key === one.key ? 'bg-primary text-primary-foreground' : ''
                }`}
                onClick={(event) => {
                  // 계를 고른 다음에 받는 순서라 메뉴가 닫히면 안 된다 — `ExportMenu` 와 같다.
                  event.preventDefault()
                  setChosen(one.key)
                }}
              >
                {one.label}
              </button>
            ))}
          </div>
          <p className="text-muted-foreground mt-1.5 text-xs">
            숫자가 이 계로 나가고, 파일 머리(<code>unit_system</code>)와 이름에 적힙니다.
            저장된 SI 값도 곁에 함께 갑니다.
          </p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={system === null || busy}
          onSelect={() => {
            if (system && filename) onExport(system, filename)
          }}
        >
          <div>
            <p className="text-sm">JSON 받기</p>
            <p className="text-muted-foreground font-mono text-xs">
              {filename ?? '단위계를 읽는 중…'}
            </p>
          </div>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
