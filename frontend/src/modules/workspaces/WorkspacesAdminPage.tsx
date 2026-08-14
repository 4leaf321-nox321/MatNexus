/**
 * 부서 관리 (시스템 관리자).
 *
 * 삭제 버튼이 없다. 부서에는 시험 데이터가 매달리게 되므로, 무엇이 그 부서를
 * 참조하는지 답할 수 있게 된 뒤에야 삭제를 논한다(의존성 레지스트리, 1-2).
 * 대신 **보관**으로 새 활동만 막는다 — 보관된 부서는 가입 신청 목록에서도 빠진다.
 */

import { useState } from 'react'
import { Archive, ArchiveRestore, Building2, Loader2, Plus, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { workspacesApi } from '@/modules/workspaces/api'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

export default function WorkspacesAdminPage() {
  const workspaces = useResource(() => workspacesApi.list(true), [])
  const [creating, setCreating] = useState(false)
  const [busySlug, setBusySlug] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)

  async function toggleArchive(slug: string, isActive: boolean) {
    setBusySlug(slug)
    setError(null)
    try {
      await workspacesApi.update(slug, { is_active: !isActive })
      workspaces.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('변경에 실패했습니다.'))
    } finally {
      setBusySlug(null)
    }
  }

  const rows = workspaces.data ?? []

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="부서 관리"
        description="부서를 만들고 이름을 관리합니다. 부서는 삭제하지 않고 보관합니다."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            부서 만들기
          </Button>
        }
      />

      <ErrorNotice error={error ?? workspaces.error} className="mb-4" />

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>부서</TableHead>
              <TableHead>주소</TableHead>
              <TableHead>인원</TableHead>
              <TableHead>상태</TableHead>
              <TableHead className="text-right">작업</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {workspaces.loading && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                  <Loader2 className="mx-auto size-4 animate-spin" />
                </TableCell>
              </TableRow>
            )}

            {!workspaces.loading && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-8 text-center text-sm">
                  부서가 없습니다.
                </TableCell>
              </TableRow>
            )}

            {rows.map((workspace) => (
              <TableRow key={workspace.id}>
                <TableCell className="font-medium">
                  <span className="flex items-center gap-2">
                    <Building2 className="text-muted-foreground size-4" />
                    {workspace.name}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground font-mono text-xs">
                  {workspace.slug}
                </TableCell>
                <TableCell>{workspace.member_count}</TableCell>
                <TableCell>
                  {workspace.is_active ? (
                    <Badge variant="outline">활성</Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      보관
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button size="sm" variant="outline" asChild>
                      <Link to={`/w/${workspace.slug}/members`}>
                        <Users className="size-4" />
                        멤버
                      </Link>
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busySlug === workspace.slug}
                      onClick={() => toggleArchive(workspace.slug, workspace.is_active)}
                    >
                      {workspace.is_active ? (
                        <>
                          <Archive className="size-4" />
                          보관
                        </>
                      ) : (
                        <>
                          <ArchiveRestore className="size-4" />
                          되살리기
                        </>
                      )}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <CreateDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false)
          workspaces.reload()
        }}
      />
    </div>
  )
}

function CreateDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: () => void
}) {
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await workspacesApi.create(slug, name)
      setSlug('')
      setName('')
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
