/**
 * 「출처」 탭 — **출처 하나에 한 줄**(2026-10-22). 이 재료의 값이 어느 문헌에서 몇 건 왔고 그
 * 문헌의 값이 어느 등급 · 방법인지. 전에는 같은 출처가 값마다 되풀이돼 「이 재료는 논문 셋에서
 * 왔다」 를 세려면 표를 끝까지 내려야 했다.
 */

import type { CatalogValue } from '@/modules/catalog/api'
import { SourceLabel, TierBadge } from '@/modules/catalog/CatalogValueTable'
import { METHOD_LABELS } from '@/modules/catalog/catalogForms'
import { sourceRows } from '@/modules/catalog/catalogShape'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'

const KIND_LABELS: Record<string, string> = {
  journal: '논문',
  book: '책',
  database: 'DB',
  datasheet: '데이터시트',
  standard: '규격',
  web: '웹',
  other: '기타',
}

export function SourcesTable({ values }: { values: CatalogValue[] }) {
  const rows = sourceRows(values)
  return (
    <div className="overflow-x-auto rounded-md border">
      <Table className="min-w-[44rem]">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[45%]">출처</TableHead>
            <TableHead>종류</TableHead>
            <TableHead className="text-right">값</TableHead>
            <TableHead className="text-right">물성</TableHead>
            <TableHead>등급</TableHead>
            <TableHead>방법</TableHead>
            <TableHead>라이선스</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.source?.id ?? 'none'}>
              <TableCell className="whitespace-normal">
                <SourceLabel source={row.source} />
              </TableCell>
              <TableCell>{row.source ? (KIND_LABELS[row.source.kind] ?? row.source.kind) : '—'}</TableCell>
              <TableCell className="text-right tabular-nums">{row.count}</TableCell>
              <TableCell className="text-right tabular-nums">{row.properties}</TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {row.tiers.map((tier) => (
                    <TierBadge key={tier} tier={tier} />
                  ))}
                </div>
              </TableCell>
              <TableCell>{row.methods.map((one) => METHOD_LABELS[one] ?? one).join(' · ') || '—'}</TableCell>
              {/* **라이선스 · 귀속**(ADR 0068) — 공개 데이터는 귀속 표기가 조건이다. 이관해 온 출처는
                  대개 비어 있다(빈칸은 「모른다」 이지 「자유」 가 아니다). */}
              <TableCell className="whitespace-normal" title={row.source?.attribution ?? undefined}>
                {row.source?.license ?? '—'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
