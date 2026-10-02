/**
 * 사용 현황 — **실제로 얼마나 잘 쓰고 있나**(관리 → 사용 현황, 시스템 관리자).
 *
 * 한 장에서 답하는 물음:
 *
 *   누가 쓰나       기간 안에 쓴 사람 · 하루 평균 · 화면 / MCP(AI) / 둘 다
 *   AI 로 쓰나      MCP 도구 호출 · 도구별 · 사람별 · 실패 · 연결된 토큰
 *   무엇을 쓰나     기능별 조회 · 쓰기 · 많이 본 재료 · 문헌 재료 · 시험 · 카드 · 가이드
 *   들어오나        가입 · 승인 대기 · 로그인
 *   남기나          기간 안에 만든 재료 · 시료 · 시편 · 시험 · 카드 · 의뢰
 *
 * **숫자는 서버가 센다.** 여기서 다시 더하거나 나누지 않는다 — 화면이 셈을 들면 서버와 다른
 * 숫자를 보일 날이 온다.
 */

import {
  Activity,
  Bot,
  Eye,
  FilePlus2,
  KeyRound,
  LogIn,
  MousePointerClick,
  UserPlus,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ActiveUsersChart, RequestsChart } from '@/modules/usage/UsageCharts'
import { usageApi } from '@/modules/usage/api'
import type { UsageSummary, ViewedItem } from '@/modules/usage/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
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
import { stamp } from '@/shared/lib/datetime'

/** 고를 수 있는 기간(일). */
const PERIODS: { days: number; label: string }[] = [
  { days: 7, label: '7일' },
  { days: 30, label: '30일' },
  { days: 90, label: '90일' },
  { days: 365, label: '1년' },
]

const number = new Intl.NumberFormat('ko-KR')

function n(value: number): string {
  return number.format(value)
}

export default function UsagePage() {
  const [days, setDays] = useState(30)
  const summary = useResource(() => usageApi.summary(days), [days])
  const data = summary.data

  return (
    <div>
      <PageHeader
        title="사용 현황"
        description="실제로 얼마나 쓰고 있는지 — 사람 · 기능 · AI(MCP) · 가입. 사람마다의 사용량이 보이므로 시스템 관리자만 엽니다."
        actions={
          <div className="flex gap-1" role="group" aria-label="기간">
            {PERIODS.map((one) => (
              <Button
                key={one.days}
                size="sm"
                variant={one.days === days ? 'default' : 'outline'}
                aria-pressed={one.days === days}
                onClick={() => setDays(one.days)}
              >
                {one.label}
              </Button>
            ))}
          </div>
        }
      />

      <ErrorNotice error={summary.error} className="mb-4" />
      {data ? <Summary data={data} /> : null}
    </div>
  )
}

function Summary({ data }: { data: UsageSummary }) {
  const { activity, mcp, requests, users, views } = data
  // **집계가 쌓이기 전 날짜는 0 으로 보인다.** 안 쓴 것이 아니라 안 센 것이다 — 그렇다고 말한다.
  const partial = data.measured_since === null || data.measured_since > data.period.start

  return (
    <div className="space-y-6">
      <p className="text-muted-foreground text-sm">
        {data.period.start} ~ {data.period.end} ({data.period.days}일)
      </p>
      {partial && (
        <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
          {data.measured_since
            ? `요청 · 조회 · MCP 도구 집계는 ${data.measured_since} 부터 쌓였습니다.`
            : '요청 · 조회 · MCP 도구 집계가 아직 쌓이지 않았습니다.'}{' '}
          그 전 날짜의 0 은 안 쓴 것이 아니라 안 센 것입니다. 가입 · 로그인 · 만든 자료 · AI 경유 기록은
          원래 기록에서 세므로 기간 전체가 맞습니다.
        </p>
      )}

      <section aria-label="요약" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          icon={Activity}
          label="쓴 사람"
          value={`${n(activity.any_users)}명`}
          detail={`화면 ${n(activity.web_users)} · MCP ${n(activity.mcp_users)} · 둘 다 ${n(activity.both_users)} · 하루 평균 ${activity.average_daily}`}
        />
        <Stat
          icon={Bot}
          label="MCP 도구 호출"
          value={`${n(mcp.calls)}건`}
          detail={`${n(mcp.users)}명 · 도구 ${n(mcp.tools_used)}가지 · 실패 ${n(mcp.failures)} · 평균 ${mcp.average_ms} ms`}
        />
        <Stat
          icon={MousePointerClick}
          label="요청"
          value={`${n(requests.total)}건`}
          detail={`조회 ${n(requests.reads)} · 쓰기 ${n(requests.writes)} · 오류 ${n(requests.errors)}`}
        />
        <Stat
          icon={Eye}
          label="상세 조회"
          value={`${n(views.total)}회`}
          detail="재료 · 문헌 재료 · 시험 · 카드 · 가이드"
        />
        <Stat
          icon={UserPlus}
          label="가입"
          value={`${n(users.signups)}명`}
          detail={`승인 대기 ${n(users.pending)} · 활성 계정 ${n(users.active_accounts)}`}
        />
        <Stat
          icon={LogIn}
          label="로그인"
          value={`${n(activity.logins)}회`}
          detail={`${n(activity.login_users)}명`}
        />
        <Stat
          icon={KeyRound}
          label="MCP · 연동 토큰"
          value={`${n(mcp.tokens.users)}명`}
          detail={`쓸 수 있는 토큰 ${n(mcp.tokens.active)} · 기간 중 쓰인 것 ${n(mcp.tokens.used_in_period)}`}
        />
        <Stat
          icon={FilePlus2}
          label="AI 경유 기록"
          value={`${n(mcp.writes_recorded)}건`}
          detail="MCP 로 들어와 변경 이력에 남은 쓰기"
        />
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <ActiveUsersChart data={data} />
        <RequestsChart data={data} />
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <Block title="MCP 도구별" empty={mcp.by_tool.length === 0} emptyText="기간 안에 불린 도구가 없습니다.">
          <Table aria-label="MCP 도구별">
            <TableHeader>
              <TableRow>
                <TableHead>도구</TableHead>
                <TableHead className="text-right">호출</TableHead>
                <TableHead className="text-right">실패</TableHead>
                <TableHead className="text-right">사람</TableHead>
                <TableHead className="text-right">평균 ms</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mcp.by_tool.map((one) => (
                <TableRow key={one.tool}>
                  <TableCell className="font-mono">{one.tool}</TableCell>
                  <TableCell className="text-right">{n(one.calls)}</TableCell>
                  <TableCell className="text-right">{n(one.failures)}</TableCell>
                  <TableCell className="text-right">{n(one.users)}</TableCell>
                  <TableCell className="text-right">{one.average_ms}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Block>

        <Block title="MCP 사용자별" empty={mcp.by_user.length === 0} emptyText="기간 안에 MCP 로 쓴 사람이 없습니다.">
          <Table aria-label="MCP 사용자별">
            <TableHeader>
              <TableRow>
                <TableHead>사람</TableHead>
                <TableHead className="text-right">호출</TableHead>
                <TableHead className="text-right">쓴 도구</TableHead>
                <TableHead>마지막</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mcp.by_user.map((one) => (
                <TableRow key={one.name}>
                  <TableCell>{one.name}</TableCell>
                  <TableCell className="text-right">{n(one.calls)}</TableCell>
                  <TableCell className="text-right">{n(one.tools)}</TableCell>
                  <TableCell>{one.last_day}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Block>
      </section>

      <Block title="기능별 사용" empty={requests.by_area.length === 0} emptyText="기간 안의 요청이 없습니다.">
        <Table aria-label="기능별 사용">
          <TableHeader>
            <TableRow>
              <TableHead>기능</TableHead>
              <TableHead className="text-right">조회</TableHead>
              <TableHead className="text-right">쓰기</TableHead>
              <TableHead className="text-right">그중 MCP</TableHead>
              <TableHead className="text-right">오류</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.by_area.map((one) => (
              <TableRow key={one.area}>
                <TableCell>{one.label}</TableCell>
                <TableCell className="text-right">{n(one.reads)}</TableCell>
                <TableCell className="text-right">{n(one.writes)}</TableCell>
                <TableCell className="text-right">{n(one.mcp)}</TableCell>
                <TableCell className="text-right">{n(one.errors)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Block>

      <Block title="사람별 활동" empty={data.people.length === 0} emptyText="기간 안에 쓴 사람이 없습니다.">
        <Table aria-label="사람별 활동">
          <TableHeader>
            <TableRow>
              <TableHead>사람</TableHead>
              <TableHead>부서</TableHead>
              <TableHead>마지막</TableHead>
              <TableHead className="text-right">활동일</TableHead>
              <TableHead className="text-right">화면 요청</TableHead>
              <TableHead className="text-right">쓰기</TableHead>
              <TableHead className="text-right">MCP 호출</TableHead>
              <TableHead className="text-right">상세 조회</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.people.map((one) => (
              <TableRow key={one.user_id}>
                <TableCell title={one.email ?? undefined}>{one.name}</TableCell>
                <TableCell>{one.workspace ?? '—'}</TableCell>
                <TableCell>{one.last_day}</TableCell>
                <TableCell className="text-right">{n(one.active_days)}</TableCell>
                <TableCell className="text-right">{n(one.web_requests)}</TableCell>
                <TableCell className="text-right">{n(one.writes)}</TableCell>
                <TableCell className="text-right">{n(one.mcp_calls)}</TableCell>
                <TableCell className="text-right">{n(one.views)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Block>

      <section aria-label="많이 본 것" className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        <Viewed title="많이 본 재료" items={views.materials} href={(id) => `/materials/${id}`} />
        <Viewed title="많이 본 문헌 재료" items={views.catalog_materials} href={(id) => `/catalog/${id}`} />
        <Viewed title="많이 본 시험" items={views.test_runs} href={(id) => `/test-runs/${id}`} />
        <Viewed title="많이 본 카드" items={views.cards} />
        <Viewed title="많이 본 가이드" items={views.guides} href={(key) => `/guide/${key}`} />
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <Block
          title="기간 안에 가입한 사람"
          empty={users.recent_signups.length === 0}
          emptyText="기간 안에 가입한 사람이 없습니다."
          actions={
            users.pending > 0 ? (
              <Link to="/admin/accounts" className="text-primary text-sm underline-offset-2 hover:underline">
                승인 대기 {n(users.pending)}명 — 계정 관리로
              </Link>
            ) : null
          }
        >
          <Table aria-label="최근 가입">
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>부서</TableHead>
                <TableHead>상태</TableHead>
                <TableHead>가입</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.recent_signups.map((one) => (
                <TableRow key={one.email}>
                  <TableCell title={one.email}>{one.name}</TableCell>
                  <TableCell>{one.workspace ?? '—'}</TableCell>
                  <TableCell>
                    <StatusBadge status={one.status} />
                  </TableCell>
                  <TableCell>{stamp(one.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Block>

        <Block title="기간 안에 만든 자료" empty={false} emptyText="">
          <Table aria-label="만든 자료">
            <TableHeader>
              <TableRow>
                <TableHead>자료</TableHead>
                <TableHead className="text-right">만든 수</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.content.map((one) => (
                <TableRow key={one.key}>
                  <TableCell>{one.label}</TableCell>
                  <TableCell className="text-right">{n(one.created)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Block>
      </section>
    </div>
  )
}

function Stat({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  detail: string
}) {
  return (
    <div className="rounded-md border p-3" aria-label={label}>
      <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <Icon className="size-3.5" />
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      <div className="text-muted-foreground mt-0.5 text-xs">{detail}</div>
    </div>
  )
}

function Block({
  title,
  empty,
  emptyText,
  actions,
  children,
}: {
  title: string
  empty: boolean
  emptyText: string
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section aria-label={title} className="rounded-md border">
      <header className="flex items-center gap-2 border-b p-3">
        <h3 className="font-medium">{title}</h3>
        {actions ? <div className="ml-auto">{actions}</div> : null}
      </header>
      {empty ? <p className="text-muted-foreground p-4 text-sm">{emptyText}</p> : children}
    </section>
  )
}

function Viewed({
  title,
  items,
  href,
}: {
  title: string
  items: ViewedItem[]
  href?: (id: string) => string
}) {
  return (
    <Block title={title} empty={items.length === 0} emptyText="기간 안의 조회가 없습니다.">
      <Table aria-label={title}>
        <TableHeader>
          <TableRow>
            <TableHead>항목</TableHead>
            <TableHead className="text-right">조회</TableHead>
            <TableHead className="text-right">사람</TableHead>
            <TableHead className="text-right">MCP</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((one) => (
            <TableRow key={one.id}>
              <TableCell>
                {href ? (
                  <Link to={href(one.id)} className="underline-offset-2 hover:underline">
                    {one.label}
                  </Link>
                ) : (
                  one.label
                )}
              </TableCell>
              <TableCell className="text-right">{n(one.views)}</TableCell>
              <TableCell className="text-right">{n(one.viewers)}</TableCell>
              <TableCell className="text-right">{n(one.mcp_views)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Block>
  )
}
