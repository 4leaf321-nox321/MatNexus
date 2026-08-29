/**
 * 서버 현황 — **디스크가 차기 전에 알아야 한다.**
 *
 * 폐쇄망에 설치해 두고 나면 그 PC 를 아무도 안 본다. 곡선 원본과 그림이 계속
 * 쌓이는데, 옆 탭의 「저장소 정리」 는 *우리가 쌓은 것*만 센다 — 같은 드라이브에
 * 다른 프로그램이 있으면 그 수는 답이 아니다. 여기가 그 나머지를 말한다.
 *
 * ## 무엇을 크게 보이나
 *
 * **남은 디스크가 맨 위다.** 나머지(CPU 모델·메모리·DB 버전)는 「무슨 컴퓨터인가」
 * 라 한 번 보면 되는 것이고, 디스크는 **매일 달라지고 차면 서비스가 선다.**
 *
 * ## 모르는 값은 「—」 로 적는다
 *
 * Windows 에는 load average 가 없다. 서버가 `null` 을 주면 화면도 없다고 말한다 —
 * 0 을 그리면 「한가하다」 로 읽힌다.
 */

import { AlertTriangle, Cpu, Database, HardDrive, MemoryStick, Server } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { serverApi } from '@/modules/server/api'
import type { Disk } from '@/modules/server/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { SubTabs } from '@/shared/components/SubTabs'
import { Badge } from '@/shared/components/ui/badge'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'
import { cn } from '@/shared/lib/utils'

/** 남은 공간이 이보다 적으면 붉게 적는다. **비율이 아니라 절대량이다** — 4TB 의 2%
 *  는 80GB 라 넉넉하지만, 500GB 의 2% 는 10GB 라 곧 선다. */
const TIGHT_BYTES = 20 * 1024 ** 3

export function bytes(value: number | null | undefined): string {
  if (value == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let size = value
  let step = 0
  while (size >= 1024 && step < units.length - 1) {
    size /= 1024
    step += 1
  }
  // GB 아래는 소수를 안 붙인다 — 「512.0 MB」 의 `.0` 은 아무것도 안 알려 준다.
  return `${size.toFixed(step >= 3 ? 1 : 0)} ${units[step]}`
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}일 ${hours}시간`
  if (hours > 0) return `${hours}시간 ${minutes}분`
  return `${minutes}분`
}

function Bar({ percent, tight }: { percent: number; tight: boolean }) {
  return (
    <div className="bg-muted h-2 w-full overflow-hidden rounded-full">
      <div
        className={cn('h-full rounded-full', tight ? 'bg-red-500' : 'bg-primary')}
        style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
      />
    </div>
  )
}

function Card({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon
  title: string
  children: ReactNode
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs font-medium">
        <Icon className="size-3.5" />
        {title}
      </div>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5 text-sm">
      <span className="text-muted-foreground shrink-0 text-xs">{label}</span>
      <span className="truncate text-right font-medium tabular-nums">{value}</span>
    </div>
  )
}

function DiskRow({ disk }: { disk: Disk }) {
  const tight = disk.free_bytes < TIGHT_BYTES
  return (
    <div className="space-y-1.5 rounded-md border p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium">{disk.label}</span>
        <span className={cn('text-sm tabular-nums', tight && 'font-semibold text-red-600')}>
          {bytes(disk.free_bytes)} 남음
        </span>
      </div>
      <Bar percent={disk.percent_used} tight={tight} />
      <div className="text-muted-foreground flex items-baseline justify-between gap-2 text-xs">
        {/* 경로를 적는다 — 어느 드라이브를 비워야 하는지가 이 줄에 있다. */}
        <span className="truncate font-mono" title={disk.path}>
          {disk.path}
        </span>
        <span className="shrink-0 tabular-nums">
          {bytes(disk.used_bytes)} / {bytes(disk.total_bytes)} · {disk.percent_used}%
        </span>
      </div>
    </div>
  )
}

/**
 * 머리글과 탭은 **불러오는 중에도 선다.** 로딩 동안 통째로 비우면 탭이 사라져,
 * 옆 화면으로 가려던 사람이 갈 데를 잃는다.
 */
export default function ServerPage() {
  return (
    <div>
      <PageHeader
        title="서버"
        description="이 프로그램이 설치된 컴퓨터의 형편입니다. 읽기만 합니다 — 여기서 서버를 만지지 않습니다."
      />
      {/* **저장소 정리는 서버의 한 면이다.** 「우리가 쌓은 것」 과 「드라이브에
          남은 것」 은 같은 질문의 두 쪽인데, 메뉴에 따로 서 있으면 디스크가 찰 때
          한쪽만 보고 「치울 게 없다」 고 결론 낸다. */}
      <SubTabs
        items={[
          { to: '/server', label: '서버 정보' },
          { to: '/admin/storage', label: '저장소 정리' },
        ]}
      />
      <Body />
    </div>
  )
}

function Body() {
  const server = useResource(() => serverApi.info(), [])
  const data = server.data

  if (server.loading && !data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    )
  }
  if (!data) return <ErrorNotice error={server.error} />

  const load = data.cpu.load_avg_1m
  const tight = data.disks.filter((disk) => disk.free_bytes < TIGHT_BYTES)

  return (
    <div className="space-y-4">
      <ErrorNotice error={server.error} />

      {/* **막힌 것부터.** 홈의 「남은 일」 과 같은 자리다 — 0 이면 줄이 사라진다. */}
      {tight.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm dark:border-red-900 dark:bg-red-950/40">
          <AlertTriangle className="size-4 shrink-0 text-red-600" />
          <span className="font-medium">디스크가 곧 찹니다</span>
          <span className="text-muted-foreground text-xs">
            {tight.map((disk) => `${disk.label} ${bytes(disk.free_bytes)}`).join(' · ')} 남음 —
            옆의 「저장소 정리」 에서 치울 것을 봅니다.
          </span>
        </div>
      )}

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs font-medium">디스크</p>
        {data.disks.map((disk) => (
          <DiskRow key={disk.path} disk={disk} />
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card icon={Server} title="호스트">
          <Row label="이름" value={data.host.hostname} />
          <Row label="OS" value={data.host.os} />
          <Row label="아키텍처" value={data.host.arch} />
          <Row label="켜진 지" value={duration(data.host.uptime_seconds)} />
        </Card>

        <Card icon={Cpu} title="CPU">
          <div className="mb-1 truncate text-sm font-medium" title={data.cpu.model}>
            {data.cpu.model}
          </div>
          <Row label="논리 코어" value={data.cpu.logical_cpus ?? '—'} />
          {/* Windows 에는 load average 가 없다. 없으면 그 줄을 아예 안 그린다 —
              「—」 만 셋 늘어놓으면 무엇이 고장 난 것처럼 보인다. */}
          {load != null && (
            <Row
              label="부하 (1·5·15분)"
              value={`${load} · ${data.cpu.load_avg_5m} · ${data.cpu.load_avg_15m}`}
            />
          )}
        </Card>

        <Card icon={MemoryStick} title="메모리">
          {data.memory.total_bytes == null ? (
            <p className="text-muted-foreground text-sm">읽지 못했습니다.</p>
          ) : (
            <>
              <Row
                label="사용"
                value={`${bytes(data.memory.used_bytes)} / ${bytes(data.memory.total_bytes)}`}
              />
              <div className="my-1.5">
                <Bar percent={data.memory.percent_used ?? 0} tight={false} />
              </div>
              <Row label="여유" value={bytes(data.memory.available_bytes)} />
            </>
          )}
        </Card>

        <Card icon={Database} title="데이터베이스">
          <Row label="PostgreSQL" value={data.database.version} />
          <Row label="크기" value={bytes(data.database.size_bytes)} />
          <Row
            label="연결 풀"
            value={
              // 풀 종류에 따라 없는 값이 있다. 있는 것만 적는다.
              data.database.pool.checkedout != null
                ? `${data.database.pool.checkedout} / ${data.database.pool.size ?? '—'} 사용 중`
                : '—'
            }
          />
        </Card>
      </div>

      <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span className="flex items-center gap-1">
          <HardDrive className="size-3" />
          앱 <Badge variant="secondary">{data.app_version}</Badge>
        </span>
        <span>Python {data.process.python_version}</span>
        <span>PID {data.process.pid}</span>
        <span>이 프로세스 {bytes(data.process.rss_bytes)}</span>
      </div>
    </div>
  )
}
