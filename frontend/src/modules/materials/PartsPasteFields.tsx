/**
 * 적용 부품 붙여넣기 칸 — **붙여넣은 범위와 열마다의 짐작을 한 화면에.**
 *
 * 재료 화면의 「붙여넣기」 와 BOM 가져오기가 같은 칸을 쓴다. 두 벌로 두면 한쪽만 열 이름을 더
 * 알아보게 된다. 짐작은 `partsPaste` 가 하고, 여기는 그것을 **보이고 고치게** 한다 — 열마다
 * 머리글과 첫 값 둘을 함께 보여 「품번」 열이 정말 부품코드인지 눈으로 확인한다.
 */

import { useMemo, useState } from 'react'

import {
  guessColumns,
  looksLikeHeader,
  parseCells,
  toRecords,
} from '@/modules/materials/partsPaste'
import type { PartField, PartFieldSpec, PartRecord } from '@/modules/materials/partsPaste'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'

export interface PartsPaste {
  text: string
  setText: (text: string) => void
  cells: string[][]
  header: boolean
  setHeader: (header: boolean) => void
  columns: (PartField | null)[]
  setColumn: (index: number, key: PartField | null) => void
  /** 머리글을 뺀 줄 — 서버로 갈 것. */
  records: PartRecord[]
}

/** 붙여넣은 글자 → 줄. 머리글 · 열은 짐작하되 사람이 고친 것이 이긴다. */
export function usePartsPaste(fields: PartFieldSpec[]): PartsPaste {
  const [text, setRawText] = useState('')
  const [headerChoice, setHeaderChoice] = useState<boolean | null>(null)
  const [columnChoice, setColumnChoice] = useState<(PartField | null)[] | null>(null)

  const cells = useMemo(() => parseCells(text), [text])
  const width = Math.max(0, ...cells.map((row) => row.length))
  const header = headerChoice ?? looksLikeHeader(cells[0], fields)
  const guessed = useMemo(
    () => guessColumns(header ? (cells[0] ?? null) : null, width, fields),
    [cells, header, width, fields]
  )
  const columns = columnChoice && columnChoice.length === width ? columnChoice : guessed
  const records = useMemo(
    () => toRecords(header ? cells.slice(1) : cells, columns),
    [cells, header, columns]
  )

  return {
    text,
    // 새로 붙여넣으면 앞의 고른 것을 버린다 — 열 차례가 다른 BOM 에 앞 BOM 의 짝이 남는다.
    setText: (next) => {
      setRawText(next)
      setHeaderChoice(null)
      setColumnChoice(null)
    },
    cells,
    header,
    setHeader: (next) => {
      setHeaderChoice(next)
      setColumnChoice(null)
    },
    columns,
    setColumn: (index, key) => {
      // **한 칸은 한 열에만.** 다른 열이 이미 그 칸이면 그 열을 비운다.
      const next = columns.map((one, at) => (at === index ? key : one === key ? null : one))
      setColumnChoice(next)
    },
    records,
  }
}

export function PartsPasteFields({
  paste,
  fields,
  placeholder,
}: {
  paste: PartsPaste
  fields: PartFieldSpec[]
  placeholder: string
}) {
  const { cells, header, columns } = paste
  const samples = header ? cells.slice(1, 3) : cells.slice(0, 2)
  const used = new Set(columns.filter(Boolean))
  const missing = fields.filter((one) => !used.has(one.key))

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="parts-paste">엑셀에서 복사한 범위</Label>
        <Textarea
          id="parts-paste"
          className="h-32 font-mono text-xs"
          placeholder={placeholder}
          value={paste.text}
          onChange={(event) => paste.setText(event.target.value)}
        />
      </div>

      {cells.length > 0 && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={header}
                onChange={(event) => paste.setHeader(event.target.checked)}
              />
              첫 줄은 머리글
            </label>
            <span className="text-muted-foreground">
              {paste.records.length.toLocaleString('ko-KR')}줄 · 열 {columns.length}개
            </span>
          </div>

          {/* **열마다 무엇인지 고른다.** 머리글과 첫 값 둘을 함께 보인다 — 「코드」 라는 머리글이
              품번인지 도면번호인지는 값을 봐야 안다. */}
          <div className="overflow-x-auto rounded-md border">
            <table className="text-xs">
              <tbody>
                <tr className="bg-muted/40">
                  {columns.map((key, index) => (
                    <td key={index} className="min-w-28 p-1.5 align-top">
                      <select
                        aria-label={`${index + 1}번 열`}
                        className="border-input bg-background h-7 w-full rounded-md border px-1"
                        value={key ?? ''}
                        onChange={(event) =>
                          paste.setColumn(index, (event.target.value || null) as PartField | null)
                        }
                      >
                        <option value="">(안 씀)</option>
                        {fields.map((one) => (
                          <option key={one.key} value={one.key}>
                            {one.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  ))}
                </tr>
                {header && (
                  <tr className="border-t font-medium">
                    {columns.map((_, index) => (
                      <td key={index} className="px-1.5 py-1">
                        {cells[0]?.[index] ?? ''}
                      </td>
                    ))}
                  </tr>
                )}
                {samples.map((row, at) => (
                  <tr key={at} className="border-t">
                    {columns.map((_, index) => (
                      <td key={index} className="px-1.5 py-1">
                        {row[index] ?? ''}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {missing.length > 0 && (
            <p className="text-muted-foreground text-xs">
              고르지 않은 칸: {missing.map((one) => one.label).join(' · ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
