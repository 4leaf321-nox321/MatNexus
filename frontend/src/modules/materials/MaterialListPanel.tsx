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
 * 왼쪽 사이드바 **바로 옆**이다. 본문 안에 두면 본문의 여백 안으로 들어가고
 * 본문과 함께 스크롤된다(`SidePanel` 의 첫 주석).
 *
 * ## 여기서 거르지 않는다
 *
 * 검색은 서버가 한다. 앞 200개를 받아 화면에서 거르던 방식은 재료가 그보다
 * 많아지는 순간 **뒤엣것을 없는 재료처럼** 보이게 만든다 — `MaterialPicker` 가
 * 같은 이유로 서버 검색을 쓴다.
 *
 * ## 분류 필터도 목록 화면과 같다
 *
 * 세는 규칙(`classification.ts`)과 고르는 컴포넌트(`OptionPicker`)를 그대로
 * 쓴다. **Category 는 Family 에 종속이다** — Family 를 고르면 그 안의 것만
 * 남긴다. 안 그러면 `Metal + PP` 처럼 결과가 늘 0건인 조합을 고를 수 있고,
 * 사람은 재료가 없는 줄 안다.
 */

import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { CatalogHits } from '@/modules/catalog/CatalogHits'
import { materialsApi } from '@/modules/materials/api'
import type { Material } from '@/modules/materials/api'
import { categoriesOf, familiesOf } from '@/modules/materials/classification'
import { OptionPicker } from '@/shared/components/OptionPicker'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'
import { ROW_FOCUS_STYLE, useRowFocus } from '@/shared/hooks/useRowFocus'
import { LeftPanel, useLeftPanel } from '@/shared/layout/SidePanel'
import { RecordName } from '@/shared/components/RecordName'

/** 한 번에 받아 오는 수. 옆 목록이라 스크롤로 훑는 것이 전부다. */
const LIMIT = 50

//: 화살표로 옮긴 뒤 그 재료를 열기까지 기다리는 시간. **누르고 있는 동안은 안
//: 간다** — 지나가는 재료마다 상세·시료·요약을 부르면 요청이 백 단위가 된다.
//: 한 번 눌렀을 때 느껴지지 않을 만큼 짧아야 해서 150ms 로 뒀다.
const FOLLOW_DELAY_MS = 150

export function MaterialListPanel({ currentId }: { currentId: string | undefined }) {
  const { search } = useLocation()
  const navigate = useNavigate()
  const panel = useLeftPanel()
  const [query, setQuery] = useState('')
  const [family, setFamily] = useState('')
  const [category, setCategory] = useState('')
  const [rows, setRows] = useState<Material[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let dropped = false
    setLoading(true)
    // 글자마다 요청하면 옆 목록 하나가 서버를 두드리는 꼴이 된다.
    const timer = setTimeout(() => {
      materialsApi
        .list({ q: query.trim() || undefined, family, category, limit: LIMIT, offset: 0 })
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
  }, [query, family, category])

  // 무엇으로 거를 수 있는지는 **데이터가 정한다.** 실제로 있는 조합만 준다 —
  // 고정 목록을 박으면 부서가 새 분류를 쓰기 시작할 때 고를 수 없게 된다.
  const classes = useResource(() => materialsApi.classifications(), [])
  const known = classes.data ?? []
  // **지금 보고 있는 재료가 Tab 이 닿는 자리다.** 첫 줄로 두면 50번째 재료를
  // 보는 중에도 처음부터 내려와야 한다.
  //
  // **여기서는 옮기는 것이 곧 고르는 것이다.** 고른 결과가 오른쪽에 그대로
  // 보이는 화면이라, 엔터를 한 번 더 누르게 하면 그 한 번이 늘 군더더기다
  // (2026-09-11 지적). 전체 목록의 표에는 이것을 안 붙였다 — 거기서는 줄이
  // 다른 화면으로 가는 링크라 화살표 한 번에 목록을 떠나 버린다.
  const focus = useRowFocus(rows.map((one) => one.id), {
    preferred: currentId,
    onMove: (id) => follow(id),
  })

  /**
   * 옮겨 간 재료를 연다. **조금 기다렸다 간다.**
   *
   * 화살표를 누르고 있으면 줄마다 상세를 읽게 되는데, 지나가는 재료의 시료·
   * 요약·카드까지 줄줄이 부른다 — 50줄을 내려가면 요청이 백 단위가 된다.
   * 사람이 멈춘 뒤에 한 번만 간다.
   *
   * **히스토리를 안 쌓는다**(`replace`). 화살표로 스무 번 내려간 뒤 뒤로
   * 가기를 누르면 스무 번을 되짚어야 하는데, 그건 사람이 뜻한 것이 아니다 —
   * 눌러서 들어간 것만 한 걸음으로 남는다.
   */
  const pending = useRef<number | null>(null)
  useEffect(() => () => {
    if (pending.current !== null) window.clearTimeout(pending.current)
  }, [])
  function follow(id: string): void {
    if (pending.current !== null) window.clearTimeout(pending.current)
    pending.current = window.setTimeout(() => {
      navigate({ pathname: `/materials/${id}`, search }, { replace: true })
    }, FOLLOW_DELAY_MS)
  }

  return (
    <LeftPanel
      label="재료 목록"
      rail={
        // **접히면 아무것도 안 남는 것이 문제였다.** 다시 펴는 길이 상단 바
        // 단추뿐이었는데, 패널에서 멀어 그것이 있는 줄도 모른다 — 실제로
        // 「접기·열기 핸들을 만들어 달라」 는 말이 나왔다. 접힌 자리에 좁은
        // 띠를 남겨, **여닫는 손잡이가 여닫히는 것 옆에** 있게 한다.
        <div className="bg-background flex h-full w-8 flex-col items-center border-r pt-2">
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            onClick={panel.toggle}
            aria-label="재료 목록 펴기"
            title="재료 목록 펴기"
          >
            <ChevronRight className="size-4" />
          </Button>
          {/* 무엇을 펴는 자리인지 적는다 — 아이콘만 있으면 다음에 또 묻는다. */}
          <span
            className="text-muted-foreground mt-2 text-[11px] tracking-wide"
            style={{ writingMode: 'vertical-rl' }}
          >
            재료 목록
          </span>
        </div>
      }
    >
      <aside className="bg-background flex h-full w-64 flex-col border-r">
        <div className="border-b p-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-muted-foreground text-xs font-medium">재료 목록</span>
            <Button
              size="icon"
              variant="ghost"
              className="size-6"
              onClick={panel.toggle}
              aria-label="재료 목록 접기"
              title="재료 목록 접기"
            >
              <ChevronLeft className="size-4" />
            </Button>
          </div>
          <div className="relative">
            <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="이름 · 별칭 · Grade"
              className="h-8 pl-7 text-sm"
              aria-label="재료 찾기"
            />
          </div>

          <div className="mt-1.5 grid grid-cols-2 gap-1">
            <OptionPicker
              label="Family"
              value={family}
              options={familiesOf(known)}
              onChange={(next) => {
                setFamily(next)
                // **Family 를 바꾸면 이전 Category 가 그 안에 없을 수 있다.**
                // 남겨 두면 조용히 0건이 되고, 사람은 재료가 없는 줄 안다.
                setCategory('')
              }}
            />
            <OptionPicker
              label="Category"
              value={category}
              options={categoriesOf(known, family)}
              onChange={setCategory}
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          {rows.map((material) => {
            const here = material.id === currentId
            return (
              <Link
                key={material.id}
                // 화살표로 앞뒤 재료를 오간다. 전체 목록의 표와 같은 규칙이다 —
                // 한 화면에서만 되면 사람은 어디서 되는지를 외워야 한다.
                {...focus.rowProps(material.id)}
                // **켜 둔 탭을 갖고 간다.** CAE 카드를 보며 재료를 갈아타는데 매번
                // 시료·시편으로 떨어지면 탭을 다시 눌러야 한다. 그 재료에 없는
                // 탭이면 `tabOf` 가 첫 탭으로 돌린다.
                to={{ pathname: `/materials/${material.id}`, search }}
                aria-current={here ? 'page' : undefined}
                className={`block border-b px-3 py-2 text-sm ${ROW_FOCUS_STYLE} ${
                  here ? 'bg-muted font-medium' : 'hover:bg-muted/50'
                }`}
              >
                <div className="truncate">
                  <RecordName name={material.record_name} />
                </div>
                {/* 번호는 불변 손잡이 — 이름이 개명돼도 이걸로 찾는다. */}
                <div className="text-muted-foreground truncate text-xs">
                  {material.code}
                  {material.alias ? ` · ${material.alias}` : ''}
                </div>
              </Link>
            )
          })}

          {!loading && rows.length === 0 && (
            <p className="text-muted-foreground p-3 text-sm">찾는 재료가 없습니다.</p>
          )}

          {/* 같은 검색어로 문헌 카탈로그도 함께 — 검색은 하나다(ADR 0027). */}
          <CatalogHits q={query} className="m-2" />
        </div>

        {/* **잘렸으면 잘렸다고 말한다.** 표시도 없이 앞 50개만 보이면 뒤엣것은
            없는 재료처럼 보이고, 사람은 그 사실을 알 방법이 없다. */}
        {total > rows.length && (
          <p className="text-muted-foreground border-t px-3 py-2 text-xs">
            {total}개 중 {rows.length}개. 찾기로 좁히세요.
          </p>
        )}
      </aside>
    </LeftPanel>
  )
}
