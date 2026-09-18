/**
 * 지식 그래프 API — **읽기만.** TestScope·StandardPlatform 의 것을 옮겨 왔다.
 *
 * 관계를 잇고 끊는 것은 각 객체의 화면이 한다. 그리는 화면에 쓰기가 들어가면 「그림에서 선을
 * 지웠는데 상세에는 남아 있는」 어긋남이 생긴다.
 *
 * 노드 id 는 `"<종류>:<식별자>"` — 물성 정의만 키 문자열, 나머지는 uuid. 표가 다르면 식별자만으로는 종류를 모른다.
 */

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type TypeNode = components['schemas']['KGTypeNodeOut']
export type TypeEdge = components['schemas']['KGTypeEdgeOut']
export type Overview = components['schemas']['KGOverviewOut']
export type GraphNode = components['schemas']['KGNodeOut']
export type GraphEdge = components['schemas']['KGEdgeOut']
export type Neighborhood = components['schemas']['KGNeighborhoodOut']
export type Subgraph = components['schemas']['KGSubgraphOut']
export type SearchHit = components['schemas']['KGSearchHitOut']
export type Browse = components['schemas']['KGBrowseOut']
export type NodeDetail = components['schemas']['KGNodeDetailOut']
export type Related = components['schemas']['KGRelatedOut']

export interface NeighborhoodQuery {
  focus: string
  depth?: number
  fanout?: number
  limit?: number
  relations?: string[]
  types?: string[]
}

export interface SubgraphQuery {
  types: string[]
  relations?: string[]
  q?: string
  limit?: number
  offset?: number
}

function neighborhoodQuery(query: NeighborhoodQuery): string {
  const params = new URLSearchParams({ focus: query.focus })
  if (query.depth !== undefined) params.set('depth', String(query.depth))
  if (query.fanout !== undefined) params.set('fanout', String(query.fanout))
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.relations?.length) params.set('relations', query.relations.join(','))
  if (query.types?.length) params.set('types', query.types.join(','))
  return `?${params.toString()}`
}

function subgraphQuery(query: SubgraphQuery): string {
  const params = new URLSearchParams({ types: query.types.join(',') })
  if (query.relations?.length) params.set('relations', query.relations.join(','))
  if (query.q) params.set('q', query.q)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset) params.set('offset', String(query.offset))
  return `?${params.toString()}`
}

export const graphApi = {
  /** 종류와 선 종류만 — 객체가 십만 개여도 답은 (종류 수) 노드다. */
  overview: () => api.get<Overview>('/graph/overview'),
  /** 종류를 가리지 않고 시작점을 찾는다. */
  search: (q: string) =>
    api.get<SearchHit[]>(`/graph/search?${new URLSearchParams({ q }).toString()}`),
  /** 한 종류를 이름순으로 쪽 단위로 — 무엇을 칠지 모르는 사람의 길. */
  browse: (type: string, options: { q?: string; limit?: number; offset?: number } = {}) => {
    const params = new URLSearchParams({ type })
    if (options.q) params.set('q', options.q)
    if (options.limit !== undefined) params.set('limit', String(options.limit))
    if (options.offset) params.set('offset', String(options.offset))
    return api.get<Browse>(`/graph/browse?${params.toString()}`)
  },
  /** 시작점에서 depth 단계 — **서버가 상한을 강제한다.** */
  neighborhood: (query: NeighborhoodQuery) =>
    api.get<Neighborhood>(`/graph/neighborhood${neighborhoodQuery(query)}`),
  /** 한 종류의 노드 전부 — **「전부」 를 묻는 사람에게 "N개 중 M개" 라고 답한다.** */
  subgraph: (query: SubgraphQuery) =>
    api.get<Subgraph>(`/graph/subgraph${subgraphQuery(query)}`),
  /** 고른 노드의 요약과 관계 목록. */
  node: (id: string) =>
    api.get<NodeDetail>(`/graph/node?${new URLSearchParams({ id }).toString()}`),
}
