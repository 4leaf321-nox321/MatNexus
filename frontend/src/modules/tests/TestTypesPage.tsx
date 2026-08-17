/**
 * 시험 종류 정의 — 무엇을 읽을 수 있는지 한눈에.
 *
 * **정의를 데이터로 둔 값이 눈에 보여야 한다**(D7). 종류가 하나일 때는 이 화면이
 * 없어도 되지만, 장비와 데이터 종류가 늘면 "우리가 지금 무슨 파일을 받을 수 있나",
 * "이 확장자는 어느 종류로 잡히나", "이 조건은 필수인가" 를 답할 곳이 필요하다.
 * 그 답이 코드 안에만 있으면 물어볼 때마다 개발자를 불러야 한다.
 *
 * **편집도 여기서 한다.** 처음에는 읽기 전용으로 두었는데, 그러면 "정의는 데이터"
 * 라고 해 놓고 새 종류를 만들려면 코드를 고치고 서버에서 스크립트를 돌려야 한다 —
 * 말과 실제가 다르다.
 *
 * 대신 **저장된 데이터의 해석을 바꾸는 수정은 서버가 거절한다.** 등록된 시험이
 * 있으면 채널의 키·단위·차원이 잠긴다. 화면은 그 사실을 잠금 표시와 이유로
 * 보여 준다 — 회색으로만 만들면 사람은 고장인 줄 안다.
 */

import { useState } from 'react'
import { Globe2, ListTree, Lock, Pencil, Plug, Plus, Trash2 } from 'lucide-react'

import { testsApi } from '@/modules/tests/api'
import type { TestType } from '@/modules/tests/api'
import { TestTypeEditor } from '@/modules/tests/TestTypeEditor'
import { display } from '@/shared/units'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
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
  const [editing, setEditing] = useState<TestType | null>(null)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const rows = types.data ?? []

  async function remove(type: TestType) {
    setError(null)
    try {
      await testsApi.removeType(type.key)
      types.reload()
    } catch (caught) {
      // 서버가 "시험이 N건 있어 지울 수 없습니다 — 중단으로 바꾸세요" 를 준다.
      setError(caught instanceof Error ? caught : new Error('삭제하지 못했습니다.'))
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="시험종류 정의"
        description="어떤 시험을 받을 수 있고, 각각 어떤 채널과 조건을 갖는지. 정의는 코드가 아니라 데이터입니다 — 배포 없이 추가됩니다."
        actions={
          <Button
            onClick={() => {
              setEditing(null)
              setOpen(true)
            }}
          >
            <Plus className="size-4" />
            종류 만들기
          </Button>
        }
      />

      <ErrorNotice error={types.error ?? error} className="mb-4" />

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
              {/* **누구 것인지 안 보이면 왜 못 고치는지 알 수 없다.** 전역은 여러
                  부서가 함께 써서 시스템 관리자만 손댄다 — 그 사실이 화면에
                  없으면 편집을 눌러 보고 403 을 받고서야 알게 된다. */}
              {type.is_global ? (
                <Badge variant="outline" className="gap-1" title="모든 부서가 씁니다. 시스템 관리자만 고칠 수 있습니다.">
                  <Globe2 className="size-3" />
                  전역
                </Badge>
              ) : (
                <Badge variant="secondary">{type.owner_workspace_name}</Badge>
              )}
              {!type.is_active && <Badge variant="destructive">중단</Badge>}
              {type.run_count > 0 && (
                <Badge variant="outline" className="gap-1" title="등록된 시험이 있어 채널의 키·단위가 잠깁니다">
                  <Lock className="size-3" />
                  시험 {type.run_count}건
                </Badge>
              )}
              <span className="text-muted-foreground ml-auto text-xs">
                최대 {Math.round(type.max_upload_bytes / (1024 * 1024))}MB
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setEditing(type)
                  setOpen(true)
                }}
              >
                <Pencil className="size-3.5" />
                편집
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={type.run_count > 0}
                title={
                  type.run_count > 0
                    ? '등록된 시험이 있습니다. 더 쓰지 않으려면 편집에서 중단으로 바꾸세요.'
                    : '삭제'
                }
                onClick={() => remove(type)}
              >
                <Trash2 className="size-3.5" />
              </Button>
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
                          {display(channel.si_unit, channel.dimension).unit || '—'}
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
                            ({display(field.si_unit, field.dimension).unit})
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

      <TestTypeEditor
        type={editing}
        open={open}
        onClose={() => setOpen(false)}
        onSaved={() => {
          setOpen(false)
          types.reload()
        }}
      />
    </div>
  )
}
