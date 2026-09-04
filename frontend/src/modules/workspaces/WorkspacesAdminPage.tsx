/**
 * 부서 관리 (시스템 관리자) — **조직도 그대로.**
 *
 * ReportArchive 의 부서 트리를 참조했다. 평면 표였을 때의 문제:
 *
 *   - 같은 이름의 팀이 본부마다 있으면 표에서 **구분할 방법이 없다**
 *   - 조직 개편(팀을 다른 본부로)을 화면에서 할 수 없었다
 *   - 순서가 이름순이라 조직도 순서와 늘 달랐다
 *   - **이름을 고칠 수 없었다.** 만들기만 있고 수정이 없었다
 *
 * 옮기는 길을 셋 둔다. 끌어 놓기는 빠른 길이지 유일한 길이 아니다 — 터치·키보드
 * 로는 못 쓰고, 부서가 많아지면 화면 밖으로 끌어야 한다.
 *
 *   끌어 놓기      빠르다. 가까운 자리로 옮길 때
 *   상위 바꾸기     검색해서 고른다. 멀리 옮길 때
 *   위/아래        형제 사이 한 칸. 키보드로도 된다
 *
 * **삭제는 참조를 보여 준 다음에 한다.** 보관이 여전히 기본 수단이다 — 삭제는
 * 잘못 만든 부서처럼 자료가 아예 없는 경우를 위한 것이다.
 */

import { useState } from 'react'
import {
  Archive,
  ArchiveRestore,
  Building2,
  ChevronDown,
  ChevronUp,
  FileUp,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
  Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { workspacesApi } from '@/modules/workspaces/api'
import type { Reference, Workspace } from '@/modules/workspaces/api'
import { WorkspacePicker } from '@/modules/workspaces/WorkspacePicker'
import { CopyId } from '@/shared/components/CopyId'
import { WorkspaceTree } from '@/modules/workspaces/WorkspaceTree'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { ImportWorkspacesDialog } from '@/modules/workspaces/ImportWorkspacesDialog'
import { MergeWorkspaceDialog } from '@/modules/workspaces/MergeWorkspaceDialog'
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
  const [importing, setImporting] = useState(false)
  const [merging, setMerging] = useState<Workspace | null>(null)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Workspace | null>(null)
  const [deleting, setDeleting] = useState<Workspace | null>(null)
  const [moving, setMoving] = useState<Workspace | null>(null)
  const [query, setQuery] = useState('')
  const [busySlug, setBusySlug] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const rows = workspaces.data ?? []

  /** 검색은 **거르지 않고 표시만 한다.** 트리에서 부모가 빠지면 자식이 뿌리처럼
   *  보여 계층이 거짓말이 된다. 맞는 줄을 강조하고 나머지는 흐린다. */
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  function matches(workspace: Workspace): boolean {
    if (words.length === 0) return true
    const haystack = `${workspace.path} ${workspace.slug}`.toLowerCase()
    return words.every((word) => haystack.includes(word))
  }

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
    <div>
      <PageHeader
        title="부서 관리"
        description="조직도 그대로 봅니다. 끌어 놓아 옮기고, 개편해도 자료는 따라 움직이지 않습니다."
        actions={
          <span className="flex items-center gap-2">
            {/* **조직도를 두 번 치지 않는다.** ReportArchive 에 이미 있는 트리를
                내보내기 한 장으로 들여온다 — 양쪽에 손으로 치면 오타 하나로
                「같은 부서가 다른 이름」 이 된다. */}
            <Button variant="outline" onClick={() => setImporting(true)}>
              <FileUp className="size-4" />
              가져오기
            </Button>
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" />
              부서 만들기
            </Button>
          </span>
        }
      />

      <ErrorNotice error={error ?? workspaces.error} className="mb-4" />

      <ImportWorkspacesDialog
        open={importing}
        onClose={() => setImporting(false)}
        onDone={() => workspaces.reload()}
      />

      <MergeWorkspaceDialog
        workspace={merging}
        candidates={workspaces.data ?? []}
        onClose={() => setMerging(null)}
        onDone={() => workspaces.reload()}
      />

      <div className="mb-3 flex items-center gap-2">
        <div className="relative">
          <Search className="text-muted-foreground absolute top-1/2 left-2 size-3.5 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="부서 찾기"
            className="h-9 w-64 pl-7"
          />
        </div>
        <span className="text-muted-foreground text-xs">
          {query
            ? `${rows.filter(matches).length}개 일치 — 계층을 보여 주려고 나머지도 남깁니다`
            : `${rows.length}개`}
        </span>
      </div>

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

      <WorkspaceTree
        workspaces={rows}
        disabled={busySlug !== null}
        onDrop={(slug, parentSlug, beforeSlug) =>
          run(slug, () => workspacesApi.move(slug, parentSlug, beforeSlug))
        }
      >
        {(workspace) => {
          const busy = busySlug === workspace.slug
          const siblings = rows.filter((row) => row.parent_slug === workspace.parent_slug)
          const position = siblings.findIndex((row) => row.slug === workspace.slug)
          const dimmed = words.length > 0 && !matches(workspace)

          return (
            <>
              <Building2 className="text-muted-foreground size-4 shrink-0" />
              <span className={`font-medium ${dimmed ? 'opacity-40' : ''}`}>
                {workspace.name}
              </span>
              <span className="text-muted-foreground font-mono text-xs">{workspace.slug}</span>
              {/* 장비 커넥터 마법사가 부서 id 를 요구한다 — 손으로 옮겨 적지 않게. */}
              <CopyId value={workspace.id} label="부서 ID" />
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
                {/* 끝이면 눌러도 안 움직이므로 아예 막는다 — 눌리는데 반응이 없으면
                    고장으로 보인다. */}
                <Button
                  size="sm"
                  variant="ghost"
                  title="위로"
                  disabled={busy || position <= 0}
                  onClick={() =>
                    run(workspace.slug, () => workspacesApi.reorder(workspace.slug, 'up'))
                  }
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

                <Button
                  size="sm"
                  variant="ghost"
                  title="이름 바꾸기"
                  disabled={busy}
                  onClick={() => setEditing(workspace)}
                >
                  <Pencil className="size-3.5" />
                </Button>

                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => setMoving(workspace)}
                >
                  상위 바꾸기
                </Button>

                {/* **자료가 매달려 못 지우는 부서의 출구.** 자료·멤버를 다른
                    부서로 옮기고 이 부서는 보관한다 — 기준정보의 병합과 같은
                    무늬다. */}
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => setMerging(workspace)}
                >
                  합치기
                </Button>

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
                    <Archive className="size-3.5" />
                  ) : (
                    <ArchiveRestore className="size-3.5" />
                  )}
                </Button>

                <Button
                  size="sm"
                  variant="ghost"
                  title="삭제 — 자료가 없을 때만 됩니다"
                  disabled={busy}
                  onClick={() => setDeleting(workspace)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            </>
          )
        }}
      </WorkspaceTree>

      <p className="text-muted-foreground mt-4 text-xs">
        줄을 끌어 <b>다른 줄 위쪽 띠</b>에 놓으면 그 앞으로, <b>줄 안쪽</b>에 놓으면 그
        하위로 들어갑니다. <b>옮겨도 자료는 하나도 안 움직입니다</b> — 시험·재료는 부서의
        내부 id 를 가리키고, 트리를 옮기거나 이름을 고쳐도 그 id 는 그대로입니다.
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

      <RenameDialog
        workspace={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null)
          workspaces.reload()
        }}
      />

      <MoveDialog
        workspace={moving}
        all={rows}
        onClose={() => setMoving(null)}
        onMove={(parentSlug) => {
          const slug = moving?.slug
          setMoving(null)
          if (slug) void run(slug, () => workspacesApi.move(slug, parentSlug))
        }}
      />

      <DeleteDialog
        workspace={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={() => {
          setDeleting(null)
          workspaces.reload()
        }}
      />
    </div>
  )
}

/** 이름 바꾸기. **주소(slug)는 못 바꾼다** — 즐겨찾기·공유한 링크가 끊어진다. */
function RenameDialog({
  workspace,
  onClose,
  onSaved,
}: {
  workspace: Workspace | null
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const open = workspace !== null
  if (open && name === '' && workspace) {
    // 열릴 때 한 번 채운다. useEffect 를 쓰면 타이핑 중에 되돌아가는 경우가 생긴다.
    setName(workspace.name)
  }

  async function submit() {
    if (!workspace) return
    setBusy(true)
    setError(null)
    try {
      await workspacesApi.update(workspace.slug, { name })
      setName('')
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('저장하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setName('')
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>부서 이름</DialogTitle>
          <DialogDescription>
            이름을 고쳐도 <b>자료는 그대로입니다</b> — 참조가 내부 id 라서 조직 개편이나
            오타 수정이 데이터를 건드리지 않습니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="rename">이름</Label>
          <Input id="rename" value={name} onChange={(event) => setName(event.target.value)} />
          <p className="text-muted-foreground text-xs">
            주소 <code>{workspace?.slug}</code> 는 바꾸지 않습니다 — 즐겨찾기와 공유한
            링크가 끊어집니다.
          </p>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !name.trim()} onClick={submit}>
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 삭제 — **무엇이 이 부서를 가리키는지 보여 준 다음에.**
 *
 * 참조 목록은 서버가 FK 를 훑어 모은다. 손으로 관리하는 목록은 반드시 뒤처진다 —
 * RA 의 부서 삭제 500 버그가 그것이었다(새 테이블이 검사에서 빠짐).
 */
function DeleteDialog({
  workspace,
  onClose,
  onDeleted,
}: {
  workspace: Workspace | null
  onClose: () => void
  onDeleted: () => void
}) {
  const references = useResource<Reference[]>(
    () => (workspace ? workspacesApi.references(workspace.slug) : Promise.resolve([])),
    [workspace?.slug]
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const rows = references.data ?? []
  const blocking = rows.filter((row) => row.blocks_delete)
  const cascading = rows.filter((row) => !row.blocks_delete)

  async function submit() {
    if (!workspace) return
    setBusy(true)
    setError(null)
    try {
      await workspacesApi.remove(workspace.slug)
      onDeleted()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('삭제하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={workspace !== null} onOpenChange={(next) => !next && onClose()}>
      {/* 확인창 — 입력 칸이 없다. 짧은 문장과 단추 둘뿐이라
          기본값(폼 폭)은 여기 과하다. */}
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{workspace?.name} 삭제</DialogTitle>
          <DialogDescription>
            <b>보관이 기본 수단입니다.</b> 삭제는 잘못 만든 부서처럼 자료가 없는 경우를
            위한 것입니다 — 자료가 있으면 지우지 말고 보관하세요.
          </DialogDescription>
        </DialogHeader>

        {references.loading && (
          <p className="text-muted-foreground text-sm">무엇이 걸려 있는지 확인하는 중…</p>
        )}

        {!references.loading && blocking.length > 0 && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
            <p className="font-medium text-amber-700 dark:text-amber-500">
              지울 수 없습니다 — 이 부서를 가리키는 자료가 있습니다
            </p>
            <ul className="mt-2 space-y-0.5 text-xs text-amber-800 dark:text-amber-400">
              {blocking.map((row) => (
                <li key={`${row.table}.${row.column}`}>
                  {row.label} {row.count}건
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-amber-800 dark:text-amber-400">
              자료를 다른 부서로 옮기거나, 지우는 대신 <b>보관</b>하세요.
            </p>
          </div>
        )}

        {!references.loading && blocking.length === 0 && (
          <div className="space-y-2 text-sm">
            <p>지울 수 있습니다. 함께 사라지는 것:</p>
            <ul className="text-muted-foreground space-y-0.5 text-xs">
              {cascading.length === 0 && <li>없습니다.</li>}
              {cascading.map((row) => (
                <li key={`${row.table}.${row.column}`}>
                  {row.label} {row.count}건{' '}
                  {row.on_delete === 'SET NULL' ? '(연결만 끊깁니다)' : '(함께 삭제됩니다)'}
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground text-xs">되돌릴 수 없습니다.</p>
          </div>
        )}

        <ErrorNotice error={references.error ?? error} />

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button
            variant="destructive"
            disabled={busy || references.loading || blocking.length > 0}
            onClick={submit}
          >
            삭제
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 상위 부서 바꾸기. 자기 하위로는 못 옮긴다 — 서버도 막지만 고를 수 없게 한다. */
function MoveDialog({
  workspace,
  all,
  onClose,
  onMove,
}: {
  workspace: Workspace | null
  all: Workspace[]
  onClose: () => void
  onMove: (parentSlug: string | null) => void
}) {
  if (!workspace) return null

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

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{workspace.name} 의 상위 부서</DialogTitle>
          <DialogDescription>
            조직 개편입니다. <b>자료는 따라 움직이지 않습니다</b> — 시험·재료는 부서의
            내부 id 를 가리키고 그 id 는 그대로입니다. 하위 부서는 함께 따라옵니다.
          </DialogDescription>
        </DialogHeader>

        <WorkspacePicker
          workspaces={all.filter((row) => !forbidden.has(row.slug))}
          value={workspace.parent_slug}
          excludeArchived={workspace.is_active}
          placeholder="상위 부서 고르기"
          className="w-full"
          emptyLabel="옮길 수 있는 부서가 없습니다"
          onChange={onMove}
        />

        <DialogFooter>
          <Button variant="outline" onClick={() => onMove(null)}>
            최상위로 올리기
          </Button>
          <Button variant="ghost" onClick={onClose}>
            닫기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
              URL 에 쓰입니다. 영소문자·숫자·하이픈, 2자 이상. <b>나중에 못 바꿉니다</b> —
              공유한 링크가 끊어집니다.
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
              비워 두면 최상위 부서가 됩니다. 나중에 끌어 놓아 옮길 수 있습니다.
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
