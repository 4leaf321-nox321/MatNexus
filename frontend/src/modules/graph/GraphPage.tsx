/**
 * 지식 그래프 — **두 그림, 하나의 규칙: 「전부」 는 없다.** TestScope·StandardPlatform 의 지식
 * 그래프를 옮겨 왔다 — 종류·관계는 MCP 가 걷는 그 정의(`shared/relations.py`)다. 노드 id 는
 * `<종류>:<식별자>`(물성 정의만 키, 나머지는 uuid).
 *
 *
 *   구조   타입이 노드, 관계 종류가 선. 객체가 백만 개여도 노드는 타입 수만큼이다.
 *          선의 굵기가 실제로 걸린 관계 수라서 「어디가 붐비나」 가 여기서 보인다.
 *   탐색   객체 하나에서 출발해 몇 단계를 본다. 서버가 상한(단계·이웃 수·노드 수)을
 *          강제하고, **잘린 자리에는 「+N」 이 붙는다.** 거기서 다시 펼친다.
 *
 * 그림 하나가 모든 것을 담으려 하면 아무것도 안 보인다. 그래서 「전체 보기」 단추가
 * 없다 — 전체는 구조 그림이고, 자세한 것은 탐색 그림에서 한 걸음씩 간다.
 *
 * 탐색 그림은 **여러 번의 응답을 합쳐** 든다(씨앗 + 펼친 것들). 그래서 같은 노드가
 * 두 응답에 있어도 하나로 합치고, 나중 응답의 degree 로 갱신한다.
 *
 * 씨앗은 둘 중 하나다:
 *   focus  객체 하나 — 검색하거나, 타입에서 훑어 고르거나, 상세에서 「그래프에서 보기」
 *   type   한 타입의 인스턴스 전부 — 쪽 단위(서버 상한), 「N개 중 M개」 를 적는다
 */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Boxes,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  Play,
  ExternalLink,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCw,
  Search,
  Share2,
  Waypoints,
  X,
} from 'lucide-react'

import { graphApi } from '@/modules/graph/api'
import type {
  GraphEdge,
  GraphNode,
  Neighborhood,
  Overview,
  Related,
  SearchHit,
  Subgraph,
} from '@/modules/graph/api'
import { colorScale, withAlpha } from '@/modules/graph/colors'
import { GraphCanvas } from '@/modules/graph/GraphCanvas'
import type { CanvasLink, CanvasNode } from '@/modules/graph/GraphCanvas'
import { COMMUNITY_MIN_NODES, useCommunities } from '@/modules/graph/useCommunities'
import { useFillHeight } from '@/modules/graph/useElementSize'
import { useFullscreen } from '@/modules/graph/useFullscreen'
import { useShortcuts } from '@/modules/graph/useShortcuts'
import { LazyPlot } from '@/modules/graph/LazyPlot'
import { ApiError } from '@/shared/api/client'
import { isSystemAdmin } from '@/shared/auth/roles'
import { useAuth } from '@/shared/auth/AuthContext'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'

/**
 * **화면을 꼭 채우고, 스크롤은 기둥마다 하나.** 넓은 화면(lg)에서 그림판은 창 아래까지를
 * 재서(`useFillHeight`) 그만큼만 차지하고, 왼쪽·오른쪽 기둥은 제 안에서 스크롤된다 — 안의
 * 목록마다 스크롤 상자를 두면 상자 셋에 스크롤 셋이 생기고, 그 밖에 화면 스크롤이 또 생겨
 * 어디를 굴려야 하는지 모른다. 좁은 화면에서는 기둥이 아래로 내려가므로 높이를 안 잰다.
 */
const FILL_GRID = 'grid gap-4 lg:h-(--fill) lg:grid-rows-[minmax(0,1fr)]'
const FILL_ASIDE = 'min-h-0 text-sm lg:overflow-y-auto lg:pr-1'
/** 캔버스 자기 높이(`useFillHeight`)를 덮고 기둥을 채운다 — 좁은 화면에서만 제 높이. */
const FILL_CANVAS = 'min-h-[420px] lg:min-h-0 lg:h-auto! lg:flex-1'

type Mode = 'schema' | 'explore'
type ColorBy = 'type' | 'workspace' | 'status' | 'community'

/** 탐색의 씨앗 — 어디서 시작하나. */
export type Seed =
  { kind: 'focus'; id: string } | { kind: 'type'; slugs: string[]; offset: number }

/**
 * 고를 수 있는 값들 — **기본은 낮게, 갈 수 있는 데까지는 넉넉히.**
 *
 * 처음 뜨는 그림은 읽히는 크기여야 하고(그래서 기본이 1단계·30개·300노드), 그 다음에
 * 「더」 를 누르는 사람은 자기가 무엇을 하는지 안다 — 거기서 막으면 그 사람은 답을
 * 못 얻는다. 부품 구성처럼 깊은 사슬은 세 단계로는 안 닿는다.
 *
 * 서버가 같은 상한을 다시 강제한다(`graph/routes.py`) — 화면을 고쳐 큰 수를 보내도
 * 서버는 안 죽는다.
 */
const DEPTHS = [1, 2, 3, 4, 5, 6]
const FANOUTS = [10, 30, 100, 300, 500]
/** 그림에 세울 노드 수. 큰 것을 고르면 느려진다는 말을 화면이 함께 한다. */
const NODE_LIMITS = [300, 800, 1500, 3000, 10000, 20000]
/** 타입별 목록의 한 쪽. */
const BROWSE_PAGE = 20
const FOCUS_RING = '#f59e0b'

/** 탐색 그림이 든 것 — 여러 응답을 합친 결과. */
interface Explored {
  /** 씨앗이 객체였으면 그 id. 타입 전부면 없다. */
  focus: string | null
  nodes: Map<string, GraphNode>
  edges: Map<string, GraphEdge>
  /** 어느 응답이든 하나라도 잘렸으면 참. */
  truncated: boolean
  /** 안내문에 적는 상한. 씨앗 종류에 따라 온 것만 든다. */
  limits: { depth?: number; fanout?: number; node_limit: number }
  /** 타입 전부일 때 — 「N개 중 M개」. `shown` 은 이 쪽에 실린 행 수(확장·숨기기와 무관). */
  page: { total: number; offset: number; limit: number; shown: number } | null
  /** 어느 노드를 펼쳐서 들어왔나(id → 펼친 노드 id). 캔버스가 새 노드를 그 곁에 놓는다. */
  origin: Map<string, string>
}

function mergeNodes(
  previous: Explored | null,
  fresh: { nodes: GraphNode[]; edges: GraphEdge[]; truncated: boolean },
  from: string | null,
) {
  const nodes = new Map(previous?.nodes ?? [])
  const edges = new Map(previous?.edges ?? [])
  const origin = new Map(previous?.origin ?? [])
  for (const node of fresh.nodes) {
    if (from && !nodes.has(node.id) && node.id !== from) origin.set(node.id, from)
    nodes.set(node.id, node)
  }
  for (const edge of fresh.edges) edges.set(edge.id, edge)
  return { nodes, edges, origin, truncated: Boolean(previous?.truncated) || fresh.truncated }
}

function mergeNeighborhood(previous: Explored | null, fresh: Neighborhood): Explored {
  return {
    ...mergeNodes(previous, fresh, previous ? fresh.focus : null),
    focus: previous ? previous.focus : fresh.focus,
    // 확장은 늘 1단계로 부르므로 안내문의 상한은 **첫 응답 것**을 지킨다.
    limits: previous?.limits ?? {
      depth: fresh.depth,
      fanout: fresh.fanout,
      node_limit: fresh.node_limit,
    },
    page: previous?.page ?? null,
  }
}

function fromSubgraph(fresh: Subgraph): Explored {
  return {
    ...mergeNodes(null, fresh, null),
    focus: null,
    limits: { node_limit: fresh.limit },
    page: {
      total: fresh.total,
      offset: fresh.offset,
      limit: fresh.limit,
      shown: fresh.nodes.length,
    },
  }
}

/** 탐색의 조작 상태 — 주소에 남겨 **붙여 넣으면 같은 그림**이 선다(ReportArchive Phase 3). */
interface Controls {
  depth: number
  fanout: number
  /** 그림에 세울 노드 상한. 서버가 여기서 자르고 **잘랐다고 말한다.** */
  nodeLimit: number
  relations: Set<string>
  types: Set<string>
  colorBy: ColorBy
  /** 관계 없는 노드를 숨긴다 — 타입 전부를 그릴 때 잎만 수백 개면 아무것도 안 보인다. */
  hideIsolated: boolean
}

const CONTROL_KEYS = {
  depth: 'd',
  fanout: 'fo',
  nodeLimit: 'n',
  relations: 'rel',
  types: 'ty',
  colorBy: 'color',
  hideIsolated: 'iso',
}

function controlsFromParams(params: URLSearchParams): Controls {
  const csv = (raw: string | null) => new Set((raw ?? '').split(',').filter(Boolean))
  const depth = Number(params.get(CONTROL_KEYS.depth))
  const fanout = Number(params.get(CONTROL_KEYS.fanout))
  const nodeLimit = Number(params.get(CONTROL_KEYS.nodeLimit))
  return {
    depth: DEPTHS.includes(depth) ? depth : 1,
    fanout: FANOUTS.includes(fanout) ? fanout : 30,
    nodeLimit: NODE_LIMITS.includes(nodeLimit) ? nodeLimit : NODE_LIMITS[0],
    relations: csv(params.get(CONTROL_KEYS.relations)),
    types: csv(params.get(CONTROL_KEYS.types)),
    colorBy:
      (['workspace', 'status', 'community'] as const).find(
        (one) => one === params.get(CONTROL_KEYS.colorBy),
      ) ?? 'type',
    hideIsolated: params.get(CONTROL_KEYS.hideIsolated) === '1',
  }
}

function writeControls(params: URLSearchParams, controls: Controls): void {
  const put = (key: string, value: string, isDefault: boolean) => {
    if (isDefault) params.delete(key)
    else params.set(key, value)
  }
  put(CONTROL_KEYS.depth, String(controls.depth), controls.depth === 1)
  put(CONTROL_KEYS.fanout, String(controls.fanout), controls.fanout === 30)
  put(
    CONTROL_KEYS.nodeLimit,
    String(controls.nodeLimit),
    controls.nodeLimit === NODE_LIMITS[0],
  )
  put(CONTROL_KEYS.relations, [...controls.relations].join(','), controls.relations.size === 0)
  put(CONTROL_KEYS.types, [...controls.types].join(','), controls.types.size === 0)
  put(CONTROL_KEYS.colorBy, controls.colorBy, controls.colorBy === 'type')
  put(CONTROL_KEYS.hideIsolated, '1', !controls.hideIsolated)
}

function seedFromParams(params: URLSearchParams): Seed | null {
  const focus = params.get('focus')
  if (focus) return { kind: 'focus', id: focus }
  const type = params.get('type')
  if (type) return { kind: 'type', slugs: type.split(',').filter(Boolean), offset: 0 }
  return null
}

/** 화면에 실린 선의 수를 노드마다 센다 — 「+N」 의 N 은 degree 에서 이것을 뺀 것이다. */
function shownDegrees(edges: Iterable<GraphEdge>): Map<string, number> {
  const counts = new Map<string, number>()
  for (const edge of edges) {
    counts.set(edge.src, (counts.get(edge.src) ?? 0) + 1)
    if (edge.dst !== edge.src) counts.set(edge.dst, (counts.get(edge.dst) ?? 0) + 1)
  }
  return counts
}

export default function GraphPage() {
  const { user } = useAuth()
  // 전체화면이 덮을 것 — 그림과 옆 판을 함께.
  const shellRef = useRef<HTMLDivElement>(null)
  const fullscreen = useFullscreen(shellRef)
  const [params, setParams] = useSearchParams()
  // **주소가 곧 상태다.** 씨앗과 조작을 따로 들고 있으면 사이드바에서 같은 화면으로 다시
  // 올 때(재마운트 없음) 옛 그림이 남는다. 쪽(offset)만은 주소에 안 적어 여기 든다.
  // 값이 같으면 같은 객체여야 한다 — 매번 새 객체면 색 기준만 바꿔도 그림을 다시 읽는다.
  const focusParam = params.get('focus')
  const typeParam = params.get('type')
  const urlSeed = useMemo(
    () =>
      seedFromParams(
        new URLSearchParams({
          ...(focusParam ? { focus: focusParam } : {}),
          ...(typeParam ? { type: typeParam } : {}),
        }),
      ),
    [focusParam, typeParam],
  )
  const [offset, setOffset] = useState(0)
  const seed = useMemo<Seed | null>(
    () => (urlSeed?.kind === 'type' ? { ...urlSeed, offset } : urlSeed),
    [urlSeed, offset],
  )
  const controlsKey = Object.values(CONTROL_KEYS)
    .map((key) => params.get(key) ?? '')
    .join('\u0000')
  const controls = useMemo(
    () => controlsFromParams(params),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [controlsKey],
  )
  const [mode, setMode] = useState<Mode>(seed ? 'explore' : 'schema')
  useEffect(() => {
    if (urlSeed) setMode('explore')
  }, [urlSeed])

  const setControls = useCallback(
    (patch: Partial<Controls>) => {
      setParams(
        (current) => {
          const query = new URLSearchParams(current)
          writeControls(query, { ...controlsFromParams(current), ...patch })
          return query
        },
        { replace: true },
      )
    },
    [setParams],
  )

  const setSeed = useCallback(
    (next: Seed | null) => {
      setOffset(next?.kind === 'type' ? next.offset : 0)
      setParams(
        (current) => {
          const query = new URLSearchParams(current)
          query.delete('focus')
          query.delete('type')
          if (next?.kind === 'focus') query.set('focus', next.id)
          if (next?.kind === 'type') query.set('type', next.slugs.join(','))
          return query
        },
        { replace: true },
      )
    },
    [setParams],
  )

  const overview = useResource(() => graphApi.overview(), [])
  // 종류·관계 종류는 구조 응답이 곧 정의다 — 온톨로지 표가 따로 없다(graph/model.py).
  const types = useMemo(
    () =>
      (overview.data?.nodes ?? []).map((one) => ({
        slug: one.slug,
        label: one.label,
        is_active: true,
        object_count: one.count,
      })),
    [overview.data],
  )
  const relationTypes = useMemo(() => {
    const seen = new Map<string, { slug: string; label: string; is_active: boolean }>()
    for (const edge of overview.data?.edges ?? []) {
      if (!seen.has(edge.relation)) {
        seen.set(edge.relation, { slug: edge.relation, label: edge.label, is_active: true })
      }
    }
    return [...seen.values()]
  }, [overview.data])

  // 종류 색은 정의 순서로 — 구조 그림과 탐색 그림이 **같은 색**을 쓴다.
  const typeColor = useMemo(() => colorScale(types.map((one) => one.slug)), [types])
  const typeLabel = useMemo(() => new Map(types.map((one) => [one.slug, one.label])), [types])

  return (
    /**
     * 전체화면은 **이 화면 전체**다 — 그림만 덮으면 옆의 고르개와 상세 판이 사라져,
     * 여럿을 고르고 하나를 골라 읽는 일이 안 된다. 그래프의 쓸모가 거기 있다.
     *
     * `fixed` 는 브라우저가 전체화면을 거절했을 때의 버팀목이다. 안쪽은 스크롤되게
     * 둔다 — 좁은 화면에서는 옆 판이 아래로 내려간다.
     */
    <div
      ref={shellRef}
      className={
        fullscreen.active
          ? 'bg-background fixed inset-0 z-50 space-y-4 overflow-auto p-4'
          : 'space-y-4'
      }
    >
      <PageHeader
        title="지식 그래프"
        description="재료·시료·시편·시험·처리 결과·물성 카드·문헌·출처·장비·의뢰·부서가 어떻게 이어지는지(구조), 그리고 하나의 주변에 무엇이 있는지(탐색). AI(MCP)가 걷는 지도와 같은 정의입니다."
        actions={
          <Tabs value={mode} onValueChange={(value) => setMode(value as Mode)}>
            <TabsList>
              <TabsTrigger value="schema">구조</TabsTrigger>
              <TabsTrigger value="explore">탐색</TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />

      {mode === 'schema' ? (
        <SchemaView
          wide={fullscreen.active}
          onToggleWide={fullscreen.toggle}
          overview={overview.data}
          error={overview.error}
          loading={overview.loading}
          typeColor={typeColor}
          canDefine={isSystemAdmin(user)}
          onDrawType={(slug) => {
            setSeed({ kind: 'type', slugs: [slug], offset: 0 })
            setMode('explore')
          }}
        />
      ) : (
        <ExploreView
          wide={fullscreen.active}
          onToggleWide={fullscreen.toggle}
          seed={seed}
          onSeed={setSeed}
          controls={controls}
          onControls={setControls}
          typeColor={typeColor}
          typeLabel={typeLabel}
          relationTypes={relationTypes}
          types={types}
        />
      )}
    </div>
  )
}

// --- 구조 ---------------------------------------------------------------------

interface SchemaViewProps {
  /** 전체화면은 이 화면 전체가 맡는다 — 캔버스는 단추만 그린다. */
  wide: boolean
  onToggleWide: () => void
  overview: Overview | null
  error: ApiError | Error | null
  loading: boolean
  typeColor: (slug: string) => string
  canDefine: boolean
  /** 이 타입의 인스턴스 전부를 탐색 그림에 그린다. */
  onDrawType: (slug: string) => void
}

function SchemaView({
  wide,
  onToggleWide,
  overview,
  error,
  loading,
  typeColor,
  canDefine,
  onDrawType,
}: SchemaViewProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const [shape, setShape] = useState<'web' | 'flow'>('web')
  const gridRef = useRef<HTMLDivElement>(null)
  const fill = useFillHeight(gridRef, { min: 480 })

  /** 사케이로 볼 정의 — 노드는 타입, 선은 **실제로 걸린** 관계의 수.
   *
   * 정의만 있고 아무것도 안 이어진 관계는 여기서 뺀다. 흐름 그림에서 굵기 0 인
   * 선은 없는 것과 같은데, 자리는 차지해서 남은 줄기를 눌러 놓는다.
   *
   * **되돌아오는 선은 못 그린다.** plotly 의 사케이는 순환을 거부한다(그림이
   * 왼쪽에서 오른쪽으로 한 번 흐른다는 전제 위에 서 있다). 그래서 굵은 것부터
   * 넣고 순환을 만드는 것만 뺀다 — 굵은 줄기가 남아야 그림이 말이 된다. 뺀 수는
   * 세어서 화면에 적는다: 조용히 빼면 그림이 「그 관계는 없다」 고 거짓말한다.
   */
  const flow = useMemo(() => {
    const nodes = overview?.nodes ?? []
    const at = new Map(nodes.map((one, index) => [one.slug, index]))
    const source: number[] = []
    const target: number[] = []
    const value: number[] = []
    const label: string[] = []
    const color: string[] = []
    let dropped = 0

    const reaches = (from: number, goal: number): boolean => {
      const seen = new Set<number>([from])
      const queue = [from]
      while (queue.length > 0) {
        const here = queue.shift() as number
        if (here === goal) return true
        source.forEach((one, index) => {
          if (one === here && !seen.has(target[index])) {
            seen.add(target[index])
            queue.push(target[index])
          }
        })
      }
      return false
    }

    const edges = [...(overview?.edges ?? [])]
      .filter((one) => one.count > 0)
      .sort((a, b) => b.count - a.count)
    for (const one of edges) {
      const from = at.get(one.src_type)
      const to = at.get(one.dst_type)
      if (from === undefined || to === undefined) continue
      if (from === to || reaches(to, from)) {
        dropped += 1
        continue
      }
      source.push(from)
      target.push(to)
      value.push(one.count)
      label.push(one.label)
      color.push(withAlpha(typeColor(one.src_type), 0.35))
    }

    return {
      node: {
        label: nodes.map((one) => one.label),
        color: nodes.map((one) => typeColor(one.slug)),
        pad: 14,
        thickness: 14,
        line: { width: 0 },
      },
      links: { source, target, value, label, color },
      dropped,
    }
  }, [overview, typeColor])

  const { nodes, links } = useMemo(() => {
    if (!overview) return { nodes: [] as CanvasNode[], links: [] as CanvasLink[] }
    const maxCount = Math.max(1, ...overview.nodes.map((one) => one.count))
    const maxEdge = Math.max(1, ...overview.edges.map((one) => one.count))
    return {
      nodes: overview.nodes.map((one): CanvasNode => ({
        id: one.slug,
        label: one.label,
        sublabel: `${one.count.toLocaleString()}개`,
        card: [one.label, `${one.count.toLocaleString()}개 · 더블클릭: 이 종류 전체 그리기`],
        color: one.count === 0 ? withAlpha(typeColor(one.slug), 0.35) : typeColor(one.slug),
        // 객체 수에 비례하되 sqrt 로 완만하게 — 1개와 1만 개가 백 배 차이 나면 작은 것이 안 보인다.
        radius: 7 + Math.sqrt(one.count / maxCount) * 12,
        shape: 'square',
      })),
      links: overview.edges.map((one): CanvasLink => ({
        id: `${one.relation}:${one.src_type}:${one.dst_type}`,
        source: one.src_type,
        target: one.dst_type,
        label: one.count
          ? `${one.label} · ${one.count.toLocaleString()}`
          : `${one.label} · 비어 있음`,
        directed: one.directed,
        width: one.count ? 1 + (one.count / maxEdge) * 5 : 1,
        dashed: one.count === 0,
      })),
    }
  }, [overview, typeColor])

  const picked = overview?.nodes.find((one) => one.slug === selected) ?? null
  const pickedEdges = useMemo(
    () =>
      (overview?.edges ?? []).filter(
        (one) => one.src_type === selected || one.dst_type === selected,
      ),
    [overview, selected],
  )

  if (error) return <ErrorNotice error={error} />
  if (!loading && overview && overview.nodes.length === 0) {
    return (
      <EmptyState
        title="그릴 종류가 없습니다"
        hint={
          canDefine
            ? '재료·시험이 들어오면 여기 구조가 그려집니다.'
            : '재료·시험이 등록되면 여기 구조가 그려집니다.'
        }
        action={
          canDefine ? (
            <Button asChild size="sm" variant="outline">
              <Link to="/materials">
                <Boxes className="mr-1 size-4" />
                재료 열기
              </Link>
            </Button>
          ) : undefined
        }
      />
    )
  }

  return (
    <div
      ref={gridRef}
      style={{ '--fill': `${fill}px` } as CSSProperties}
      className={`${FILL_GRID} lg:grid-cols-[1fr_280px]`}
    >
      {/* **같은 정의를 두 모양으로 본다.** 그물은 「무엇이 무엇과 이어지나」 를, 흐름은
          「어디서 어디로 얼마나 가나」 를 보여 준다 — 관계가 단계로 이어지는 구조
          (접수 → 검토 → 승인)는 그물에서 잘 안 읽힌다. */}
      {shape === 'flow' ? (
        <div className="relative min-h-0 rounded-md border p-2 lg:overflow-y-auto">
          {/* **나갈 길은 어느 모양에서나 있어야 한다.** 전체화면에서 흐름으로 넘어온
              사람에게 축소 단추가 없으면, 브라우저가 전체화면을 거절한 경우 ESC 도
              안 먹어 갇힌다. */}
          <div className="absolute top-2 left-2 z-10 flex items-center gap-1">
            <Button
              size="sm"
              variant="outline"
              className="bg-background/90 backdrop-blur"
              onClick={() => setShape('web')}
            >
              <Share2 className="mr-1 size-3.5" />
              그물로
            </Button>
            <Button
              size="icon-sm"
              variant="outline"
              className="bg-background/90 backdrop-blur"
              aria-label={wide ? '축소' : '넓게 보기'}
              title={wide ? '축소' : '넓게 보기'}
              onClick={onToggleWide}
            >
              {wide ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
            </Button>
          </div>
          {flow.links.source.length === 0 ? (
            <p className="text-muted-foreground py-16 text-center text-sm">
              이어진 관계가 아직 없습니다 — 흐름은 <strong>실제 연결된</strong> 관계가 있어야
              그려집니다. 정의만 있는 관계는 굵기가 없어 그릴 것이 없습니다.
            </p>
          ) : (
            <LazyPlot
              height={520}
              title="종류 사이의 흐름"
              data={[{ type: 'sankey', node: flow.node, link: flow.links }]}
              layout={{ margin: { t: 44, r: 16, b: 16, l: 16 }, showlegend: false }}
            />
          )}
          {flow.dropped > 0 && (
            <p className="text-muted-foreground px-2 pb-1 text-xs">
              되돌아오는 관계 {flow.dropped}개는 흐름에서 뺐습니다 — 흐름 그림은 한 방향으로만
              흐릅니다. 그 관계들은 <strong>그물</strong>에서 보입니다.
            </p>
          )}
        </div>
      ) : (
        <GraphCanvas
          className={FILL_CANVAS}
          nodes={nodes}
          links={links}
          wide={wide}
          onToggleWide={onToggleWide}
          linkLabels
          selectedId={selected}
          onNodeClick={setSelected}
          onNodeDoubleClick={(slug) => {
            if ((overview?.nodes.find((one) => one.slug === slug)?.count ?? 0) > 0)
              onDrawType(slug)
          }}
          onBackgroundClick={() => setSelected(null)}
          onEscape={() => setSelected(null)}
          exportName="구조"
          overlay={
            <>
              {/* **그물에서는 단계가 안 읽힌다.** 접수 → 검토 → 승인처럼 한 방향으로
                  이어지는 구조는 흐름에서 한눈에 보인다. 이을 관계가 하나도 없으면
                  단추를 안 낸다 — 눌러서 빈 그림을 보는 일은 없는 편이 낫다. */}
              {flow.links.source.length > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  className="bg-background/90 absolute top-2 left-2 z-10 backdrop-blur"
                  onClick={() => setShape('flow')}
                >
                  <Waypoints className="mr-1 size-3.5" />
                  흐름으로
                </Button>
              )}
              {loading && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Loader2 className="text-muted-foreground size-5 animate-spin" />
                </div>
              )}
              {overview && (
                <div className="text-muted-foreground bg-background/80 absolute bottom-2 left-2 rounded px-2 py-1 text-xs">
                  종류 {overview.nodes.length} · 관계 종류 {overview.edges.length} · 객체{' '}
                  {overview.object_count.toLocaleString()} · 관계{' '}
                  {overview.edge_count.toLocaleString()}
                </div>
              )}
            </>
          }
        />
      )}
      <aside className={`${FILL_ASIDE} space-y-3`}>
        {picked ? (
          <div className="space-y-3 rounded-md border p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block size-3 shrink-0 rounded-sm"
                    style={{ background: typeColor(picked.slug) }}
                  />
                  <span className="font-medium">{picked.label}</span>
                </div>
                <p className="text-muted-foreground mt-0.5 font-mono text-xs">{picked.slug}</p>
              </div>
              <Button size="icon-sm" variant="ghost" onClick={() => setSelected(null)}>
                <X className="size-4" />
              </Button>
            </div>
            <p>
              객체 <strong>{picked.count.toLocaleString()}</strong>개
            </p>
            {pickedEdges.length > 0 && (
              <ul className="space-y-1">
                {pickedEdges.map((edge) => (
                  <li
                    key={`${edge.relation}:${edge.src_type}:${edge.dst_type}`}
                    className="text-muted-foreground flex justify-between gap-2"
                  >
                    <span className="truncate">
                      {edge.src_type === picked.slug ? '→' : '←'} {edge.label}{' '}
                      <span className="opacity-70">
                        ({edge.src_type === picked.slug ? edge.dst_type : edge.src_type})
                      </span>
                    </span>
                    <span className="shrink-0 tabular-nums">
                      {edge.count.toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-2">
              {picked.detail_path && (
                <Button asChild size="sm" variant="outline">
                  <Link to={picked.detail_path}>
                    <ExternalLink className="mr-1 size-3.5" />
                    목록 보기
                  </Link>
                </Button>
              )}
              {/* 채운 색 — 테두리만 있으면 표제처럼 읽혀 누를 수 있다는 것을 모른다. */}
              <Button
                size="sm"
                disabled={picked.count === 0}
                onClick={() => onDrawType(picked.slug)}
              >
                <Play className="mr-1 size-3.5" />이 종류 전체 그리기
              </Button>
            </div>
          </div>
        ) : (
          <div className="text-muted-foreground rounded-md border border-dashed p-3">
            종류를 클릭하면 연결된 관계와 수가 나오고, 그 종류의 객체 전부를 그릴 수 있습니다.
            점선은 정의만 있고 아직 아무것도 안 이어진 관계입니다.
          </div>
        )}
      </aside>
    </div>
  )
}

// --- 탐색 ---------------------------------------------------------------------

interface ExploreViewProps {
  /** 전체화면은 이 화면 전체가 맡는다 — 캔버스는 단추만 그린다. */
  wide: boolean
  onToggleWide: () => void
  seed: Seed | null
  onSeed: (seed: Seed | null) => void
  controls: Controls
  onControls: (patch: Partial<Controls>) => void
  typeColor: (slug: string) => string
  typeLabel: Map<string, string>
  relationTypes: { slug: string; label: string; is_active: boolean }[]
  types: { slug: string; label: string; is_active: boolean; object_count: number }[]
}

function ExploreView({
  wide,
  onToggleWide,
  seed,
  onSeed,
  controls,
  onControls,
  typeColor,
  typeLabel,
  relationTypes,
  types,
}: ExploreViewProps) {
  const gridRef = useRef<HTMLDivElement>(null)
  const fill = useFillHeight(gridRef, { min: 480 })
  const {
    depth,
    fanout,
    nodeLimit,
    relations: relationFilter,
    types: typeFilter,
    colorBy,
    hideIsolated,
  } = controls
  const setDepth = (value: number) => onControls({ depth: value })
  const setFanout = (value: number) => onControls({ fanout: value })
  const setNodeLimit = (value: number) => onControls({ nodeLimit: value })
  const setRelationFilter = (value: Set<string>) => onControls({ relations: value })
  const setTypeFilter = (value: Set<string>) => onControls({ types: value })
  const setColorBy = (value: ColorBy) => onControls({ colorBy: value })
  /** 새로고침 — 같은 씨앗을 다시 든다. 다른 화면에서 관계를 이은 뒤 돌아왔을 때. */
  const [reloadTick, setReloadTick] = useState(0)
  /** 목록에서 고른 노드로 찾아가기. nonce 로 같은 노드도 다시. */
  const [centerOn, setCenterOn] = useState<{ id: string; nonce: number } | null>(null)
  const findRef = useRef<HTMLInputElement>(null)
  const [explored, setExplored] = useState<Explored | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)

  const query = useCallback(
    (id: string, depthOverride?: number) =>
      graphApi.neighborhood({
        focus: id,
        depth: depthOverride ?? depth,
        fanout,
        limit: nodeLimit,
        relations: [...relationFilter],
        types: [...typeFilter],
      }),
    [depth, fanout, nodeLimit, relationFilter, typeFilter],
  )

  // 씨앗·상한·필터가 바뀌면 **처음부터 다시** 든다. 펼쳐 둔 것은 버린다 —
  // 필터가 바뀐 뒤에도 옛 노드가 남아 있으면 그 그림은 무엇을 거른 것인지 말할 수 없다.
  // 진행 중인 요청의 세대. 씨앗·필터가 바뀌면 올라가고, 늦게 온 응답은 버린다 —
  // 안 버리면 필터를 바꾼 뒤에 옛 확장 응답이 걸러 낸 노드를 도로 넣는다.
  const generation = useRef(0)
  useEffect(() => {
    generation.current += 1
    if (!seed) {
      setExplored(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    const request =
      seed.kind === 'focus'
        ? query(seed.id).then((fresh) => mergeNeighborhood(null, fresh))
        : graphApi
            .subgraph({
              types: seed.slugs,
              relations: [...relationFilter],
              // 「한 타입 전부」 도 같은 상한을 쓴다 — 화면에서 고른 값이 여기만
              // 안 먹으면 「왜 저기서는 3,000개가 되고 여기서는 안 되지」 가 된다.
              limit: nodeLimit,
              offset: seed.offset,
            })
            .then(fromSubgraph)
    request
      .then((fresh) => {
        if (cancelled) return
        setExplored(fresh)
        setSelected(fresh.focus)
      })
      .catch((caught: unknown) => {
        if (!cancelled)
          setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [seed, query, relationFilter, reloadTick])

  const pickFocus = (id: string | null) => onSeed(id ? { kind: 'focus', id } : null)

  /** 노드에서 한 단계 더 — 이미 든 것에 합친다. */
  const expand = async (id: string) => {
    const mine = generation.current
    setLoading(true)
    setError(null)
    try {
      const fresh = await query(id, 1)
      if (generation.current !== mine) return // 그새 씨앗·필터가 바뀌었다 — 이 응답은 옛것
      setExplored((previous) => (previous ? mergeNeighborhood(previous, fresh) : previous))
    } catch (caught: unknown) {
      if (generation.current === mine) {
        setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
      }
    } finally {
      if (generation.current === mine) setLoading(false)
    }
  }

  const edgeList = useMemo(() => [...(explored?.edges.values() ?? [])], [explored])
  const shown = useMemo(() => shownDegrees(edgeList), [edgeList])
  const allNodes = useMemo(() => [...(explored?.nodes.values() ?? [])], [explored])
  // 관계 없는 것 숨기기 — 화면에 선이 하나도 안 닿는 노드. 시작점은 늘 남긴다.
  const nodeList = useMemo(
    () =>
      hideIsolated
        ? allNodes.filter((one) => one.id === explored?.focus || (shown.get(one.id) ?? 0) > 0)
        : allNodes,
    [allNodes, hideIsolated, shown, explored?.focus],
  )
  const isolatedCount = allNodes.length - nodeList.length
  const nodeIds = useMemo(() => nodeList.map((one) => one.id), [nodeList])
  const communities = useCommunities(nodeIds, edgeList, colorBy === 'community')
  const [findText, setFindText] = useState('')

  // 그림 안 검색 — 매칭만 또렷. 노드가 200개면 이름을 눈으로 못 찾는다.
  const matchIds = useMemo(() => {
    const needle = findText.trim().toLowerCase()
    if (!needle) return null
    return new Set(
      nodeList
        .filter((one) => `${one.label} ${one.key ?? ''}`.toLowerCase().includes(needle))
        .map((one) => one.id),
    )
  }, [findText, nodeList])

  // 노드 색 — 색 기준별 키와 라벨. 부서·상태는 그림에 있는 값의 순서로 색을 받는다.
  const nodeCategory = useCallback(
    (one: GraphNode): { key: string; label: string } => {
      if (colorBy === 'workspace') {
        return one.owner_workspace_slug
          ? { key: one.owner_workspace_slug, label: one.owner_workspace_slug }
          : { key: '__none__', label: '부서 없음' }
      }
      if (colorBy === 'status') return { key: one.status, label: one.status }
      return { key: one.type_slug, label: one.type_label }
    },
    [colorBy],
  )
  const categoryScale = useMemo(() => {
    if (colorBy === 'type') return typeColor
    const keys: string[] = []
    for (const one of nodeList) {
      const { key } = nodeCategory(one)
      if (!keys.includes(key)) keys.push(key)
    }
    return colorScale(keys)
  }, [colorBy, typeColor, nodeList, nodeCategory])
  const nodeColorOf = useCallback(
    (one: GraphNode) =>
      communities.ready ? communities.colorOf(one.id) : categoryScale(nodeCategory(one).key),
    [communities, categoryScale, nodeCategory],
  )

  // 선 색 — 관계 종류가 둘 이상일 때만 종류별로. 하나뿐이면 회색이 덜 시끄럽다.
  const relationScale = useMemo(() => {
    const slugs: string[] = []
    for (const one of edgeList) if (!slugs.includes(one.relation)) slugs.push(one.relation)
    return slugs.length > 1 ? colorScale(slugs) : null
  }, [edgeList])

  // 범례 — 그림에 실제로 있는 범주만. 노드 범주는 눌러서 「그것만 또렷」.
  const [legendActive, setLegendActive] = useState<string | null>(null)
  // 색 기준이나 씨앗이 바뀌면 범례의 키가 다른 것이 된다 — 옛 키로 거르면 전부 흐려진다.
  useEffect(() => {
    setLegendActive(null)
  }, [colorBy, seed, communities.ready])
  const legend = useMemo(() => {
    const items: { color: string; label: string; key?: string; line?: boolean }[] = []
    if (!communities.ready) {
      const seen = new Map<string, string>()
      for (const one of nodeList) {
        const { key, label } = nodeCategory(one)
        if (!seen.has(key)) seen.set(key, label)
      }
      for (const [key, label] of seen) items.push({ color: categoryScale(key), label, key })
    }
    if (relationScale) {
      const seen = new Map<string, string>()
      for (const one of edgeList)
        if (!seen.has(one.relation)) seen.set(one.relation, one.label)
      for (const [slug, label] of seen)
        items.push({ color: relationScale(slug), label, line: true })
    }
    return items
  }, [nodeList, edgeList, communities.ready, nodeCategory, categoryScale, relationScale])
  const legendMatch = useMemo(() => {
    if (!legendActive) return null
    return new Set(
      nodeList.filter((one) => nodeCategory(one).key === legendActive).map((one) => one.id),
    )
  }, [legendActive, nodeList, nodeCategory])

  const { nodes, links } = useMemo(() => {
    const maxDegree = Math.max(1, ...nodeList.map((one) => one.degree))
    const visible = new Set(nodeList.map((one) => one.id))
    return {
      nodes: nodeList.map((one): CanvasNode => {
        const hidden = one.degree - (shown.get(one.id) ?? 0)
        return {
          id: one.id,
          label: one.label,
          sublabel: one.type_label,
          card: [
            one.label,
            `${one.type_label}${one.key ? ` · ${one.key}` : ''}`,
            `관계 ${one.degree}개${hidden > 0 ? ` · 화면에 없는 것 ${hidden}` : ''}`,
            '클릭: 선택 · 더블클릭: 여기를 중심으로',
          ],
          color: nodeColorOf(one),
          radius: 4 + Math.sqrt(one.degree / maxDegree) * 6,
          shape: 'circle',
          ring: one.id === explored?.focus ? FOCUS_RING : null,
          badge: hidden > 0 ? `+${hidden}` : null,
          near: explored?.origin.get(one.id) ?? null,
          hull: communities.ready ? communities.keyOf(one.id) : null,
          hullColor: communities.ready ? communities.colorOf(one.id) : undefined,
        }
      }),
      links: edgeList
        .filter((one) => visible.has(one.src) && visible.has(one.dst))
        .map((one): CanvasLink => ({
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
          color: relationScale ? relationScale(one.relation) : undefined,
        })),
    }
  }, [
    nodeList,
    edgeList,
    shown,
    communities,
    nodeColorOf,
    relationScale,
    explored?.focus,
    explored?.origin,
  ])

  const picked = selected ? (explored?.nodes.get(selected) ?? null) : null
  const pickedHidden = picked ? picked.degree - (shown.get(picked.id) ?? 0) : 0

  /** 목록에서 선택 — 선택하고 카메라도 옮긴다. 캔버스 클릭과 달리 어디 있는지 모르니까. */
  const selectAndGo = useCallback((id: string) => {
    setSelected(id)
    setCenterOn((current) => ({ id, nonce: (current?.nonce ?? 0) + 1 }))
  }, [])

  const hostShortcuts = useMemo(
    () => [
      { keys: 'Enter', what: '고른 노드에서 확장' },
      { keys: 'Shift+Enter', what: '고른 노드를 중심으로' },
      { keys: '/', what: '그림 안에서 검색' },
      { keys: 'R', what: '새로고침' },
    ],
    [],
  )
  useShortcuts(
    useMemo(
      () => ({
        Enter: () => {
          if (picked && pickedHidden > 0 && !loading) void expand(picked.id)
        },
        'shift+Enter': () => {
          if (picked && picked.id !== explored?.focus) pickFocus(picked.id)
        },
        '/': (event) => {
          event.preventDefault()
          findRef.current?.focus()
        },
        r: () => {
          if (seed) setReloadTick((value) => value + 1)
        },
        R: () => {
          if (seed) setReloadTick((value) => value + 1)
        },
      }),
      // expand·pickFocus 는 매 렌더 새 함수라 그대로 적는다 — 빼면 옛 필터로 펼친다.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [picked, pickedHidden, loading, explored?.focus, seed, expand, pickFocus],
    ),
    Boolean(seed),
  )

  const toggle = (set: Set<string>, value: string, update: (next: Set<string>) => void) => {
    const next = new Set(set)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    update(next)
  }

  return (
    <div
      ref={gridRef}
      style={{ '--fill': `${fill}px` } as CSSProperties}
      className={`${FILL_GRID} lg:grid-cols-[260px_1fr_280px]`}
    >
      {/* 왼쪽 — 시작점과 상한 */}
      <aside className={`${FILL_ASIDE} space-y-4`}>
        <SeedPanel
          seed={seed}
          current={explored?.focus ? (explored.nodes.get(explored.focus) ?? null) : null}
          types={types}
          typeLabel={typeLabel}
          onPick={(id) => pickFocus(id)}
          onDrawTypes={(slugs) => onSeed({ kind: 'type', slugs, offset: 0 })}
          onClear={() => onSeed(null)}
        />

        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <span className="text-muted-foreground text-xs">단계</span>
            <Select value={String(depth)} onValueChange={(value) => setDepth(Number(value))}>
              <SelectTrigger size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEPTHS.map((one) => (
                  <SelectItem key={one} value={String(one)}>
                    {one}단계
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <label className="space-y-1">
            <span className="text-muted-foreground text-xs">노드당 이웃</span>
            <Select value={String(fanout)} onValueChange={(value) => setFanout(Number(value))}>
              <SelectTrigger size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {FANOUTS.map((one) => (
                  <SelectItem key={one} value={String(one)}>
                    {one}개까지
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <label className="col-span-2 space-y-1">
            <span className="text-muted-foreground text-xs">그림에 세울 노드</span>
            <Select
              value={String(nodeLimit)}
              onValueChange={(value) => setNodeLimit(Number(value))}
            >
              <SelectTrigger size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {NODE_LIMITS.map((one) => (
                  <SelectItem key={one} value={String(one)}>
                    {one === NODE_LIMITS[NODE_LIMITS.length - 1]
                      ? `전부 (${one.toLocaleString()}개까지)`
                      : `${one.toLocaleString()}개까지`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* **많이 고르면 느려진다는 말을 미리 한다.** 느려진 뒤에 알게 되면 사람은
                그것을 고장으로 읽고, 다음부터 이 화면을 안 연다. */}
            {nodeLimit > NODE_LIMITS[1] && (
              <span className="text-muted-foreground block text-xs">
                수천 개를 한 그림에 두면 배치가 느려집니다 — 1만 개가 넘으면 자리 잡는 데 수십
                초가 걸릴 수 있습니다. 필터로 좁히는 편이 대개 빠르고 잘 읽힙니다.
              </span>
            )}
          </label>
        </div>

        <FilterList
          title="관계 종류"
          options={relationTypes.filter((one) => one.is_active)}
          picked={relationFilter}
          onToggle={(slug) => toggle(relationFilter, slug, setRelationFilter)}
          onClear={() => setRelationFilter(new Set())}
        />
        <FilterList
          title="이웃 종류"
          options={types.filter((one) => one.is_active)}
          picked={typeFilter}
          onToggle={(slug) => toggle(typeFilter, slug, setTypeFilter)}
          onClear={() => setTypeFilter(new Set())}
          swatch={typeColor}
        />

        <label className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded px-1 py-0.5">
          <input
            type="checkbox"
            className="size-3.5"
            checked={hideIsolated}
            onChange={(event) => onControls({ hideIsolated: event.target.checked })}
          />
          <span>
            관계 없는 것 숨기기
            {isolatedCount > 0 && (
              <span className="text-muted-foreground ml-1 text-xs">
                ({isolatedCount}개 숨김)
              </span>
            )}
          </span>
        </label>

        <label className="space-y-1">
          <span className="text-muted-foreground text-xs">색</span>
          <Select value={colorBy} onValueChange={(value) => setColorBy(value as ColorBy)}>
            <SelectTrigger size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="type">종류별</SelectItem>
              <SelectItem value="workspace">부서별 (재료·시험·장비)</SelectItem>
              <SelectItem value="status">상태별</SelectItem>
              <SelectItem value="community">
                무리별
                {nodeList.length < COMMUNITY_MIN_NODES
                  ? ` (노드 ${COMMUNITY_MIN_NODES}개부터)`
                  : ''}
              </SelectItem>
            </SelectContent>
          </Select>
        </label>
      </aside>

      {/* 가운데 — 그림 */}
      <div className="flex min-h-0 flex-col gap-2">
        {error && <ErrorNotice error={error} />}
        {seed && (
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="text-muted-foreground absolute top-2 left-2 size-4" />
              <Input
                ref={findRef}
                value={findText}
                onChange={(event) => setFindText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    setFindText('')
                    event.currentTarget.blur()
                  }
                }}
                placeholder="그림 안에서 검색 (/) — 맞는 노드만 또렷하게"
                className="pl-8"
                disabled={nodeList.length < 2}
              />
              {matchIds && (
                <span className="text-muted-foreground absolute top-2 right-2 text-xs">
                  {matchIds.size}개
                </span>
              )}
            </div>
            <Button
              size="icon-sm"
              variant="outline"
              aria-label="새로고침"
              title="같은 씨앗을 다시 읽기 (R)"
              disabled={loading}
              onClick={() => setReloadTick((value) => value + 1)}
            >
              <RotateCw className={`size-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        )}
        {!seed ? (
          <EmptyState
            title="시작점을 선택하세요"
            hint="왼쪽에서 이름으로 찾거나(재료·시험·물성·문헌 …), 종류에서 훑어 고르거나, 한 종류를 전부 그립니다. 모든 종류를 한 번에 그리는 단추는 없습니다 — 전체 모양은 「구조」 에서 봅니다."
          />
        ) : (
          <GraphCanvas
            className={FILL_CANVAS}
            nodes={nodes}
            links={links}
            wide={wide}
            onToggleWide={onToggleWide}
            selectedId={selected}
            matchIds={matchIds ?? legendMatch}
            legend={legend}
            legendActive={legendActive}
            onLegendClick={(key) =>
              setLegendActive((current) => (current === key ? null : key))
            }
            onNodeClick={setSelected}
            onNodeDoubleClick={(id) => pickFocus(id)}
            onBackgroundClick={() => setSelected(null)}
            onEscape={() => setSelected(null)}
            centerOn={centerOn}
            hostShortcuts={hostShortcuts}
            exportName="탐색"
            overlay={
              <>
                {loading && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Loader2 className="text-muted-foreground size-5 animate-spin" />
                  </div>
                )}
                {explored && nodeList.length === 1 && !loading && (
                  <div className="text-muted-foreground absolute inset-x-0 top-3 text-center text-xs">
                    연결된 관계가 없습니다
                    {relationFilter.size + typeFilter.size > 0
                      ? ' — 필터를 넓혀 보세요.'
                      : '.'}
                  </div>
                )}
                {explored && (
                  <div className="text-muted-foreground bg-background/80 absolute bottom-2 left-2 flex items-center gap-2 rounded px-2 py-1 text-xs">
                    <span>
                      {explored.page
                        ? `${explored.page.total.toLocaleString()}개 중 ${explored.page.offset + 1}–${(
                            explored.page.offset + explored.page.shown
                          ).toLocaleString()} · 노드 ${nodeList.length}`
                        : `노드 ${nodeList.length}`}
                      {' · '}관계 {edgeList.length}
                      {communities.ready ? ` · 무리 ${communities.count}` : ''}
                    </span>
                    {explored.page &&
                      explored.page.total > explored.page.limit &&
                      seed?.kind === 'type' && (
                        <span className="flex items-center gap-0.5">
                          <Button
                            size="icon-xs"
                            variant="ghost"
                            aria-label="앞 쪽"
                            disabled={loading || explored.page.offset === 0}
                            onClick={() =>
                              onSeed({
                                ...seed,
                                offset: Math.max(
                                  0,
                                  explored.page!.offset - explored.page!.limit,
                                ),
                              })
                            }
                          >
                            <ChevronLeft className="size-3.5" />
                          </Button>
                          <Button
                            size="icon-xs"
                            variant="ghost"
                            aria-label="다음 쪽"
                            disabled={
                              loading ||
                              explored.page.offset + explored.page.limit >= explored.page.total
                            }
                            onClick={() =>
                              onSeed({
                                ...seed,
                                offset: explored.page!.offset + explored.page!.limit,
                              })
                            }
                          >
                            <ChevronRight className="size-3.5" />
                          </Button>
                        </span>
                      )}
                    {explored.truncated && (
                      <span className="text-amber-600 dark:text-amber-400">
                        · 일부만 실었습니다 — 「+N」 이 붙은 노드에서 더 펼칩니다
                      </span>
                    )}
                  </div>
                )}
              </>
            }
          />
        )}
      </div>

      {/* 오른쪽 — 고른 노드 */}
      <aside className={FILL_ASIDE}>
        {picked ? (
          <NodeDetail
            node={picked}
            hidden={pickedHidden}
            isFocus={picked.id === explored?.focus}
            loading={loading}
            inGraph={(id) => Boolean(explored?.nodes.has(id))}
            color={typeColor(picked.type_slug)}
            typeLabel={typeLabel.get(picked.type_slug) ?? picked.type_label}
            onExpand={() => void expand(picked.id)}
            onFocus={() => pickFocus(picked.id)}
            onSelect={selectAndGo}
            onClose={() => setSelected(null)}
          />
        ) : (
          <div className="text-muted-foreground rounded-md border border-dashed p-3">
            노드를 클릭하면 상세와 「여기서 확장」 가 나옵니다. 더블클릭은 「여기를 중심으로」.
            주황 링이 시작점, 「+N」 은 화면에 안 실린 관계의 수입니다.
          </div>
        )}
        {explored && (
          <p className="text-muted-foreground mt-3 text-xs">
            {explored.limits.depth !== undefined
              ? `한 번에 ${explored.limits.depth}단계 · 노드당 이웃 ${explored.limits.fanout}개 · `
              : '한 쪽에 '}
            노드 {explored.limits.node_limit}개까지. 상한은 서버가 정합니다.
          </p>
        )}
      </aside>
    </div>
  )
}

// --- 고른 노드 -----------------------------------------------------------------

interface NodeDetailProps {
  node: GraphNode
  /** 화면에 안 실린 관계의 수. */
  hidden: number
  isFocus: boolean
  loading: boolean
  inGraph: (id: string) => boolean
  color: string
  typeLabel: string
  onExpand: () => void
  onFocus: () => void
  onSelect: (id: string) => void
  onClose: () => void
}

/** 상세에서 보여 줄 속성 수 — 전부는 상세 화면이 있다. */
const DETAIL_PROPERTIES = 6

/**
 * 고른 노드의 요약 — **그래프를 떠나지 않고 「이게 뭐지」 에 답한다.**
 *
 * 속성 몇 개와 관계를 종류별로 묶어 보여 준다. 관계 목록의 한 줄은 그림에 있으면
 * 그 노드를 고르고(선택), 없으면 「확장」 로 안내한다 — 목록과 그림이 같은 것을
 * 가리켜야 사람이 둘을 오가며 읽는다.
 */
function NodeDetail({
  node,
  hidden,
  isFocus,
  loading,
  inGraph,
  color,
  typeLabel,
  onExpand,
  onFocus,
  onSelect,
  onClose,
}: NodeDetailProps) {
  const profile = useResource(() => graphApi.node(node.id), [node.id])

  const properties = useMemo(
    () =>
      (profile.data?.facts ?? [])
        .map((one) => ({ key: one.label, label: one.label, text: one.value }))
        .slice(0, DETAIL_PROPERTIES),
    [profile.data],
  )

  // 관계 — 종류(방향에 맞는 말)별로 묶고, 방향을 함께 적는다. 「소속 시험 항목」 과 「규격」 이
  // 같은 관계의 두 얼굴이라는 것을 말로 보여 주는 자리다.
  const related = useMemo(() => {
    const groups = new Map<string, { label: string; outgoing: boolean; rows: Related[] }>()
    for (const one of profile.data?.related ?? []) {
      const key = `${one.outgoing ? 'out' : 'in'}:${one.label}`
      if (!groups.has(key))
        groups.set(key, { label: one.label, outgoing: one.outgoing, rows: [] })
      groups.get(key)!.rows.push(one)
    }
    return [...groups.values()]
  }, [profile.data])

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="inline-block size-3 shrink-0 rounded-full"
              style={{ background: color }}
            />
            <span className="truncate font-medium">{node.label}</span>
          </div>
          <p className="text-muted-foreground mt-0.5 text-xs">
            {typeLabel}
            {node.key ? ` · ${node.key}` : ''}
          </p>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="닫기">
          <X className="size-4" />
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={hidden > 0 ? 'default' : 'outline'}
          disabled={loading || hidden === 0}
          onClick={onExpand}
        >
          여기서 확장{hidden > 0 ? ` (+${hidden})` : ''}
        </Button>
        <Button size="sm" variant="outline" disabled={isFocus} onClick={onFocus}>
          <Crosshair className="mr-1 size-3.5" />
          여기를 중심으로
        </Button>
        {node.detail_path && (
          <Button asChild size="sm" variant="outline">
            <Link to={node.detail_path}>
              <ExternalLink className="mr-1 size-3.5" />
              상세 보기
            </Link>
          </Button>
        )}
      </div>

      {profile.error && <ErrorNotice error={profile.error} />}
      {properties.length > 0 && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {properties.map((one) => (
            <Fragment key={one.key}>
              <dt className="text-muted-foreground whitespace-nowrap">{one.label}</dt>
              <dd className="truncate" title={one.text}>
                {one.text}
              </dd>
            </Fragment>
          ))}
        </dl>
      )}

      <div className="space-y-1.5">
        <p className="text-muted-foreground text-xs">
          관계 {node.degree}개
          {hidden > 0 && (
            <>
              {' '}
              · <Badge variant="secondary">화면에 없는 것 {hidden}</Badge>
            </>
          )}
        </p>
        {related.map(({ label, outgoing, rows }) => (
          <div key={`${outgoing}:${label}`}>
            <p className="text-xs font-medium">
              {label} <span className="text-muted-foreground font-normal">{rows.length}</span>
              <span className="text-muted-foreground ml-1 text-[10px] font-normal">
                {outgoing ? '(이 객체 → 대상)' : '(대상 → 이 객체)'}
              </span>
            </p>
            <ul className="mt-0.5 space-y-0.5">
              {rows.map((one, index) => {
                const here = inGraph(one.node_id)
                return (
                  <li key={`${one.relation}:${one.node_id}:${index}`}>
                    <button
                      type="button"
                      className="hover:bg-muted flex w-full items-baseline justify-between gap-2 rounded px-1.5 py-0.5 text-left text-xs disabled:cursor-default disabled:opacity-60"
                      title={
                        here
                          ? '그림에서 선택'
                          : '그림에 없습니다 — 「여기서 확장」 로 불러옵니다'
                      }
                      disabled={!here}
                      onClick={() => onSelect(one.node_id)}
                    >
                      <span className="truncate">{one.node_label}</span>
                      <span className="text-muted-foreground shrink-0">
                        {one.node_type_label}
                        {!here && ' · 화면 밖'}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

// --- 부품 -----------------------------------------------------------------------

interface SeedPanelProps {
  seed: Seed | null
  current: GraphNode | null
  types: { slug: string; label: string; is_active: boolean; object_count: number }[]
  typeLabel: Map<string, string>
  onPick: (id: string) => void
  onDrawTypes: (slugs: string[]) => void
  onClear: () => void
}

/**
 * 씨앗 선택 — **세 길.**
 *
 *   치는 것    이름의 일부를 알 때(타입을 가리지 않는다)
 *   훑는 것    무엇이 있는지 모를 때 — 타입을 고르고 쪽 단위로 본다
 *   전부       고른 타입(들)을 통째로 — 「N개 중 M개」 를 적는다
 *
 * 검색만 있으면 뭘 쳐야 할지 모르는 사람이 막힌다. 그래서 훑는 길이 함께 선다.
 * 타입 칩은 **여러 개** 고를 수 있다 — 타입별 목록은 고른 타입 중 하나를 보여 주고(처음엔
 * 마지막에 고른 것, 고른 타입이 둘 이상이면 그 사이를 오간다), 「전체 그리기」 는 고른 것
 * 전부를 한 그림에 그린다.
 */
function SeedPanel({
  seed,
  current,
  types,
  typeLabel,
  onPick,
  onDrawTypes,
  onClear,
}: SeedPanelProps) {
  const [text, setText] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const [pickedTypes, setPickedTypes] = useState<string[]>([])
  // 훑는 타입 — 고른 것 중 하나. 고른 목록이 바뀌면 마지막에 고른 것으로 옮겨 가되, 이미 보던
  // 타입이 아직 고른 채면 그대로 둔다(칩 하나 더 눌렀다고 보던 목록이 바뀌면 안 된다).
  const [browsePick, setBrowsePick] = useState('')
  const browseType = pickedTypes.includes(browsePick)
    ? browsePick
    : (pickedTypes[pickedTypes.length - 1] ?? '')
  const [browseOffset, setBrowseOffset] = useState(0)
  const [rows, setRows] = useState<{ items: SearchHit[]; total: number } | null>(null)
  const [browsing, setBrowsing] = useState(false)

  useEffect(() => {
    const needle = text.trim()
    if (!needle) {
      setHits([])
      setSearching(false)
      return
    }
    let cancelled = false
    setSearching(true)
    const timer = window.setTimeout(() => {
      graphApi
        .search(needle)
        .then((found) => {
          if (!cancelled) setHits(found)
        })
        .catch(() => {
          if (!cancelled) setHits([])
        })
        .finally(() => {
          if (!cancelled) setSearching(false)
        })
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [text])

  // 목록 — 그래프의 훑기 API. 상한과 쪽은 서버 규칙이다.
  useEffect(() => {
    if (!browseType) {
      setRows(null)
      return
    }
    let cancelled = false
    setBrowsing(true)
    graphApi
      .browse(browseType, { limit: BROWSE_PAGE, offset: browseOffset })
      .then((page) => {
        if (!cancelled) setRows({ items: page.items, total: page.total })
      })
      .catch(() => {
        if (!cancelled) setRows({ items: [], total: 0 })
      })
      .finally(() => {
        if (!cancelled) setBrowsing(false)
      })
    return () => {
      cancelled = true
    }
  }, [browseType, browseOffset])

  const browsed = types.find((one) => one.slug === browseType) ?? null
  const pickedRows = pickedTypes
    .map((slug) => types.find((one) => one.slug === slug))
    .filter((one): one is (typeof types)[number] => one !== undefined)
  const pickedCount = pickedRows.reduce((sum, one) => sum + one.object_count, 0)
  const seedType =
    seed?.kind === 'type'
      ? seed.slugs.map((slug) => typeLabel.get(slug) ?? slug).join(' · ')
      : null

  return (
    <div className="space-y-3">
      <span className="text-muted-foreground text-xs">시작점</span>
      {(current || seedType) && (
        <div className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5">
          <span className="truncate">
            {current ? (
              <>
                <span className="font-medium">{current.label}</span>
                <span className="text-muted-foreground ml-1 text-xs">
                  {current.type_label}
                </span>
              </>
            ) : (
              <>
                <span className="font-medium">{seedType}</span>
                <span className="text-muted-foreground ml-1 text-xs">전부</span>
              </>
            )}
          </span>
          <Button size="icon-xs" variant="ghost" onClick={onClear} aria-label="시작점 삭제">
            <X className="size-3.5" />
          </Button>
        </div>
      )}

      <div className="relative">
        <Search className="text-muted-foreground absolute top-2 left-2 size-4" />
        <Input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="이름·식별자로 검색"
          className="pl-8"
        />
        {searching && (
          <Loader2 className="text-muted-foreground absolute top-2 right-2 size-4 animate-spin" />
        )}
      </div>
      {text.trim() && !searching && hits.length === 0 && (
        <p className="text-muted-foreground text-xs">맞는 것이 없습니다.</p>
      )}
      {hits.length > 0 && (
        <ul className="space-y-0.5 rounded-md border p-1">
          {hits.map((hit) => (
            <li key={hit.id}>
              <button
                type="button"
                className="hover:bg-muted flex w-full items-baseline justify-between gap-2 rounded px-2 py-1 text-left"
                onClick={() => {
                  onPick(hit.id)
                  setText('')
                  setHits([])
                }}
              >
                <span className="truncate">{hit.label}</span>
                <span className="text-muted-foreground shrink-0 text-xs">
                  {hit.type_label}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="space-y-1.5">
        <span className="text-muted-foreground text-xs">종류별 목록</span>
        {/* 드롭다운이 아니라 칩이다 — **무엇이 있는지가 열기 전에 보여야** 목록다. */}
        <ul className="flex flex-wrap gap-1">
          {types
            .filter((one) => one.is_active)
            .map((one) => {
              const on = pickedTypes.includes(one.slug)
              return (
                <li key={one.slug}>
                  <button
                    type="button"
                    aria-pressed={on}
                    className={`rounded-full border px-2 py-0.5 text-xs ${
                      on ? 'bg-foreground text-background border-foreground' : 'hover:bg-muted'
                    }`}
                    onClick={() => {
                      setPickedTypes(
                        on
                          ? pickedTypes.filter((slug) => slug !== one.slug)
                          : [...pickedTypes, one.slug],
                      )
                      if (!on) setBrowsePick(one.slug)
                      setBrowseOffset(0)
                    }}
                  >
                    {one.label}{' '}
                    <span className={on ? 'opacity-70' : 'text-muted-foreground'}>
                      {one.object_count.toLocaleString()}
                    </span>
                  </button>
                </li>
              )
            })}
        </ul>
        {pickedRows.length > 0 && (
          // 채운 색 — 테두리만 있으면 고른 종류의 표제처럼 읽혀 누를 수 있다는 것을 모른다.
          <Button
            size="sm"
            className="w-full shadow-sm"
            disabled={pickedCount === 0}
            onClick={() => onDrawTypes(pickedRows.map((one) => one.slug))}
          >
            <Play className="mr-1 size-3.5" />
            {pickedRows.length === 1
              ? `${pickedRows[0].label} 전체 그리기`
              : `고른 ${pickedRows.length}개 종류 전체 그리기`}{' '}
            ({pickedCount.toLocaleString()})
          </Button>
        )}
        {browsed && rows && (
          <>
            {pickedRows.length > 1 && (
              // 고른 타입이 둘 이상이면 어느 것을 훑을지 고른다 — 마지막에 고른 것에 묶이면
              // 앞서 고른 타입은 훑을 길이 없다.
              <div className="flex flex-wrap items-center gap-1 text-xs" role="tablist">
                <span className="text-muted-foreground">목록:</span>
                {pickedRows.map((one) => (
                  <button
                    key={one.slug}
                    type="button"
                    role="tab"
                    aria-selected={one.slug === browseType}
                    className={`rounded px-1.5 py-0.5 ${
                      one.slug === browseType ? 'bg-muted font-medium' : 'hover:bg-muted/60'
                    }`}
                    onClick={() => {
                      setBrowsePick(one.slug)
                      setBrowseOffset(0)
                    }}
                  >
                    {one.label}
                  </button>
                ))}
              </div>
            )}
            {rows.items.length === 0 ? (
              <p className="text-muted-foreground text-xs">
                {browsing ? '읽는 중…' : '보이는 객체가 없습니다.'}
              </p>
            ) : (
              <ul className="space-y-0.5 rounded-md border p-1">
                {rows.items.map((row) => (
                  <li key={row.id}>
                    <button
                      type="button"
                      className={`hover:bg-muted flex w-full items-baseline justify-between gap-2 rounded px-2 py-1 text-left ${
                        current?.id === row.id ? 'bg-muted font-medium' : ''
                      }`}
                      onClick={() => onPick(row.id)}
                    >
                      <span className="truncate">{row.label}</span>
                      {row.key && (
                        <span className="text-muted-foreground shrink-0 font-mono text-xs">
                          {row.key}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {rows.total > BROWSE_PAGE && (
              <div className="text-muted-foreground flex items-center justify-between text-xs">
                <span>
                  {rows.total.toLocaleString()}개 중 {browseOffset + 1}–
                  {Math.min(browseOffset + BROWSE_PAGE, rows.total).toLocaleString()}
                </span>
                <span className="flex gap-0.5">
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label="앞 쪽"
                    disabled={browsing || browseOffset === 0}
                    onClick={() => setBrowseOffset(Math.max(0, browseOffset - BROWSE_PAGE))}
                  >
                    <ChevronLeft className="size-3.5" />
                  </Button>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label="다음 쪽"
                    disabled={browsing || browseOffset + BROWSE_PAGE >= rows.total}
                    onClick={() => setBrowseOffset(browseOffset + BROWSE_PAGE)}
                  >
                    <ChevronRight className="size-3.5" />
                  </Button>
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

interface FilterListProps {
  title: string
  options: { slug: string; label: string }[]
  picked: Set<string>
  onToggle: (slug: string) => void
  onClear: () => void
  swatch?: (slug: string) => string
}

/** 필터 — **아무것도 안 고르면 전부다.** 고른 것이 있으면 그것만. */
function FilterList({ title, options, picked, onToggle, onClear, swatch }: FilterListProps) {
  if (options.length === 0) return null
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-xs">
          {title}
          {picked.size > 0 ? ` · ${picked.size}개만` : ' · 전부'}
        </span>
        {picked.size > 0 && (
          <button
            type="button"
            className="text-muted-foreground text-xs underline"
            onClick={onClear}
          >
            전부
          </button>
        )}
      </div>
      <ul className="space-y-0.5">
        {options.map((one) => (
          <li key={one.slug}>
            <label className="hover:bg-muted flex cursor-pointer items-center gap-2 rounded px-1 py-0.5">
              <input
                type="checkbox"
                checked={picked.has(one.slug)}
                onChange={() => onToggle(one.slug)}
                className="size-3.5"
              />
              {swatch && (
                <span
                  className="inline-block size-2.5 shrink-0 rounded-full"
                  style={{ background: swatch(one.slug) }}
                />
              )}
              <span className="truncate">{one.label}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}
