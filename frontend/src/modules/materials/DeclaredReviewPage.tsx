/**
 * 승인 대기 값 — **승인하면 등급이 오르는 선언 값을 한 목록으로**(2026-10-04, ADR 0049 의 열린 것).
 *
 * 재료마다 열어 봐야 「무엇을 확인하면 되나」 를 알았다. 여기서 모아 보이고, **자료 관리자는
 * 여기서 바로 승인한다**(2026-10-04 사용자 결정 — 줄에 값 · 출처 · 근거 문서가 다 있어 재료
 * 화면까지 갈 이유가 적다). 근거를 더 펴 봐야 하면 재료 이름을 눌러 그 화면으로 간다.
 *
 * ## 보던 값을 승인한다
 *
 * 목록은 오래 열어 둘 수 있다. 그 사이 누가 값을 고쳤으면 화면에 보인 값과 승인되는 값이
 * 다르다 — 그래서 줄의 지문(`digest`)을 함께 보내고 서버가 대 본다(`MNX-MATERIALS-0050`).
 *
 * 큐는 아니다: 배정 · 마감 · 알림은 운영을 본 뒤에 만든다(ADR 0049 결정 5). 보기는 누구나다
 * (ADR 0035) — 적은 사람도 「내 값이 아직 확인 전」 임을 안다.
 */

import { useState } from 'react'
import { BadgeCheck, Undo2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { DeclaredReviewPage as ReviewPage } from '@/modules/materials/api'
import { SOURCE_LABEL } from '@/modules/materials/DeclaredPropertiesCard'
import { fetchAll } from '@/shared/api/paging'
import { isDataSteward } from '@/shared/auth/roles'
import { useMaybeAuth } from '@/shared/auth/AuthContext'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { RecordName } from '@/shared/components/RecordName'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
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

type Row = ReviewPage['items'][number]

const keyOf = (row: Row) => `${row.material_id}:${row.sample_id ?? ''}:${row.item}`

function valueOf(row: Row): string {
  const first =
    row.first_value_si === null || row.first_value_si === undefined
      ? '—'
      : formatScalar(row.first_value_si, row.si_unit)
  return row.point_count > 1 ? `${first} 외 ${row.point_count - 1}점` : first
}

export default function DeclaredReviewPage() {
  // 한 쪽 상한(200)에서 자르면 나머지가 「없는」 것이 된다 — 끝까지 모은다(천장 2000).
  const page = useResource(
    () => fetchAll((limit, offset) => materialsApi.declaredReview(limit, offset)),
    []
  )
  const rows = page.data?.items ?? []
  const total = page.data?.total ?? 0
  // **승인은 자료 관리자만**(ADR 0049) — 단추를 미리 가린다. 판정은 서버다.
  const steward = isDataSteward(useMaybeAuth()?.user)

  /** 승인하려는 줄 — 확인 창에 값 · 출처 · 근거를 다시 보인다. */
  const [asking, setAsking] = useState<Row | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  /** 방금 승인한 줄 — 「되돌리기」 를 그 자리에서. 목록에서는 빠지므로 여기 들고 있는다. */
  const [done, setDone] = useState<Row | null>(null)
  const [undone, setUndone] = useState(false)

  async function approve(row: Row) {
    setBusy(true)
    setError(null)
    try {
      const memo = note.trim() || undefined
      if (row.sample_id) {
        await materialsApi.approveSampleDeclared(row.sample_id, row.item, memo, row.digest)
      } else {
        await materialsApi.approveDeclared(row.material_id, row.item, memo, row.digest)
      }
      setDone(row)
      setUndone(false)
      setAsking(null)
      setNote('')
      page.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('승인하지 못했습니다.'))
      // **그 사이 값이 바뀌었으면 목록을 다시 읽는다** — 새 값과 새 지문으로 다시 보게.
      page.reload()
    } finally {
      setBusy(false)
    }
  }

  async function undo(row: Row) {
    setBusy(true)
    setError(null)
    try {
      if (row.sample_id) await materialsApi.unapproveSampleDeclared(row.sample_id, row.item)
      else await materialsApi.unapproveDeclared(row.material_id, row.item)
      setUndone(true)
      page.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('승인을 거두지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="승인 대기 값"
        description={
          steward
            ? '승인하면 등급이 오르는 선언 값(문헌 3 → 2 · 추정 4 → 3). 근거 문서와 대조한 뒤 줄의 「승인」 을 누르세요 — 근거를 더 봐야 하면 재료 이름을 눌러 그 화면으로 갑니다. 값을 고치면 승인은 저절로 풀립니다.'
            : '승인하면 등급이 오르는 선언 값(문헌 3 → 2 · 추정 4 → 3). 자료 관리자가 근거 문서와 대조해 승인합니다 — 값을 고치면 승인은 저절로 풀립니다.'
        }
      />
      {page.error && <ErrorNotice error={page.error} />}
      {/* 창 밖의 오류(되돌리기) — 창 안의 것은 창이 보인다. */}
      {!asking && error && <ErrorNotice error={error} className="mb-3" />}

      {done && (
        <div
          aria-label="방금 승인한 값"
          className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-emerald-600/40 bg-emerald-500/5 p-2 text-sm"
        >
          {undone ? (
            <span>
              「{done.material_name} · {done.item}」 의 승인을 거뒀습니다 — 목록에 다시 섭니다.
            </span>
          ) : (
            <>
              <span>
                「{done.material_name} · {done.item}」 를 승인했습니다 — 등급 {done.quality_tier} →{' '}
                {done.tier_if_approved}.
              </span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={busy}
                onClick={() => void undo(done)}
              >
                <Undo2 className="size-3.5" />
                되돌리기
              </Button>
            </>
          )}
        </div>
      )}

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
                {steward && <TableHead className="w-20">승인</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={keyOf(row)}>
                  <TableCell>
                    {/* 근거를 더 펴 보는 자리로 — 재료 값은 「물성」 탭, 시료 값은 「시료·시편」 탭. */}
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
                  <TableCell>{valueOf(row)}</TableCell>
                  <TableCell>{SOURCE_LABEL[row.source ?? ''] ?? row.source ?? '—'}</TableCell>
                  <TableCell>{row.reference || '—'}</TableCell>
                  <TableCell>
                    {row.quality_tier} → {row.tier_if_approved}
                  </TableCell>
                  {steward && (
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={`${row.material_name} ${row.item} 승인`}
                        disabled={busy}
                        onClick={() => {
                          setError(null)
                          setNote('')
                          setAsking(row)
                        }}
                      >
                        <BadgeCheck className="size-3.5" />
                        승인
                      </Button>
                    </TableCell>
                  )}
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

      {/* **무엇을 승인하는지 다시 보인다.** 줄의 단추만 누르게 두면, 긴 목록에서 옆 줄을 눌러도
          알 길이 없다. 「근거 문서와 대조했나」 를 한 번 더 묻는 자리이기도 하다. */}
      <ConfirmDialog
        open={asking !== null}
        title="이 값을 승인할까요?"
        confirmLabel="승인"
        undoable="승인한 뒤 그 자리의 「되돌리기」 로 거둘 수 있습니다."
        busy={busy}
        body={
          asking && (
            <span className="block space-y-2">
              <span className="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-3 gap-y-1">
                <span className="text-muted-foreground">재료</span>
                <span>
                  {asking.material_name}
                  {asking.sample_id ? ` · 시료${asking.lot_no ? ` (로트 ${asking.lot_no})` : ''}` : ''}
                </span>
                <span className="text-muted-foreground">항목</span>
                <span>{asking.item}</span>
                <span className="text-muted-foreground">값</span>
                <span className="font-mono">{valueOf(asking)}</span>
                <span className="text-muted-foreground">출처</span>
                <span>{SOURCE_LABEL[asking.source ?? ''] ?? asking.source ?? '—'}</span>
                <span className="text-muted-foreground">근거 문서</span>
                <span>{asking.reference || '— (적힌 근거가 없습니다)'}</span>
                <span className="text-muted-foreground">등급</span>
                <span>
                  {asking.quality_tier} → {asking.tier_if_approved}
                </span>
              </span>
              <span className="block">
                근거 문서와 대조해 맞는 값이면 승인하세요. 값 · 단위 · 조건 · 출처 · 근거 문서를 고치면
                승인은 저절로 풀립니다.
              </span>
              <Input
                aria-label="무엇을 확인했나"
                placeholder="무엇을 확인했나 (선택) — 예: 원문 p.120 대조"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <ErrorNotice error={error} />
            </span>
          )
        }
        onConfirm={() => asking && void approve(asking)}
        onClose={() => {
          setAsking(null)
          setError(null)
        }}
      />
    </div>
  )
}
