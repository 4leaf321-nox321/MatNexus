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
 */

import { FileDown } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import type { ExportFormat, PropertyCard } from '@/modules/fitting/api'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'

export function ExportMenu({
  card,
  formats,
  onError,
}: {
  card: PropertyCard
  formats: ExportFormat[]
  onError: (error: Error) => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline">
          <FileDown className="size-3.5" />
          내보내기
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        {formats.map((format) => {
          const blocked = !card.available_formats.includes(format.key)
          return (
            <DropdownMenuItem
              key={format.key}
              disabled={blocked}
              onSelect={() => {
                fittingApi
                  .download(card.id, format, card.label)
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
