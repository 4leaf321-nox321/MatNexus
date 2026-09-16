/**
 * 「낼 수 있는 형식」 — 이 재료로 어느 솔버 형식이 **나오나 · 왜 안 나오나 · 어디서 채우나.**
 *
 * 전에는 카드를 하나씩 열어 내보내기 메뉴를 봐야 「나오나」 를 알았고, 「왜 안 나오나」 는
 * 내려받기를 누른 뒤의 오류로만 알았다. 판정은 서버가 렌더와 같은 규칙으로 한다
 * (`GET /fitting/materials/{id}/deck-readiness`) — 여기는 그 답을 표로 편다.
 *
 * 빠진 블록마다 **채울 길**을 함께 적는다. 「소성 표가 없다」 만 말하면 다음에 무엇을 해야
 * 하는지는 사람이 알아내야 한다 — 어느 시험을 하면 생기고, 문헌에 채택할 값이 몇인지가
 * 같은 줄에 선다.
 */

import { CheckCircle2, XCircle } from 'lucide-react'
import { fittingApi } from '@/modules/fitting/api'
import type { DeckReadiness, ReadinessMissing } from '@/modules/fitting/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

function Ways({ item }: { item: ReadinessMissing }) {
  const parts: string[] = []
  for (const test of item.tests) {
    parts.push(
      test.test_type_ids.length > 0
        ? `${test.label} 시험을 하면 생깁니다`
        : `${test.label} 시험이 내지만 그 시험 종류를 만든 부서가 아직 없습니다`,
    )
  }
  if (item.catalog) {
    parts.push(
      item.catalog.values_available > 0
        ? `이어진 문헌 재료에 채택할 값 ${item.catalog.values_available}건`
        : '이어진 문헌 재료에 채택할 값 없음',
    )
  }
  if (item.declarable_values.length > 0) parts.push('재료 기본 정보 카드로 적어 넣을 수 있습니다')
  if (parts.length === 0) return null
  return <span className="text-muted-foreground"> — {parts.join(' · ')}</span>
}

export function DeckReadinessTable({ materialId }: { materialId: string }) {
  const readiness = useResource<DeckReadiness>(
    () => fittingApi.deckReadiness(materialId),
    [materialId],
  )
  const data = readiness.data

  return (
    <section className="mt-6">
      <h3 className="mb-1 font-medium">낼 수 있는 형식</h3>
      <p className="text-muted-foreground mb-2 text-xs">
        확정 카드를 먼저 대어 봅니다. 안 나오는 형식은 무엇이 빠졌고 어디서 채울 수 있는지
        함께 적습니다 — 판정은 내보내기와 같은 규칙입니다.
      </p>
      <ErrorNotice error={readiness.error} className="mb-2" />
      {data && data.note && <p className="text-muted-foreground mb-2 text-xs">{data.note}</p>}
      {data && (
        <div className="overflow-x-auto rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>형식</TableHead>
                <TableHead>카드</TableHead>
                <TableHead>빠진 것 · 채울 길</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.formats.map((format) => (
                <TableRow key={format.key} data-testid={`readiness-${format.key}`}>
                  <TableCell>
                    {format.ready ? (
                      <CheckCircle2 className="size-4 text-emerald-600" aria-label="나옵니다" />
                    ) : (
                      <XCircle className="text-muted-foreground size-4" aria-label="안 나옵니다" />
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="font-medium">{format.label}</span>{' '}
                    <span className="text-muted-foreground font-mono text-xs">
                      {format.key}.{format.extension}
                    </span>
                  </TableCell>
                  <TableCell>
                    {format.card_id ? (
                      // 카드는 이 탭의 위 목록에 있다 — 따로 가는 화면이 없다.
                      <span>{format.card_label}</span>
                    ) : (
                      <span className="text-muted-foreground">없음</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {format.ready ? (
                      <Badge variant="secondary">나옵니다</Badge>
                    ) : (
                      <ul className="space-y-0.5">
                        {format.missing.map((item) => (
                          <li key={item.block}>
                            <span className="font-medium">{item.what.join(', ')}</span>
                            <Ways item={item} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}
