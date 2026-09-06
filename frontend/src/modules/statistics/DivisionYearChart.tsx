/**
 * 연도 × 사업부 시험 수 — **세로 누적 막대, 높이 고정.**
 *
 * 한 해가 한 막대이고 사업부가 색 구간이라, 해마다 총량과 구성이 한 막대에서 같이
 * 읽힌다. 연도는 시간축이라 가로(X)에 둔다 — 해가 늘면 막대가 가늘어질 뿐 화면은
 * 안 늘어난다.
 *
 * ## 왜 뒤집었나 (2026-09-05)
 *
 * 전에는 한 해가 한 **줄**인 가로 막대였고 높이가 `해 수 × 44px` 로 늘어났다.
 * 7년이면 370px, 10년이면 500px — 잘리지는 않지만 옆 표와 키가 안 맞고 홈이
 * 길어진다. 홈은 현황판이라 옛날 해를 늘 볼 이유도 없다. 그래서 (1) 세로로 뒤집어
 * 높이를 고정하고, (2) 해가 많으면 최근 여섯 해만 펼치고 그 앞은 「~2019」 한
 * 묶음으로 접는다(`foldYears`). 「전체 보기」 로 펼친다.
 *
 * ## 왜 따로 떨어져 있나
 *
 * recharts 가 무겁다. 홈 청크에 같이 넣었더니 **11.9kB → 381kB** 였다(실측).
 * **홈은 로그인 직후 첫 화면**이라 그 값을 첫 페인트에 물릴 이유가 없다 — 표는 즉시
 * 그리고 그래프(370kB)만 `lazy` 로 뒤따른다. 다른 화면이 같은 그래프를 쓰게 되면
 * 이 조각을 함께 받는다.
 */

import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DivisionOverview } from '@/modules/statistics/api'
import {
  RECENT_YEARS,
  colorOf,
  divisionRank,
  foldYears,
  yearRows,
} from '@/modules/statistics/divisionColors'

/** 옆 표(사업부 5~6줄)와 키를 맞춘 값. 해가 늘어도 이 높이다. */
const HEIGHT = 220

export default function DivisionYearChart({
  data,
  order,
}: {
  data: DivisionOverview
  order: string[]
}) {
  const all = yearRows(data.yearly)
  const [expanded, setExpanded] = useState(false)
  if (all.length === 0) {
    return <p className="text-muted-foreground self-center text-sm">아직 시험이 없습니다.</p>
  }
  const folded = foldYears(all)
  const foldable = folded.length < all.length
  const rows = expanded ? all : folded
  const divisions = order.filter((division) => data.yearly.some((one) => one.division === division))

  return (
    <div>
      <div className="mb-1 flex items-baseline gap-2">
        <span className="text-muted-foreground text-xs">연간 시험 수</span>
        {foldable && (
          // **접었다는 사실을 말한다.** 그래프만 보면 「~2019」 가 한 해로 읽힌다.
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground ml-auto text-xs underline-offset-2 hover:underline"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? `최근 ${RECENT_YEARS}년만` : `전체 보기 (${all.length}년)`}
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={HEIGHT}>
        <BarChart data={rows} margin={{ top: 16, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} strokeOpacity={0.4} />
          <XAxis dataKey="year" tick={{ fontSize: 11 }} interval={0} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
          {/* **툴팁 안의 차례도 맞춘다.** recharts 는 누적 순서로 담아 주는데,
              표·범례와 다르면 같은 다섯 값이 세 가지 차례로 서게 된다.
              `zIndex` 는 범례에 가리지 않게. */}
          <Tooltip
            wrapperStyle={{ zIndex: 50 }}
            cursor={{ fillOpacity: 0.08 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <div className="bg-background rounded-md border px-2.5 py-1.5 text-xs shadow-md">
                  <div className="mb-1 font-medium">
                    {String(label).startsWith('~') ? `${String(label).slice(1)}년까지` : `${String(label)}년`}
                  </div>
                  {[...payload]
                    .sort((a, b) => {
                      const [ai, an] = divisionRank(String(a.name))
                      const [bi, bn] = divisionRank(String(b.name))
                      return ai - bi || an.localeCompare(bn)
                    })
                    .map((one) => (
                      <div key={String(one.name)} className="flex items-center gap-1.5">
                        <span
                          className="inline-block size-2 rounded-full"
                          style={{ backgroundColor: one.color }}
                        />
                        <span className="text-muted-foreground">{String(one.name)}</span>
                        <span className="ml-auto tabular-nums">{String(one.value)}건</span>
                      </div>
                    ))}
                </div>
              ) : null
            }
          />
          {divisions.map((division, index) => (
            <Bar
              key={division}
              dataKey={division}
              stackId="year"
              fill={colorOf(division, order)}
              radius={index === divisions.length - 1 ? [3, 3, 0, 0] : undefined}
            >
              {/* 합계는 **마지막 구간에만** 붙인다 — 구간마다 붙이면 좁은 구간에서 겹친다. */}
              {index === divisions.length - 1 && (
                <LabelList dataKey="합계" position="top" fontSize={11} />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
      {/* **범례는 직접 그린다.** recharts 3 은 Legend 의 `payload` 를 없앴고, 맡기면
          누적 순서(아래에서 위로)로 뒤집혀 선다 — 그러면 표와 순서가 어긋나고,
          사람은 색을 표에서 그래프로 옮겨 읽을 수 없다. */}
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {divisions.map((division) => (
          <span key={division} className="text-muted-foreground inline-flex items-center gap-1">
            <span
              className="inline-block size-2 rounded-full"
              style={{ backgroundColor: colorOf(division, order) }}
            />
            {division}
          </span>
        ))}
      </div>
    </div>
  )
}
