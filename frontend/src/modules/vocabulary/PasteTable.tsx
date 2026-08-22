/**
 * 표로 붙여넣기 — **무엇을 적을 수 있는지 화면이 먼저 말한다.**
 *
 * 전에는 빈 칸에 줄을 붙여넣게 했다. 상위·값·표기 셋만 받을 때는 그래도 됐는데,
 * 속성까지 받게 되면서 **사용자가 무엇을 적어야 하는지 알 방법이 없어졌다** —
 * 헤더에 칸 이름을 적으라고만 하면 그 이름이 무엇인지 모른다. 규격의 칸은 분류가
 * 정하고 분류마다 다르다.
 *
 * 그래서 열을 **서버가 주는 목록에서 고르고**, 표에 그대로 붙여넣는다.
 *
 * ## 표는 껍데기다
 *
 * 서버로 갈 때는 지금까지와 같은 **탭으로 갈린 줄 + 헤더**가 된다. 표는 사람이
 * 보기 좋으라고 있는 것이지 새 형식이 아니다 — 형식이 둘이 되면 두 곳이 갈라진다.
 *
 * ## 숫자 열은 단위를 헤더에 적는다
 *
 * `50` 이 50 mm 인지 50 m 인지 서버가 알 방법이 없다. 화면이 표시 단위를 알고
 * 있으므로(`shared/units`) 헤더 글자를 여기서 만든다 — 사람이 적다가 틀릴 자리를
 * 없앤다.
 */

import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { ClipboardEvent } from 'react'
import { Check, Copy, Plus, Trash2 } from 'lucide-react'

import type { SpecimenField } from '@/modules/vocabulary/api'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { copyText } from '@/shared/clipboard'
import { display } from '@/shared/units'

/** 표의 한 열. 값·상위·표기는 늘 있고, 나머지는 고른 칸이다. */
export interface Column {
  key: string
  /** 화면에 보이는 이름이자 **서버로 가는 헤더 글자**. */
  header: string
  fixed?: boolean
  help?: string | null
}

/** 숫자 칸이면 표시 단위를 괄호에 넣는다 — 서버가 그걸 보고 환산한다. */
export function headerOf(field: SpecimenField): string {
  if (field.kind !== 'number') return field.label
  const unit = display(field.si_unit, field.dimension).unit
  return unit ? `${field.label} (${unit})` : field.label
}

export function columnsOf(fields: SpecimenField[], picked: Set<string>, hasParent: boolean) {
  const fixed: Column[] = [
    ...(hasParent ? [{ key: '상위', header: '상위', fixed: true }] : []),
    { key: '값', header: '값', fixed: true },
    { key: '표기', header: '표기', fixed: true, help: '다른 표기. 여럿이면 ; 로.' },
  ]
  const chosen: Column[] = fields
    .filter((field) => picked.has(field.key))
    .map((field) => ({ key: field.key, header: headerOf(field), help: field.help }))
  return [...fixed, ...chosen]
}

/** 표를 서버가 받는 모양으로. **헤더 한 줄 + 탭으로 갈린 줄들.** */
export function toLines(columns: Column[], rows: string[][]): string[] {
  return [
    columns.map((column) => column.header).join('\t'),
    ...rows
      // 값 칸이 빈 줄은 안 보낸다 — 표에는 늘 빈 줄이 하나 남아 있다.
      .filter((row) => row.some((cell) => cell.trim()))
      .map((row) => row.join('\t')),
  ]
}

export function PasteTable({
  fields,
  hasParent,
  picked,
  onPicked,
  rows,
  onRows,
  borrow,
}: {
  fields: SpecimenField[]
  hasParent: boolean
  picked: Set<string>
  onPicked: (next: Set<string>) => void
  rows: string[][]
  onRows: (next: string[][]) => void
  /** 기존 값에서 열을 가져오는 자리. 축에 따라 없을 수도 있다. */
  borrow?: ReactNode
}) {
  const columns = useMemo(
    () => columnsOf(fields, picked, hasParent),
    [fields, picked, hasParent]
  )
  const [focus, setFocus] = useState<[number, number]>([0, 0])
  /** 복사 결과. **눌렀는데 아무 일도 안 일어나면 됐는지 알 수 없다.** */
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  async function copy() {
    // 헤더까지 함께 — 엑셀에 붙이면 그대로 표가 되고, 채워서 다시 붙여넣으면
    // 열 이름이 맞는다.
    const ok = await copyText(toLines(columns, rows).join('\n'))
    setCopied(ok ? 'yes' : 'no')
    window.setTimeout(() => setCopied(null), ok ? 2000 : 8000)
  }

  function edit(row: number, column: number, value: string) {
    const next = rows.map((one) => [...one])
    while (next.length <= row) next.push(columns.map(() => ''))
    next[row][column] = value
    // 마지막 줄에 뭔가 적으면 빈 줄을 하나 더 둔다 — '줄 더하기' 를 누르러 가지
    // 않아도 계속 칠 수 있다.
    if (row === next.length - 1 && value.trim()) next.push(columns.map(() => ''))
    onRows(next)
  }

  /** 엑셀에서 복사한 범위를 **초점 칸부터** 채운다. */
  function paste(event: ClipboardEvent<HTMLInputElement>, row: number, column: number) {
    const text = event.clipboardData.getData('text/plain')
    if (!text.includes('\t') && !text.includes('\n')) return // 한 칸 붙여넣기는 그대로
    event.preventDefault()

    const pasted = text
      .replace(/\r/g, '')
      .split('\n')
      .filter((line, index, all) => line.trim() || index < all.length - 1)
      .map((line) => line.split('\t'))
    const next = rows.map((one) => [...one])
    pasted.forEach((cells, atRow) => {
      const target = row + atRow
      while (next.length <= target) next.push(columns.map(() => ''))
      cells.forEach((cell, atColumn) => {
        const index = column + atColumn
        if (index < columns.length) next[target][index] = cell.trim()
      })
    })
    if (next[next.length - 1].some((cell) => cell.trim())) next.push(columns.map(() => ''))
    onRows(next)
  }

  return (
    <div className="space-y-2">
      {/* **고를 수 있는 것을 먼저 보여 준다.** 이름을 알 방법이 없으면 헤더에
          무엇을 적으라는 말이 소용없다. */}
      {borrow}

      {fields.length > 0 && (
        <div className="space-y-1">
          <p className="text-muted-foreground text-xs">
            함께 넣을 속성을 고르세요. 분류가 주는 칸과, 가져온 칸입니다.
          </p>
          <div className="flex flex-wrap gap-1">
            {fields.map((field) => (
              <Button
                key={field.key}
                size="sm"
                variant={picked.has(field.key) ? 'default' : 'outline'}
                className="h-6 px-2 text-xs"
                title={field.help ?? undefined}
                onClick={() => {
                  const next = new Set(picked)
                  if (!next.delete(field.key)) next.add(field.key)
                  onPicked(next)
                }}
              >
                {headerOf(field)}
                {/* **이 칸은 새로 선언된다.** 분류가 주는 칸과 다르다 — 값을
                    넣으려면 그 규격이 그 칸을 갖게 되는 것이라, 그 사실이
                    보여야 한다. */}
                {!field.inherited && <span className="ml-1 opacity-60">＋</span>}
              </Button>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-xs">
          <thead className="bg-muted/40">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="px-1.5 py-1 text-left font-medium">
                  {column.header}
                  {column.fixed && column.key === '값' && (
                    <Badge variant="outline" className="ml-1 text-xs">
                      필수
                    </Badge>
                  )}
                </th>
              ))}
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, atRow) => (
              <tr key={atRow} className="border-t">
                {columns.map((column, atColumn) => (
                  <td key={column.key} className="p-0.5">
                    <Input
                      className="h-7 text-xs"
                      aria-label={`${atRow + 1}번 줄 ${column.header}`}
                      value={row[atColumn] ?? ''}
                      onFocus={() => setFocus([atRow, atColumn])}
                      onPaste={(event) => paste(event, atRow, atColumn)}
                      onChange={(event) => edit(atRow, atColumn, event.target.value)}
                    />
                  </td>
                ))}
                <td className="p-0.5">
                  {rows.length > 1 && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="size-6"
                      aria-label={`${atRow + 1}번 줄 빼기`}
                      onClick={() => onRows(rows.filter((_, at) => at !== atRow))}
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => onRows([...rows, columns.map(() => '')])}
        >
          <Plus className="size-3.5" />줄 더하기
        </Button>
        {/* **엑셀에서 채워 오는 길.** 빈 표라도 헤더가 복사되므로, 그것을 붙여
            놓고 채운 뒤 다시 가져오면 열 이름이 맞는다. */}
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => void copy()}>
          {copied === 'yes' ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied === 'yes' ? '복사했습니다' : '엑셀로 복사'}
        </Button>
        <span className="text-muted-foreground text-xs">
          엑셀에서 범위를 복사해 아무 칸에나 붙여넣으면 그 자리부터 채워집니다
          {focus[0] > 0 || focus[1] > 0 ? ` (지금 ${focus[0] + 1}번 줄)` : ''}.
        </span>
      </div>

      {/* **브라우저가 복사를 막는 자리가 있다.** HTTPS 가 아니면 클립보드 API 가
          아예 없다 — 그때는 글자를 내어 주고 직접 복사하게 한다. 버튼만 눌리고
          아무 일도 안 일어나는 것이 가장 나쁘다. */}
      {copied === 'no' && (
        <div className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/5 p-2.5">
          <p className="text-xs">
            브라우저가 복사를 막았습니다. 아래를 골라서 직접 복사하세요.
          </p>
          <textarea
            readOnly
            aria-label="복사할 표"
            className="border-input bg-background h-24 w-full rounded-md border p-1.5 font-mono text-xs"
            value={toLines(columns, rows).join('\n')}
            onFocus={(event) => event.currentTarget.select()}
          />
        </div>
      )}
    </div>
  )
}
