/**
 * 표로 붙여넣기 — **엑셀과 오가는 자리.**
 *
 * 빈 칸에 줄을 붙여넣게 하면 **무엇을 적어야 하는지 알 방법이 없다.** 열이 몇
 * 개인지, 어떤 이름인지, 숫자에 단위를 붙여야 하는지 — 그 전부를 안내 문구로
 * 설명하는 것보다 표로 보여 주는 편이 짧다.
 *
 * ## 표는 껍데기다
 *
 * 서버로 갈 때는 **탭으로 갈린 줄 + 헤더 한 줄**이 된다. 표는 사람이 보기
 * 좋으라고 있는 것이지 새 형식이 아니다 — 형식이 둘이 되면 두 곳이 갈라진다.
 *
 * ## 왜 shared 에 있는가
 *
 * 기준정보(값·상위·표기·속성)와 시험 요약표(시편·조건·요약값)가 같은 장치를
 * 쓴다. 모듈끼리 직접 부르지 않는다는 규칙 때문이기도 하지만, 애초에 이 파일에는
 * 도메인이 없다 — 열 이름과 줄만 안다.
 */

import { useState } from 'react'
import type { ClipboardEvent, ReactNode } from 'react'
import { Check, Copy, Plus, Trash2 } from 'lucide-react'

import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { copyText } from '@/shared/clipboard'

/** 표의 한 열. `header` 가 곧 서버로 가는 글자다. */
export interface Column {
  key: string
  header: string
  help?: string | null
}

/** 표를 서버가 받는 모양으로. **헤더 한 줄 + 탭으로 갈린 줄들.** */
export function toLines(columns: Column[], rows: string[][]): string[] {
  return [
    columns.map((column) => column.header).join('\t'),
    ...rows
      // 다 빈 줄은 안 보낸다 — 표에는 늘 빈 줄이 하나 남아 있다.
      .filter((row) => row.some((cell) => cell.trim()))
      .map((row) => row.join('\t')),
  ]
}

export function PasteGrid({
  columns,
  rows,
  onRows,
  header,
  required,
}: {
  columns: Column[]
  rows: string[][]
  onRows: (next: string[][]) => void
  /** 표 위에 둘 것 — 열 고르기 같은 것. 무엇을 두는지는 쓰는 쪽이 정한다. */
  header?: ReactNode
  /** 이 열이 비면 그 줄은 안 나간다. 표 머리에 '필수' 로 보인다. */
  required?: string
}) {
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
      {header}

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-xs">
          <thead className="bg-muted/40">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="px-1.5 py-1 text-left font-medium">
                  {column.header}
                  {column.key === required && (
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
