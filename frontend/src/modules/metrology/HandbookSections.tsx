/**
 * 그 물성 · 규격을 다룬 **핸드북 절** — 측정법에서 핸드북으로(2026-10-03).
 *
 * 장비 표는 「무엇으로 재나」 까지만 말한다. 시편을 어떻게 자르고 잰 것이 어떻게 물성이
 * 되는지는 핸드북에 있다 — 두 화면을 따로 뒤지게 하지 않는다. 반대 방향(절 → 측정법)은
 * 핸드북 절 옆에 선다(`guide/mentions`).
 *
 * 찾는 말과 차례는 `handbookTerms` 가 정한다 — 규격이 먼저, 이름이 뒤.
 */

import { BookOpen } from 'lucide-react'
import { Link } from 'react-router-dom'

import { guideApi } from '@/modules/guide/api'
import type { SearchHit } from '@/modules/guide/api'
import { handbookTerms } from '@/modules/metrology/handbook'
import type { MetrologyProperty } from '@/modules/metrology/api'
import { useResource } from '@/shared/hooks/useResource'

/** 한 번에 세우는 절 수. 넘으면 핸드북 찾기로 보낸다. */
const SHOWN = 8

export function HandbookSections({ detail }: { detail: MetrologyProperty }) {
  const found = useResource(async () => {
    const terms = handbookTerms(detail)
    const groups = await Promise.all(
      terms.map((one) =>
        guideApi
          .search(one.term)
          .then((hits) => hits.map((hit) => ({ hit, term: one.term })))
          // 말 하나가 막혀도 나머지 절은 세운다 — 이 칸은 길잡이다.
          .catch(() => [] as { hit: SearchHit; term: string }[])
      )
    )
    const seen = new Set<string>()
    const merged: { hit: SearchHit; term: string }[] = []
    for (const group of groups) {
      for (const one of group) {
        if (seen.has(one.hit.section_id)) continue
        seen.add(one.hit.section_id)
        merged.push(one)
      }
    }
    return merged
  }, [detail])

  const rows = found.data ?? []
  return (
    <section className="rounded-md border p-3" aria-label="핸드북의 관련 절">
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
        <BookOpen className="size-4" />
        핸드북
      </h3>
      {found.loading && !found.data && <p className="text-muted-foreground text-sm">찾는 중…</p>}
      {found.data && rows.length === 0 && (
        <p className="text-muted-foreground text-sm">
          이 물성 · 규격을 다룬 절이 핸드북에 아직 없습니다.
        </p>
      )}
      {rows.length > 0 && (
        <ul className="space-y-1 text-sm">
          {rows.slice(0, SHOWN).map(({ hit, term }) => (
            <li key={hit.section_id}>
              <Link
                className="font-medium hover:underline"
                to={`/guide/${hit.document_key}/${hit.section_key}`}
              >
                {hit.section_title}
              </Link>
              <span className="text-muted-foreground">
                {' '}
                · {hit.document_title} · 「{term}」
              </span>
            </li>
          ))}
        </ul>
      )}
      {rows.length > SHOWN && (
        <Link
          className="mt-2 inline-block text-sm underline"
          to={`/guide?q=${encodeURIComponent(detail.name)}`}
        >
          핸드북에서 「{detail.name}」 더 찾기
        </Link>
      )}
    </section>
  )
}
