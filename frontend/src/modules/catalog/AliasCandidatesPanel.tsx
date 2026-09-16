/**
 * 별칭 후보 — **못 푼 물성 이름이 사전이 되는 자리.**
 *
 * 사람이나 AI 가 「UTS」 로 물성을 찾다 빈손이면 서버가 그 말을 여기 쌓는다. 전에는 그
 * 사실이 아무 데도 남지 않아 다음 사람도 같은 말로 다시 실패했다. 관리자가 줄마다 둘 중
 * 하나를 누른다 — 「이 물성의 별칭으로」(다음부터 찾힌다) 또는 「무시」(물성 이름이 아니다).
 *
 * 물성을 고르는 칸은 값 넣기 창과 같은 이름 해소(`resolveProperty`)를 쓴다 — 키를 손으로
 * 치게 하면 오타 하나로 별칭이 허공을 가리킨다(서버도 없는 키는 거절한다).
 */

import { Check, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { catalogApi } from '@/modules/catalog/api'
import type { AliasCandidate, PropertyCandidate } from '@/modules/catalog/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

const SOURCE_LABEL: Record<string, string> = {
  search: '값 검색',
  resolve: '이름 해소',
  import: '이관',
}

function Row({
  row,
  onDone,
  onError,
}: {
  row: AliasCandidate
  onDone: () => void
  onError: (error: Error) => void
}) {
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<PropertyCandidate[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const needle = query.trim()
    if (needle.length < 1) {
      setCandidates([])
      return
    }
    let alive = true
    const timer = setTimeout(() => {
      catalogApi
        .resolveProperty(needle)
        .then((got) => {
          if (alive) setCandidates(got.candidates.filter((one) => !one.deprecated))
        })
        .catch(() => {
          if (alive) setCandidates([])
        })
    }, 200)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [query])

  async function act(action: () => Promise<unknown>) {
    setBusy(true)
    try {
      await action()
      onDone()
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('처리하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <TableRow>
      <TableCell className="font-medium">{row.text}</TableCell>
      <TableCell className="tabular-nums">{row.count}</TableCell>
      <TableCell>
        <Badge variant="secondary">{SOURCE_LABEL[row.source] ?? row.source}</Badge>
      </TableCell>
      <TableCell>
        <div className="relative w-64">
          <Input
            className="h-8"
            placeholder="어느 물성의 별칭인가 — 이름으로 찾기"
            aria-label={`${row.text} 의 물성`}
            value={query}
            disabled={busy}
            onChange={(event) => setQuery(event.target.value)}
          />
          {candidates.length > 0 && (
            <ul className="bg-popover absolute z-10 mt-1 w-full rounded-md border shadow-md">
              {candidates.slice(0, 6).map((one) => (
                <li key={one.key}>
                  <button
                    type="button"
                    className="hover:bg-muted flex w-full items-center justify-between px-2 py-1 text-left text-sm"
                    onClick={() =>
                      void act(() => catalogApi.acceptAliasCandidate(row.id, one.key))
                    }
                  >
                    <span>{one.name}</span>
                    <span className="text-muted-foreground font-mono text-xs">{one.key}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </TableCell>
      <TableCell>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => void act(() => catalogApi.ignoreAliasCandidate(row.id))}
          title="물성 이름이 아니다 — 목록에서 내린다(지우지는 않는다)"
        >
          <X className="size-3.5" />
          무시
        </Button>
      </TableCell>
    </TableRow>
  )
}

export function AliasCandidatesPanel() {
  const rows = useResource(() => catalogApi.aliasCandidates(), [])
  const [error, setError] = useState<Error | null>(null)
  const list = rows.data ?? []

  return (
    <section className="space-y-2">
      <div>
        <h3 className="font-medium">해소 못 한 물성 이름</h3>
        <p className="text-muted-foreground text-xs">
          사람이나 AI 가 물성을 찾다 빈손이었던 말입니다. 어느 물성인지 이어 주면 다음부터
          그 말로 찾힙니다 — 많이 물은 것부터.
        </p>
      </div>
      <ErrorNotice error={error ?? rows.error} />
      {rows.data && list.length === 0 && (
        <p className="text-muted-foreground rounded-md border py-3 text-center text-xs">
          <Check className="mr-1 inline size-3.5" />
          남은 것이 없습니다.
        </p>
      )}
      {list.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>말</TableHead>
                <TableHead>횟수</TableHead>
                <TableHead>어디서</TableHead>
                <TableHead>이 물성의 별칭으로</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((row) => (
                <Row
                  key={row.id}
                  row={row}
                  onDone={() => {
                    setError(null)
                    rows.reload()
                  }}
                  onError={setError}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}
