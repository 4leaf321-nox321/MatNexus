/**
 * 부서 관리 (시스템 관리자) — **조직도 그대로.**
 *
 * ReportArchive 의 부서 트리를 참조했다. 평면 표였을 때의 문제:
 *
 *   - 같은 이름의 팀이 본부마다 있으면 표에서 **구분할 방법이 없다**
 *   - 조직 개편(팀을 다른 본부로)을 화면에서 할 수 없었다
 *   - 순서가 이름순이라 조직도 순서와 늘 달랐다
 *
 * RA 는 끌어 놓기(DnD)로 옮기는데, 여기서는 **상위 부서 고르기 + 위/아래**로
 * 한다. 라이브러리를 하나 덜 쓰고, 키보드로도 되고, 조직 개편은 자주 하는 일이
 * 아니다. 대신 옮길 곳을 *검색해서* 고를 수 있다 — 부서가 많아지면 끌어 놓기가
 * 오히려 어렵다(화면 밖으로 끌어야 한다).
 *
 * 삭제 버튼이 없는 것은 그대로다. 부서에는 시험 데이터가 매달리므로, 무엇이 그
 * 부서를 참조하는지 답할 수 있게 된 뒤에야 삭제를 논한다(의존성 레지스트리, 1-2).
 */

import { useState } from 'react'
import {
  Archive,
  ArchiveRestore,
  Building2,
  ChevronDown,
  ChevronUp,
  CornerDownRight,
  Loader2,
  Plus,
  Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { workspacesApi } from '@/modules/workspaces/api'
import type { Workspace } from '@/modules/workspaces/api'
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'

export default function WorkspacesAdminPage() {
  const workspaces = useResource(() => workspacesApi.list(true), [])
  const [creating, setCreating] = useState(false)
  const [busySlug, setBusySlug] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const rows = workspaces.data ?? []

  /** 서버가 준 트리 순서를 그대로 쓴다 — 화면이 다시 정렬하면 두 순서가 갈라진다. */
  async function run(slug: string, action: () => Promise<unknown>) {
    setBusySlug(slug)
    setError(null)
    try {
      await action()
      workspaces.reload()
    } catch (caught) {
      // 서버가 이유를 준다: "하위 부서 2개가 아직 활성입니다(…)" 처럼.
      setError(caught instanceof Error ? caught : new Error('변경에 실패했습니다.'))
    } finally {
      setBusySlug(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="부서 관리"
        description="조직도 그대로 봅니다. 본부 아래 팀을 두고, 개편하면 옮깁니다 — 자료는 따라 움직이지 않습니다."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            부서 만들기
          </Button>
        }
      />

      <ErrorNotice error={error ?? workspaces.error} className="mb-4" />

      {workspaces.loading && (
        <div className="text-muted-foreground rounded-md border py-10 text-center">
          <Loader2 className="mx-auto size-4 animate-spin" />
        </div>
      )}

      {!workspaces.loading && rows.length === 0 && (
        <div className="text-muted-foreground rounded-md border py-10 text-center text-sm">
          부서가 없습니다.
        </div>
      )}

      <ul className="space-y-1">
        {rows.map((workspace, index) => {
          const busy = busySlug === workspace.slug
          const siblings = rows.filter((row) => row.parent_slug === workspace.parent_slug)
          const position = siblings.findIndex((row) => row.slug === workspace.slug)

          return (
            <li
              key={workspace.id}
              className="flex flex-wrap items-center gap-2 rounded-md border p-2"
              // 들여쓰기가 계층이다. 표의 '상위' 열보다 눈으로 읽기 쉽다.
              style={{ marginLeft: `${workspace.depth * 24}px` }}
            >
              {workspace.depth > 0 && (
                <CornerDownRight className="text-muted-foreground size-3.5 shrink-0" />
              )}
              <Building2 className="text-muted-foreground size-4 shrink-0" />
              <span className="font-medium">{workspace.name}</span>
              <span className="text-muted-foreground font-mono text-xs">
                {workspace.slug}
              </span>
              <Badge variant="outline" className="gap-1">
                <Users className="size-3" />
                {workspace.member_count}
              </Badge>
              {!workspace.is_active && (
                <Badge variant="outline" className="text-muted-foreground">
                  보관
                </Badge>
              )}

              <div className="ml-auto flex items-center gap-1">
                {/* 순서는 형제 사이에서만 의미가 있다. 끝이면 눌러도 아무 일이
                    없으므로 아예 막아 둔다 — 눌리는데 안 움직이면 고장으로 보인다. */}
                <Button
                  size="sm"
                  variant="ghost"
                  title="위로"
                  disabled={busy || position <= 0}
                  onClick={() => run(workspace.slug, () => workspacesApi.reorder(workspace.slug, 'up'))}
                >
                  <ChevronUp className="size-3.5" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  title="아래로"
                  disabled={busy || position < 0 || position >= siblings.length - 1}
                  onClick={() =>
                    run(workspace.slug, () => workspacesApi.reorder(workspace.slug, 'down'))
                  }
                >
                  <ChevronDown className="size-3.5" />
                </Button>

                <MoveControl
                  workspace={workspace}
                  all={rows}
                  disabled={busy}
                  onMove={(parentSlug) =>
                    run(workspace.slug, () => workspacesApi.move(workspace.slug, parentSlug))
                  }
                />

                <Button size="sm" variant="outline" asChild>
                  <Link to={`/w/${workspace.slug}/members`}>
                    <Users className="size-3.5" />
                    멤버
                  </Link>
                </Button>

                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  title={
                    workspace.is_active
                      ? '보관합니다. 활성 하위 부서가 있으면 서버가 막습니다.'
                      : '되살립니다.'
                  }
                  onClick={() =>
                    run(workspace.slug, () =>
                      workspacesApi.update(workspace.slug, { is_active: !workspace.is_active })
                    )
                  }
                >
                  {workspace.is_active ? (
                    <>
                      <Archive className="size-3.5" />
                      보관
                    </>
                  ) : (
                    <>
                      <ArchiveRestore className="size-3.5" />
                      되살리기
                    </>
                  )}
                </Button>
              </div>
              {index === 0 && null}
            </li>
          )
        })}
      </ul>

      <p className="text-muted-foreground mt-4 text-xs">
        <b>옮겨도 자료는 하나도 안 움직입니다.</b> 시험·재료는 부서의 내부 id 를
        가리키고, 트리를 옮겨도 그 id 는 그대로입니다. 부서 이름이나 주소를 고쳐도
        마찬가지입니다.
      </p>

      <CreateDialog
        open={creating}
        all={rows}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false)
          workspaces.reload()
        }}
      />
    </div>
  )
}

/** 상위 부서 바꾸기. 자기 하위로는 못 옮긴다 — 서버도 막지만 고를 수 없게 한다. */
function MoveControl({
  workspace,
  all,
  disabled,
  onMove,
}: {
  workspace: Workspace
  all: Workspace[]
  disabled?: boolean
  onMove: (parentSlug: string | null) => void
}) {
  const [open, setOpen] = useState(false)

  const forbidden = new Set<string>([workspace.slug])
  let grew = true
  while (grew) {
    grew = false
    for (const row of all) {
      if (row.parent_slug && forbidden.has(row.parent_slug) && !forbidden.has(row.slug)) {
        forbidden.add(row.slug)
        grew = true
      }
    }
  }
  const candidates = all.filter((row) => !forbidden.has(row.slug))

  return (
    <>
      <Button size="sm" variant="ghost" disabled={disabled} onClick={() => setOpen(true)}>
        상위 바꾸기
      </Button>

      <Dialog open={open} onOpenChange={(next) => !next && setOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{workspace.name} 의 상위 부서</DialogTitle>
            <DialogDescription>
              조직 개편입니다. <b>자료는 따라 움직이지 않습니다</b> — 시험·재료는 부서의
              내부 id 를 가리키고 그 id 는 그대로입니다. 하위 부서는 함께 따라옵니다.
            </DialogDescription>
          </DialogHeader>

          <WorkspacePicker
            workspaces={candidates}
            value={workspace.parent_slug}
            excludeArchived={workspace.is_active}
            placeholder="상위 부서 고르기"
            className="w-full"
            emptyLabel="옮길 수 있는 부서가 없습니다"
            onChange={(slug) => {
              onMove(slug)
              setOpen(false)
            }}
          />

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                onMove(null)
                setOpen(false)
              }}
            >
              최상위로 올리기
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              닫기
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function CreateDialog({
  open,
  all,
  onClose,
  onCreated,
}: {
  open: boolean
  all: Workspace[]
  onClose: () => void
  onCreated: () => void
}) {
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [parent, setParent] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await workspacesApi.create(slug, name, parent)
      setSlug('')
      setName('')
      setParent(null)
      onCreated()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('생성에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>부서 만들기</DialogTitle>
          <DialogDescription>
            만든 사람이 그 부서의 관리자가 됩니다. 관리자가 없는 부서는 멤버를 넣을 수 없습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="ws-name">부서 이름</Label>
            <Input
              id="ws-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예) 금속재료팀"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ws-slug">주소</Label>
            <Input
              id="ws-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="metal"
            />
            <p className="text-muted-foreground text-xs">
              URL 에 쓰입니다. 영소문자·숫자·하이픈만 가능합니다.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>상위 부서 (선택)</Label>
            <div className="flex gap-1">
              <WorkspacePicker
                workspaces={all}
                value={parent}
                excludeArchived
                placeholder="없음 — 최상위"
                className="w-full flex-1"
                onChange={setParent}
              />
              {parent && (
                <Button variant="ghost" onClick={() => setParent(null)}>
                  지우기
                </Button>
              )}
            </div>
            <p className="text-muted-foreground text-xs">
              비워 두면 최상위 부서가 됩니다. 나중에 바꿀 수 있습니다.
            </p>
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !slug || !name} onClick={submit}>
            만들기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
