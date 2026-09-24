/**
 * 내 자료 변경 이력 — **내가 등록한 자료에 남이 한 일**(2026-09-25, ADR 0035 남은 것).
 *
 * 보기가 모두에게 열리고 고치기가 자료 관리자·편집을 받은 부서로 넓어진 뒤, 등록자는 제 자료에
 * 누가 손댔는지 물을 자리가 없었다 — 변경 이력(`AuditPage`)은 관리자 것이고, 남이 칸을 고친
 * 일은 기록조차 안 됐다. 이제 판정 자리가 「남의 자료 고침」 을 근거와 함께 남기고, 여기서
 * 제 자료의 기록만 본다.
 *
 * **내가 손으로 한 일은 안 보인다** — 내가 한 일은 내가 안다. 내 이름으로 AI 가 한 일은 선다.
 */

import { useState } from 'react'
import { History } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Changes } from '@/modules/audit/Changes'
import { ACTION_LABELS, auditApi } from '@/modules/audit/api'
import type { AuditEntry } from '@/modules/audit/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { stamp } from '@/shared/lib/datetime'

const PAGE = 50

/** 무엇의 기록인가 — 표 이름을 사람 말로. 모르는 표는 이름 그대로 보인다. */
const KINDS: Record<string, string> = {
  materials: '재료',
  samples: '시료',
  specimens: '시편',
  test_runs: '시험',
  property_cards: '물성 카드',
  group_results: '묶음 결과',
  processing_results: '처리 결과',
  test_types: '시험 정의',
  format_profiles: '장비 파일 정의',
  processing_recipes: '레시피',
  export_profiles: '해석용 물성 정의',
  equipment_units: '장비',
}

/** 열어 볼 수 있는 대상의 주소. **지운 것에는 안 건다** — 누르면 없는 화면이 뜬다. */
const PAGES: Record<string, (id: string) => string> = {
  materials: (id) => `/materials/${id}`,
  specimens: (id) => `/specimens/${id}`,
  test_runs: (id) => `/test-runs/${id}`,
  equipment_units: (id) => `/settings/equipment/${id}`,
}

function hrefOf(entry: AuditEntry): string | null {
  const page = PAGES[entry.target_table]
  if (!page || !entry.target_id || entry.action.endsWith('.deleted')) return null
  return page(entry.target_id)
}

export default function MyDataHistoryPage() {
  const [offset, setOffset] = useState(0)
  const page = useResource(() => auditApi.mine({ limit: PAGE, offset }), [offset])
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0

  return (
    // 표라 폭을 스스로 좁히지 않는다(`boundaries.test`).
    <div>
      <PageHeader
        title="내 자료 변경 이력"
        description="내가 등록한 자료에 다른 사람이 한 일입니다 — 고친 것 · 지운 것 · 확정하거나 넘긴 것. 내 이름으로 AI 가 한 일도 여기 섭니다."
      />

      <ErrorNotice error={page.error} className="mb-4" />

      {!page.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <History className="mx-auto mb-2 size-5 opacity-50" />
          아직 없습니다. 다른 사람이 내 자료를 고치거나 지우면 여기 남습니다.
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">언제</TableHead>
                <TableHead>누가</TableHead>
                <TableHead>한 일</TableHead>
                <TableHead>대상</TableHead>
                <TableHead>내용</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((entry) => {
                const href = hrefOf(entry)
                return (
                  <TableRow key={entry.id}>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {stamp(entry.created_at)}
                    </TableCell>
                    <TableCell>
                      {entry.actor_label}
                      {entry.client && (
                        <Badge variant="secondary" className="ml-2">
                          {entry.client === 'mcp' ? 'AI(MCP) 경유' : entry.client}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {ACTION_LABELS[entry.action] ?? entry.action}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {href ? (
                        <Link to={href} className="hover:underline">
                          {entry.target_label}
                        </Link>
                      ) : (
                        entry.target_label
                      )}
                      <span className="text-muted-foreground ml-1.5">
                        {KINDS[entry.target_table] ?? entry.target_table}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Changes entry={entry} />
                      {entry.reason && (
                        <p className="text-muted-foreground mt-1 text-xs">{entry.reason}</p>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {total > PAGE && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <span className="text-muted-foreground tabular-nums">
            {offset + 1}–{Math.min(offset + PAGE, total)} / {total}건
          </span>
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              이전
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              다음
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
