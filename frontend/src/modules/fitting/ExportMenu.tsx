/**
 * 카드 하나를 솔버 덱으로 내보내는 메뉴.
 *
 * **두 화면이 같은 것을 쓴다** — 재료 상세의 'CAE 카드' 탭과 전역 카드 목록.
 * 각자 만들면 한쪽만 고쳐지는 날이 오고, 그때 같은 카드가 화면에 따라 다른
 * 형식 목록을 갖는다.
 *
 * ## 낼 수 있는지 서버가 판정한다
 *
 * 전에는 화면이 한국어 이름(`탄성계수`)을 카드 필드에 손으로 이어 붙였다 —
 * 새 물성이 붙으면 그 표에도 줄을 더해야 했고, 안 더하면 낼 수 있는 형식이
 * 회색으로 남았다. 지금은 카드가 `available_formats` 를 들고 온다.
 *
 * **누르기 전에 알려 준다.** 내려받기를 누른 뒤에 "푸아송비가 없습니다" 를
 * 보는 것은 늦다.
 *
 * ## 단위계는 형식보다 위에 있다
 *
 * 형식마다 두 벌로 늘리면 목록이 열두 줄이 된다. 그리고 그 배치는 「형식을
 * 고르다가 단위계를 잘못 고르는」 실수를 만든다 — 두 줄이 나란히 있고 이름이
 * 거의 같기 때문이다. 단위계를 **먼저 한 번** 고르고, 그 아래에서 형식을
 * 고른다. 고른 계는 항상 화면에 떠 있다.
 */

import { useState } from 'react'
import { FileDown } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import type { ExportFormat, PropertyCard } from '@/modules/fitting/api'
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

export function ExportMenu({
  card,
  formats,
  onError,
}: {
  card: PropertyCard
  formats: ExportFormat[]
  onError: (error: Error) => void
}) {
  const systems = useResource(() => fittingApi.unitSystems(), [])
  const [chosen, setChosen] = useState<string | null>(null)
  const available = systems.data ?? []
  // 고르기 전에는 서버가 기본이라고 말한 것. **화면이 'si' 를 적어 두지 않는다.**
  const system =
    available.find((one) => one.key === chosen) ??
    available.find((one) => one.is_default) ??
    available[0] ??
    null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline">
          <FileDown className="size-3.5" />
          내보내기
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="font-normal">
          <p className="text-xs font-medium">덱의 단위계</p>
          <div className="mt-1.5 flex gap-1">
            {available.map((one) => (
              <button
                key={one.key}
                type="button"
                className={`flex-1 rounded-md border px-2 py-1 text-xs ${
                  system?.key === one.key ? 'bg-primary text-primary-foreground' : ''
                }`}
                onClick={(event) => {
                  // **메뉴가 닫히면 안 된다** — 계를 고른 다음에 형식을 고르는
                  // 순서라, 닫히면 다시 열어야 하고 그때 계가 초기화되면 사람은
                  // 자기가 고른 줄 알고 SI 를 받는다.
                  //
                  // Radix 는 `DropdownMenuItem` 의 select 에서 닫는다. 이 단추는
                  // `DropdownMenuLabel` 안이라 원래 안 닫히지만, 그 사실에
                  // 기대지 않는다 — 이 한 줄은 값이 없고 위험도 없다.
                  event.preventDefault()
                  setChosen(one.key)
                }}
              >
                {one.label}
              </button>
            ))}
          </div>
          {/* **덱에 무엇이라 적히는지 그대로 보인다.** 받는 사람이 파일에서
              읽을 줄과 같은 글자라, 나중에 대조할 수 있다. */}
          <p className="text-muted-foreground mt-1.5 font-mono text-xs">
            {system ? system.declaration : '단위계를 읽는 중…'}
          </p>
          <p className="text-muted-foreground mt-1 text-xs">
            값이 이 계로 환산돼 나가고, 덱 머리와 <b>파일 이름</b>에 적힙니다.
            단위계가 섞인 덱은 조용히 1000배 틀린 답을 냅니다.
          </p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {formats.map((format) => {
          const blocked = !card.available_formats.includes(format.key)
          return (
            <DropdownMenuItem
              key={format.key}
              disabled={blocked || system === null}
              onSelect={() => {
                if (!system) return
                fittingApi
                  .download(card.id, format, card.label, system)
                  .catch((caught: unknown) =>
                    onError(
                      caught instanceof Error ? caught : new Error('내보내지 못했습니다.')
                    )
                  )
              }}
            >
              <div>
                <p className="text-sm">{format.label}</p>
                <p className="text-muted-foreground text-xs">
                  {blocked
                    ? `${format.requires.join('·')} 가 있어야 냅니다. 카드에 아직 없습니다.`
                    : format.describe}
                </p>
              </div>
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
