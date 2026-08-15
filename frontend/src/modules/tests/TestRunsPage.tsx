/**
 * 시험 데이터 목록.
 *
 * 업로드는 202 로 끝나고 파싱은 워커가 한다. 그래서 목록에 **아직 끝나지 않은
 * 시험이 있으면 스스로 갱신한다** — 사용자가 새로고침을 눌러야 상태가 바뀌면,
 * 비동기로 처리하는 이유(요청을 붙잡지 않는 것)의 이득이 사용자에게 안 간다.
 *
 * **등록 진입점이 두 곳이다.** 시험은 시편에 매달리므로 처음에는 재료 상세의
 * 시편 줄에만 두었는데, 그러면 재료 → 재료 상세 → 시료 펼치기 → 시편까지
 * 세 단계를 파고들어야 시작할 수 있다. 실제로 이 화면에 온 사람이 등록 버튼을
 * 찾지 못했다. 화면 이름이 "시험 데이터" 인데 시험을 만들 수 없으면 안 된다.
 *
 * 여기서는 시편을 직접 고르고(`SpecimenPicker`), 시편 줄에서 열 때는 그 단계를
 * 건너뛴다. 같은 다이얼로그가 둘 다 한다 — 업로드 폼을 두 벌 만들면 갈라진다.
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, FlaskConical, Plus, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'

import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import { UploadDialog } from '@/modules/tests/UploadDialog'
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

const POLL_MS = 3000

function statusVariant(status: string): 'default' | 'secondary' | 'outline' | 'destructive' {
  if (status === 'failed') return 'destructive'
  if (status === 'parsed') return 'secondary'
  return 'outline'
}

export default function TestRunsPage() {
  const [uploading, setUploading] = useState(false)
  const runs = useResource(() => testsApi.runs({ limit: 100 }), [])
  const rows = runs.data?.items ?? []
  const pending = rows.some((run) => isPending(run.status))

  useEffect(() => {
    if (!pending) return
    const timer = setInterval(() => runs.reload(), POLL_MS)
    return () => clearInterval(timer)
  }, [pending, runs])

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="시험 데이터"
        description="장비 원본을 올리면 서버가 읽어 곡선으로 만듭니다."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => runs.reload()}>
              <RefreshCw className={`size-4 ${pending ? 'animate-spin' : ''}`} />
              새로고침
            </Button>
            <Button size="sm" onClick={() => setUploading(true)}>
              <Plus className="size-4" />
              시험 등록
            </Button>
          </>
        }
      />

      <ErrorNotice error={runs.error} className="mb-4" />

      {pending && (
        <p className="text-muted-foreground mb-3 text-sm">
          읽는 중인 시험이 있어 {POLL_MS / 1000}초마다 상태를 확인합니다.
        </p>
      )}

      {!runs.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <FlaskConical className="mx-auto mb-2 size-5 opacity-50" />
          등록된 시험이 없습니다.
          <div className="mt-2">
            위의 <span className="text-foreground font-medium">시험 등록</span> 을 누르거나,{' '}
            <Link to="/materials" className="text-primary hover:underline">
              재료 상세
            </Link>{' '}
            의 시편에서 올리세요.
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>이름</TableHead>
              <TableHead>재료</TableHead>
              <TableHead>방향</TableHead>
              <TableHead>종류</TableHead>
              <TableHead>상태</TableHead>
              <TableHead className="text-right">행</TableHead>
              <TableHead>등록</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((run) => (
              <TableRow key={run.id}>
                <TableCell className="font-mono text-xs">
                  <Link to={`/test-runs/${run.id}`} className="hover:text-primary hover:underline">
                    {run.record_name}
                  </Link>
                  {run.warnings.length > 0 && (
                    <AlertTriangle className="ml-1 inline size-3 text-amber-500" />
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs">
                  {run.material_name ?? '—'}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{run.orientation ?? '—'}</Badge>
                </TableCell>
                <TableCell className="text-sm">{run.test_type_label}</TableCell>
                <TableCell>
                  <Badge variant={statusVariant(run.status)}>
                    {RUN_STATUS_LABEL[run.status] ?? run.status}
                  </Badge>
                  {run.parse_error && (
                    <p className="text-destructive mt-1 max-w-xs text-xs">{run.parse_error}</p>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {run.row_count?.toLocaleString('ko-KR') ?? '—'}
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {new Date(run.created_at).toLocaleDateString('ko-KR')}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <UploadDialog
        open={uploading}
        onClose={() => setUploading(false)}
        onDone={() => {
          setUploading(false)
          runs.reload()
        }}
      />
    </div>
  )
}
