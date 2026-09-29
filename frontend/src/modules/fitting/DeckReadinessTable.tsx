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
 *
 * ## 탭에 펼치지 않고 「형식 점검」 모달로 (2026-09-29)
 *
 * 형식이 6종 50개로 늘자 CAE 카드 탭 아래에 50줄이 늘 펼쳐져 있었고, 표에서 고르거나
 * 누를 것이 없어 「무엇을 하라는 표인가」 가 됐다(사용자 지적). 이 표는 **점검용**이다 —
 * 실제 내려받기는 카드의 내보내기 메뉴가 한다. 그래서 단추로 열고, 열 때만 서버에 묻는다.
 */

import { useState } from 'react'
import { CheckCircle2, ListChecks, XCircle } from 'lucide-react'
import { fittingApi } from '@/modules/fitting/api'
import type { DeckReadiness, ReadinessMissing } from '@/modules/fitting/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
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

/** 판정 표 — 모달 안에 선다. 열 때 한 번 서버에 묻는다. */
export function DeckReadinessTable({ materialId }: { materialId: string }) {
  const readiness = useResource<DeckReadiness>(
    () => fittingApi.deckReadiness(materialId),
    [materialId],
  )
  const data = readiness.data
  // **나오는 형식이 위로.** 50줄에서 「무엇이 나오나」 를 찾으려고 끝까지 굴리지 않게.
  // 같은 무리 안에서는 서버 차례(솔버별)를 지킨다.
  const formats = data
    ? [...data.formats.filter((one) => one.ready), ...data.formats.filter((one) => !one.ready)]
    : []
  const readyCount = formats.filter((one) => one.ready).length

  return (
    <div>
      <ErrorNotice error={readiness.error} className="mb-2" />
      {readiness.loading && !data && <p className="text-muted-foreground">판정하는 중…</p>}
      {data && (
        <p className="mb-2" data-testid="readiness-summary">
          전체 <b>{formats.length}</b>개 형식 중 <b>{readyCount}</b>개를 지금 낼 수 있습니다.
        </p>
      )}
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
              {formats.map((format) => (
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
                      // 카드는 CAE 카드 탭의 목록에 있다 — 따로 가는 화면이 없다.
                      <span>{format.card_label}</span>
                    ) : (
                      <span className="text-muted-foreground">없음</span>
                    )}
                  </TableCell>
                  {/* **이 칸만 줄을 바꾼다.** 표 칸은 기본이 한 줄이라, 채울 길이 긴 형식에서
                      글이 창 밖으로 잘렸다(2026-09-29 화면 확인). */}
                  <TableCell className="whitespace-normal">
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
    </div>
  )
}

/** 「형식 점검」 단추 + 모달. 표는 모달이 열려 있을 때만 그려진다(그때만 서버에 묻는다). */
export function DeckReadinessCheck({
  materialId,
  className,
}: {
  materialId: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className={className}
        onClick={() => setOpen(true)}
        title="이 재료로 낼 수 있는 해석 양식과, 안 나오는 양식에 빠진 것을 확인합니다."
      >
        <ListChecks className="size-3.5" />
        형식 점검
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-5xl">
          <DialogHeader>
            <DialogTitle>낼 수 있는 형식 점검</DialogTitle>
            <DialogDescription>
              이 재료의 카드로 어떤 해석 양식을 낼 수 있는지 확인합니다. 확정 카드를 먼저 대어 보고,
              안 나오는 양식은 빠진 것과 채울 길을 함께 적습니다. 판정은 내보내기와 같은
              규칙이며, 실제 내려받기는 카드의 <b>내보내기</b> 메뉴에서 합니다.
            </DialogDescription>
          </DialogHeader>
          {open && <DeckReadinessTable materialId={materialId} />}
        </DialogContent>
      </Dialog>
    </>
  )
}
