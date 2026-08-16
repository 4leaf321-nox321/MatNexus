/**
 * 부서 트리 — 끌어 놓기로 옮긴다.
 *
 * ReportArchive 의 `WorkspaceTreeDnD` 를 참조했다. 거기서 가져온 **드롭 자리 두
 * 개** 구조가 핵심이다.
 *
 *   줄 위쪽 얇은 띠  →  그 부서의 **앞 형제**가 된다
 *   줄 본문         →  그 부서의 **마지막 자식**이 된다
 *
 * '뒤 형제' 자리를 따로 두지 않는다. 맨 뒤로 보내려면 부모 줄에 놓으면 된다(그
 * 부모의 마지막 자식이 된다). 자리가 둘이면 어떤 위치든 한두 번에 닿으면서
 * 화면이 단순해진다 — RA 도 같은 이유로 둘만 둔다.
 *
 * **라이브러리를 쓰지 않는다.** RA 는 `@dnd-kit` 을 쓰지만, 여기는 세로 목록
 * 하나뿐이라 브라우저의 기본 끌어 놓기로 충분하다. 이 프로젝트는 차트에서도
 * 같은 판단을 했다(Recharts 100KB 대신 SVG 직접).
 *
 * 끌어 놓기가 **유일한 길이면 안 된다.** 터치·키보드로는 못 쓰고, 부서가 많아지면
 * 화면 밖으로 끌어야 한다. 그래서 위/아래 버튼과 '상위 바꾸기'(검색해서 고르기)를
 * 그대로 둔다 — 끌어 놓기는 빠른 길이지 유일한 길이 아니다.
 */

import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { CornerDownRight, GripVertical } from 'lucide-react'

import type { Workspace } from '@/modules/workspaces/api'

/** 드롭 자리. `before` = 그 줄 앞에, `inside` = 그 줄의 자식으로. */
type Zone = 'before' | 'inside'

interface Props {
  workspaces: Workspace[]
  disabled?: boolean
  /** `(끌린 부서, 상위, 이 부서 앞에)` — `before` 가 없으면 맨 뒤로. */
  onDrop: (slug: string, parentSlug: string | null, beforeSlug: string | null) => void
  children: (workspace: Workspace) => ReactNode
}

export function WorkspaceTree({ workspaces, disabled, onDrop, children }: Props) {
  const [dragging, setDragging] = useState<string | null>(null)
  const [over, setOver] = useState<{ slug: string; zone: Zone } | null>(null)

  /** 자기 자신과 하위에는 놓을 수 없다. 놓이면 트리가 끊어진 고리가 된다. */
  const forbidden = useMemo(() => {
    if (!dragging) return new Set<string>()
    const set = new Set([dragging])
    let grew = true
    while (grew) {
      grew = false
      for (const row of workspaces) {
        if (row.parent_slug && set.has(row.parent_slug) && !set.has(row.slug)) {
          set.add(row.slug)
          grew = true
        }
      }
    }
    return set
  }, [dragging, workspaces])

  function zoneOf(event: React.DragEvent, slug: string): Zone | null {
    if (forbidden.has(slug)) return null
    const box = event.currentTarget.getBoundingClientRect()
    // 위쪽 1/3 은 '앞에 끼우기'. 나머지는 '자식으로'. 띠를 너무 얇게 잡으면
    // 조준이 어렵고, 너무 두껍게 잡으면 자식으로 넣기가 어렵다.
    return event.clientY - box.top < box.height / 3 ? 'before' : 'inside'
  }

  return (
    <ul className="space-y-1">
      {workspaces.map((workspace) => {
        const isOver = over?.slug === workspace.slug
        const blocked = forbidden.has(workspace.slug)

        return (
          <li
            key={workspace.id}
            style={{ marginLeft: `${workspace.depth * 24}px` }}
            draggable={!disabled}
            onDragStart={(event) => {
              setDragging(workspace.slug)
              event.dataTransfer.effectAllowed = 'move'
              // 파이어폭스는 데이터가 없으면 드래그를 시작하지 않는다.
              event.dataTransfer.setData('text/plain', workspace.slug)
            }}
            onDragEnd={() => {
              setDragging(null)
              setOver(null)
            }}
            onDragOver={(event) => {
              if (!dragging) return
              const zone = zoneOf(event, workspace.slug)
              if (!zone) return
              // preventDefault 를 해야 브라우저가 '놓을 수 있는 곳' 으로 친다.
              event.preventDefault()
              event.dataTransfer.dropEffect = 'move'
              setOver({ slug: workspace.slug, zone })
            }}
            onDragLeave={() => setOver((current) => (current?.slug === workspace.slug ? null : current))}
            onDrop={(event) => {
              event.preventDefault()
              const zone = over?.slug === workspace.slug ? over.zone : zoneOf(event, workspace.slug)
              const moved = dragging
              setDragging(null)
              setOver(null)
              if (!moved || !zone || moved === workspace.slug) return
              if (zone === 'before') {
                onDrop(moved, workspace.parent_slug, workspace.slug)
              } else {
                onDrop(moved, workspace.slug, null)
              }
            }}
            className={[
              'flex flex-wrap items-center gap-2 rounded-md border p-2',
              dragging === workspace.slug ? 'opacity-40' : '',
              // 놓일 자리를 **다르게** 보여 준다. 둘이 같아 보이면 앞에 끼우려다
              // 자식으로 들어가는 일이 계속 생긴다.
              isOver && over?.zone === 'before' ? 'border-t-primary border-t-2' : '',
              isOver && over?.zone === 'inside' ? 'ring-primary bg-primary/5 ring-2' : '',
              dragging && blocked ? 'opacity-30' : '',
            ].join(' ')}
          >
            {!disabled && (
              <GripVertical className="text-muted-foreground size-4 shrink-0 cursor-grab" />
            )}
            {workspace.depth > 0 && (
              <CornerDownRight className="text-muted-foreground size-3.5 shrink-0" />
            )}
            {children(workspace)}
          </li>
        )
      })}

      {/* 맨 아래 빈 자리 — **최상위로 올리는 길이 끌어 놓기에도 있어야 한다.**
          없으면 자식을 뿌리로 빼려면 버튼을 써야 하는데, 끌어 놓기를 쓰던 사람은
          그걸 찾지 못한다. */}
      {dragging && (
        <li
          onDragOver={(event) => {
            event.preventDefault()
            event.dataTransfer.dropEffect = 'move'
            setOver({ slug: '', zone: 'inside' })
          }}
          onDrop={(event) => {
            event.preventDefault()
            const moved = dragging
            setDragging(null)
            setOver(null)
            if (moved) onDrop(moved, null, null)
          }}
          className={`text-muted-foreground rounded-md border border-dashed p-3 text-center text-xs ${
            over?.slug === '' ? 'ring-primary bg-primary/5 ring-2' : ''
          }`}
        >
          여기에 놓으면 최상위 부서가 됩니다
        </li>
      )}
    </ul>
  )
}
