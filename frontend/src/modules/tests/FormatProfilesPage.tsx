/**
 * 형식 프로파일 목록 — **지금 어떤 장비 파일을 읽을 수 있나.**
 *
 * 시험종류 정의가 "무엇을 재는가" 라면, 여기는 "그 파일이 어떻게 생겼는가" 다.
 * 둘을 나눈 이유: 같은 시험 종류라도 장비마다, 심지어 같은 장비의 소프트웨어
 * 버전마다 파일 모양이 다르다. 종류를 늘리지 않고 프로파일만 하나 더 만들면 된다.
 *
 * 우선순위를 보여 주는 이유: 지문이 겹치는 일이 **실제로 생긴다.** 같은 장비의
 * 형식이 조금 달라져 프로파일을 하나 더 만들면 헤더가 겹치기 때문이다. 그때 어느
 * 쪽이 이기는지가 화면에 없으면 "왜 이걸로 읽혔지" 를 코드로 확인해야 한다.
 */

import { useState } from 'react'
import { FileCode2, Globe2, Pencil, Plus, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { testsApi } from '@/modules/tests/api'
import type { FormatProfile, ProfileDefinition } from '@/modules/tests/api'
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

export default function FormatProfilesPage() {
  const profiles = useResource(() => testsApi.formats(), [])
  const [error, setError] = useState<Error | null>(null)
  const rows = profiles.data ?? []

  async function remove(item: FormatProfile) {
    setError(null)
    try {
      await testsApi.removeFormat(item.key)
      profiles.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('삭제하지 못했습니다.'))
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="형식 프로파일"
        description="장비 파일을 어떻게 읽을지. 구조는 코드가 자동으로 읽고, '이 열이 무엇인가'만 여기에 저장합니다 — 새 장비를 붙이는 데 배포가 필요 없습니다."
        actions={
          <Button asChild>
            <Link to="/admin/formats/new">
              <Plus className="size-4" />
              프로파일 만들기
            </Link>
          </Button>
        }
      />

      <ErrorNotice error={profiles.error ?? error} className="mb-4" />

      {!profiles.loading && rows.length === 0 ? (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          <FileCode2 className="mx-auto mb-2 size-5 opacity-50" />
          프로파일이 없습니다.
          <p className="mx-auto mt-2 max-w-md text-xs">
            장비 파일 하나를 놓고 만들면 됩니다. 파일은 저장되지 않고 구조만 읽습니다.
          </p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>이름</TableHead>
              <TableHead>누구 것</TableHead>
              <TableHead>시험 종류</TableHead>
              <TableHead>지문</TableHead>
              <TableHead>열</TableHead>
              <TableHead>우선</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => {
              const definition = item.definition as unknown as ProfileDefinition
              const match = definition.match ?? {}
              const columnCount = Object.keys(definition.columns ?? {}).length
              return (
                <TableRow key={item.key}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{item.label}</span>
                      {!item.is_active && <Badge variant="destructive">중단</Badge>}
                    </div>
                    <span className="text-muted-foreground font-mono text-xs">{item.key}</span>
                    {item.description && (
                      <p className="text-muted-foreground mt-0.5 text-xs">{item.description}</p>
                    )}
                  </TableCell>
                  {/* **장비는 부서마다 다르다.** 누구 것인지 안 보이면 왜 내
                      파일이 저 규칙으로 읽혔는지 알 수 없다. */}
                  <TableCell className="text-sm">
                    {item.is_global ? (
                      <Badge variant="outline" className="gap-1">
                        <Globe2 className="size-3" />
                        전역
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        {item.owner_workspace_name}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-sm">{item.test_type_label}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {(match.extensions ?? []).map((extension) => (
                        <Badge key={extension} variant="outline" className="font-mono text-xs">
                          {extension}
                        </Badge>
                      ))}
                      {(match.header_any ?? []).slice(0, 2).map((name) => (
                        <Badge key={name} variant="secondary" className="text-xs">
                          {name}
                        </Badge>
                      ))}
                      {(match.header_any ?? []).length > 2 && (
                        <span className="text-muted-foreground text-xs">
                          외 {(match.header_any ?? []).length - 2}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {columnCount}개
                    {definition.tables?.mode === 'all' && ' · 표 전부'}
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">
                    {item.priority}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" asChild>
                      <Link to={`/admin/formats/${item.key}`}>
                        <Pencil className="size-3.5" />
                        편집
                      </Link>
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      title="지웁니다. 이미 읽은 데이터는 그대로 남습니다."
                      onClick={() => remove(item)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}

      <p className="text-muted-foreground mt-4 text-xs">
        <b>부서 관리자가 자기 부서 프로파일을 만듭니다.</b> 장비는 부서마다 다르고, 남의
        부서 파일을 어떻게 읽을지는 그 부서가 가장 잘 압니다. 여러 부서가 같은 장비를
        쓰게 되면 시스템 관리자가 전역으로 올립니다. 파일을 읽을 때는 <b>내 부서 것이
        전역보다 먼저</b>입니다.
      </p>
      <p className="text-muted-foreground mt-2 text-xs">
        프로파일을 고쳐도 <b>이미 읽은 데이터는 바뀌지 않습니다.</b> 원본을 그대로
        보관하므로, 규칙이 틀렸다는 것을 나중에 알면 고친 뒤 시험 상세에서 다시 읽으면
        됩니다.
      </p>
    </div>
  )
}
