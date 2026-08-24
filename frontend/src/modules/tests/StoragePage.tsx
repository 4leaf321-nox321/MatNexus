/**
 * 저장소 정리 — 무엇이 쌓였고 무엇을 치울 수 있는지.
 *
 * **실행 경로가 없으면 만들어 둔 정리 잡은 없는 것과 같다.** 핸들러만 등록해 두고
 * 큐에 넣는 곳을 안 만들어서 한 번도 돌지 않았고, 그동안 파일이 쌓였다.
 *
 * 치울 것이 세 종류라는 것을 화면이 그대로 보여 준다. 하나로 뭉뚱그리면 "지울 게
 * 3건 있습니다" 만 남는데, 셋은 성격이 다르고 위험도도 다르다.
 */

import { useState } from 'react'
import { AlertTriangle, FileWarning, HardDrive, Trash2 } from 'lucide-react'

import { testsApi } from '@/modules/tests/api'
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

function mb(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export default function StoragePage() {
  const report = useResource(() => testsApi.storage(), [])
  const [action, setAction] = useState<Error | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const data = report.data

  async function cleanup(dryRun: boolean) {
    setBusy(true)
    setAction(null)
    setMessage(null)
    try {
      const result = await testsApi.cleanup({ dry_run: dryRun })
      setMessage(result.message)
      // 워커가 처리하므로 곧바로 반영되지는 않는다. 잠시 뒤 다시 읽는다.
      setTimeout(() => report.reload(), 2500)
    } catch (caught) {
      setAction(caught instanceof Error ? caught : new Error('정리 요청에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="저장소 정리"
        description="시험 원본과 곡선 파일이 사는 곳. 주인 없는 파일은 여기서 치웁니다."
        actions={
          <>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => cleanup(true)}>
              미리보기 실행
            </Button>
            <Button
              size="sm"
              disabled={busy || !data?.reclaimable_bytes}
              onClick={() => cleanup(false)}
            >
              <Trash2 className="size-4" />
              정리하기
            </Button>
          </>
        }
      />

      <ErrorNotice error={report.error ?? action} className="mb-4" />

      {message && (
        <div className="bg-muted/40 mb-4 rounded-md border p-3 text-sm">{message}</div>
      )}

      {data && (
        <>
          <dl className="mb-6 grid grid-cols-2 gap-x-6 gap-y-3 rounded-md border p-4 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground text-xs">전체</dt>
              <dd className="mt-0.5 flex items-center gap-1.5 tabular-nums">
                <HardDrive className="size-3.5" />
                {mb(data.total_bytes)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs">살아 있는 시험</dt>
              <dd className="mt-0.5 tabular-nums">
                {data.live_count}건 · {mb(data.live_bytes)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs">치울 수 있음</dt>
              <dd
                className={`mt-0.5 tabular-nums ${
                  data.reclaimable_bytes ? 'text-amber-600 dark:text-amber-500' : ''
                }`}
              >
                {mb(data.reclaimable_bytes)}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground text-xs">보존기간</dt>
              <dd className="mt-0.5 tabular-nums">{data.retention_days}일</dd>
            </div>
          </dl>

          <p className="text-muted-foreground mb-4 font-mono text-xs">{data.root}</p>

          <Section
            title="주인 없는 파일 (오펀)"
            hint="DB 에 행이 없는 폴더입니다. 트랜잭션이 파일시스템까지 덮지 못해 생깁니다."
            count={data.orphans.length}
            bytes={data.orphans.reduce((sum, item) => sum + item.bytes, 0)}
          >
            {data.orphans.map((item) => (
              <TableRow key={item.path}>
                <TableCell className="font-mono text-xs">{item.path}</TableCell>
                <TableCell className="text-right tabular-nums">{mb(item.bytes)}</TableCell>
              </TableRow>
            ))}
          </Section>

          <Section
            title="쓰다 만 파일 (.part)"
            hint="업로드가 중간에 끊긴 흔적입니다. 폴더는 살아 있어서 오펀 탐색에는 안 걸립니다. 1시간이 안 지난 것은 진행 중일 수 있어 제외합니다."
            count={data.incomplete.length}
            bytes={data.incomplete.reduce((sum, item) => sum + item.bytes, 0)}
          >
            {data.incomplete.map((item) => (
              <TableRow key={item.path}>
                <TableCell className="font-mono text-xs">
                  {item.path}
                  <span className="text-muted-foreground ml-2">{item.age_hours}시간 전</span>
                </TableCell>
                <TableCell className="text-right tabular-nums">{mb(item.bytes)}</TableCell>
              </TableRow>
            ))}
          </Section>

          <Section
            title="보존기간이 지난 삭제분"
            hint={`지운 지 ${data.retention_days}일이 지난 시험의 파일입니다. 소프트 삭제는 행을 남기므로 오펀 탐색으로는 영원히 안 잡힙니다 — 셋 중 가장 큰 구멍입니다. 파일만 지우고 기록은 남깁니다.`}
            count={data.expired.length}
            bytes={data.expired.reduce((sum, item) => sum + item.bytes, 0)}
            warn
          >
            {data.expired.map((item) => (
              <TableRow key={item.path}>
                <TableCell className="text-xs">
                  <span className="font-mono">{item.record_name}</span>
                  <span className="text-muted-foreground ml-2">
                    {new Date(item.deleted_at).toLocaleDateString('ko-KR')} 삭제
                  </span>
                </TableCell>
                <TableCell className="text-right tabular-nums">{mb(item.bytes)}</TableCell>
              </TableRow>
            ))}
          </Section>

          <p className="text-muted-foreground mt-6 text-xs">
            정리는 워커가 처리합니다. 워커가 꺼져 있으면 큐에 쌓이기만 합니다. 정기 실행이
            필요하면 <code>python scripts/cleanup_storage.py --apply</code> 를 작업
            스케줄러에 겁니다.
          </p>
        </>
      )}
    </div>
  )
}

function Section({
  title,
  hint,
  count,
  bytes,
  warn,
  children,
}: {
  title: string
  hint: string
  count: number
  bytes: number
  warn?: boolean
  children: React.ReactNode
}) {
  return (
    <section className="mb-6">
      <div className="mb-1 flex items-center gap-2">
        <h2 className="font-medium">{title}</h2>
        <Badge variant={count > 0 ? (warn ? 'destructive' : 'secondary') : 'outline'}>
          {count}건
        </Badge>
        {count > 0 && (
          <span className="text-muted-foreground text-xs tabular-nums">{mb(bytes)}</span>
        )}
      </div>
      <p className="text-muted-foreground mb-2 text-xs">{hint}</p>

      {count === 0 ? (
        <p className="text-muted-foreground rounded-md border py-4 text-center text-sm">
          없습니다.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>
                {warn ? (
                  <AlertTriangle className="mr-1 inline size-3.5 text-amber-500" />
                ) : (
                  <FileWarning className="text-muted-foreground mr-1 inline size-3.5" />
                )}
                대상
              </TableHead>
              <TableHead className="w-28 text-right">크기</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>{children}</TableBody>
        </Table>
      )}
    </section>
  )
}
