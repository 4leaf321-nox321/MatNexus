/**
 * 부서 홈 — **여기서 무엇을 어디서 하는지 말한다.**
 *
 * 이 자리가 여태 「구현 예정: Phase 1」 공사 표지판이었다. 로그인하면 맨 처음
 * 뜨는 화면이 그것이라, 사이드바에 메뉴가 스무 개 넘게 있어도 **어디부터
 * 눌러야 하는지 알 방법이 없었다.**
 *
 * 그래서 이 화면은 목록이 아니라 **순서**다. 파일 → 처리 → 물성 → 카드가 이
 * 시스템이 하는 일의 전부이고, 네 칸이 각 단계로 들어가는 문이다. 숫자는
 * "지금 우리 부서가 어디까지 와 있나" 다 — 할 일이 남은 칸은 스스로 눈에
 * 띈다.
 *
 * **숫자는 서버가 센다.** 목록을 받아 화면이 세면 상한에 걸린 순간 조용히
 * 틀린다(`adopted` 필터를 그래서 더했다).
 */

import { ArrowRight, FileUp, Layers, PackageCheck, SlidersHorizontal } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import { RUN_STATUS_LABEL, testsApi } from '@/modules/tests/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { workspacesApi } from '@/modules/workspaces/api'
import { CopyId } from '@/shared/components/CopyId'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'
import { statisticsApi } from '@/modules/statistics/api'
import { DivisionPanel } from '@/modules/statistics/DivisionPanel'
import { OverviewPanel } from '@/modules/statistics/OverviewPanel'
import { useResource } from '@/shared/hooks/useResource'

/** 최근 목록에 몇 건. 훑어보는 자리라 한 화면을 넘기지 않는다. */
const RECENT = 8

interface StepProps {
  index: number
  icon: LucideIcon
  title: string
  detail: string
  to: string
  action: string
  count?: { value: number; unit: string; loud?: boolean }
  loading: boolean
}

function Step({ index, icon: Icon, title, detail, to, action, count, loading }: StepProps) {
  return (
    <Link
      to={to}
      className="hover:border-primary/50 hover:bg-accent/40 group flex flex-col rounded-md border p-4 transition-colors"
    >
      <div className="flex items-center gap-2">
        <span className="bg-muted text-muted-foreground flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-medium">
          {index}
        </span>
        <Icon className="text-muted-foreground size-4 shrink-0" />
        <span className="font-medium">{title}</span>
      </div>

      <p className="text-muted-foreground mt-2 flex-1 text-sm">{detail}</p>

      <div className="mt-3 flex items-baseline justify-between gap-2">
        {loading ? (
          <Skeleton className="h-6 w-16" />
        ) : count ? (
          <span className={count.loud ? 'text-destructive font-semibold' : 'font-semibold'}>
            {count.value.toLocaleString()}
            <span className="text-muted-foreground ml-1 text-xs font-normal">{count.unit}</span>
          </span>
        ) : (
          <span />
        )}
        <span className="text-muted-foreground group-hover:text-foreground flex items-center gap-1 text-xs">
          {action}
          <ArrowRight className="size-3" />
        </span>
      </div>
    </Link>
  )
}

export default function WorkspaceHomePage() {
  const { slug } = useParams<{ slug?: string }>()
  const workspaceSlug = slug ?? DEFAULT_WORKSPACE
  const { user } = useAuth()
  const here = user?.memberships.find((item) => item.slug === workspaceSlug)

  // 최근 목록과 총 건수를 한 번에 받는다(`total` 이 함께 온다).
  const recent = useResource(
    () => testsApi.runs({ workspace: workspaceSlug, limit: RECENT }),
    [workspaceSlug]
  )
  // **읽힌 것 중 아직 아무것도 안 한 것.** 이것이 2단계에 남은 일이다.
  const waiting = useResource(
    () => testsApi.runs({ workspace: workspaceSlug, status: 'parsed', adopted: false, limit: 1 }),
    [workspaceSlug]
  )
  const failed = useResource(
    () => testsApi.runs({ workspace: workspaceSlug, status: 'failed', limit: 1 }),
    [workspaceSlug]
  )
  // 재료는 **전사 카탈로그**다. 부서로 안 좁히는 것이 맞다 — 남의 부서가 잰
  // 물성도 보라고 만든 자리다.
  const materials = useResource(() => materialsApi.list({ limit: 1 }), [])
  // **세는 일은 서버가 한다.** 재료 94개를 세려고 94행을 받을 이유가 없다.
  const summary = useResource(() => statisticsApi.overview(), [])
  // 부서 id — 장비 커넥터 마법사가 요구한다. 멤버십에는 slug 만 있어서 따로 읽는다.
  const details = useResource(() => workspacesApi.list(), [])
  const divisions = useResource(() => statisticsApi.divisions(), [])
  const workspaceId = details.data?.find((row) => row.slug === workspaceSlug)?.id

  const rows = recent.data?.items ?? []
  const loading = recent.loading || waiting.loading || failed.loading || materials.loading
  const failedCount = failed.data?.total ?? 0

  return (
    <div className="space-y-6">
      <div>
        {/* 시스템 관리자는 자기 소속이 아닌 부서도 연다 — 그때는 이름을 모르니
            slug 라도 적는다. '부서' 라고만 쓰면 어디에 있는지 알 수 없다. */}
        <h1 className="text-xl font-semibold">{here?.name ?? workspaceSlug}</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          {here?.path ? <span className="mr-1">{here.path} ·</span> : null}
          시험 파일이 물성이 되고, 물성이 솔버 카드가 됩니다.{' '}
          <strong>아래 순서대로 갑니다.</strong>
        </p>
        {workspaceId && (
          <p className="text-muted-foreground mt-1 text-xs">
            부서 ID <CopyId value={workspaceId} label="부서 ID" />
          </p>
        )}
      </div>

      <ErrorNotice error={recent.error ?? materials.error ?? summary.error} />

      {/* **매일 오는 사람에게는 안내가 아니라 현황이 필요하다.** 아래 4단계는
          한 번 읽으면 끝인데 자리는 계속 차지한다 — 요약을 그 위에 둔다. */}
      <OverviewPanel
        data={summary.data ?? null}
        loading={summary.loading}
        workspaceSlug={workspaceSlug}
      />

      <DivisionPanel data={divisions.data ?? null} loading={divisions.loading} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Step
          index={1}
          icon={FileUp}
          title="업로드"
          detail="장비 파일을 그대로 올립니다. 어떻게 읽을지는 부서가 정한 「파일 형식」이 압니다 — 손으로 옮겨 적지 않습니다."
          to={`/w/${workspaceSlug}/tests/upload`}
          action="파일 올리기"
          count={{ value: recent.data?.total ?? 0, unit: '건 등록됨' }}
          loading={loading}
        />
        <Step
          index={2}
          icon={SlidersHorizontal}
          title="처리"
          detail="원본 곡선을 다듬고(단위·토우 보정·평활) 어느 결과를 쓸지 채택합니다. 채택한 것만 물성으로 올라갑니다."
          to={`/w/${workspaceSlug}/tests`}
          action="시험 데이터"
          count={{
            value: waiting.data?.total ?? 0,
            unit: '건 처리 대기',
            loud: (waiting.data?.total ?? 0) > 0,
          }}
          loading={loading}
        />
        <Step
          index={3}
          icon={Layers}
          title="물성 조회"
          detail="같은 재료·시험 종류·방향의 시편을 묶어 대표 곡선과 물성을 냅니다. 재료 상세의 「물성」 탭입니다."
          to="/materials"
          action="재료"
          count={{ value: materials.data?.total ?? 0, unit: '개 재료' }}
          loading={loading}
        />
        <Step
          index={4}
          icon={PackageCheck}
          title="카드 내보내기"
          detail="재료 상세의 「CAE 카드」 탭에서 Abaqus·OpenRadioss 덱으로 내려받습니다. 무엇을 가정했는지가 덱 주석에 함께 적힙니다."
          to="/materials"
          action="재료 상세 → CAE 카드"
          loading={loading}
        />
      </div>

      {/* **못 읽은 파일은 조용히 두면 없는 데이터가 된다.** 올린 사람은 올렸다고
          믿고 있다 — 목록에 들어가 봐야만 알 수 있으면 안 본다. */}
      {failedCount > 0 && (
        <Link
          to={`/w/${workspaceSlug}/tests`}
          className="border-destructive/40 bg-destructive/5 text-destructive flex items-center gap-2 rounded-md border p-3 text-sm"
        >
          <strong>읽지 못한 파일 {failedCount}건.</strong>
          <span className="opacity-80">
            형식이 안 맞거나 파일이 상했습니다. 시험 데이터 목록에서 이유를 볼 수 있습니다.
          </span>
          <ArrowRight className="ml-auto size-4 shrink-0" />
        </Link>
      )}

      <div>
        <div className="mb-2 flex items-baseline gap-2">
          <h2 className="font-medium">최근 올라온 시험</h2>
          <Link
            to={`/w/${workspaceSlug}/tests`}
            className="text-muted-foreground hover:text-foreground ml-auto text-xs"
          >
            전부 보기
          </Link>
        </div>

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-10 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          // **첫 화면이 빈 표면 시작을 못 한다.** 무엇을 하면 되는지 적는다.
          <p className="text-muted-foreground rounded-md border p-6 text-center text-sm">
            아직 올라온 시험이 없습니다. 위 1번에서 장비 파일을 올리면 여기에 쌓입니다.
          </p>
        ) : (
          <ul className="divide-y rounded-md border">
            {rows.map((run) => (
              <li key={run.id}>
                <Link
                  to={`/test-runs/${run.id}`}
                  className="hover:bg-accent/40 flex items-center gap-3 px-3 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate font-medium">{run.record_name}</span>
                  <span className="text-muted-foreground hidden shrink-0 sm:inline">
                    {run.test_type_label}
                  </span>
                  <span className="text-muted-foreground hidden min-w-0 max-w-48 shrink truncate md:inline">
                    {run.material_name ?? '—'}
                  </span>
                  <Badge
                    variant={
                      run.status === 'failed'
                        ? 'destructive'
                        : run.status === 'parsed'
                          ? 'secondary'
                          : 'outline'
                    }
                    className="shrink-0"
                  >
                    {RUN_STATUS_LABEL[run.status] ?? run.status}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
