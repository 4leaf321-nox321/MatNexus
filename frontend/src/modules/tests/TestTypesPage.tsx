/**
 * 시험 종류 정의 — 무엇을 읽을 수 있는지 한눈에.
 *
 * **정의를 데이터로 둔 값이 눈에 보여야 한다**(D7). 종류가 하나일 때는 이 화면이
 * 없어도 되지만, 장비와 데이터 종류가 늘면 "우리가 지금 무슨 파일을 받을 수 있나",
 * "이 확장자는 어느 종류로 잡히나", "이 조건은 필수인가" 를 답할 곳이 필요하다.
 * 그 답이 코드 안에만 있으면 물어볼 때마다 개발자를 불러야 한다.
 *
 * 지금은 읽기 전용이다. 편집은 정의를 바꿀 실제 필요가 생겼을 때 붙인다 —
 * 잘못 만든 편집 화면이 채널 키를 바꿔 버리면 이미 저장된 곡선과 어긋난다.
 */

import { ListTree, Plug } from 'lucide-react'

import { testsApi } from '@/modules/tests/api'
import { display } from '@/modules/tests/units'
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

export default function TestTypesPage() {
  const types = useResource(() => testsApi.types(), [])
  const rows = types.data ?? []

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="시험종류 정의"
        description="어떤 시험을 받을 수 있고, 각각 어떤 채널과 조건을 갖는지. 정의는 코드가 아니라 데이터입니다."
      />

      <ErrorNotice error={types.error} className="mb-4" />

      {!types.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <ListTree className="mx-auto mb-2 size-5 opacity-50" />
          정의된 시험 종류가 없습니다.
          <p className="mt-1 text-xs">
            <code>python scripts/ensure_test_types.py</code> 로 기본 정의를 넣습니다.
          </p>
        </div>
      )}

      <div className="space-y-6">
        {rows.map((type) => (
          <section key={type.key} className="rounded-md border">
            <header className="flex flex-wrap items-center gap-2 border-b p-4">
              <h2 className="font-medium">{type.label}</h2>
              <Badge variant="secondary" className="font-mono">
                {type.key}
              </Badge>
              <Badge variant="outline">{type.abbr}</Badge>
              {!type.is_active && <Badge variant="destructive">중단</Badge>}
              <span className="text-muted-foreground ml-auto text-xs">
                최대 {Math.round(type.max_upload_bytes / (1024 * 1024))}MB
              </span>
            </header>

            <div className="space-y-4 p-4">
              {type.description && (
                <p className="text-muted-foreground text-sm">{type.description}</p>
              )}

              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Plug className="text-muted-foreground size-3.5" />
                <span className="text-muted-foreground text-xs">파서</span>
                {type.parser_key ? (
                  <>
                    <code className="bg-muted rounded px-1.5 py-0.5 text-xs">
                      {type.parser_key}
                    </code>
                    {type.extensions.length > 0 ? (
                      type.extensions.map((extension) => (
                        <Badge key={extension} variant="outline" className="font-mono">
                          {extension}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        확장자 선언 없음 — 일괄 등록에서 자동 인식되지 않습니다
                      </span>
                    )}
                  </>
                ) : (
                  <span className="text-muted-foreground text-xs">
                    없음 — 파일을 읽지 못하고 수동 입력만 받습니다
                  </span>
                )}
              </div>

              <div>
                <p className="mb-1 text-xs font-medium">채널 (곡선의 열)</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>키</TableHead>
                      <TableHead>이름</TableHead>
                      <TableHead>차원</TableHead>
                      <TableHead>저장 단위</TableHead>
                      <TableHead>표시</TableHead>
                      <TableHead>필수</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {type.channels.map((channel) => (
                      <TableRow key={channel.key}>
                        <TableCell className="font-mono text-xs">{channel.key}</TableCell>
                        <TableCell className="text-sm">{channel.label}</TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {channel.dimension}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{channel.si_unit}</TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {display(channel.si_unit).unit || '—'}
                        </TableCell>
                        <TableCell>
                          {channel.is_required ? (
                            <Badge variant="secondary">필수</Badge>
                          ) : (
                            <span className="text-muted-foreground text-xs">선택</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <p className="text-muted-foreground mt-1 text-xs">
                  필수 채널이 파일에 없으면 등록이 실패합니다 — 곡선이 조용히 반쪽이
                  되는 것보다 낫습니다.
                </p>
              </div>

              {type.conditions.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium">조건 (입력 항목)</p>
                  <div className="flex flex-wrap gap-2">
                    {type.conditions.map((field) => (
                      <span
                        key={field.key}
                        className="rounded-md border px-2 py-1 text-xs"
                        title={field.key}
                      >
                        {field.label}
                        {field.si_unit && (
                          <span className="text-muted-foreground">
                            {' '}
                            ({display(field.si_unit).unit})
                          </span>
                        )}
                        {field.is_required && <span className="text-destructive"> *</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
