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
 *
 * 재료·로트·규격·방향은 **서버가 센 목록에서 고른다**(재료·시험 목록과 같은
 * 두 층 머리, 2026-09-12). 치면 「SECC」 가 「SECC-1」 까지 물고, 「규격 없음」 은
 * 쳐서는 표현이 안 된다 — 목록이 많으면 칸 안에서 찾아 고른다.
 *
 * 치수는 **재료의 기준 두께와 얼마나 다른가**로 거른다(2026-09-29). 두께가 다른 재료에
 * 넣은 시편을 찾아 「다른 두께로 옮기기」 로 옮기는 자리다(ADR 0042).
 */

import { useEffect, useState } from 'react'
import { FlaskConical, MoveRight, PencilLine } from 'lucide-react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { SpecimenRow } from '@/modules/materials/api'
import { BulkSpecimenDialog } from '@/modules/materials/BulkSpecimenDialog'
import { RelocateDialog } from '@/modules/materials/RelocateDialog'
import {
  ColumnFilter,
  ColumnLabel,
  FILTER_HEAD,
  FILTER_ROW,
} from '@/shared/components/ColumnFilter'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Stamp } from '@/shared/components/Stamp'
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
import { ROW_FOCUS_STYLE, useRowFocus } from '@/shared/hooks/useRowFocus'
import { useRowSelection } from '@/shared/hooks/useRowSelection'
import { useSort } from '@/shared/hooks/useSort'
import { formatScalar } from '@/shared/units'
import { specimenHref } from '@/modules/materials/SpecimenEntry'
import { RecordName } from '@/shared/components/RecordName'

const PAGE = 50

//: 치수 값이 어디서 왔나 → 사람에게 할 말. **잰 것이 아니면 그렇다고 말한다.**
const SIZE_SOURCES: Record<string, string> = {
  measured: '잰 값입니다',
  run: '이 시험에서 잰 값입니다',
  nominal: '규격이 정한 공칭입니다',
  material: '재료의 스펙 두께입니다 — 실제로 재면 그 값이 이깁니다',
}

/** 치수 한 줄. **잰 값이 아닌 것은 흐리게** — 합치면 사람은 전부 실측으로 읽는다. */
function Sizes({ row }: { row: { sizes: { label: string; value: number | null; source: string }[] } }) {
  const shown = row.sizes.filter((one) => one.value != null)
  if (shown.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    // **접지 않는다.** 접히면 `gauge_length 50 mm` 의 이름과 값이 다른 줄로
    // 갈라져, 어느 숫자가 무엇인지 눈으로 다시 맞춰야 한다. 열은 내용만큼
    // 넓어지고, 표가 넘치면 가로로 밀린다(바깥이 `overflow-x-auto`).
    <div className="flex flex-nowrap gap-x-2 whitespace-nowrap">
      {shown.map((one) => (
        <span
          key={one.label}
          className={`text-xs tabular-nums ${
            one.source === 'measured' || one.source === 'run'
              ? ''
              : 'text-muted-foreground italic'
          }`}
          title={SIZE_SOURCES[one.source] ?? '잰 값입니다'}
        >
          {one.label} {formatScalar(one.value ?? 0, 'm', 'length')}
        </span>
      ))}
    </div>
  )
}

//: 견준 두께가 어디서 왔나.
const GAP_SOURCES: Record<string, string> = {
  measured: '시편에 적은 두께',
  run: '시험 파일이 잰 두께',
}

/**
 * **기준 두께와 크게 다르면 그 줄에서 말한다**(ADR 0042) — 두께가 다른 재료에 넣은 시편을
 * 찾는 표시다. 기준(`from`)은 가장 작은 거르기 선택지라, 배지가 선 줄은 거르면 나온다.
 *
 * 시험 파일이 잰 두께는 치수 칸에 안 보인다(시험마다 다르다) — 그래서 무엇과 무엇을
 * 견줬는지를 배지가 말한다.
 */
function ThicknessGap({ gap, from }: { gap: SpecimenRow['thickness_gap']; from: number | null }) {
  // 경계는 서버와 같게 — 0.95 / 1.0 은 부동소수로 5% 에 조금 못 미친다(`thickness_gap.EPSILON`).
  if (!gap || from == null || Math.abs(gap.deviation) < from - 1e-9) return null
  const percent = `${gap.deviation > 0 ? '+' : ''}${Math.round(gap.deviation * 100)}%`
  const value = formatScalar(gap.value, 'm', 'length')
  return (
    <Badge
      variant="outline"
      className="border-amber-500/50 font-normal text-amber-700 dark:text-amber-500"
      title={
        `${GAP_SOURCES[gap.source] ?? '잰 두께'} ${value} — ` +
        `재료의 기준 두께 ${formatScalar(gap.spec, 'm', 'length')} 와 ${percent} 다릅니다. ` +
        '다른 두께의 재료에 넣은 것이면 골라서 「다른 두께로 옮기기」 로 옮기세요.'
      }
    >
      {/* **시험 파일이 잰 값은 치수 칸에 없다** — 그 칸에는 재료 두께가 흐리게 서 있어서,
          값을 안 적으면 「0.8 mm 인데 +25%?」 로 읽힌다(2026-09-29 화면 확인). */}
      {gap.source === 'run' ? `시험 파일 ${value} · ` : ''}기준 대비 {percent}
    </Badge>
  )
}

/** 서버가 센 줄을 거르개 선택지로 — 값은 이름이 아니라 key 다(재료는 id). */
function pickable(rows: { key: string; label: string; count: number }[] | undefined) {
  return (rows ?? []).map((one) => ({ value: one.key, label: one.label, count: one.count }))
}

export default function SpecimensPage() {
  const [material, setMaterial] = useState('')
  const [lot, setLot] = useState('')
  const [name, setName] = useState('')
  const [orientation, setOrientation] = useState('')
  const [standard, setStandard] = useState('')
  // **기준 두께와 차이** — 선택지의 key 가 비율이다(`0.1` = 10%).
  const [gap, setGap] = useState('')
  const facets = useResource(() => materialsApi.specimenFacets(), [])
  const gapSteps = (facets.data?.thickness_gaps ?? []).map((one) => Number(one.key))
  const gapFrom = gapSteps.length > 0 ? Math.min(...gapSteps) : null
  const [offset, setOffset] = useState(0)
  // 기본은 **최근 등록순.** 목록에 늘 순서가 있어야 한다.
  const { sort, handle } = useSort('created_at', {
    // **이 브라우저가 기억한다.** 계정이 아니다 — 같은 PC 를 다른 사람이
    // 쓰면 앞사람 설정이 보인다. 정렬은 데이터가 아니라 보는 방식이라
    // 새어도 잃을 것이 없다.
    remember: 'specimens',
    // **저장된 열이 지금도 정렬 가능한지 확인한다.** 표에서 열을 빼면
    // 서버가 422 를 내고, 그러면 그 브라우저에서만 목록이 영영 안 뜬다.
    allowed: ['created_at', 'material_name', 'lot_no', 'record_name', 'orientation', 'standard'],
  })
  const [editing, setEditing] = useState(false)
  // **다른 두께로 옮기기**(2026-09-29) — 두께가 다른 재료에 잘못 넣은 시편을 바로잡는다.
  const [relocating, setRelocating] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  // **거르면 첫 쪽으로 돌아간다.** 3쪽을 보다 거르면 걸러진 결과의 3쪽이 나오는데,
  // 그게 비어 있으면 사람은 "없다" 로 읽는다.
  useEffect(() => {
    setOffset(0)
    // **선택도 함께 푼다.** 걸러서 안 보이게 된 줄이 골라진 채 남으면, 「12건에
    // 걸기」 가 화면에 없는 것까지 건드린다.
    selection.clear()
  }, [material, lot, name, orientation, standard, gap])

  const page = useResource(
    () =>
      materialsApi.specimenRows({
        material_id: material,
        lot_no: lot,
        q: name,
        orientation,
        standard_exact: standard,
        thickness_gap: gap ? Number(gap) : undefined,
        sort: sort.key,
        desc: sort.descending,
        limit: PAGE,
        offset,
      }),
    [material, lot, name, orientation, standard, gap, sort, offset]
  )

  const rows = page.data?.items ?? []

  // **Shift 로 범위를 고른다.** 수백 장을 하나씩 누르는 것은 일이 아니다.

  const selection = useRowSelection(rows.map((row) => row.id))
  const focus = useRowFocus(rows.map((row) => row.id))

  const picked = selection.picked
  const total = page.data?.total ?? 0
  const filtered = !!(material || lot || name || orientation || standard || gap)

  return (
    <div className="space-y-4">
      <PageHeader
        title="시편"
        description="재료를 거치지 않고 시편을 찾습니다. 규격·방향·치수가 시편에 붙어 있으므로, 규격으로 찾는 자리가 여기입니다."
      />

      <ErrorNotice error={page.error ?? facets.error} />

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
              setGap('')
            }}
          >
            필터 해제
          </Button>
        )}
      </div>

      {picked.size > 0 && (
        <div className="bg-muted/40 flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
          <span className="text-sm">
            <b>{picked.size}건</b> 선택
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            onClick={() => selection.clear()}
          >
            선택 해제
          </Button>
          {/* **이관에서 규격이 빈 시편이 무더기로 생겼다.** 그때 고칠 길이
              하나씩 여는 것뿐이었다 — 수백 장이면 그것은 길이 아니다. */}
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            <PencilLine className="size-4" />
            일괄 수정
          </Button>
          {/* **재료 이름의 두께와 시편 치수가 한 줄에 보이는 자리다** — 잘못 들어간 것이
              눈에 띄는 곳에서 바로 옮긴다. 재료 수정으로 두께를 바꾸면 제대로 들어간
              시료까지 옮겨진다. */}
          <Button size="sm" variant="outline" onClick={() => setRelocating(true)}>
            <MoveRight className="size-4" />
            다른 두께로 옮기기
          </Button>
        </div>
      )}

      {notice && (
        <p className="bg-muted/40 rounded-md border px-3 py-2 text-sm">{notice}</p>
      )}

      <RelocateDialog
        open={relocating}
        specimenIds={[...picked]}
        onClose={() => setRelocating(false)}
        onDone={(done) => {
          // **무엇이 어디로 갔는지 말한다** — 「옮겼습니다」 만으로는 새 재료가 생겼는지 모른다.
          const where = [
            ...done.created_materials.map((name) => `${name}(새로 만듦)`),
            ...done.joined_materials,
          ].join(', ')
          setNotice(
            `시편 ${done.moved}개(시험 ${done.test_runs}건)를 ${where} 로 옮겼습니다.` +
              (done.cards_noted > 0
                ? ` 카드 ${done.cards_noted}장에 코멘트를 남겼습니다` +
                  (done.cards_deprecated > 0 ? `(정리 ${done.cards_deprecated}장).` : '.')
                : '') +
              (done.blocked.length > 0 ? ` 못 옮긴 것 ${done.blocked.length}개.` : '')
          )
          selection.clear()
          page.reload()
          // 옮긴 시편은 이제 기준과 맞는다 — 선택지 옆의 수도 다시 센다.
          facets.reload()
        }}
      />

      <BulkSpecimenDialog
        open={editing}
        specimenIds={[...picked]}
        onClose={() => {
          setEditing(false)
          // **선택은 닫을 때 푼다.** 걸자마자 풀면 창이 「0건」 으로 바뀐다.
          selection.clear()
        }}
        onDone={() => {
          page.reload()
          facets.reload()
        }}
      />

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
              {/* **수백 장을 하나씩 여는 것은 일이 아니다.** 골라서 한 번에 맞춘다. */}
              <TableHead className={`w-8 ${FILTER_HEAD}`}>
                <div className="flex h-[3.25rem] items-end pb-2">
                  <input
                    type="checkbox"
                    aria-label="이 쪽 전부 선택"
                    checked={selection.allOn}
                    ref={(node) => {
                      if (node) node.indeterminate = selection.someOn
                    }}
                    onChange={(event) => selection.setAll(event.target.checked)}
                  />
                </div>
              </TableHead>
              <TableHead className={`min-w-[10rem] ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="재료"
                  sort={handle('material_name')}
                  value={material}
                  onChange={setMaterial}
                  options={pickable(facets.data?.materials)}
                />
              </TableHead>
              <TableHead className={`min-w-[8rem] ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="로트"
                  sort={handle('lot_no')}
                  value={lot}
                  onChange={setLot}
                  options={pickable(facets.data?.lots)}
                />
              </TableHead>
              <TableHead className={`min-w-[11rem] ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="시편"
                  sort={handle('record_name')}
                  value={name}
                  onChange={setName}
                  placeholder="이름 · 규격"
                />
              </TableHead>
              <TableHead className={`w-24 ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="방향"
                  sort={handle('orientation')}
                  value={orientation}
                  onChange={setOrientation}
                  options={pickable(facets.data?.orientations)}
                />
              </TableHead>
              <TableHead className={`min-w-[11rem] ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="규격"
                  sort={handle('standard')}
                  value={standard}
                  onChange={setStandard}
                  options={pickable(facets.data?.standards)}
                />
              </TableHead>
              {/* 시험 수는 **서버가 거르는 축이 아니다.** 거르는 칸을 두면 눌러도
                  아무 일이 안 일어나거나, 이 쪽에 실린 것만 걸러 거짓말을 한다.
                  치수는 **기준 두께와의 차이** 하나로만 거른다 — 서버가 시편에 적은
                  두께와 시험 파일이 잰 두께를 재료의 기준 두께와 견줘 센다. */}
              {/* **치수는 내용만큼 넓다.** `min-w-[10rem]` 이 이 열을 160px 에
                  묶어서, `width 12.47 mm · thickness 0.986 mm · gauge_length 50 mm`
                  가 두 줄로 접혔다. `w-px` 는 표에서 「내용만큼」 이라는 뜻이다. */}
              <TableHead className={`w-px whitespace-nowrap ${FILTER_HEAD}`}>
                <ColumnFilter
                  label="치수"
                  value={gap}
                  onChange={setGap}
                  options={pickable(facets.data?.thickness_gaps)}
                />
              </TableHead>
              <TableHead className={`text-right ${FILTER_HEAD}`}>
                <ColumnLabel align="right">시험</ColumnLabel>
              </TableHead>
              <TableHead className={`w-36 ${FILTER_HEAD}`}>
                <ColumnLabel sort={handle('created_at')}>등록 일시</ColumnLabel>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id} className={ROW_FOCUS_STYLE} {...focus.rowProps(row.id)}>
                <TableCell>
                  <input
                    type="checkbox"
                    aria-label={`${row.record_name} 선택`}
                    checked={picked.has(row.id)}
                    // **`onClick` 이다.** `onChange` 에는 shiftKey 가 안 실린다.
                    onClick={(event) => selection.toggle(row.id, event)}
                    onChange={() => {}}
                  />
                </TableCell>
                <TableCell className="font-mono">
                  <Link
                    to={`/materials/${row.material_id}`}
                    className="hover:text-primary hover:underline"
                  >
                    {row.material_name}
                  </Link>
                </TableCell>
                <TableCell>
                  {row.lot_no ?? '—'}
                </TableCell>
                <TableCell className="font-mono font-medium">
                  {/* **시편 이름이 곧 들어가는 문이다.** 전에는 재료 이름만
                      링크라, 시편을 찾아 놓고도 그 시편으로는 못 갔다 —
                      재료로 간 다음 시료를 하나씩 열어 눈으로 찾아야 했다
                      (2026-09-11 지적). */}
                  <Link to={specimenHref(row)} className="hover:text-primary hover:underline">
                    <RecordName name={row.record_name} />
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{row.orientation}</Badge>
                </TableCell>
                <TableCell>
                  {row.standard ?? (
                    // **비어 있다는 것이 중요한 정보다.** 규격이 없으면 그 시편은
                    // 치수 칸조차 못 갖는다(ADR 0010) — 이관에서 실제로 그랬다.
                    <span className="text-amber-700 dark:text-amber-500">규격 없음</span>
                  )}
                </TableCell>
                <TableCell>
                  {/* **배지는 치수 아래 줄에 선다.** 옆에 두면 이 열이 배지만큼 넓어져
                      시험·등록 일시가 화면 밖으로 밀렸다(2026-09-29 화면 확인). */}
                  <div className="flex flex-col items-start gap-1">
                    <Sizes row={row} />
                    <ThicknessGap gap={row.thickness_gap} from={gapFrom} />
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">
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
                <TableCell>
                  <Stamp at={row.created_at} />
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
