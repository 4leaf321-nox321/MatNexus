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
import { ChevronDown, ChevronRight, FileDown } from 'lucide-react'

import { fittingApi } from '@/modules/fitting/api'
import { groupBySolver } from '@/modules/fitting/formatGroups'
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
  siblings = [],
}: {
  card: PropertyCard
  formats: ExportFormat[]
  onError: (error: Error) => void
  /** 같은 재료의 다른 카드 — **짝 카드**로 고를 수 있다(ADR 0037). 이방성(r값) 카드는 혼자서는
   *  Hill 형식을 못 낸다: 경화 곡선·탄성이 MD 카드에 있다. 카드를 합쳐 새로 만들지 않고 내보낼
   *  때만 합친다. */
  siblings?: PropertyCard[]
}) {
  const systems = useResource(() => fittingApi.unitSystems(), [])
  const [chosen, setChosen] = useState<string | null>(null)
  const [showBlocked, setShowBlocked] = useState(false)
  const [pair, setPair] = useState<{ card: PropertyCard; keys: string[] } | null>(null)
  const systemList = systems.data ?? []
  // 고르기 전에는 서버가 기본이라고 말한 것. **화면이 'si' 를 적어 두지 않는다.**
  const system =
    systemList.find((one) => one.key === chosen) ??
    systemList.find((one) => one.is_default) ??
    systemList[0] ??
    null

  const available = formats.filter((one) => card.available_formats.includes(one.key))
  const blocked = formats.filter((one) => !card.available_formats.includes(one.key))

  const partners = siblings.filter(
    (one) => one.id !== card.id && one.material_id === card.material_id
  )

  function download(format: ExportFormat, withCard?: string) {
    if (!system) return
    fittingApi
      .download(card.id, format, card.label, system, withCard)
      .catch((caught: unknown) =>
        onError(caught instanceof Error ? caught : new Error('내보내지 못했습니다.'))
      )
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline">
          <FileDown className="size-3.5" />
          내보내기
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[70vh] w-80 overflow-y-auto">
        <DropdownMenuLabel className="font-normal">
          <p className="text-xs font-medium">덱의 단위계</p>
          <div className="mt-1.5 flex gap-1">
            {systemList.map((one) => (
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
        {/* **낼 수 있는 것을 솔버로 묶어 먼저.** 솔버 × 물성 모델로 형식이 서른 개 가까이라
            (2026-09-27) 한 줄로 늘어놓으면 고를 것을 찾는 데 시간이 든다. 못 내는 것은
            접어 둔다 — 없애지 않는다: 「왜 못 내나」 가 그 자리에 적혀 있다. */}
        {groupBySolver(available).map((group) => (
          <div key={group.solver}>
            <p className="text-muted-foreground px-2 pt-2 pb-0.5 text-xs font-medium">
              {group.solver}
            </p>
            {group.items.map((format) => (
              <FormatItem
                key={format.key}
                format={format}
                blocked={false}
                disabled={system === null}
                onSelect={() => download(format)}
              />
            ))}
          </div>
        ))}
        {available.length === 0 ? (
          <p className="text-muted-foreground px-2 py-1.5 text-xs">
            이 카드로 낼 수 있는 형식이 아직 없습니다.
          </p>
        ) : null}
        {blocked.length > 0 && partners.length > 0 ? (
          <>
            <DropdownMenuSeparator />
            <div className="px-2 py-1.5">
              <p className="text-xs font-medium">짝 카드와 합쳐 내기</p>
              <p className="text-muted-foreground mt-0.5 text-xs">
                이 카드에 없는 것(경화 곡선·탄성)을 같은 재료의 다른 카드에서 가져옵니다 — 이방성
                카드는 <b>압연 방향(MD)</b> 카드를 고르세요.
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {partners.map((one) => (
                  <button
                    key={one.id}
                    type="button"
                    className={`rounded-md border px-2 py-0.5 text-xs ${
                      pair?.card.id === one.id ? 'bg-primary text-primary-foreground' : ''
                    }`}
                    onClick={(event) => {
                      // 메뉴가 닫히면 안 된다 — 짝을 고른 다음에 형식을 고른다.
                      event.preventDefault()
                      fittingApi
                        .pairedFormats(card.id, one.id)
                        .then((found) => setPair({ card: one, keys: found.available_formats }))
                        .catch((caught: unknown) =>
                          onError(
                            caught instanceof Error ? caught : new Error('짝 카드를 못 읽었습니다.')
                          )
                        )
                    }}
                  >
                    {one.label}
                    {one.orientation ? ` · ${one.orientation}` : ''}
                  </button>
                ))}
              </div>
              {pair && pair.keys.length === 0 ? (
                <p className="text-muted-foreground mt-1.5 text-xs">
                  이 짝으로 새로 낼 수 있는 형식이 없습니다.
                </p>
              ) : null}
            </div>
            {pair
              ? formats
                  .filter((one) => pair.keys.includes(one.key))
                  .map((format) => (
                    <FormatItem
                      key={`pair-${format.key}`}
                      format={format}
                      blocked={false}
                      disabled={system === null}
                      onSelect={() => download(format, pair.card.id)}
                    />
                  ))
              : null}
          </>
        ) : null}
        {blocked.length > 0 ? (
          <>
            <DropdownMenuSeparator />
            <button
              type="button"
              className="text-muted-foreground flex w-full items-center gap-1 px-2 py-1.5 text-left text-xs"
              onClick={(event) => {
                // 펼쳐도 메뉴가 닫히면 안 된다 — 계를 고르는 단추와 같다.
                event.preventDefault()
                setShowBlocked((open) => !open)
              }}
            >
              {showBlocked ? (
                <ChevronDown className="size-3.5" />
              ) : (
                <ChevronRight className="size-3.5" />
              )}
              이 카드로는 못 내는 형식 {blocked.length}개
            </button>
            {showBlocked
              ? blocked.map((format) => (
                  <FormatItem key={format.key} format={format} blocked disabled onSelect={() => {}} />
                ))
              : null}
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function FormatItem({
  format,
  blocked,
  disabled,
  onSelect,
}: {
  format: ExportFormat
  blocked: boolean
  disabled: boolean
  onSelect: () => void
}) {
  return (
    <DropdownMenuItem disabled={blocked || disabled} onSelect={onSelect}>
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
}
