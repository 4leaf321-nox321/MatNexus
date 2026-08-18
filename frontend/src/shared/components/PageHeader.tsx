/** 화면 제목 줄. 제목·설명·오른쪽 액션의 배치를 화면마다 다시 정하지 않는다. */

import type { ReactNode } from 'react'
import { ChevronLeft } from 'lucide-react'
import { Link } from 'react-router-dom'

interface PageHeaderProps {
  title: string
  description?: string
  actions?: ReactNode
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
}

export function PageHeader({ title, description, actions, back }: PageHeaderProps) {
  return (
    <div className="mb-6">
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
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}
