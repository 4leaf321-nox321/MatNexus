/**
 * 기준정보 보기 — **고르는 사람이 목록을 볼 수 있어야 한다.**
 *
 * 지금까지 기준정보는 시스템 관리자에게만 보였다. 그런데 그 값을 매일 고르는
 * 것은 멤버다 — 재료를 만들 때 제조사·Grade·규격을 드롭다운에서 고른다. 목록을
 * 못 보면 **찾는 값이 없을 때 그것이 「아직 없다」 인지 「이름이 다르다」 인지
 * 구별할 수 없고**, 누구에게 요청해야 하는지도 모른다. 실제로 「소속 드롭다운이
 * 이상하다」 가 그렇게 나왔다.
 *
 * ## 편집 화면을 열어 주지 않고 보기를 따로 만든 이유
 *
 * `/admin/vocabulary` 는 1700줄이고 지우기·병합·어긋남 점검이 섞여 있다. 거기서
 * 쓰기 단추만 골라 감추면 **한두 개를 빠뜨린다** — 그러면 멤버가 누르고 403 을
 * 본다. 「눌러 보고 알게 하지 않는다」 는 사이드바에 붙인 규칙과 같은 자리다.
 *
 * 서버는 이미 열려 있었다. `GET /vocabularies` 와 `.../terms` 는 `current_user`
 * 다 — 막고 있던 것은 화면뿐이었다.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Pencil, Search } from 'lucide-react'

import { UnitsContent } from '@/modules/units/UnitsPage'
import { vocabularyApi } from '@/modules/vocabulary/api'
import { VocabularyAxisPanel } from '@/modules/vocabulary/VocabularyAxisPanel'
import { useAuth } from '@/shared/auth/AuthContext'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'

/** 한 번에 보는 줄 수. 훑어보는 화면이라 넉넉히 준다. */
const PAGE_SIZE = 100

/**
 * 단위를 고른 상태. **축 slug 와 같은 자리에 들어가므로 겹치지 않을 이름**이어야
 * 한다 — 축은 `manufacturer`·`family` 처럼 도메인 낱말이라 이 접두사와 안 겹친다.
 */
const UNITS = '@units'

export default function VocabularyPage() {
  const { user } = useAuth()
  const axes = useResource(() => vocabularyApi.list(), [])
  const [slug, setSlug] = useState<string | null>(null)
  const [term, setTerm] = useState('')
  const list = axes.data ?? []
  const showingUnits = slug === UNITS
  const active = showingUnits ? null : (list.find((item) => item.slug === slug) ?? list[0] ?? null)

  // 검색은 서버가 한다 — 강종은 수만 개가 될 수 있어 전체를 받을 수 없다.
  const terms = useResource(
    () =>
      active
        ? vocabularyApi.search(active.slug, term, { limit: PAGE_SIZE })
        : Promise.resolve(null),
    [active?.slug, term]
  )
  const rows = terms.data?.items ?? []
  const total = terms.data?.total ?? 0

  const parentLabel = useMemo(
    () => list.find((item) => item.slug === active?.parent_slug)?.label ?? null,
    [list, active?.parent_slug]
  )

  return (
    <div>
      <PageHeader
        title="기준정보"
        description="재료·시편·시험을 등록할 때 고르는 값의 목록입니다. 찾는 값이 없으면 시스템 관리자에게 요청하세요."
        actions={
          // **고칠 수 있는 사람에게는 가는 길을 준다.** 없으면 관리자도 이 화면을
          // 보고 나서 주소를 외워 편집 화면으로 가야 한다.
          user?.is_system_admin ? (
            <Button asChild size="sm" variant="outline">
              <Link to="/admin/vocabulary">
                <Pencil className="size-3.5" />
                편집
              </Link>
            </Button>
          ) : null
        }
      />

      <ErrorNotice error={axes.error} className="mb-4" />

      {/* **단위는 축과 섞지 않되, 이름을 붙이지 않는다.**
          축은 값을 더할 수 있고 단위는 못 고친다 — 다른 종류라는 것은 선으로
          충분하다. 한 항목뿐인데 제목을 달면 「여기 더 있다」 로 읽히고, 무엇보다
          그 제목이 잘 안 붙는다: 「고칠 수 없는 것」 은 무엇이 못 고치는지(권한?
          고장?)가 안 드러나고, 부정형이라 **무엇인지는 안 말하고 무엇이 아닌지만**
          말한다. 필요해지는 때는 여기 항목이 둘 이상이 될 때다. */}
      <VocabularyAxisPanel
        axes={list}
        current={showingUnits ? UNITS : (active?.slug ?? null)}
        onPick={setSlug}
        extras={[{ key: UNITS, label: '단위' }]}
      />

      {showingUnits && <UnitsContent />}

      {active && !showingUnits && (
        <div className="mt-4">
          <div className="mb-3 flex items-center gap-2">
            <div className="relative w-full max-w-sm">
              <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
              <Input
                value={term}
                onChange={(event) => setTerm(event.target.value)}
                placeholder={`${active.label} 값 검색`}
                className="h-8 pl-7 text-xs"
              />
            </div>
            <span className="text-muted-foreground text-xs">
              {/* **몇 개 중 몇 개인지 말한다.** 100줄만 그리고 마는데 그 말이
                  없으면 「이것이 전부」 로 읽힌다. */}
              {total}개{total > rows.length && ` 중 ${rows.length}개`}
            </span>
          </div>

          <ErrorNotice error={terms.error} className="mb-3" />

          {terms.loading && !terms.data ? (
            <Skeleton className="h-40" />
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground rounded-md border border-dashed px-3 py-6 text-center text-sm">
              {term ? `'${term}' 에 맞는 값이 없습니다.` : '등록된 값이 없습니다.'}
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground text-xs">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">값</th>
                    {active.parent_slug && (
                      <th className="px-3 py-2 text-left font-medium">{parentLabel ?? '상위'}</th>
                    )}
                    <th className="px-3 py-2 text-right font-medium">쓰는 곳</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((item) => (
                    <tr key={item.id} className="border-t">
                      <td className="px-3 py-1.5">
                        {item.value}
                        {/* 감춘 값은 드롭다운에 안 뜬다 — 목록에 있는데 못 고르는
                            이유가 화면에 있어야 한다. */}
                        {item.status !== 'active' && (
                          <Badge variant="outline" className="ml-2 text-[11px]">
                            감춤
                          </Badge>
                        )}
                      </td>
                      {active.parent_slug && (
                        <td className="text-muted-foreground px-3 py-1.5">
                          {item.parent_value ?? '—'}
                        </td>
                      )}
                      <td className="text-muted-foreground px-3 py-1.5 text-right tabular-nums">
                        {item.usage_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
