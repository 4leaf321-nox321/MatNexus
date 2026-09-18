/**
 * 커뮤니티 — **노드가 많아지면 타입 색만으로는 안 읽힌다.**
 *
 * 부품 200개가 전부 같은 색이면 그림은 한 덩어리다. 촘촘히 이어진 것끼리 묶어(Louvain)
 * 색을 주면 「이 무리와 저 무리」 가 보인다. 서버는 모른다 — 화면에 실린 것만 묶는
 * 것이므로 클라이언트에서 한다.
 *
 * 작은 그래프에는 안 건다. 노드 30개 미만이면 묶음이 곧 노이즈다.
 */

import { useMemo } from 'react'
import Graph from 'graphology'
import louvain from 'graphology-communities-louvain'

import { colorScale, OVERFLOW_COLOR } from '@/modules/graph/colors'

export const COMMUNITY_MIN_NODES = 30
const MIN_COMMUNITY_SIZE = 3
const SMALL = '__small__'

/** 고정 시드 — Louvain 은 난수를 쓰므로, 고정하지 않으면 리렌더마다 색이 바뀐다. */
function seededRng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

interface Edge {
  src: string
  dst: string
}

export interface Communities {
  /** 걸 만한 크기였나. 거짓이면 화면은 타입 색으로 돌아간다. */
  ready: boolean
  colorOf: (nodeId: string) => string
  /** 무리 키. 소규모(회색)면 null — 외곽선도 안 감싼다. */
  keyOf: (nodeId: string) => string | null
  count: number
}

export function useCommunities(
  nodeIds: string[],
  edges: Edge[],
  enabled: boolean,
): Communities {
  return useMemo(() => {
    const none: Communities = {
      ready: false,
      colorOf: () => OVERFLOW_COLOR,
      keyOf: () => null,
      count: 0,
    }
    if (!enabled || nodeIds.length < COMMUNITY_MIN_NODES) return none

    const graph = new Graph({ type: 'undirected', multi: false })
    for (const id of nodeIds) graph.mergeNode(id)
    for (const edge of edges) {
      if (edge.src === edge.dst) continue
      if (!graph.hasNode(edge.src) || !graph.hasNode(edge.dst)) continue
      if (!graph.hasEdge(edge.src, edge.dst)) graph.addEdge(edge.src, edge.dst)
    }
    if (graph.size === 0) return none

    const mapping = louvain(graph, { rng: seededRng(0x9e3779b9) })
    const sizeOf = new Map<number, number>()
    for (const id of nodeIds) {
      const c = mapping[id]
      if (c === undefined) continue
      sizeOf.set(c, (sizeOf.get(c) ?? 0) + 1)
    }
    const survivors = [...sizeOf.entries()]
      .filter(([, n]) => n >= MIN_COMMUNITY_SIZE)
      .sort((a, b) => b[1] - a[1])
      .map(([c]) => String(c))
    if (survivors.length === 0) return none

    const scale = colorScale(survivors)
    const keyOf = new Map<string, string>()
    for (const id of nodeIds) {
      const c = mapping[id]
      const key = c !== undefined && survivors.includes(String(c)) ? String(c) : SMALL
      keyOf.set(id, key)
    }
    return {
      ready: true,
      count: survivors.length,
      colorOf: (id) => {
        const key = keyOf.get(id)
        return key === undefined || key === SMALL ? OVERFLOW_COLOR : scale(key)
      },
      keyOf: (id) => {
        const key = keyOf.get(id)
        return key === undefined || key === SMALL ? null : key
      },
    }
  }, [nodeIds, edges, enabled])
}
