/**
 * 아직 만들지 않은 화면 자리.
 *
 * 메뉴에는 있지만 구현이 안 된 화면을 빈 페이지로 두면 "고장난 것"처럼 보인다.
 * 어느 단계에서 들어오는지 명시해 두면 사용자도 개발자도 상태를 안다.
 *
 * 화면이 실제로 구현되면 이 컴포넌트 사용처가 하나씩 사라진다 — 남은 개수가
 * 곧 진행 상황이다.
 */

import { Construction } from 'lucide-react'

interface PlaceholderProps {
  title: string
  phase: string
  description?: string
}

export function Placeholder({ title, phase, description }: PlaceholderProps) {
  return (
    <div className="mx-auto max-w-lg py-16 text-center">
      <Construction className="text-muted-foreground mx-auto size-8" />
      <h1 className="mt-4 text-lg font-semibold">{title}</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        {description ?? '아직 구현되지 않은 화면입니다.'}
      </p>
      <p className="text-muted-foreground mt-4 text-xs">
        구현 예정: <span className="font-mono">{phase}</span>
      </p>
    </div>
  )
}
