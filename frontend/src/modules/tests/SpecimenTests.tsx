/**
 * 한 시편의 시험들 — 재료 상세에 끼워 넣는 조각.
 *
 * 시험 UI 를 시험 모듈이 갖고 있고, 재료 화면은 **자리만 내어 준다.** 워크벤치
 * 규칙(R5)과 같은 이유다 — 도메인 로직이 남의 화면에 쌓이기 시작하면 그 화면이
 * 모든 도메인을 알게 된다.
 */

import { useEffect, useState } from 'react'
import { AlertTriangle, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import { UploadDialog } from '@/modules/tests/UploadDialog'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

interface Props {
  specimenId: string
  specimenName: string
}

export function SpecimenTests({ specimenId, specimenName }: Props) {
  const [uploading, setUploading] = useState(false)
  const runs = useResource(() => testsApi.runs({ specimen_id: specimenId }), [specimenId])
  const rows = runs.data?.items ?? []
  const pending = rows.some((run) => isPending(run.status))

  // 올린 직후에는 워커가 아직 읽는 중이다. 사용자가 새로고침을 눌러야 결과가
  // 보이면, 비동기로 처리하는 이득이 사용자에게 가지 않는다.
  useEffect(() => {
    if (!pending) return
    const timer = setInterval(() => runs.reload(), 3000)
    return () => clearInterval(timer)
  }, [pending, runs])

  return (
    <div className="mt-2 border-t pt-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-muted-foreground text-xs">
          시험 {rows.length}건{pending && ' · 읽는 중'}
        </span>
        <Button size="sm" variant="ghost" onClick={() => setUploading(true)}>
          <Plus className="size-3.5" />
          시험 등록
        </Button>
      </div>

      {rows.length > 0 && (
        <ul className="space-y-1">
          {rows.map((run) => (
            <li key={run.id} className="flex items-center gap-2 text-xs">
              <Link
                to={`/test-runs/${run.id}`}
                className="hover:text-primary font-mono hover:underline"
              >
                {run.record_name}
              </Link>
              <Badge
                variant={
                  run.status === 'failed'
                    ? 'destructive'
                    : run.status === 'parsed'
                      ? 'secondary'
                      : 'outline'
                }
              >
                {RUN_STATUS_LABEL[run.status] ?? run.status}
              </Badge>
              {run.warnings.length > 0 && <AlertTriangle className="size-3 text-amber-500" />}
              {run.row_count != null && (
                <span className="text-muted-foreground ml-auto tabular-nums">
                  {run.row_count.toLocaleString('ko-KR')}행
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <UploadDialog
        specimenId={specimenId}
        specimenName={specimenName}
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
