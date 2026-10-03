/**
 * 커뮤니티 — **노드가 많아지면 타입 색만으로는 안 읽힌다.**
 *
 * 부품 200개가 전부 같은 색이면 그림은 한 덩어리다. 촘촘히 이어진 것끼리 묶어(Louvain)
 * 색을 주면 「이 무리와 저 무리」 가 보인다. 서버는 모른다 — 화면에 실린 것만 묶는
 * 것이므로 클라이언트에서 한다.
 *
 * 작은 그래프에는 안 건다. 노드 30개 미만이면 묶음이 곧 노이즈다.
 *
 * **무리마다 색을 준다 — 작은 무리도.** 전에는 3개 미만 무리와 열셋째 무리부터 회색이었는데,
 * 노드가 늘수록 회색이 번져 「이 무리와 저 무리」 를 보려던 그림이 회색 덩어리가 됐다
 * (2026-10-03 지적). 큰 무리부터 색을 받으므로 큰 무리가 늘 또렷한 앞 색을 쓰고, 외곽선은
 * 여전히 3개 이상인 무리만 감싼다 — 한두 점짜리를 감싸면 그림이 얼룩진다.
 */

import { useMemo } from 'react'
import Graph from 'graphology'
import louvain from 'graphology-communities-louvain'

import { colorScale, paletteColor } from '@/modules/graph/colors'

export const COMMUNITY_MIN_NODES = 30
/** 외곽선을 감쌀 무리의 최소 크기. 색은 이보다 작아도 준다. */
const MIN_COMMUNITY_SIZE = 3

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
  /** 외곽선을 감쌀 무리 키. 3개 미만 무리면 null — 색은 있어도 외곽선은 안 감싼다. */
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
      // 걸지 않았으면 화면은 이 색을 안 쓴다(타입 색으로 돌아간다).
      colorOf: () => paletteColor(0),
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
    // 큰 무리부터 — 큰 무리가 앞의 고른 색을 받는다. 크기가 같으면 번호 순(늘 같은 색).
    const ordered = [...sizeOf.entries()]
      .sort((a, b) => b[1] - a[1] || a[0] - b[0])
      .map(([c]) => String(c))
    const survivors = new Set(
      [...sizeOf.entries()].filter(([, n]) => n >= MIN_COMMUNITY_SIZE).map(([c]) => String(c)),
    )
    if (survivors.size === 0) return none

    const scale = colorScale(ordered)
    const communityOf = new Map<string, string>()
    for (const id of nodeIds) {
      const c = mapping[id]
      if (c !== undefined) communityOf.set(id, String(c))
    }
    return {
      ready: true,
      count: survivors.size,
      colorOf: (id) => scale(communityOf.get(id) ?? id),
      keyOf: (id) => {
        const key = communityOf.get(id)
        return key !== undefined && survivors.has(key) ? key : null
      },
    }
  }, [nodeIds, edges, enabled])
}
