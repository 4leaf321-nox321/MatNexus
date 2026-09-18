/**
 * 무거운 그림(사케이) — **plotly 가 그린다.** StandardPlatform 의 `shared/charts/LazyPlot` 을 옮겨 왔다.
 *
 * plotly 는 압축해도 1MB 를 훌쩍 넘으므로 **정적으로 import 하지 않는다** — 그러면 이 그림을 한 번도
 * 안 여는 사람까지 첫 화면에서 그만큼을 받는다. 여기서만 `import()` 로 불러 별도 덩어리에 둔다.
 * 받는 동안에도 같은 높이를 차지하고(아래 것이 밀리지 않게), 못 받으면 그렇다고 말한다(빈 칸은
 * 「데이터가 없다」 로 읽힌다).
 */

import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'

export type PlotTrace = Record<string, unknown>
export type PlotLayout = Record<string, unknown>

interface Props {
  data: PlotTrace[]
  layout?: PlotLayout
  height?: number
  toolbar?: boolean
  className?: string
  title?: string
}

function baseLayout(height: number): PlotLayout {
  return {
    height,
    margin: { t: 24, r: 16, b: 40, l: 48 },
    // 배경을 비운다 — 흰색으로 박으면 어두운 테마에서 그림만 하얗게 뜬다.
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { size: 12, color: 'var(--muted-foreground)' },
    showlegend: false,
  }
}

export function LazyPlot({
  data,
  layout,
  height = 320,
  toolbar = false,
  className,
  title,
}: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    const node = box.current
    if (!node) return

    import('plotly.js-dist-min')
      .then((plotly) => {
        if (cancelled || !box.current) return
        setReady(true)
        type Args = Parameters<typeof plotly.default.react>
        const merged = { ...baseLayout(height), ...layout } as Args[2]
        return plotly.default.react(box.current, data as Args[1], merged, {
          displayModeBar: toolbar,
          responsive: true,
        })
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      if (node) {
        void import('plotly.js-dist-min').then((plotly) => plotly.default.purge(node))
      }
    }
    // data·layout 은 매 렌더 새 객체일 수 있어 **내용**으로 비교한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(data), JSON.stringify(layout), height, toolbar])

  if (failed) {
    return (
      <p className="text-muted-foreground py-8 text-center text-sm">
        그림 도구를 불러오지 못했습니다. 새로고침해 보고, 그래도 안 되면 관리자에게 알려 주세요
        — 데이터가 없는 것은 아닙니다.
      </p>
    )
  }

  return (
    <div className={className} style={{ height }} role="img" aria-label={title ?? '차트'}>
      {!ready && (
        <div className="text-muted-foreground flex h-full items-center justify-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" />
          그림 준비 중…
        </div>
      )}
      <div ref={box} style={{ height: '100%', display: ready ? 'block' : 'none' }} />
    </div>
  )
}
