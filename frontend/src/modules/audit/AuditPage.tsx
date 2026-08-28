/**
 * 변경 이력 — **무엇이 바뀌었고 누가 승인했는가.**
 *
 * 화면에서는 「변경 이력」이라 부른다. 코드·API 는 `audit` 그대로다 —
 * 「감사 로그」는 개발자에게는 정확한 말이지만 **쓰는 사람이 안 쓰는 말**이다.
 *
 * 기록은 v1.49.0 부터 쌓이는데 **볼 자리가 API 뿐이었다.** 이 저장소가 반복해서
 * 데인 패턴이라(만들어 두고 안 쓰는 것) 바로 붙인다.
 *
 * ## 고치는 단추가 없다
 *
 * 이 화면에는 만들기·고치기·지우기가 없다. 이력은 **변경이 일어난 그
 * 트랜잭션 안에서만** 생기고, API 에도 쓰는 길이 없다 — 고칠 수 있으면 이력이
 * 아니다.
 *
 * ## 바뀐 것만 보인다
 *
 * 서버가 달라진 키만 담아 준다. 통째로 담으면 안 바뀐 값 스무 개 사이에서 바뀐
 * 하나를 찾게 된다.
 */

import { useState } from 'react'

import { ACTION_LABELS, auditApi } from '@/modules/audit/api'
import type { AuditEntry } from '@/modules/audit/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
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
import { stamp } from '@/shared/lib/datetime'

function Changes({ entry }: { entry: AuditEntry }) {
  const keys = Object.keys(entry.changes ?? {})
  if (keys.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <div className="space-y-0.5">
      {keys.map((key) => {
        const change = (entry.changes as Record<string, { before?: unknown; after?: unknown }>)[key]
        return (
          <div key={key} className="text-xs">
            <span className="text-muted-foreground">{key}</span>{' '}
            <span className="line-through opacity-60">{String(change?.before ?? '없음')}</span>{' '}
            → <span className="font-medium">{String(change?.after ?? '없음')}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function AuditPage() {
  const [action, setAction] = useState('')
  const entries = useResource(() => auditApi.list(action ? { action } : {}), [action])
  const rows = entries.data ?? []

  return (
    <div className="space-y-4">
      <PageHeader
        title="변경 이력"
        description="되돌릴 수 없거나 권한이 실린 변경만 남습니다. 고칠 수 있으면 이력이 아니므로, 이 화면에는 만들기·고치기·지우기가 없습니다."
      />

      <ErrorNotice error={entries.error} />

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">행위</span>
        <select
          aria-label="행위로 거르기"
          className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          value={action}
          onChange={(event) => setAction(event.target.value)}
        >
          <option value="">전부</option>
          {Object.entries(ACTION_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {!entries.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          {action
            ? '그 행위로 남은 기록이 없습니다.'
            : '아직 남은 기록이 없습니다. 물성 카드를 확정하거나 내리면 여기 남습니다.'}
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">언제</TableHead>
                <TableHead>행위</TableHead>
                <TableHead>대상</TableHead>
                <TableHead>누가</TableHead>
                <TableHead>바뀐 것</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="text-muted-foreground whitespace-nowrap text-xs tabular-nums">
                    {stamp(entry.created_at)}
                  </TableCell>
                  <TableCell>
                    {/* **모르는 코드도 감추지 않는다.** 모르는 일이 일어났다는
                        것 자체가 알아야 할 일이다. */}
                    <Badge variant="outline">{ACTION_LABELS[entry.action] ?? entry.action}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="text-sm">{entry.target_label}</div>
                    <div className="text-muted-foreground text-xs">{entry.target_table}</div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {entry.actor_label}
                    {/* 계정이 지워지면 id 는 비고 이름만 남는다 — 그 사실이 보여야 한다. */}
                    {!entry.actor_id && (
                      <span className="text-muted-foreground ml-1 text-xs">(지워진 계정)</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Changes entry={entry} />
                    {entry.reason && (
                      <p className="text-muted-foreground mt-1 text-xs">{entry.reason}</p>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {rows.length > 0 && (
        <p className="text-muted-foreground text-xs">
          최근 것부터 보여 줍니다. 서버가 개수 상한을 강제하므로 오래된 기록은 여기
          안 뜰 수 있습니다 — 그때는 행위로 걸러서 보세요.
        </p>
      )}
    </div>
  )
}
