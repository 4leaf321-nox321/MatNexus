/**
 * 파일의 표를 **그 파일 그대로** 보여 준다.
 *
 * 「N행 × M열」 만으로는 어느 표가 자기가 찾는 것인지 알 수 없다. 특히 한 파일에
 * 표가 여섯 벌 들어 있는 장비(TA DMA850 의 `[step]` 마다 별개 측정)에서는
 * 이름도 비슷해서 눈으로 못 가른다.
 *
 * **값을 눈으로 보는 것 자체가 근거다.** 자동 감지는 인코딩이 이중으로 깨진
 * 파일도 '성공' 시킨다(실측) — 숫자는 멀쩡하고 글자만 깨지므로, 표를 직접
 * 보지 않으면 알 수 없다.
 *
 * 단위 글자를 손으로 적지 않는다. 전부 응답의 `units`·`unit_symbols` 에서 읽는다.
 */

import type { TablePreview } from '@/modules/tests/api'

export function TablePreviewRows({ table }: { table: TablePreview }) {
  const hasUnits = table.units.length > 0
  return (
    <div>
      {/* 표가 넓으면 **이 안에서만** 옆으로 굴린다. 페이지가 옆으로 굴러가면
          왼쪽 칸의 다른 구역까지 따라 밀린다. */}
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-xs">
          <thead className="bg-muted/50">
            <tr>
              {table.header.map((name, index) => (
                <th key={index} className="px-2 py-1 text-left font-medium whitespace-nowrap">
                  {name || <span className="text-muted-foreground">(이름 없음)</span>}
                </th>
              ))}
            </tr>
            {hasUnits && (
              <tr className="text-muted-foreground">
                {table.header.map((_, index) => {
                  const raw = table.units[index] ?? ''
                  const symbol = table.unit_symbols[index]
                  return (
                    <th
                      key={index}
                      className="px-2 py-1 text-left font-mono font-normal whitespace-nowrap"
                    >
                      {/* 서버가 표기를 바꿔 읽었으면 그 사실을 보인다 — `°C → degC`. */}
                      {raw.trim() === '' ? (
                        <span className="text-amber-700 dark:text-amber-500">빈 칸</span>
                      ) : symbol && symbol !== raw.trim() ? (
                        `${raw} → ${symbol}`
                      ) : symbol ? (
                        raw
                      ) : (
                        <span className="text-amber-700 dark:text-amber-500">{raw} ?</span>
                      )}
                    </th>
                  )
                })}
              </tr>
            )}
          </thead>
          <tbody>
            {table.sample_rows.map((row, index) => (
              <tr key={index} className="border-t">
                {table.header.map((_, cell) => (
                  // 행이 헤더보다 짧을 수 있다. 서버도 읽을 때 같은 가드를 한다.
                  <td key={cell} className="px-2 py-1 font-mono whitespace-nowrap">
                    {row[cell] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">
        앞 {table.sample_rows.length}행만 보입니다 (전체 {table.row_count}행 ×{' '}
        {table.column_count}열 · 파일 {table.first_line}줄부터).
        {!hasUnits && ' 이 파일에는 단위 줄이 없습니다 — ④ 에서 단위를 지정해야 읽힙니다.'}
      </p>
    </div>
  )
}
