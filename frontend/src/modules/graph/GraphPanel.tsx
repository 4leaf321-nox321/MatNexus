/**
 * 상세 화면 안의 작은 관계도 — **문서를 떠나지 않고 「이게 무엇과 이어졌나」 를 본다.**
 *
 * StandardPlatform 을 거쳐 ReportArchive 의 `EntityGraphPanel` 에서 왔다. 2단계까지만 그리고, 노드를
 * 누르면 그 객체의 상세로 **이동**한다(순회) — 상세 안에서는 「선택」 이 아니라 「가기」
 * 가 맞는 동작이다. 더 넓게 보려면 오른쪽 위 단추로 지식 그래프에 넘긴다.
 *
 * 관계가 하나도 없으면 안 그린다. 빈 캔버스는 「고장」 으로 읽힌다.
 */

import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Waypoints } from 'lucide-react'

import { graphApi } from '@/modules/graph/api'
import { colorScale } from '@/modules/graph/colors'
import { GraphCanvas } from '@/modules/graph/GraphCanvas'
import type { CanvasLink, CanvasNode } from '@/modules/graph/GraphCanvas'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

const FOCUS_RING = '#f59e0b'
/** 상세 안에서는 얕게 — 2단계면 「이웃의 이웃」 까지. 그 너머는 지식 그래프. */
const DEPTH = 2
const FANOUT = 20

interface GraphPanelProps {
  /** 노드 id — `<종류>:<uuid>`. */
  objectId: string
}

export function GraphPanel({ objectId }: GraphPanelProps) {
  const navigate = useNavigate()
  const overview = useResource(() => graphApi.overview(), [])
  // 색을 정의 순서로 — 지식 그래프와 같은 색.
  const typeSlugs = useMemo(
    () => (overview.data?.nodes ?? []).map((one) => one.slug),
    [overview.data],
  )
  const graph = useResource(
    () => graphApi.neighborhood({ focus: objectId, depth: DEPTH, fanout: FANOUT }),
    [objectId],
  )
  const typeColor = useMemo(() => colorScale(typeSlugs), [typeSlugs])

  const { nodes, links } = useMemo(() => {
    const data = graph.data
    // 응답 모양이 아니면(다른 화면의 가짜 응답·옛 서버) 빈 그림 — 죽지 않는다.
    if (!data || !Array.isArray(data.edges) || !Array.isArray(data.nodes)) {
      return { nodes: [] as CanvasNode[], links: [] as CanvasLink[] }
    }
    const shown = new Map<string, number>()
    for (const edge of data.edges) {
      shown.set(edge.src, (shown.get(edge.src) ?? 0) + 1)
      if (edge.dst !== edge.src) shown.set(edge.dst, (shown.get(edge.dst) ?? 0) + 1)
    }
    const maxDegree = Math.max(1, ...data.nodes.map((one) => one.degree))
    return {
      nodes: data.nodes.map((one): CanvasNode => {
        const hidden = one.degree - (shown.get(one.id) ?? 0)
        return {
          id: one.id,
          label: one.label,
          sublabel: one.type_label,
          card: [one.label, one.type_label, '클릭: 이 객체로 이동'],
          color: typeColor(one.type_slug),
          radius: 4 + Math.sqrt(one.degree / maxDegree) * 5,
          shape: 'circle',
          ring: one.id === data.focus ? FOCUS_RING : null,
          badge: hidden > 0 ? `+${hidden}` : null,
        }
      }),
      links: data.edges.map((one): CanvasLink => ({
        id: one.id,
        source: one.src,
        target: one.dst,
        label: one.label,
        tooltip:
          one.directed && one.inverse_label && one.inverse_label !== one.label
            ? `${one.label} ↔ ${one.inverse_label}`
            : one.label,
        directed: one.directed,
        width: 1,
      })),
    }
  }, [graph.data, typeColor])

  if (graph.error) return <ErrorNotice error={graph.error} />
  // 관계가 없으면 이 절 자체가 없다 — 「관련 객체」 가 이미 「없다」 고 말한다.
  if (!graph.data || !Array.isArray(graph.data.edges) || graph.data.edges.length === 0)
    return null

  const pathOf = new Map(graph.data.nodes.map((one) => [one.id, one.detail_path]))
  const truncated = graph.data.truncated

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium">
          관계도{' '}
          <span className="text-muted-foreground font-normal">
            {DEPTH}단계 · 노드 {graph.data.nodes.length}
            {truncated ? ' · 일부' : ''}
          </span>
        </h2>
        <Button asChild size="sm" variant="outline">
          <Link to={`/graph?focus=${objectId}`}>
            <Waypoints className="mr-1 size-3.5" />
            지식 그래프에서 넓게
          </Link>
        </Button>
      </div>
      <GraphCanvas
        nodes={nodes}
        links={links}
        className="h-[360px]! min-h-0!"
        exportName="관계도"
        onNodeClick={(id) => {
          if (id === objectId) return
          const path = pathOf.get(id)
          if (path) navigate(path)
        }}
      />
    </section>
  )
}
