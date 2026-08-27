/**
 * 시험 상세 — 곡선, 장비 요약값, 원본.
 *
 * **장비가 계산한 값과 우리가 계산한 값을 나란히 둔다**(`source`). 지금은 장비
 * 값만 있지만, Phase 3 에서 우리 계산이 붙으면 같은 표에서 대조된다. 둘이 크게
 * 다르면 뭔가 잘못된 것이고, 섞어 두었다면 그 사실을 영영 모른다.
 *
 * 원본 내려받기와 다시 읽기를 여기 두는 이유: 파서가 못 읽었을 때 사람이 파일을
 * 열어 보고, 파서를 고친 뒤 다시 돌릴 수 있어야 한다. 그 경로가 없으면 실패한
 * 업로드는 서버 파일시스템을 직접 뒤지는 수밖에 없다.
 */

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ChevronDown, Download, RefreshCw, Trash2 } from 'lucide-react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { backTarget } from '@/modules/tests/backTarget'
import type { BackTarget } from '@/modules/tests/backTarget'

import { ProcessingPanel } from '@/modules/processing/ProcessingPanel'
import { ResultsPanel } from '@/modules/processing/ResultsPanel'
import { CurveChart } from '@/modules/tests/CurveChart'
import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import type { TestConditionField, TestRunDetail } from '@/modules/tests/api'
import {
  axisOptionsFor,
  groupCurveFamilies,
  memberLabel,
  resolveAxes,
} from '@/modules/tests/curves'
import { NOTABLE_DIFFERENCE, pairSummaries } from '@/modules/tests/summaries'
import { axisLabel, formatValue, toDisplay } from '@/shared/units'
import { useAuth } from '@/shared/auth/AuthContext'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { ViscoelasticPanel } from '@/modules/viscoelastic/ViscoelasticPanel'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'

export default function TestRunDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  // **목록이 넘겨 준 「왔던 자리」.** 없으면(주소를 직접 쳤거나 재료에서 왔다)
  // 아래에서 재료로 돌린다. 화면이 스스로 추측하지 않는다 — 시험 목록의 주소는
  // 부서 슬러그를 알아야 만들 수 있는데, 여기는 그것을 모른다.
  const from = (useLocation().state as { from?: BackTarget } | null)?.from
  const run = useResource(() => testsApi.run(id), [id])
  const types = useResource(() => testsApi.types(), [])
  const [axes, setAxes] = useState<{ x: string; y: string } | null>(null)
  const [action, setAction] = useState<Error | null>(null)
  const [removing, setRemoving] = useState(false)
  /** 이 시험 종류로 쓸 수 있는 형식들. **키를 외워서 치게 할 수는 없다.** */
  /**
   * 종류를 바꿀 수 있나. **아직 아무것도 안 나온 시험만** — 곡선이나 처리
   * 결과가 있으면 그것들이 무엇의 결과인지 알 수 없게 된다.
   *
   * 서버가 최종 판정을 한다(409). 여기서 감추는 것은 **눌러도 막히는 것을
   * 보여 주지 않으려는 것**뿐이다.
   */
  const retypable = (run.data?.curves?.length ?? 0) === 0 && !run.data?.adopted_result_id

  const formats = useResource(
    () => testsApi.formats(run.data?.test_type_key ?? undefined),
    [run.data?.test_type_key]
  )
  /** 다시 읽기가 무엇으로 걸렸는지. **말 안 하면 눌렸는지도 모른다.** */
  const [notice, setNotice] = useState<string | null>(null)

  const { user } = useAuth()
  /** 관리자인 부서만. 아닌 부서 것으로 레시피를 만들면 서버가 거절한다. */
  const managed = (user?.memberships ?? [])
    .filter((membership) => membership.role === 'manager')
    .map((membership) => ({ slug: membership.slug, name: membership.name }))

  const item = run.data
  /** 장비 값과 우리 값을 같은 줄에. 짝이 있는 것이 위로 온다. */
  const pairs = useMemo(() => pairSummaries(item?.summary ?? []), [item?.summary])
  const pending = item ? isPending(item.status) : false

  // 읽는 중이면 스스로 따라간다 — 올린 직후 이 화면으로 오는 경우가 흔하다.
  useEffect(() => {
    if (!pending) return
    const timer = setInterval(() => run.reload(), 3000)
    return () => clearInterval(timer)
  }, [pending, run])

  const definition = useMemo(
    () => (types.data ?? []).find((t) => t.key === item?.test_type_key),
    [types.data, item?.test_type_key],
  )
  // `?? []` 를 그대로 두면 매 렌더마다 새 배열이라 아래 useEffect 가 계속 돈다.
  const channels = useMemo(() => definition?.channels ?? [], [definition])

  /**
   * 점탄성 탭을 보여 줄지. **시험 종류 키를 박지 않는다.**
   *
   * `test_type_key === 'dma_sweep'` 으로 두면 부서가 자기 DMA 종류를 만드는
   * 순간(D7 — 정의는 데이터다) 그 시험에는 탭이 안 뜬다. 대신 **저장·손실
   * 탄성률 채널이 있는가**를 본다 — 그 둘이 있으면 겹치고 맞출 수 있다.
   */
  const isViscoelastic = useMemo(() => {
    const keys = new Set(channels.map((channel) => channel.key))
    return keys.has('storage_modulus') && keys.has('loss_modulus')
  }, [channels])

  /**
   * 어느 곡선을 볼 것인가. **한 시험이 곡선을 여럿 가진다.**
   *
   * TA DMA850 주파수-온도 스윕은 `[step]` 마다 별개 측정이라 곡선이 6벌 나온다.
   * 고를 수 없던 때는 저장은 다 돼 있는데 **화면에서 하나도 안 보였다** — 목록·
   * 상세·차트가 전부 `raw` 키만 찾았고, 표가 여럿인 파일에는 그 키가 없다.
   */
  const curves = useMemo(() => item?.curves ?? [], [item])

  // 묶고 고르는 규칙은 `curves.ts` 에 있다 — 화면 안에 있으면 시험할 수 없고,
  // 시험할 수 없으면 같은 결함이 반복된다(실제로 두 번 났다).
  const families = useMemo(() => groupCurveFamilies(curves), [curves])

  const [familyName, setFamilyName] = useState<string | null>(null)
  const activeFamily = families.find((f) => f.name === familyName) ?? families[0] ?? null

  const [curveKey, setCurveKey] = useState<string | null>(null)
  const activeCurve =
    activeFamily?.items.find((c) => c.key === curveKey) ?? activeFamily?.items[0] ?? null

  const axisOptions = useMemo(
    () => axisOptionsFor(activeCurve, channels),
    [activeCurve, channels],
  )

  // 곡선을 바꾸면 축이 그 곡선에 없을 수 있다. **바꿀 때마다 확인한다** —
  // 안 하면 "이 시험에 없는 채널입니다: step_time" 이 뜬다(실제로 떴다).
  useEffect(() => {
    const next = resolveAxes(axes, axisOptions)
    if (next !== axes) setAxes(next)
  }, [axes, axisOptions])

  const curve = useResource(
    () =>
      item?.status === 'parsed' && axes
        ? testsApi.curve(id, {
            x: axes.x,
            y: axes.y,
            curve: activeCurve?.key,
            maxPoints: 1200,
          })
        : Promise.resolve(null),
    [id, item?.status, axes?.x, axes?.y, activeCurve?.key],
  )

  const xChannel = axisOptions.find((c) => c.key === axes?.x)
  const yChannel = axisOptions.find((c) => c.key === axes?.y)
  const points = useMemo<[number, number][]>(
    () =>
      (curve.data?.points ?? []).map(([x, y]) => [
        // 차원까지 넘긴다. 변형률과 tan δ 는 저장 단위가 둘 다 `1` 이라
        // 단위만으로는 못 가른다 — 변형률만 %로 보여야 한다.
        toDisplay(x, xChannel?.si_unit, xChannel?.dimension),
        toDisplay(y, yChannel?.si_unit, yChannel?.dimension),
      ]),
    [
      curve.data,
      xChannel?.si_unit,
      xChannel?.dimension,
      yChannel?.si_unit,
      yChannel?.dimension,
    ],
  )

  async function download() {
    setAction(null)
    try {
      await testsApi.downloadSource(id, item?.source_filename ?? 'source.dat')
    } catch (caught) {
      // 링크였을 때는 이 오류가 새 탭에서 나 화면에 안 보였다.
      setAction(caught instanceof Error ? caught : new Error('원본을 받지 못했습니다.'))
    }
  }

  /**
   * 다시 읽는다.
   *
   * `profileKey` 를 안 주면 **지금 정해진 대로** 읽는다 — 고정을 골라 뒀으면
   * 그것이 이어진다. `null` 이면 고정을 풀고 자동으로 되돌린다.
   */
  /**
   * 종류를 바로잡는다. **아직 아무것도 안 나온 시험만** — 서버가 막는다.
   *
   * 이름이 바뀌므로 목록을 다시 읽는다. 바뀐 이름을 말해 주지 않으면, 사람은
   * 자기가 보던 시험을 목록에서 못 찾는다.
   */
  async function retype(testTypeKey: string) {
    setAction(null)
    try {
      const done = await testsApi.retype(id, testTypeKey)
      setNotice(done.message)
      run.reload()
    } catch (caught) {
      setAction(caught instanceof Error ? caught : new Error('종류를 바꾸지 못했습니다.'))
    }
  }

  async function reparse(profileKey?: string | null) {
    setAction(null)
    try {
      const done = await testsApi.reparse(id, profileKey)
      setNotice(done.message)
      run.reload()
    } catch (caught) {
      setAction(caught instanceof Error ? caught : new Error('다시 읽기에 실패했습니다.'))
    }
  }

  async function remove() {
    setAction(null)
    setRemoving(false)
    try {
      await testsApi.remove(id)
      navigate('/materials')
    } catch (caught) {
      setAction(caught instanceof Error ? caught : new Error('삭제에 실패했습니다.'))
    }
  }

  return (
    /* **이 화면만 넓다.** 처리 탭이 순서도·단계·곡선 셋을 나란히 놓는 작업
       화면이라 4xl(896px)에서는 곡선이 손바닥만 해진다. 다른 화면은 읽는
       화면이라 좁은 것이 맞다 — 여기만 넓힌다. */
    <div>
      <ConfirmDialog
        open={removing}
        title="이 시험을 지웁니다"
        body={
          <>
            <b className="font-mono">{item?.record_name}</b> 이 목록에서 사라집니다.
            원본 파일과 처리 결과도 함께 가려집니다.
          </>
        }
        onConfirm={remove}
        onClose={() => setRemoving(false)}
      />

      <PageHeader
        title={item?.record_name ?? '시험'}
        description={
          item ? `${item.test_type_label} · ${item.material_name ?? ''}` : undefined
        }
        created={item?.created_at}
        // **왔던 자리로 돌려보낸다.** 규칙은 `backTarget` 이 갖는다 — 화면에
        // 박아 두면 시험할 데가 없다.
        back={backTarget(from, item ?? null)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={download} disabled={!item}>
              <Download className="size-4" />
              원본
            </Button>
            {/* **자동이 틀리면 고칠 자리가 있어야 한다.** 전에는 「다시 읽기」
                뿐이라 같은 선택을 그대로 반복했다 — 실패한 파일은 손쓸 방법이
                없었다. */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <RefreshCw className="size-4" />
                  다시 읽기
                  <ChevronDown className="size-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem onSelect={() => void reparse()}>
                  같은 형식으로 다시
                  {item?.parse_profile_key && (
                    <span className="text-muted-foreground ml-auto text-xs">
                      {item.parse_profile_key}
                    </span>
                  )}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-xs font-normal">
                  형식을 골라 읽기
                </DropdownMenuLabel>
                {(formats.data ?? []).map((one) => (
                  <DropdownMenuItem
                    key={one.key}
                    onSelect={() => void reparse(one.key)}
                    disabled={one.key === item?.parse_profile_key}
                  >
                    <span className="truncate">{one.label}</span>
                    <span className="text-muted-foreground ml-auto text-xs">{one.key}</span>
                  </DropdownMenuItem>
                ))}
                {(formats.data?.length ?? 0) === 0 && (
                  <DropdownMenuItem disabled>
                    이 시험 종류에 등록된 형식이 없습니다
                  </DropdownMenuItem>
                )}
                {item?.parse_profile_key && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => void reparse(null)}>
                      고정 풀고 자동으로
                    </DropdownMenuItem>
                  </>
                )}
                {/* **형식이 아니라 종류가 틀린 경우가 있다.** 인장 파일을 DMA
                    로 올린 것은 어떤 형식으로도 안 읽힌다 — 그때 지우고 다시
                    올리게 하면 파일과 시편 연결을 처음부터 다시 한다. */}
                {retypable && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel className="text-xs font-normal">
                      시험 종류를 바로잡기 (이름도 바뀝니다)
                    </DropdownMenuLabel>
                    {(types.data ?? [])
                      .filter((one) => one.key !== item?.test_type_key)
                      .map((one) => (
                        <DropdownMenuItem
                          key={one.key}
                          onSelect={() => void retype(one.key)}
                        >
                          {one.label}
                          <span className="text-muted-foreground ml-auto text-xs">
                            {one.abbr}
                          </span>
                        </DropdownMenuItem>
                      ))}
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button variant="outline" size="sm" onClick={() => setRemoving(true)}>
              <Trash2 className="size-4" />
            </Button>
          </>
        }
      />

      <ErrorNotice error={run.error ?? action} className="mb-4" />

      {notice && (
        // **눌렀는지 모르면 또 누른다.** 큐에 들어간 것은 바로 안 보이므로
        // 무엇으로 걸렸는지 한 줄로 말한다.
        <p className="bg-muted/40 mb-4 rounded-md border px-3 py-2 text-sm">{notice}</p>
      )}

      {item && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <Badge variant={item.status === 'failed' ? 'destructive' : 'secondary'}>
            {RUN_STATUS_LABEL[item.status] ?? item.status}
          </Badge>
          {item.specimen_name && (
            <span className="text-muted-foreground font-mono text-xs">
              {item.specimen_name}
            </span>
          )}
          {item.source_filename && (
            <span className="text-muted-foreground text-xs">
              {item.source_filename} · {((item.source_bytes ?? 0) / 1024).toFixed(1)}KB
            </span>
          )}
          {item.row_count != null && (
            <span className="text-muted-foreground text-xs">
              {item.row_count.toLocaleString('ko-KR')}행
            </span>
          )}
        </div>
      )}

      {item && definition && <ConditionBlock item={item} fields={definition.conditions} />}

      {item?.parse_error && (
        <div className="border-destructive/40 bg-destructive/5 text-destructive mb-6 rounded-md border p-3 text-sm">
          <p className="font-medium">읽지 못했습니다</p>
          <p className="mt-1">{item.parse_error}</p>
          <p className="mt-2 text-xs opacity-80">
            원본을 내려받아 형식을 확인하세요. <b>「다시 읽기」 를 열면 형식을 골라
            읽을 수 있습니다</b> — 자동으로 고른 것이 틀렸을 때 쓰는 길입니다. 맞는
            형식이 없으면 <b>기준정보 · 파일 형식</b>에서 새로 만들고 다시 읽습니다.
          </p>
        </div>
      )}

      {item?.note && (
        <div className="bg-muted/40 mb-6 rounded-md border p-3 text-sm">
          {/* 서버가 sha256 으로 잡은 중복 안내가 여기 온다. 실을 곳이 없으면
              서버만 알고 사용자는 끝내 모른다. */}
          <p className="whitespace-pre-wrap">{item.note}</p>
        </div>
      )}

      {item && item.warnings.length > 0 && (
        <div className="mb-6 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          <p className="flex items-center gap-1.5 font-medium text-amber-700 dark:text-amber-500">
            <AlertTriangle className="size-4" />
            읽기는 했지만 확인이 필요합니다
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-amber-800 dark:text-amber-400">
            {item.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {/* **세로로 이어 붙이지 않는다.** 원본 → 처리 → 결과가 한 화면에 쌓이면,
          처리하는 동안 원본 곡선이 위로 사라지고 결과는 또 아래에 있다. 계획서의
          워크벤치(Data → Process → Stats → Fit → Export)와 같은 구조라, 나중에
          여러 시험을 다루는 워크벤치로 그대로 넓어진다(ADR 0007). */}
      {item && (
        <Tabs defaultValue="source">
          <TabsList>
            <TabsTrigger value="source">원본</TabsTrigger>
            <TabsTrigger value="process" disabled={item.status !== 'parsed'}>
              처리
            </TabsTrigger>
            {/* **DMA 일 때만 뜬다.** 점탄성은 온도가 다른 스윕 여럿을 겹치는
                일이라 인장 시험에는 할 것이 없다 — 눌러 봐야 "겹칠 스윕이
                없습니다" 만 나오는 탭은 두지 않는다. */}
            {isViscoelastic && (
              <TabsTrigger value="viscoelastic" disabled={item.status !== 'parsed'}>
                점탄성
              </TabsTrigger>
            )}
            <TabsTrigger value="results" disabled={item.status !== 'parsed'}>
              결과
              {item.result_count > 0 && (
                <Badge variant="secondary" className="ml-1.5 text-xs">
                  {item.result_count}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="source">
            {item?.status === 'parsed' && (
              <section className="mb-8">
                <h2 className="mb-2 font-medium">곡선</h2>

                {/* **종류 → 벌 → 축** 으로 좁혀 들어간다. 한 줄에 8개를 늘어놓으면
                    무엇이 같은 종류의 반복이고 무엇이 성격이 다른 곡선인지 구분이 안 된다. */}
                <div className="mb-3 space-y-1">
                  {families.length > 1 && (
                    <div className="flex flex-wrap items-center gap-1 text-xs">
                      <span className="text-muted-foreground w-12 shrink-0">종류</span>
                      {families.map((family) => (
                        <Button
                          key={family.name}
                          size="sm"
                          variant={activeFamily?.name === family.name ? 'default' : 'outline'}
                          onClick={() => {
                            setFamilyName(family.name)
                            // 종류를 바꾸면 벌 선택은 처음으로. 안 그러면 다른 종류의
                            // 키가 남아 첫 벌로 조용히 되돌아간 것처럼 보인다.
                            setCurveKey(null)
                          }}
                        >
                          {family.name}
                          <span className="ml-1 opacity-70">
                            {family.kind === 'derived' ? '처리결과' : '측정'}
                            {family.items.length > 1 && ` ${family.items.length}벌`}
                          </span>
                        </Button>
                      ))}
                    </div>
                  )}

                  {/* 그 종류가 여러 벌일 때만. 한 벌뿐이면 고를 것이 없다. */}
                  {(activeFamily?.items.length ?? 0) > 1 && (
                    <div className="flex flex-wrap items-center gap-1 text-xs">
                      <span className="text-muted-foreground w-12 shrink-0">구간</span>
                      {activeFamily?.items.map((curveItem) => (
                        <Button
                          key={curveItem.key}
                          size="sm"
                          variant={activeCurve?.key === curveItem.key ? 'default' : 'outline'}
                          onClick={() => setCurveKey(curveItem.key)}
                          title={`${curveItem.row_count}행 · ${curveItem.channels.join(', ')}`}
                        >
                          {/* 종류 이름을 뗀 나머지 — `- 3` 처럼 구간만 보인다. */}
                          {memberLabel(curveItem, activeFamily.name)}
                        </Button>
                      ))}
                    </div>
                  )}

                  {/* **X 도 고를 수 있어야 한다.** 처리결과 곡선은 열이 12개다 —
                      주파수-저장탄성률로 볼지, 온도-이동인자로 볼지는 그때그때 다르다.
                      X 가 첫 채널로 고정돼 있던 때는 볼 수 없는 조합이 대부분이었다. */}
                  {(['x', 'y'] as const).map((axis) => (
                    <div key={axis} className="flex flex-wrap items-center gap-1 text-xs">
                      <span className="text-muted-foreground w-12 shrink-0">
                        {axis === 'x' ? 'X축' : 'Y축'}
                      </span>
                      {axisOptions.map((channel) => (
                        <Button
                          key={channel.key}
                          size="sm"
                          variant={axes?.[axis] === channel.key ? 'default' : 'outline'}
                          onClick={() =>
                            setAxes((current) =>
                              current ? { ...current, [axis]: channel.key } : current,
                            )
                          }
                          disabled={axes?.[axis === 'x' ? 'y' : 'x'] === channel.key}
                        >
                          {channel.label}
                        </Button>
                      ))}
                    </div>
                  ))}
                </div>

                <ErrorNotice error={curve.error} className="mb-2" />

                <CurveChart
                  points={points}
                  xLabel={axisLabel(
                    xChannel?.label ?? '',
                    xChannel?.si_unit,
                    xChannel?.dimension,
                  )}
                  yLabel={axisLabel(
                    yChannel?.label ?? '',
                    yChannel?.si_unit,
                    yChannel?.dimension,
                  )}
                />
                {curve.data && (
                  <p className="text-muted-foreground mt-2 text-xs">
                    원본 {curve.data.row_count.toLocaleString('ko-KR')}행 중{' '}
                    {curve.data.returned}점을 표시합니다 — 모양을 지키면서 줄였습니다(LTTB).
                  </p>
                )}
              </section>
            )}
            {item && item.summary.length > 0 && (
              <section className="mb-8">
                <h2 className="mb-1 font-medium">요약값</h2>
                {/* **나란히 두는 것이 목적이다.** 한 줄씩 평평하게 그리면 같은
                    항복강도가 표의 다른 자리에 떨어져, source 를 나눈 의미가
                    사라진다. 실측: 장비 160.0 MPa vs 우리 249.5 MPa. */}
                <p className="text-muted-foreground mb-2 text-xs">
                  장비가 계산한 값과 우리가 계산한 값을 같은 줄에 둡니다. 크게 다르면
                  둘 중 하나가 틀린 것인데, <b>어느 쪽인지는 곡선을 봐야 압니다</b> —
                  대개 탄성 구간을 어디로 잡았는지에서 갈립니다.
                </p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>항목</TableHead>
                      <TableHead className="text-right">장비</TableHead>
                      <TableHead className="text-right">MatNexus</TableHead>
                      <TableHead className="text-right">차이</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pairs.map((pair) => {
                      const notable =
                        pair.differencePercent !== null &&
                        Math.abs(pair.differencePercent) >= NOTABLE_DIFFERENCE
                      return (
                        <TableRow key={pair.key}>
                          <TableCell>
                            <span className="text-sm">{pair.label}</span>
                            <p className="text-muted-foreground font-mono text-xs">
                              {pair.key}
                            </p>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {pair.instrument
                              ? formatValue(
                                  pair.instrument.value,
                                  pair.instrument.text,
                                  pair.instrument.si_unit,
                                  pair.dimension
                                )
                              : '—'}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {pair.ours
                              ? formatValue(
                                  pair.ours.value,
                                  pair.ours.text,
                                  pair.ours.si_unit,
                                  pair.dimension
                                )
                              : '—'}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {pair.differencePercent === null ? (
                              <span className="text-muted-foreground">—</span>
                            ) : (
                              <span
                                className={
                                  notable ? 'font-medium text-amber-700 dark:text-amber-500' : ''
                                }
                              >
                                {pair.differencePercent > 0 ? '+' : ''}
                                {pair.differencePercent.toPrecision(3)}%
                              </span>
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </section>
            )}

            {item && Object.keys(item.source_metadata).length > 0 && (
              <section>
                <h2 className="mb-2 font-medium">장비가 준 시편 정보</h2>
                <p className="text-muted-foreground mb-2 text-xs">
                  시험 결과가 아니라 입력값입니다. 시편 실측치를 자동으로 덮어쓰지 않습니다 —
                  사람이 이미 재어 넣은 값을 파일이 조용히 바꾸면 어느 것이 맞는지 알 수
                  없습니다.
                </p>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-1 rounded-md border p-3 text-sm sm:grid-cols-3">
                  {Object.entries(item.source_metadata).map(([key, value]) => (
                    <div key={key}>
                      <dt className="text-muted-foreground text-xs">{key}</dt>
                      <dd className="font-mono text-xs">{value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
          </TabsContent>

          <TabsContent value="process">
            {activeCurve ? (
              <ProcessingPanel
                testRunId={item.id}
                testTypeKey={item.test_type_key}
                curveKey={activeCurve.key}
                sourceColumns={activeCurve.channels}
                /* 변수 목록이 `displacement` 를 '변위 (m)' 로 읽게 한다. */
                sourceChannels={channels}
                managedWorkspaces={managed}
              />
            ) : (
              <p className="text-muted-foreground py-12 text-center text-sm">
                처리할 곡선이 없습니다.
              </p>
            )}
          </TabsContent>

          {isViscoelastic && (
            <TabsContent value="viscoelastic">
              <ViscoelasticPanel testRunId={item.id} />
            </TabsContent>
          )}

          <TabsContent value="results">
            <ResultsPanel testRunId={item.id} onAdoptChange={run.reload} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

/**
 * 시험 조건과 시험 메타.
 *
 * **넣기는 하는데 볼 데가 없었다.** 업로드 창이 시험 온도·속도·예하중·센서 종류·
 * 시편 규격·시험 그룹을 받아 저장하고, `conditions` 는 API 응답에도 실려 있는데,
 * 상세 화면이 그리지 않아 입력한 사람도 다시 못 봤다. 조건을 모르는 곡선은
 * 비교할 수 없다 — 200℃에서 잰 것과 상온 것이 같은 표에 서면 그 차이는 산포로
 * 읽힌다.
 *
 * 비어 있으면 통째로 감춘다. 값이 하나도 없는 표는 화면만 차지하고, "이 시험은
 * 조건을 안 적었다" 는 사실은 빈 표보다 없는 것이 더 분명하다.
 */
/** 치수가 **어디서 왔는가.** 정본은 서버의 `Size.source` 다. */
const DIMENSION_SOURCE: Record<string, string> = {
  run: '이 시험이 잰 값',
  measured: '시편에 적힌 값',
  nominal: '규격 공칭',
}

function ConditionBlock({
  item,
  fields,
}: {
  item: TestRunDetail
  fields: TestConditionField[]
}) {
  /**
   * 이 시험이 쓰는 시편 치수.
   *
   * 실사용에서 나왔다 — *"시험에서 잰 두께, 폭은 어디서 확인할 수 있어?"*.
   * 값은 파싱이 시험에 담고 있었지만(v1.118.0) 볼 데가 처리 화면뿐이었고,
   * 원본 메타에는 `specimen_thickness_a0 / 0.986` 같은 **원시 글자**로만 있었다.
   *
   * 여기 두는 이유는 「시편 규격」 이 여기 있는 이유와 같다 — 곡선을 보는
   * 자리에서 "이게 어떤 시편이었나" 를 알아야 한다. 그리고 치수는 이제 **그
   * 시험의 값**이라 조건과 나란히 서는 것이 맞다.
   */
  const dimensions = useResource(() => testsApi.instrumentDimensions(item.id), [item.id])
  const sized = (dimensions.data?.items ?? []).filter((one) => one.run_m != null)

  const filled = fields.filter((field) => item.conditions[field.key] != null)
  const meta: [string, string][] = [
    ['시험일시', item.tested_at ? new Date(item.tested_at).toLocaleString('ko-KR') : ''],
    ['시험자', item.operator ?? ''],
    ['장비', item.instrument ?? ''],
    ['사업부', item.division ?? ''],
  ]
  const filledMeta = meta.filter(([, value]) => value !== '')
  if (
    filled.length === 0 &&
    filledMeta.length === 0 &&
    sized.length === 0 &&
    !item.specimen_standard
  )
    return null

  return (
    <section className="mb-6 rounded-md border p-4">
      <h2 className="mb-3 text-sm font-medium">시험 조건</h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
        {/* **시편의 값이지 시험의 값이 아니다.** 그래도 여기 보여 준다 — 곡선을
            보는 자리에서 "이게 어떤 시편이었나" 를 알아야 하고, 다른 규격끼리
            연신율을 견주면 그 차이는 재료가 아니라 시편의 것이다. */}
        {item.specimen_standard && (
          <div>
            <dt className="text-muted-foreground text-xs">시편 규격</dt>
            <dd>{item.specimen_standard}</dd>
          </div>
        )}
        {filled.map((field) => (
          <div key={field.key}>
            <dt className="text-muted-foreground text-xs">{field.label}</dt>
            <dd className="tabular-nums">
              {/* **저장은 SI, 화면은 실무 단위.** 온도를 298.15 K 로 보여 주면
                  아무도 25℃ 인 줄 모른다. */}
              {/* `formatValue(value, text, siUnit, dimension)` — 인자가 넷이다.
                  셋으로 부르면 단위 자리에 dimension 이 들어가는데, 타입이 전부
                  `string | null` 이라 컴파일러가 안 잡는다(실제로 그렇게 썼다). */}
              {field.si_unit
                ? formatValue(
                    Number(item.conditions[field.key]),
                    null,
                    field.si_unit,
                    field.dimension
                  )
                : String(item.conditions[field.key])}
            </dd>
          </div>
        ))}
        {filledMeta.map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted-foreground text-xs">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {/* **조건과 섞지 않는다.**
       *
       * 실사용에서 나왔다 — *"시험 조건이면 시험종류 정의에서 정의해서 넣어야
       * 하는 거 아냐?"*. 맞다. 위 표의 계약은 **시험 종류가 선언한 것**인데,
       * 두께·폭은 **시편 규격**이 선언한다(ADR 0010 — 평판은 폭·두께, 환봉은
       * 직경). 선언한 곳이 다르므로 같은 표에 섞으면 사람은 두께도 시험 종류에서
       * 정하는 줄 안다.
       *
       * 선언을 시험 종류로 옮기지는 않는다. 그러면 같은 것을 규격도 정하고 시험
       * 종류도 정하게 되고, 둘이 어긋날 때 답이 없다 — `grade` 를 「재료 속성」
       * 에서 뺀 것과 같은 이유다. 기하는 규격이 정하는 것이 맞다.
       *
       * 그래도 **같은 자리에 붙여 둔다.** 곡선을 보는 사람에게는 "이 시험이
       * 무엇으로 돌았나" 가 한 덩어리다. */}
      {sized.length > 0 && (
        <div className="mt-4 border-t pt-3">
          <h3 className="text-muted-foreground mb-2 text-xs">
            이 시험이 쓴 시편 치수 <span className="opacity-70">— 시편 규격이 정한 칸</span>
          </h3>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
            {sized.map((one) => (
              <div key={one.field}>
                <dt className="text-muted-foreground text-xs">
                  {one.label}
                  {one.symbol && <span className="ml-1 opacity-60">{one.symbol}</span>}
                </dt>
                <dd className="tabular-nums">
                  {formatValue(one.run_m ?? 0, null, 'm', 'length')}
                  {one.source && DIMENSION_SOURCE[one.source] && (
                    <span
                      className={`ml-1 text-xs ${
                        one.source === 'run'
                          ? 'text-muted-foreground'
                          : 'text-amber-700 dark:text-amber-500'
                      }`}
                    >
                      ({DIMENSION_SOURCE[one.source]})
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </section>
  )
}
