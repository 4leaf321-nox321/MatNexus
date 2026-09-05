/**
 * 문헌 연결 — **사내 재료 상세에 꽂히는 조각.**
 *
 * 이 재료가 문헌(카탈로그)에서 어느 등급인지 잇고, 이었으면 그 문헌 값으로
 * 「채우기」 를 바로 연다. 연결은 재료당 하나이고, 편집 권한은 재료 편집과
 * 같다(부서 관리자·전역은 시스템 관리자 — 서버가 판정한다).
 */

import { BookMarked, Link2, Link2Off, PackagePlus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { AdoptDialog } from '@/modules/catalog/AdoptDialog'
import { CATEGORY_LABELS, catalogApi } from '@/modules/catalog/api'
import type { CatalogLink, CatalogMaterialDetail } from '@/modules/catalog/api'
import type { components } from '@/shared/api/schema'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'

type MaterialOut = components['schemas']['MaterialOut']

export function LinkedCatalogSection({
  material,
  onChanged,
}: {
  material: MaterialOut
  /** 채우기가 재료를 바꿨을 때 — 부모가 재료를 다시 읽는다. */
  onChanged?: () => void
}) {
  const [link, setLink] = useState<CatalogLink | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [searching, setSearching] = useState(false)
  const [typed, setTyped] = useState('')
  const [found, setFound] = useState<{ id: string; name: string; category: string }[]>([])
  const [detail, setDetail] = useState<CatalogMaterialDetail | null>(null)
  const [adopting, setAdopting] = useState(false)

  const materialId = String(material.id)

  const refresh = useCallback(() => {
    catalogApi
      .link(materialId)
      .then(setLink)
      .catch((caught) =>
        setError(caught instanceof Error ? caught : new Error('연결을 읽지 못했습니다.'))
      )
  }, [materialId])

  useEffect(() => refresh(), [refresh])

  // 문헌 재료 검색 — 연결할 때만.
  useEffect(() => {
    if (!searching) return
    const timer = setTimeout(() => {
      catalogApi
        .materials({ q: typed || undefined, limit: 8 })
        .then((page) =>
          setFound(
            page.items.map((one) => ({
              id: String(one.id),
              name: one.name,
              category: one.category,
            }))
          )
        )
        .catch((caught) =>
          setError(caught instanceof Error ? caught : new Error('검색하지 못했습니다.'))
        )
    }, 250)
    return () => clearTimeout(timer)
  }, [typed, searching])

  // 연결돼 있으면 채우기용 상세를 미리 받아 둔다.
  useEffect(() => {
    if (!link?.catalog_material_id) {
      setDetail(null)
      return
    }
    catalogApi
      .material(String(link.catalog_material_id))
      .then(setDetail)
      .catch(() => setDetail(null))
  }, [link?.catalog_material_id])

  async function connect(catalogMaterialId: string) {
    setError(null)
    try {
      setLink(await catalogApi.setLink(materialId, catalogMaterialId))
      setSearching(false)
      setTyped('')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('연결하지 못했습니다.'))
    }
  }

  async function disconnect() {
    setError(null)
    try {
      await catalogApi.clearLink(materialId)
      setLink({ ...(link ?? {}), catalog_material_id: null } as CatalogLink)
      refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('연결을 풀지 못했습니다.'))
    }
  }

  return (
    <section className="space-y-2 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <BookMarked className="text-muted-foreground size-4" />
        <span className="text-sm font-semibold">문헌 물성</span>
        {link?.catalog_material_id ? (
          <>
            <Link
              className="text-sm hover:underline"
              to={`/catalog/${link.catalog_material_id}`}
            >
              {link.name}
            </Link>
            <Badge variant="outline">
              {CATEGORY_LABELS[link.category ?? ''] ?? link.category}
            </Badge>
            <span className="text-muted-foreground text-xs">물성값 {link.value_count}건</span>
            <Button
              size="sm"
              variant="outline"
              disabled={!detail}
              onClick={() => setAdopting(true)}
            >
              <PackagePlus className="size-4" />
              채우기
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void disconnect()}>
              <Link2Off className="size-4" />
              연결 해제
            </Button>
          </>
        ) : searching ? (
          <Button size="sm" variant="ghost" onClick={() => setSearching(false)}>
            취소
          </Button>
        ) : (
          <>
            <span className="text-muted-foreground text-xs">
              아직 문헌 재료와 이어지지 않았습니다.
            </span>
            <Button size="sm" variant="outline" onClick={() => setSearching(true)}>
              <Link2 className="size-4" />
              문헌 재료 연결
            </Button>
          </>
        )}
      </div>

      <ErrorNotice error={error} />

      {searching && !link?.catalog_material_id && (
        <div className="space-y-1">
          <Input
            aria-label="문헌 재료 검색"
            placeholder="문헌 재료 이름으로 검색"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
          {found.map((one) => (
            <button
              key={one.id}
              type="button"
              className="hover:bg-muted block w-full rounded-md border px-3 py-2 text-left text-sm"
              onClick={() => void connect(one.id)}
            >
              {one.name}
              <span className="text-muted-foreground ml-2 text-xs">
                {CATEGORY_LABELS[one.category] ?? one.category}
              </span>
            </button>
          ))}
        </div>
      )}

      {detail && (
        <AdoptDialog
          detail={detail}
          open={adopting}
          onClose={() => setAdopting(false)}
          fixedTarget={material}
          onDone={onChanged}
        />
      )}
    </section>
  )
}
