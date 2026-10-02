/**
 * 사용 현황의 그래프 둘 — 날마다 **쓴 사람**(화면 / MCP)과 **요청 · MCP 도구 호출**.
 *
 * 사람 수와 요청 수를 한 그래프에 두지 않는다 — 단위가 달라(명 · 건) 한쪽이 납작해진다.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { UsageSummary } from '@/modules/usage/api'

const HEIGHT = 220

/** `2026-10-02` → `10-02`. 축에 해를 적으면 칸이 모자란다(기간은 화면 위에 적혀 있다). */
function short(day: string): string {
  return day.slice(5)
}

export function ActiveUsersChart({ data }: { data: UsageSummary }) {
  return (
    <div aria-label="날마다 쓴 사람">
      <p className="text-muted-foreground mb-1 text-xs">날마다 쓴 사람(명) — 화면 · MCP</p>
      <ResponsiveContainer width="100%" height={HEIGHT}>
        <BarChart data={data.activity.by_day}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day" tickFormatter={short} fontSize={11} />
          <YAxis allowDecimals={false} fontSize={11} width={28} />
          <Tooltip />
          <Legend />
          <Bar dataKey="web" name="화면" stackId="users" fill="#3b82f6" />
          <Bar dataKey="mcp" name="MCP(AI)" stackId="users" fill="#10b981" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function RequestsChart({ data }: { data: UsageSummary }) {
  return (
    <div aria-label="날마다 요청과 MCP 도구 호출">
      <p className="text-muted-foreground mb-1 text-xs">날마다 요청 · MCP 도구 호출(건)</p>
      <ResponsiveContainer width="100%" height={HEIGHT}>
        <LineChart data={data.requests.by_day}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day" tickFormatter={short} fontSize={11} />
          <YAxis allowDecimals={false} fontSize={11} width={36} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="web" name="화면 요청" stroke="#3b82f6" dot={false} />
          <Line type="monotone" dataKey="mcp" name="MCP 요청" stroke="#10b981" dot={false} />
          <Line
            type="monotone"
            dataKey="mcp_tools"
            name="MCP 도구 호출"
            stroke="#f59e0b"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
