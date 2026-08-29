/** 화면 제목 줄. 제목·설명·오른쪽 액션의 배치를 화면마다 다시 정하지 않는다. */

import type { ReactNode } from 'react'
import { ChevronLeft } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/shared/lib/utils'

interface PageHeaderProps {
  title: string
  description?: string
  actions?: ReactNode
  /** 스크롤해도 맨 위에 남는다. **긴 화면에만 켠다** — 짧은 화면에서는 얻는 것
   *  없이 세로만 먹는다. */
  sticky?: boolean
  /**
   * 돌아갈 곳. **브라우저 뒤로가기에 기대지 않는다.**
   *
   * 재료 → 시편 → 시험으로 들어간 뒤 돌아갈 길이 없다는 보고가 있었다. 뒤로가기
   * 버튼은 브라우저에 있지만, 앱 안에서 세 단계를 들어온 사람은 화면 안에서
   * 길을 찾는다 — 게다가 링크를 새 탭으로 열었거나 주소를 직접 붙여 넣었으면
   * 히스토리가 아예 없다. `navigate(-1)` 이 그 경우 아무 데도 못 간다.
   *
   * 그래서 **어디로 가는지 이름이 적힌 링크**를 둔다. 히스토리가 아니라 계층을
   * 따라가므로 어떤 경로로 들어왔든 같은 곳으로 간다.
   */
  back?: { to: string; label: string }
  /**
   * 이 데이터가 **언제 생겼는가.** ISO 문자열을 그대로 넘긴다.
   *
   * 제목 옆에 둔다. 아래 표 어딘가에 적어 두면 **찾아야 보이고**, 찾지 않으면
   * 「이게 언제 것인가」를 모른 채로 값을 읽게 된다 — 물성은 그 물음이 늘 따라
   * 붙는다(어느 로트인가, 언제 잰 것인가).
   *
   * 절대 시각으로 적는다. 「3일 전」은 읽는 시점에 따라 달라져서, 화면을 캡처해
   * 주고받는 순간 뜻을 잃는다.
   */
  created?: string | null
}

/** `2026-08-25` 로. **시각까지 적지 않는다** — 제목 줄이 길어지고, 날짜면 족하다. */
function shownDate(raw: string): string {
  const when = new Date(raw)
  return Number.isNaN(when.getTime()) ? raw : when.toLocaleDateString('ko-KR')
}

export function PageHeader({
  title,
  description,
  actions,
  back,
  created,
  sticky = false,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        'mb-6',
        // **긴 화면에서 「지금 무엇을 보고 있나」 를 잃지 않게.** 스크롤을 내리면
        // 제목·재료·시험 종류가 사라지고, 곡선만 남으면 그것이 어느 시험의
        // 곡선인지 화면에 없다 — 되돌아가는 단추도 함께 사라진다.
        //
        // 스크롤 상자는 `AppShell` 의 `<main>`(`overflow-auto p-6`)이다. 음수
        // 여백으로 그 안쪽 여백까지 덮어야 **내용이 옆으로 새어 보이지 않는다.**
        sticky &&
          'bg-background sticky top-0 z-20 -mx-6 -mt-6 mb-4 border-b px-6 pt-6 pb-3'
      )}
    >
      {back && (
        <Link
          to={back.to}
          className="text-muted-foreground hover:text-foreground mb-2 -ml-1 inline-flex items-center gap-1 text-sm"
        >
          <ChevronLeft className="size-4" />
          {back.label}
        </Link>
      )}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
            {created && (
              <span
                className="text-muted-foreground text-xs"
                title="이 데이터가 만들어진 날"
              >
                {shownDate(created)} 등록
              </span>
            )}
          </div>
          {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}
