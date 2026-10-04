/**
 * 승인 대기 값 — **승인하면 등급이 오르는 선언 값을 한 목록으로**(2026-10-04, ADR 0049 의 열린 것).
 *
 * 재료마다 열어 봐야 「무엇을 확인하면 되나」 를 알았다. 여기서는 모아서 보이기만 한다 —
 * 승인은 근거 문서를 펴 보는 일이라 그 값이 사는 화면(재료의 「물성」 탭 · 시료의 밀시트)에서
 * 한다. 큐가 아니다: 상태만 두고 절차는 운영이 보인 뒤에 만든다(ADR 0049 결정 5).
 *
 * 보기는 누구나다(ADR 0035) — 적은 사람도 「내 값이 아직 확인 전」 임을 안다.
 */

import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import { SOURCE_LABEL } from '@/modules/materials/DeclaredPropertiesCard'
import { fetchAll } from '@/shared/api/paging'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { RecordName } from '@/shared/components/RecordName'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

export default function DeclaredReviewPage() {
  // 한 쪽 상한(200)에서 자르면 나머지가 「없는」 것이 된다 — 끝까지 모은다(천장 2000).
  const page = useResource(
    () => fetchAll((limit, offset) => materialsApi.declaredReview(limit, offset)),
    []
  )
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0

  return (
    <div>
      <PageHeader
        title="승인 대기 값"
        description="승인하면 등급이 오르는 선언 값(문헌 3 → 2 · 추정 4 → 3). 자료 관리자가 근거 문서와 대조해 그 재료 · 시료 화면에서 승인합니다 — 값을 고치면 승인은 저절로 풀립니다."
      />
      {page.error && <ErrorNotice error={page.error} />}

      {!page.loading && rows.length === 0 && !page.error && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          승인을 기다리는 값이 없습니다.
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>재료</TableHead>
                <TableHead>층</TableHead>
                <TableHead>항목</TableHead>
                <TableHead>값</TableHead>
                <TableHead>출처</TableHead>
                <TableHead>근거 문서</TableHead>
                <TableHead>등급</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={`${row.material_id}:${row.sample_id ?? ''}:${row.item}`}
                >
                  <TableCell>
                    {/* 승인하는 자리로 곧장 — 재료 값은 「물성」 탭, 시료 값은 「시료·시편」 탭. */}
                    <Link
                      to={`/materials/${row.material_id}?tab=${row.sample_id ? 'samples' : 'properties'}`}
                      className="hover:underline"
                    >
                      <RecordName name={row.material_name} />
                    </Link>
                  </TableCell>
                  <TableCell>
                    {row.level}
                    {row.lot_no ? ` · 로트 ${row.lot_no}` : ''}
                  </TableCell>
                  <TableCell>{row.item}</TableCell>
                  <TableCell>
                    {row.first_value_si === null || row.first_value_si === undefined
                      ? '—'
                      : formatScalar(row.first_value_si, row.si_unit)}
                    {row.point_count > 1 && ` 외 ${row.point_count - 1}점`}
                  </TableCell>
                  <TableCell>{SOURCE_LABEL[row.source ?? ''] ?? row.source ?? '—'}</TableCell>
                  <TableCell>{row.reference || '—'}</TableCell>
                  <TableCell>
                    {row.quality_tier} → {row.tier_if_approved}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {rows.length > 0 && (
        <p className="mt-2 text-sm">
          {total.toLocaleString('ko-KR')}건
          {rows.length < total && ` — 앞 ${rows.length.toLocaleString('ko-KR')}건만 보입니다`}
        </p>
      )}
    </div>
  )
}
