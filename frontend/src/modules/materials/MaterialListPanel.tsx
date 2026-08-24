/**
 * 재료 상세 옆의 재료 목록 — **다른 재료를 보려고 뒤로 갈 필요가 없다.**
 *
 * 실사용에서 나왔다. 재료를 하나 고르면 상세로 들어가는데, 옆 재료를 보려면
 * **브라우저 뒤로 가기밖에 길이 없었다.** 목록으로 돌아가는 단추조차 없었다.
 * 재료를 여러 개 견주는 일(같은 강종의 두께별, 같은 판의 방향별)이 흔한데
 * 그때마다 목록 → 상세 → 뒤로 → 상세를 반복하게 된다.
 *
 * ## 껍데기 층에 붙는다
 *
 * 왼쪽 사이드바 **바로 옆**이다. 본문 안에 두면 `max-w-[1600px]` 을 따라 가운데로
 * 딸려 들어가고, 화면 왼쪽 끝에는 여백만 남는다(`SidePanel` 의 첫 주석).
 *
 * ## 여기서 거르지 않는다
 *
 * 검색은 서버가 한다. 앞 200개를 받아 화면에서 거르던 방식은 재료가 그보다
 * 많아지는 순간 **뒤엣것을 없는 재료처럼** 보이게 만든다 — `MaterialPicker` 가
 * 같은 이유로 서버 검색을 쓴다.
 */

import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { Link } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import type { Material } from '@/modules/materials/api'
import { Input } from '@/shared/components/ui/input'
import { LeftPanel } from '@/shared/layout/SidePanel'

/** 한 번에 받아 오는 수. 옆 목록이라 스크롤로 훑는 것이 전부다. */
const LIMIT = 50

export function MaterialListPanel({ currentId }: { currentId: string | undefined }) {
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<Material[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let dropped = false
    setLoading(true)
    // 글자마다 요청하면 옆 목록 하나가 서버를 두드리는 꼴이 된다.
    const timer = setTimeout(() => {
      materialsApi
        .list({ q: query.trim() || undefined, limit: LIMIT, offset: 0 })
        .then((page) => {
          if (dropped) return
          setRows(page.items)
          setTotal(page.total)
        })
        .catch(() => {
          if (!dropped) setRows([])
        })
        .finally(() => {
          if (!dropped) setLoading(false)
        })
    }, 250)
    return () => {
      dropped = true
      clearTimeout(timer)
    }
  }, [query])

  return (
    <LeftPanel label="재료 목록">
      <aside className="bg-background flex h-full w-64 flex-col border-r">
        <div className="border-b p-2">
          <div className="relative">
            <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="이름 · 별칭 · Grade"
              className="h-8 pl-7 text-xs"
              aria-label="재료 찾기"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {rows.map((material) => {
            const here = material.id === currentId
            return (
              <Link
                key={material.id}
                to={`/materials/${material.id}`}
                aria-current={here ? 'page' : undefined}
                className={`block border-b px-3 py-2 text-xs ${
                  here ? 'bg-muted font-medium' : 'hover:bg-muted/50'
                }`}
              >
                <div className="truncate">{material.record_name}</div>
                {material.alias && (
                  <div className="text-muted-foreground truncate text-[11px]">
                    {material.alias}
                  </div>
                )}
              </Link>
            )
          })}

          {!loading && rows.length === 0 && (
            <p className="text-muted-foreground p-3 text-xs">찾는 재료가 없습니다.</p>
          )}
        </div>

        {/* **잘렸으면 잘렸다고 말한다.** 표시도 없이 앞 50개만 보이면 뒤엣것은
            없는 재료처럼 보이고, 사람은 그 사실을 알 방법이 없다. */}
        {total > rows.length && (
          <p className="text-muted-foreground border-t px-3 py-2 text-[11px]">
            {total}개 중 {rows.length}개. 찾기로 좁히세요.
          </p>
        )}
      </aside>
    </LeftPanel>
  )
}
