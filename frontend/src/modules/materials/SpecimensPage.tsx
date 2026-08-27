/**
 * 시편 카탈로그 — **재료를 거치지 않고 시편을 찾는다.**
 *
 * ## 왜 만들었나
 *
 * 시편은 중첩 경로로만 닿았다 — 재료를 고르고, 시료를 고르고, 그제서야 시편이
 * 보였다. 그래서 **시편을 가로지르는 물음**에 답할 자리가 없었다:
 *
 *     "ASTM E8/E8M 박판형으로 자른 시편이 전부 몇 장인가"
 *     "MD 방향인데 규격을 아직 안 붙인 시편은 어느 것인가"
 *
 * 규격은 시편에 붙는데(ADR 0010) 시편을 가로질러 보는 화면이 없으면 **규격으로는
 * 아무것도 못 찾는다.** 물성 카드가 같은 이유로 `/cards` 를 얻었다 — "그 카드가
 * 어느 재료였더라" 에 답할 데가 없었다.
 *
 * ## 행의 단위는 시편이다
 *
 * 시료를 별도 화면으로 또 만들지 않았다. 규격·방향·치수·번호가 전부 시편에
 * 붙어 있고, 시료가 자기만 갖는 검색 축은 로트 정도라 **이 표의 한 열**로 충분
 * 하다. 필요해지면 그때 나누는 편이 싸다.
 *
 * ## 거르는 자리는 열 머리다
 *
 * 표 위에 상자를 늘어놓으면 어느 상자가 어느 열을 거르는지 글자로 적어 둬야
 * 알 수 있다. 열 머리에 붙이면 그 설명이 필요 없다 — 칸이 곧 그 열이다.
 */

import { useEffect, useState } from 'react'
import { FlaskConical } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ORIENTATIONS, materialsApi } from '@/modules/materials/api'
import {
  ColumnFilter,
  ColumnLabel,
  FILTER_HEAD,
  FILTER_ROW,
} from '@/shared/components/ColumnFilter'
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
import { formatScalar } from '@/shared/units'

const PAGE = 50

/** 치수 한 줄. **규격에서 온 값은 흐리게** — 합치면 사람은 전부 실측으로 읽는다. */
function Sizes({ row }: { row: { sizes: { label: string; value: number | null; source: string }[] } }) {
  const shown = row.sizes.filter((one) => one.value != null)
  if (shown.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-0.5">
      {shown.map((one) => (
        <span
          key={one.label}
          className={`text-xs tabular-nums ${
            one.source === 'nominal' ? 'text-muted-foreground italic' : ''
          }`}
          title={one.source === 'nominal' ? '규격이 정한 공칭입니다' : '잰 값입니다'}
        >
          {one.label} {formatScalar(one.value ?? 0, 'm', 'length')}
        </span>
      ))}
    </div>
  )
}

export default function SpecimensPage() {
  const [material, setMaterial] = useState('')
  const [lot, setLot] = useState('')
  const [name, setName] = useState('')
  const [orientation, setOrientation] = useState('')
  const [standard, setStandard] = useState('')
  const [offset, setOffset] = useState(0)

  // **거르면 첫 쪽으로 돌아간다.** 3쪽을 보다 거르면 걸러진 결과의 3쪽이 나오는데,
  // 그게 비어 있으면 사람은 "없다" 로 읽는다.
  useEffect(() => {
    setOffset(0)
  }, [material, lot, name, orientation, standard])

  const page = useResource(
    () =>
      materialsApi.specimenRows({
        material,
        lot,
        q: name,
        orientation,
        standard,
        limit: PAGE,
        offset,
      }),
    [material, lot, name, orientation, standard, offset]
  )

  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0
  const filtered = !!(material || lot || name || orientation || standard)

  return (
    <div className="space-y-4">
      <PageHeader
        title="시편"
        description="재료를 거치지 않고 시편을 찾습니다. 규격·방향·치수가 시편에 붙어 있으므로, 규격으로 찾는 자리가 여기입니다."
      />

      <ErrorNotice error={page.error} />

      <div className="text-muted-foreground flex items-center gap-2 text-sm">
        <span>
          {total.toLocaleString('ko-KR')}건{filtered && ' (걸러진 결과)'}
        </span>
        {filtered && (
          <Button
            size="sm"
            variant="ghost"
            className="h-6 text-xs"
            onClick={() => {
              setMaterial('')
              setLot('')
              setName('')
              setOrientation('')
              setStandard('')
            }}
          >
            거르기 지우기
          </Button>
        )}
      </div>

      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            {/* **머리 띠를 본문과 가른다.** 거르는 칸이 들어가 두 층이 되면서
                띠가 두꺼워졌는데, 배경이 없으면 첫 줄이 머리인지 자료인지
                한눈에 안 갈린다. */}
            <TableRow className={FILTER_ROW}>
              {/* **열마다 그 열을 거른다.** 서버가 거르므로 다음 쪽까지 걸러진다 —
                  화면에서 거르면 이 쪽에 실린 것만 걸러지고, 사람은 그것을
                  「없다」 로 읽는다. */}
              <TableHead className={`min-w-[10rem] ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="재료"
                  value={material}
                  onChange={setMaterial}
                  placeholder="SECC"
                />
              </TableHead>
              <TableHead className={`min-w-[8rem] ${FILTER_HEAD}`}>
                <ColumnFilter label="로트" value={lot} onChange={setLot} placeholder="L-9" />
              </TableHead>
              <TableHead className={`min-w-[11rem] ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="시편"
                  value={name}
                  onChange={setName}
                  placeholder="이름 · 규격"
                />
              </TableHead>
              <TableHead className={`w-24 ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="방향"
                  value={orientation}
                  onChange={setOrientation}
                  options={ORIENTATIONS}
                />
              </TableHead>
              <TableHead className={`min-w-[11rem] ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="규격"
                  value={standard}
                  onChange={setStandard}
                  placeholder="ASTM E8"
                />
              </TableHead>
              {/* 치수와 시험 수는 **서버가 거르는 축이 아니다.** 거르는 칸을
                  두면 눌러도 아무 일이 안 일어나거나, 이 쪽에 실린 것만 걸러
                  거짓말을 한다. */}
              <TableHead className={`min-w-[10rem] ${FILTER_HEAD}`}>
                <ColumnLabel>치수</ColumnLabel>
              </TableHead>
              <TableHead className={`text-right ${FILTER_HEAD}`}>
                <ColumnLabel align="right">시험</ColumnLabel>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="font-mono text-xs">
                  <Link
                    to={`/materials/${row.material_id}`}
                    className="hover:text-primary hover:underline"
                  >
                    {row.material_name}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {row.lot_no ?? '—'}
                </TableCell>
                <TableCell className="font-mono text-xs">{row.record_name}</TableCell>
                <TableCell>
                  <Badge variant="outline">{row.orientation}</Badge>
                </TableCell>
                <TableCell className="text-xs">
                  {row.standard ?? (
                    // **비어 있다는 것이 중요한 정보다.** 규격이 없으면 그 시편은
                    // 치수 칸조차 못 갖는다(ADR 0010) — 이관에서 실제로 그랬다.
                    <span className="text-amber-700 dark:text-amber-500">규격 없음</span>
                  )}
                </TableCell>
                <TableCell>
                  <Sizes row={row} />
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums">
                  {row.test_run_count > 0 ? (
                    <span className="inline-flex items-center gap-1">
                      <FlaskConical className="size-3 opacity-60" />
                      {row.test_run_count}
                      {row.adopted_count > 0 && (
                        <span className="text-muted-foreground">
                          (채택 {row.adopted_count})
                        </span>
                      )}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {!page.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-12 text-center text-sm">
          {filtered ? '걸러진 결과가 없습니다.' : '아직 시편이 없습니다.'}
        </div>
      )}

      {total > PAGE && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground tabular-nums">
            {offset + 1}–{Math.min(offset + PAGE, total)} / {total.toLocaleString('ko-KR')}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
          >
            이전
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={offset + PAGE >= total}
            onClick={() => setOffset(offset + PAGE)}
          >
            다음
          </Button>
        </div>
      )}
    </div>
  )
}
