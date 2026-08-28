/**
 * 연도 × 사업부 시험 수 — **가로 누적 막대.**
 *
 * 한 해가 한 줄이고 사업부가 색 구간이라, 해마다 총량과 구성이 한 줄에서 같이
 * 읽힌다. 이 패널이 가로로 긴 자리라 세로 막대보다 이 방향이 맞다.
 *
 * ## 왜 따로 떨어져 있나
 *
 * recharts 가 무겁다. 홈 청크에 같이 넣었더니 **11.9kB → 381kB** 였다(실측).
 * **홈은 로그인 직후 첫 화면**이라 그 값을 첫 페인트에 물릴 이유가 없다 — 표는 즉시
 * 그리고 그래프(370kB)만 `lazy` 로 뒤따른다. 다른 화면이 같은 그래프를 쓰게 되면
 * 이 조각을 함께 받는다.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DivisionOverview } from '@/modules/statistics/api'
import { colorOf, yearRows } from '@/modules/statistics/divisionColors'

export default function DivisionYearChart({
  data,
  order,
}: {
  data: DivisionOverview
  order: string[]
}) {
  const rows = yearRows(data.yearly)
  if (rows.length === 0) {
    return <p className="text-muted-foreground self-center text-sm">아직 시험이 없습니다.</p>
  }
  const divisions = order.filter((division) => data.yearly.some((one) => one.division === division))

  return (
    <div>
      <div className="text-muted-foreground mb-1 text-xs">연간 시험 수</div>
      <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 44 + 64)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 32, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} strokeOpacity={0.4} />
          <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="year" width={44} tick={{ fontSize: 12 }} />
          <Tooltip
            formatter={(value, name) => [`${String(value)}건`, String(name)]}
            labelFormatter={(year) => `${String(year)}년`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {divisions.map((division, index) => (
            <Bar
              key={division}
              dataKey={division}
              stackId="year"
              fill={colorOf(division, order)}
              radius={index === divisions.length - 1 ? [0, 3, 3, 0] : undefined}
            >
              {/* 합계는 **마지막 구간에만** 붙인다 — 구간마다 붙이면 좁은 구간에서 겹친다. */}
              {index === divisions.length - 1 && (
                <LabelList
                  dataKey="합계"
                  position="right"
                  fontSize={11}
                  formatter={(value: unknown) => `${String(value)}건`}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
