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
import { AlertTriangle, Download, RefreshCw, Trash2 } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { CurveChart } from '@/modules/tests/CurveChart'
import { RUN_STATUS_LABEL, isPending, testsApi } from '@/modules/tests/api'
import { axisLabel, formatValue, toDisplay } from '@/modules/tests/units'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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
import { useResource } from '@/shared/hooks/useResource'

const SOURCE_LABEL: Record<string, string> = {
  instrument: '장비',
  matnexus: 'MatNexus',
}

export default function TestRunDetailPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const run = useResource(() => testsApi.run(id), [id])
  const types = useResource(() => testsApi.types(), [])
  const [axes, setAxes] = useState<{ x: string; y: string } | null>(null)
  const [action, setAction] = useState<Error | null>(null)

  const item = run.data
  const pending = item ? isPending(item.status) : false

  // 읽는 중이면 스스로 따라간다 — 올린 직후 이 화면으로 오는 경우가 흔하다.
  useEffect(() => {
    if (!pending) return
    const timer = setInterval(() => run.reload(), 3000)
    return () => clearInterval(timer)
  }, [pending, run])

  const definition = useMemo(
    () => (types.data ?? []).find((t) => t.key === item?.test_type_key),
    [types.data, item?.test_type_key]
  )
  // `?? []` 를 그대로 두면 매 렌더마다 새 배열이라 아래 useEffect 가 계속 돈다.
  const channels = useMemo(() => definition?.channels ?? [], [definition])

  useEffect(() => {
    if (axes || channels.length < 2) return
    // 정의에 있는 채널이라도 **그 곡선에 없을 수 있다.** DMA 는 구간마다 열
    // 구성이 다르다 — 없는 채널을 축으로 잡으면 첫 화면부터 오류가 뜬다.
    const present = item?.curves?.[0]?.channels
    const usable = present
      ? channels.filter((channel) => present.includes(channel.key))
      : channels
    const pick = usable.length >= 2 ? usable : channels
    setAxes({ x: pick[0].key, y: pick[1].key })
  }, [axes, channels, item?.curves])

  /**
   * 어느 곡선을 볼 것인가. **한 시험이 곡선을 여럿 가진다.**
   *
   * TA DMA850 주파수-온도 스윕은 `[step]` 마다 별개 측정이라 곡선이 6벌 나온다.
   * 고를 수 없던 때는 저장은 다 돼 있는데 **화면에서 하나도 안 보였다** — 목록·
   * 상세·차트가 전부 `raw` 키만 찾았고, 표가 여럿인 파일에는 그 키가 없다.
   */
  const curves = useMemo(() => item?.curves ?? [], [item])
  const [curveKey, setCurveKey] = useState<string | null>(null)
  const activeCurve = curves.find((c) => c.key === curveKey) ?? curves[0] ?? null

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
    [id, item?.status, axes?.x, axes?.y, activeCurve?.key]
  )

  const xChannel = channels.find((c) => c.key === axes?.x)
  const yChannel = channels.find((c) => c.key === axes?.y)
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
    ]
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

  async function reparse() {
    setAction(null)
    try {
      await testsApi.reparse(id)
      run.reload()
    } catch (caught) {
      setAction(caught instanceof Error ? caught : new Error('다시 읽기에 실패했습니다.'))
    }
  }

  async function remove() {
    setAction(null)
    try {
      await testsApi.remove(id)
      navigate('/materials')
    } catch (caught) {
      setAction(caught instanceof Error ? caught : new Error('삭제에 실패했습니다.'))
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={item?.record_name ?? '시험'}
        description={item ? `${item.test_type_label} · ${item.material_name ?? ''}` : undefined}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={download} disabled={!item}>
              <Download className="size-4" />
              원본
            </Button>
            <Button variant="outline" size="sm" onClick={reparse}>
              <RefreshCw className="size-4" />
              다시 읽기
            </Button>
            <Button variant="outline" size="sm" onClick={remove}>
              <Trash2 className="size-4" />
            </Button>
          </>
        }
      />

      <ErrorNotice error={run.error ?? action} className="mb-4" />

      {item && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <Badge variant={item.status === 'failed' ? 'destructive' : 'secondary'}>
            {RUN_STATUS_LABEL[item.status] ?? item.status}
          </Badge>
          {item.specimen_name && (
            <span className="text-muted-foreground font-mono text-xs">{item.specimen_name}</span>
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

      {item?.parse_error && (
        <div className="border-destructive/40 bg-destructive/5 text-destructive mb-6 rounded-md border p-3 text-sm">
          <p className="font-medium">읽지 못했습니다</p>
          <p className="mt-1">{item.parse_error}</p>
          <p className="mt-2 text-xs opacity-80">
            원본을 내려받아 형식을 확인하세요. 파서를 고친 뒤 '다시 읽기' 를 누르면 같은
            원본으로 다시 시도합니다.
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

      {item?.status === 'parsed' && (
        <section className="mb-8">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h2 className="font-medium">곡선</h2>
            <div className="ml-auto flex items-center gap-1 text-xs">
              <span className="text-muted-foreground">Y축</span>
              {channels.map((channel) => (
                <Button
                  key={channel.key}
                  size="sm"
                  variant={axes?.y === channel.key ? 'default' : 'outline'}
                  onClick={() => setAxes((a) => (a ? { ...a, y: channel.key } : a))}
                  disabled={axes?.x === channel.key}
                >
                  {channel.label}
                </Button>
              ))}
            </div>
          </div>

          {/* **한 시험이 곡선을 여럿 가진다.** DMA 주파수-온도 스윕은 `[step]`
              마다 별개 측정이라 6벌이 나온다. 고를 수 없던 때는 저장은 다 돼
              있는데 화면에서 하나도 안 보였다. 하나뿐이면 굳이 보여 주지 않는다. */}
          {curves.length > 1 && (
            <div className="mb-3 space-y-2">
              {/* **측정과 처리결과를 나눠 보여 준다.** 섞어 두면 사람은 마스터
                  곡선을 원본으로 본다 — 요약값에서 `장비 / MatNexus` 를 나란히
                  두는 것과 같은 이유다. */}
              {(['measured', 'derived'] as const).map((kind) => {
                const group = curves.filter((item) => item.kind === kind)
                if (group.length === 0) return null
                return (
                  <div key={kind}>
                    <p className="text-muted-foreground mb-1 text-xs">
                      {kind === 'measured'
                        ? `측정 ${group.length}벌 — 구간마다 별개 측정입니다`
                        : `처리결과 ${group.length}벌 — 장비가 계산해 준 것입니다`}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {group.map((item) => (
                        <Button
                          key={item.key}
                          size="sm"
                          variant={activeCurve?.key === item.key ? 'default' : 'outline'}
                          onClick={() => setCurveKey(item.key)}
                          title={`${item.row_count}행 · ${item.channels.join(', ')}`}
                        >
                          {item.label ?? item.key}
                        </Button>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <ErrorNotice error={curve.error} className="mb-2" />

          <CurveChart
            points={points}
            xLabel={axisLabel(xChannel?.label ?? '', xChannel?.si_unit, xChannel?.dimension)}
            yLabel={axisLabel(yChannel?.label ?? '', yChannel?.si_unit, yChannel?.dimension)}
          />
          {curve.data && (
            <p className="text-muted-foreground mt-2 text-xs">
              원본 {curve.data.row_count.toLocaleString('ko-KR')}행 중 {curve.data.returned}점을
              표시합니다 — 모양을 지키면서 줄였습니다(LTTB).
            </p>
          )}
        </section>
      )}

      {item && item.summary.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-2 font-medium">요약값</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>항목</TableHead>
                <TableHead>값</TableHead>
                <TableHead>출처</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {item.summary.map((row) => (
                <TableRow key={`${row.source}-${row.key}`}>
                  <TableCell>
                    <span className="font-mono text-xs">{row.key}</span>
                    {row.label && (
                      <p className="text-muted-foreground text-xs">{row.label}</p>
                    )}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatValue(row.value, row.text, row.si_unit)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{SOURCE_LABEL[row.source] ?? row.source}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}

      {item && Object.keys(item.source_metadata).length > 0 && (
        <section>
          <h2 className="mb-2 font-medium">장비가 준 시편 정보</h2>
          <p className="text-muted-foreground mb-2 text-xs">
            시험 결과가 아니라 입력값입니다. 시편 실측치를 자동으로 덮어쓰지 않습니다 —
            사람이 이미 재어 넣은 값을 파일이 조용히 바꾸면 어느 것이 맞는지 알 수 없습니다.
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
    </div>
  )
}
