/**
 * 붙여넣기 일괄 등록 — **엑셀에서 복사해 붙인다.**
 *
 * `.xlsx` 파서를 들이지 않았다. 재료 일괄 등록이 이미 이 방식이고(`PasteGrid`),
 * 라이브러리를 하나 더 넣으면 폐쇄망 wheel 번들만 커진다.
 *
 * **드라이런이 먼저다.** 무엇이 만들어지고 **어떤 기준정보가 새로 생기는지**를
 * 보고 나서 누른다 — 오타 하나가 새 조직을 만드는 것이 이 화면의 가장 흔한
 * 사고다. 서버도 같은 규율이라 `dry_run` 이 기본이다(이관기와 같다).
 */

import { useState } from 'react'

import { equipmentApi } from '@/modules/equipment/api'
import type { EquipmentBulkResult } from '@/modules/equipment/api'
import type { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PasteGrid } from '@/shared/components/PasteGrid'
import type { Column } from '@/shared/components/PasteGrid'
import { Button } from '@/shared/components/ui/button'

/** 표의 열. **헤더가 서버 필드 이름과 짝이다** — 순서를 바꾸면 여기만 고친다. */
const COLUMNS: (Column & { field: string })[] = [
  { key: 'name', field: 'name', header: '장비명', help: '필수. 「생기연 DMA」 처럼 부르는 이름' },
  { key: 'asset_no', field: 'asset_no', header: '자산번호', help: '스티커에 적힌 그대로. 없으면 비움' },
  { key: 'instrument_type', field: 'instrument_type', header: '장비 유형', help: 'UTM · DSC · 항온항습기' },
  {
    key: 'workspace',
    field: 'workspace',
    header: '조직(부서)',
    // **없으면 그 줄이 걸린다** — 붙여넣기로 부서를 만들지 않는다.
    help: '이미 있는 부서 이름 또는 slug. 없으면 그 줄이 걸립니다',
  },
  { key: 'lab', field: 'lab', header: '시험실' },
  { key: 'location_detail', field: 'location_detail', header: '방 안 위치', help: '3번 벤치' },
  { key: 'vendor', field: 'vendor', header: '제조사' },
  { key: 'model', field: 'model', header: '모델' },
  { key: 'serial_no', field: 'serial_no', header: '시리얼' },
  { key: 'owner_name', field: 'owner_name', header: '담당자' },
]

const BLANK = () => COLUMNS.map(() => '')

export function EquipmentBulkDialog({ onDone }: { onDone: () => void }) {
  const [rows, setRows] = useState<string[][]>(() => [BLANK(), BLANK(), BLANK()])
  const [result, setResult] = useState<EquipmentBulkResult | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)

  function payload(): Record<string, unknown>[] {
    return rows
      .filter((row) => row.some((cell) => cell.trim()))
      .map((row) => {
        const one: Record<string, unknown> = {}
        COLUMNS.forEach((column, at) => {
          const value = (row[at] ?? '').trim()
          // 빈 칸은 안 보낸다 — 「비운 것」 이 아니라 「안 적은 것」 이다.
          if (value) one[column.field] = value
        })
        return one
      })
  }

  async function run(dryRun: boolean) {
    setBusy(true)
    setError(null)
    try {
      const got = await equipmentApi.bulk(payload(), dryRun)
      setResult(got)
      if (!got.dry_run && got.errors === 0) onDone()
    } catch (caught) {
      setError(caught as ApiError | Error)
    } finally {
      setBusy(false)
    }
  }

  const fresh = result ? [...new Set(result.rows.flatMap((row) => row.new_terms))] : []

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">
        엑셀에서 표를 복사해 아래 칸에 붙여 넣으세요. <b>장비명만 필수</b>이고 나머지는
        비워도 됩니다. 장비 유형·조직·시험실은 <b>이름으로 적으면 됩니다</b> — 없는
        이름이면 기준정보에 새로 만들어집니다. <b>다만 조직(부서)은 만들지
        않습니다</b> — 이미 있는 부서만 적을 수 있습니다.
      </p>

      {error != null && <ErrorNotice error={error} />}

      <PasteGrid columns={COLUMNS} rows={rows} onRows={setRows} required="name" />

      <div className="flex gap-2">
        <Button variant="outline" onClick={() => run(true)} disabled={busy}>
          {busy ? '보는 중…' : '먼저 확인 (아무것도 안 씀)'}
        </Button>
        <Button
          onClick={() => run(false)}
          disabled={busy || result === null || result.errors > 0}
          title={result === null ? '먼저 확인을 눌러 무엇이 들어갈지 보세요' : undefined}
        >
          등록
        </Button>
      </div>

      {result && (
        <div className="space-y-2 rounded border p-3 text-sm">
          <div>
            {result.dry_run ? '확인 결과' : '등록 완료'} — 새로 {result.created}대 ·
            건너뜀 {result.skipped}건 · 문제 {result.errors}건
          </div>

          {/* **새로 생길 기준정보를 먼저 말한다.** 오타 하나가 새 조직을 만든다. */}
          {fresh.length > 0 && (
            <div className="rounded border border-amber-200 bg-amber-50 p-2">
              <div className="mb-1 font-medium text-amber-900">
                기준정보에 새로 생깁니다 — 오타가 아닌지 보세요
              </div>
              <ul className="list-inside list-disc text-amber-900">
                {fresh.map((one) => (
                  <li key={one}>{one}</li>
                ))}
              </ul>
            </div>
          )}

          {result.rows.some((row) => row.outcome !== 'create') && (
            <table className="w-full text-left">
              <tbody>
                {result.rows
                  .filter((row) => row.outcome !== 'create')
                  .map((row) => (
                    <tr key={row.index} className="border-b last:border-0">
                      <td className="text-muted-foreground py-1 pr-2 tabular-nums">
                        {row.index + 1}
                      </td>
                      <td className="py-1 pr-2">{row.name}</td>
                      <td className="py-1">{row.reason}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
