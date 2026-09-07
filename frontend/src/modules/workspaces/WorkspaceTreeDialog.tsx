/**
 * 부서 트리에서 고르기 — **목록이 길어졌을 때의 두 번째 길.**
 *
 * `WorkspacePicker` 는 검색으로 좁힌다. 그런데 조직이 수백이 되면 **찾을 이름을
 * 이미 알고 있어야** 검색이 쓸모가 있다. 조직도를 훑어 내려가며 고르는 길이
 * 따로 있어야 하는 이유다 — "그 장비가 어느 본부 밑이더라" 는 검색으로 못 푼다.
 *
 * **접기가 기본이다.** 다 펴 놓으면 트리인 의미가 없다. 골라져 있는 값이 있으면
 * 그 길만 펴서 연다 — 열자마자 지금 무엇이 골라져 있는지 보여야 한다.
 */

import { useMemo, useState } from 'react'
import { Building2, ChevronDown, ChevronRight } from 'lucide-react'

import type { PickableWorkspace } from '@/modules/workspaces/WorkspacePicker'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

/** 트리를 그리려면 부모가 필요하다 — `WorkspacePicker` 가 쓰는 모양에 하나 더. */
export interface TreeWorkspace extends PickableWorkspace {
  parent_slug: string | null
}

function childrenOf(all: TreeWorkspace[], slug: string | null): TreeWorkspace[] {
  return all.filter((one) => (one.parent_slug ?? null) === slug)
}

/** 뿌리에서 이 값까지의 slug 들. 열자마자 골라진 자리가 보이게 편다. */
function pathTo(all: TreeWorkspace[], slug: string | null): string[] {
  const by = new Map(all.map((one) => [one.slug, one]))
  const found: string[] = []
  let at = slug ? by.get(slug) : undefined
  while (at?.parent_slug) {
    found.push(at.parent_slug)
    at = by.get(at.parent_slug)
  }
  return found
}

function Node({
  all,
  node,
  value,
  open,
  onToggle,
  onPick,
}: {
  all: TreeWorkspace[]
  node: TreeWorkspace
  value: string | null
  open: Set<string>
  onToggle: (slug: string) => void
  onPick: (slug: string) => void
}) {
  const kids = childrenOf(all, node.slug)
  const expanded = open.has(node.slug)
  const chosen = node.slug === value
  return (
    <li>
      <div
        className={`flex items-center gap-1 rounded px-1 py-0.5 ${
          chosen ? 'bg-accent font-medium' : ''
        }`}
      >
        {kids.length > 0 ? (
          <button
            type="button"
            className="text-muted-foreground"
            aria-label={expanded ? '접기' : '펴기'}
            onClick={() => onToggle(node.slug)}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          // 자식이 없어도 자리를 비워 둔다 — 안 그러면 같은 층의 이름이 어긋난다.
          <span className="inline-block w-[14px]" />
        )}
        <button
          type="button"
          className="flex-1 text-left text-sm hover:underline"
          onClick={() => onPick(node.slug)}
        >
          {node.name}
          {node.is_active === false && (
            <span className="text-muted-foreground ml-1 text-xs">(보관)</span>
          )}
        </button>
      </div>
      {expanded && kids.length > 0 && (
        <ul className="ml-4 border-l pl-2">
          {kids.map((kid) => (
            <Node
              key={kid.slug}
              all={all}
              node={kid}
              value={value}
              open={open}
              onToggle={onToggle}
              onPick={onPick}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

export function WorkspaceTreeDialog({
  workspaces,
  value,
  onChange,
  onClose,
}: {
  workspaces: TreeWorkspace[]
  value: string | null
  onChange: (slug: string) => void
  onClose: () => void
}) {
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(pathTo(workspaces, value))
  )
  const roots = useMemo(() => childrenOf(workspaces, null), [workspaces])

  function toggle(slug: string) {
    setOpen((was) => {
      const next = new Set(was)
      if (next.has(slug)) next.delete(slug)
      else next.add(slug)
      return next
    })
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Building2 size={16} /> 조직도에서 고르기
          </DialogTitle>
          <DialogDescription>
            본부를 펴 내려가며 고릅니다. 이름을 알고 있으면 위 칸에서 검색하는 편이
            빠릅니다.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-96 overflow-y-auto">
          {roots.length === 0 ? (
            <p className="text-muted-foreground text-sm">부서가 없습니다.</p>
          ) : (
            <ul>
              {roots.map((root) => (
                <Node
                  key={root.slug}
                  all={workspaces}
                  node={root}
                  value={value}
                  open={open}
                  onToggle={toggle}
                  onPick={(slug) => {
                    onChange(slug)
                    onClose()
                  }}
                />
              ))}
            </ul>
          )}
        </div>
        <div className="flex justify-end gap-2">
          {value && (
            <Button
              variant="ghost"
              onClick={() => {
                onChange('')
                onClose()
              }}
            >
              고른 것 지우기
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
