/**
 * 시험 종류로 거르는 옆패널 — **파일 형식과 레시피가 같은 것을 쓴다.**
 *
 * 둘 다 시험 종류에 매달린 목록이다. 인장 레시피를 손보는 사람에게 DMA 레시피는
 * 소음이고, DMA 프로파일을 찾는 사람에게 인장 프로파일이 그렇다. 그런데 두
 * 화면 다 `test_type_label` 을 **표에 보여만 주고 거르지는 못했다** — 눈으로
 * 훑어야 했다.
 *
 * 자리는 재료 목록·기준정보 축과 같다(`SidePanel`). 본문 안에 두면
 * 본문의 여백 안으로 들어가고 본문과 함께 스크롤된다.
 *
 * ## 개수는 목록이 정한다
 *
 * 시험 종류 전체를 뿌리지 않고 **지금 목록에 실제로 있는 것**만 준다. 등록된
 * 종류는 스무 개인데 레시피가 인장에만 있으면, 나머지 열아홉은 눌러 봐야 0건인
 * 칸이다 — 재료 분류가 같은 이유로 `classifications` 를 쓴다(고정 목록을 박지
 * 않는다).
 *
 * ## 부서 축은 켜야 나온다
 *
 * 레시피는 부서가 갖거나 전역이다. 그런데 **부서가 하나뿐인 조직에서는 그 축이
 * 늘 한 줄짜리 소음**이다 — 개발 DB 도 지금 부서 둘에 레시피는 한 부서 것뿐이다.
 *
 * 그래서 기본은 꺼져 있고, 필요할 때 켠다. 켜 두면 **다음에 올 때도 켜져 있다**
 * (`localStorage`) — 부서가 여럿인 조직에서는 매번 켜는 것이 그 자체로 일이다.
 *
 * 두 축은 **함께 걸린다**(AND). 「인장 + 우리 부서」가 실제로 찾는 것이지,
 * 둘 중 하나만 고르게 하면 절반은 여전히 눈으로 훑어야 한다.
 */

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Building2 } from 'lucide-react'

import { Button } from '@/shared/components/ui/button'
import { LeftPanel } from '@/shared/layout/SidePanel'

/** 거를 수 있는 최소한. 프로파일이든 레시피든 이 둘만 있으면 된다. */
export interface HasTestType {
  test_type_key: string
  test_type_label: string
}

/** 부서 축을 쓰려면 이것도 있어야 한다. 없으면 그 축을 아예 안 그린다. */
export interface HasOwner {
  owner_workspace_name?: string | null
  is_global?: boolean
}

/** 전역인 것들을 묶는 이름. 부서 이름과 같은 자리에 놓는다. */
export const GLOBAL = '(전역)'

/** 소유를 사람이 읽는 이름 하나로. */
export function ownerOf(row: HasOwner): string {
  return row.is_global ? GLOBAL : (row.owner_workspace_name ?? GLOBAL)
}

/** 목록에 실제로 있는 소유자와 그 개수. */
export function ownersIn(rows: HasOwner[]): { key: string; label: string; count: number }[] {
  const seen = new Map<string, number>()
  for (const row of rows) {
    const name = ownerOf(row)
    seen.set(name, (seen.get(name) ?? 0) + 1)
  }
  return [...seen]
    .map(([label, count]) => ({ key: label, label, count }))
    // 전역이 먼저다 — 모든 부서가 쓰는 것이라 목록의 뿌리에 가깝다.
    .sort((a, b) =>
      a.label === GLOBAL ? -1 : b.label === GLOBAL ? 1 : a.label.localeCompare(b.label, 'ko')
    )
}

/** 목록에 실제로 있는 종류와 그 개수. 없는 종류는 애초에 안 보인다. */
export function testTypesIn(rows: HasTestType[]): { key: string; label: string; count: number }[] {
  const seen = new Map<string, { key: string; label: string; count: number }>()
  for (const row of rows) {
    const found = seen.get(row.test_type_key)
    if (found) found.count += 1
    else seen.set(row.test_type_key, { key: row.test_type_key, label: row.test_type_label, count: 1 })
  }
  return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label, 'ko'))
}

export function TestTypeFilterPanel<Row extends HasTestType & HasOwner>({
  label,
  rows,
  current,
  onPick,
  owner,
  onPickOwner,
  ownerKey,
  footer,
}: {
  /** 상단 바 단추에 뜨는 이름. 「레시피 종류」처럼 무엇의 목록인지 적는다. */
  label: string
  rows: Row[]
  /** `null` 이면 전체. */
  current: string | null
  onPick: (key: string | null) => void
  /**
   * 부서 축을 쓰려면 셋을 함께 준다. 안 주면 그 축을 **아예 안 그린다** —
   * 파일 형식처럼 소유가 없는 목록에서는 켤 것도 없다.
   */
  owner?: string | null
  onPickOwner?: (key: string | null) => void
  /** 켜짐 상태를 기억하는 열쇠. 화면마다 따로 기억한다. */
  ownerKey?: string
  footer?: ReactNode
}) {
  const kinds = testTypesIn(rows)
  const splittable = onPickOwner !== undefined
  const [split, setSplit] = useSticky(ownerKey ?? '', false)
  const owners = splittable && split ? ownersIn(rows) : []

  // 축을 끄면 걸어 둔 필터도 푼다. **안 풀면 안 보이는 필터가 걸린 채로 남고**,
  // 목록이 왜 짧은지 알 방법이 없다.
  useEffect(() => {
    if (!split && owner) onPickOwner?.(null)
  }, [split, owner, onPickOwner])

  return (
    <LeftPanel label={label}>
      <aside className="bg-background flex h-full w-60 flex-col border-r">
        {/* **맨 위다.** 목록 아래에 두면 축이 길어질수록 멀어지고, 스크롤을
            내려야 보인다 — 목록의 모양을 바꾸는 단추가 그 목록에 가려지면 안 된다.

            부서가 하나뿐인 조직에서는 이 축이 늘 한 줄짜리 소음이라 기본은 꺼져
            있고, 켠 상태는 다음에 올 때까지 남는다. */}
        {splittable && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-pressed={split}
            className="text-muted-foreground h-7 shrink-0 justify-start rounded-none border-b px-3 text-sm"
            onClick={() => setSplit(!split)}
          >
            <Building2 className="size-3.5" />
            부서로 나누기 {split ? '끄기' : '켜기'}
          </Button>
        )}

        <div className="min-h-0 flex-1 overflow-auto py-1">
          <Row
            label="전체"
            count={rows.length}
            here={current === null}
            onClick={() => onPick(null)}
          />
          {kinds.map((kind) => (
            <Row
              key={kind.key}
              label={kind.label}
              count={kind.count}
              here={current === kind.key}
              onClick={() => onPick(kind.key)}
            />
          ))}

          {/* **비어 있으면 왜 비었는지 말한다.** 빈 옆패널은 고장으로 보인다. */}
          {rows.length === 0 && (
            <p className="text-muted-foreground p-3 text-sm">아직 등록된 것이 없습니다.</p>
          )}

          {split && owners.length > 0 && (
            <>
              <p className="text-muted-foreground mt-3 px-3 py-1 text-xs font-medium">
                부서
              </p>
              <Row
                label="전체"
                count={rows.length}
                here={!owner}
                onClick={() => onPickOwner?.(null)}
              />
              {owners.map((item) => (
                <Row
                  key={item.key}
                  label={item.label}
                  count={item.count}
                  here={owner === item.key}
                  onClick={() => onPickOwner?.(item.key)}
                />
              ))}
            </>
          )}
        </div>

        {footer}
      </aside>
    </LeftPanel>
  )
}

function Row({
  label,
  count,
  here,
  onClick,
}: {
  label: string
  count: number
  here: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-current={here ? 'true' : undefined}
      onClick={onClick}
      className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-sm ${
        here ? 'bg-muted font-medium' : 'hover:bg-muted/50'
      }`}
    >
      <span className="truncate">{label}</span>
      <span className="text-muted-foreground ml-2 shrink-0 tabular-nums">{count}</span>
    </button>
  )
}

/**
 * 켜짐 상태를 브라우저에 남긴다.
 *
 * 부서가 여럿인 조직에서는 **매번 켜는 것이 그 자체로 일이다.** 반대로 서버에
 * 저장할 일은 아니다 — 보는 방식이지 데이터가 아니고, 사람마다 다르다.
 *
 * `localStorage` 는 사생활 보호 모드나 정책에 따라 던진다. 그때는 기억을 포기하고
 * 기본값으로 돈다 — **화면이 안 뜨는 것보다 낫다.**
 */
function useSticky(key: string, fallback: boolean): [boolean, (next: boolean) => void] {
  const name = `mnx.split.${key}`
  const [value, setValue] = useState(() => {
    if (!key) return fallback
    try {
      const found = window.localStorage.getItem(name)
      return found === null ? fallback : found === '1'
    } catch {
      return fallback
    }
  })
  return [
    value,
    (next: boolean) => {
      setValue(next)
      if (!key) return
      try {
        window.localStorage.setItem(name, next ? '1' : '0')
      } catch {
        /* 못 남겨도 이번 세션에는 켜져 있다. */
      }
    },
  ]
}
