/**
 * 적어 둔 값의 **등급과 승인** — 물성 요약 · 밀시트 목록이 같은 모양으로 보인다(ADR 0049).
 *
 * 등급은 **서버가 센 것**(`quality_tier`)을 그대로 적는다. 출처 → 등급 표를 화면이 들면
 * 승인 규칙(한 단계 위, 2 까지)이 두 곳에 살고, 갈라진 날 화면은 서버와 다른 등급을 보인다.
 *
 * 승인은 지금 값에 유효한 것만 온다 — 승인 뒤 값을 고쳤으면 서버가 비워서 보낸다.
 */

import { BadgeCheck } from 'lucide-react'

import type { components } from '@/shared/api/schema'
import { Badge } from '@/shared/components/ui/badge'
import { stamp } from '@/shared/lib/datetime'

type Approval = components['schemas']['DeclaredApprovalOut']
type Catalog = components['schemas']['DeclaredCatalogOut']

/** 승인을 한 줄로 — 툴팁과 편집 창이 같은 말을 쓴다. */
export function approvalText(approval: Approval): string {
  return `${approval.by} 승인 · ${stamp(approval.at)}${approval.note ? ` — ${approval.note}` : ''}`
}

export function DeclaredGrade({
  tier,
  approval,
  catalog,
}: {
  tier: number
  approval?: Approval | null
  /** 문헌 카탈로그에서 받아 온 값이면 그 근거 — 등급이 그 문헌 값의 것이다(2026-10-03). */
  catalog?: Catalog | null
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <Badge
        variant="outline"
        className="px-1 py-0 text-[10px] font-normal"
        title={
          catalog
            ? `문헌 카탈로그에서 받아 온 값 — 그 문헌 값의 등급(${catalog.tier})을 잇습니다. 값을 고치면 출처의 등급으로 돌아갑니다.`
            : '값의 등급 1~4 — 1 제품 문서 실측 · 2 규격 · 공인 DB · 3 옮겨 적은 값 · 4 추정'
        }
      >
        등급 {tier}
      </Badge>
      {approval ? (
        <span
          className="inline-flex items-center gap-0.5 text-emerald-700 dark:text-emerald-400"
          title={`자료 관리자가 근거 문서와 대조해 승인했습니다 — ${approvalText(approval)}`}
        >
          <BadgeCheck className="size-3" aria-hidden />
          승인
        </span>
      ) : null}
    </span>
  )
}
