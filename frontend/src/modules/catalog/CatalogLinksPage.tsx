/**
 * 사내 재료 연결 후보 — **문헌과 안 이어진 사내 재료를 한 화면에서 잇는다.**
 *
 * 연결은 BOM 덱 · 선언 물성 받아오기 · 비교가 그 재료의 문헌 값을 쓰는 입구다. 잇는 길이
 * 재료 상세에서 이름을 쳐서 찾는 것뿐이라 개발 DB 사내 재료 135개 중 9개만 이어져
 * 있었다(2026-10-08). 서버가 등급 · 별칭이 문헌 재료의 코드 · 이름과 같은 것만 후보로
 * 주고(`catalog/material_links`), 사람이 **한 건씩** 누른다 — 일괄로 잇지 않는다.
 *
 * 이은 줄은 그 자리에 「이음」 으로 남기고 되돌리기를 준다 — 목록을 다시 읽어 줄이 사라지면
 * 방금 무엇을 이었는지 확인할 길이 없다.
 */

import { Check, Link2, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  CATEGORY_LABELS,
  MATCHED_BY_LABELS,
  MATCHED_ON_LABELS,
  catalogApi,
} from '@/modules/catalog/api'
import type { LinkCandidatesPage } from '@/modules/catalog/api'
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

type Row = LinkCandidatesPage['items'][number]

function MaterialRow({
  row,
  onError,
}: {
  row: Row
  onError: (error: Error | null) => void
}) {
  const [linked, setLinked] = useState<{ id: string; name: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const materialId = String(row.material_id)

  async function act(action: () => Promise<unknown>, after: () => void) {
    onError(null)
    setBusy(true)
    try {
      await action()
      after()
    } catch (caught) {
      onError(caught instanceof Error ? caught : new Error('처리하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <TableRow>
      <TableCell className="align-top">
        <Link className="font-medium hover:underline" to={`/materials/${materialId}`}>
          {row.record_name}
        </Link>
        <div>
          {row.family} · {row.category}
          {row.alias ? ` · ${row.alias}` : ''}
        </div>
      </TableCell>
      <TableCell className="space-y-1">
        {linked ? (
          <div className="flex flex-wrap items-center gap-2">
            <Check className="size-4" />
            <span>
              <Link className="hover:underline" to={`/catalog/${linked.id}`}>
                {linked.name}
              </Link>{' '}
              에 이음
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                void act(
                  () => catalogApi.clearLink(materialId),
                  () => setLinked(null)
                )
              }
            >
              <Undo2 className="size-4" />
              되돌리기
            </Button>
          </div>
        ) : (
          row.candidates.map((one) => (
            <div key={one.catalog_material_id} className="flex flex-wrap items-center gap-2">
              <Link className="hover:underline" to={`/catalog/${one.catalog_material_id}`}>
                {one.name}
              </Link>
              <Badge variant="outline">{CATEGORY_LABELS[one.category] ?? one.category}</Badge>
              <span>
                {MATCHED_ON_LABELS[one.matched_on] ?? one.matched_on} 「{one.matched_text}」 ·{' '}
                {MATCHED_BY_LABELS[one.matched_by] ?? one.matched_by} · 물성값{' '}
                {one.value_count}건
              </span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={busy || !row.can_edit}
                title={row.can_edit ? undefined : '이 재료를 고칠 수 있는 사람만 잇습니다.'}
                aria-label={`${row.record_name} 을 ${one.name} 에 연결`}
                onClick={() =>
                  void act(
                    () => catalogApi.setLink(materialId, String(one.catalog_material_id)),
                    () => setLinked({ id: String(one.catalog_material_id), name: one.name })
                  )
                }
              >
                <Link2 className="size-4" />
                연결
              </Button>
            </div>
          ))
        )}
      </TableCell>
    </TableRow>
  )
}

export default function CatalogLinksPage() {
  const page = useResource(() => catalogApi.linkCandidateList(), [])
  const [error, setError] = useState<Error | null>(null)
  const data = page.data

  return (
    <div className="space-y-4">
      <PageHeader
        title="사내 재료 연결 후보"
        description="문헌과 아직 안 이어진 사내 재료마다, 등급이나 별칭이 문헌 재료의 코드 · 이름과 같은 것을 후보로 보입니다. 연결은 BOM 덱 · 선언 물성 받아오기 · 비교가 문헌 값을 쓰는 입구라, 맞는지 보고 한 건씩 누르세요."
      />
      <ErrorNotice error={error ?? page.error} />

      {data && (
        <p className="text-muted-foreground text-sm">
          안 이어진 사내 재료 {data.unlinked.toLocaleString('ko-KR')}종 · 그중 후보가 있는 것{' '}
          {data.with_candidates.toLocaleString('ko-KR')}종
          {data.items.length < data.with_candidates
            ? ` · 앞의 ${data.items.length.toLocaleString('ko-KR')}종만 보입니다`
            : ''}
        </p>
      )}

      {data && data.items.length === 0 && (
        <p className="text-muted-foreground rounded-md border py-3 text-center text-sm">
          후보가 있는 재료가 없습니다. 등급 · 별칭이 문헌 이름과 다르면 재료 상세에서 이름으로
          찾아 이으세요.
        </p>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>사내 재료</TableHead>
                <TableHead>이을 만한 문헌 재료</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((row) => (
                <MaterialRow key={row.material_id} row={row} onError={setError} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
