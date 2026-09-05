/**
 * 문헌 물성 검색 결과 — **사내 재료 화면에 꽂히는 조각.**
 *
 * 사용자가 두 체계를 따로 뒤지게 하지 않는다: 재료 목록에서 검색하면 문헌
 * 카탈로그도 같은 검색어로 함께 치고, 맞는 것이 있으면 이 블록이 선다.
 * 저장은 갈라져 있어도(ADR 0027) 검색은 하나다.
 *
 * 검색어가 없거나 문헌에 맞는 것이 없으면 **아무것도 그리지 않는다** — 이 블록은
 * 보조이지 사내 결과를 밀어내는 것이 아니다.
 */

import { BookMarked } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { CATEGORY_LABELS, catalogApi } from '@/modules/catalog/api'
import type { CatalogMaterialPage } from '@/modules/catalog/api'
import { Badge } from '@/shared/components/ui/badge'

export function CatalogHits({
  q,
  limit = 5,
  className = '',
}: {
  q: string
  limit?: number
  className?: string
}) {
  const trimmed = q.trim()
  const [page, setPage] = useState<CatalogMaterialPage | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!trimmed) {
      setPage(null)
      setFailed(false)
      return
    }
    let alive = true
    const timer = setTimeout(() => {
      catalogApi
        .materials({ q: trimmed, limit })
        .then((found) => {
          if (alive) {
            setPage(found)
            setFailed(false)
          }
        })
        .catch(() => alive && setFailed(true))
    }, 250)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [trimmed, limit])

  if (!trimmed) return null
  if (failed) {
    // 실패를 조용히 삼키지 않는다 — 다만 사내 검색을 방해하지 않게 한 줄이다.
    return (
      <p className={`text-muted-foreground text-xs ${className}`}>
        문헌 물성 검색에 실패했습니다 — 사내 결과만 보입니다.
      </p>
    )
  }
  if (!page || page.total === 0) return null

  return (
    <div className={`rounded-md border ${className}`}>
      <p className="text-muted-foreground flex items-center gap-1.5 border-b px-3 py-1.5 text-xs font-medium">
        <BookMarked className="size-3.5" />
        문헌 물성에서 {page.total.toLocaleString('ko-KR')}건
        <Link className="ml-auto hover:underline" to={`/catalog?q=${encodeURIComponent(trimmed)}`}>
          전부 보기
        </Link>
      </p>
      {page.items.map((one) => (
        <Link
          key={one.id}
          to={`/catalog/${one.id}`}
          className="hover:bg-muted/50 flex items-center gap-2 border-b px-3 py-1.5 text-sm last:border-b-0"
        >
          <span className="min-w-0 flex-1 truncate">{one.name}</span>
          <Badge variant="outline">{CATEGORY_LABELS[one.category] ?? one.category}</Badge>
          <span className="text-muted-foreground text-xs whitespace-nowrap">
            물성 {one.value_count}
          </span>
        </Link>
      ))}
    </div>
  )
}
