/**
 * 부서 멤버.
 *
 * 조회는 그 부서 멤버면 되고, 변경은 부서 관리자(또는 시스템 관리자)만 할 수 있다.
 * 화면은 권한을 스스로 판정하지 않고 서버가 준 `my_role` 로 버튼만 감춘다 —
 * 판정은 서버가 하고, 화면은 그 결과를 반영할 뿐이다.
 */

import { useState } from 'react'
import { Loader2, ShieldCheck, UserMinus, UserPlus } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { workspacesApi } from '@/modules/workspaces/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/shared/components/ui/table'
import { useResource } from '@/shared/hooks/useResource'

export default function MembersPage() {
  const { slug = '' } = useParams<{ slug: string }>()
  const { user } = useAuth()

  const members = useResource(() => workspacesApi.members(slug), [slug])
  const [adding, setAdding] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const membership = user?.memberships.find((m) => m.slug === slug)
  const canManage = Boolean(user?.is_system_admin) || membership?.role === 'manager'

  async function run(id: string, action: () => Promise<unknown>) {
    setBusyId(id)
    setError(null)
    try {
      await action()
      members.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('처리에 실패했습니다.'))
    } finally {
      setBusyId(null)
    }
  }

  const rows = members.data ?? []

  return (
    <div>
      <PageHeader
        title="부서 멤버"
        description={`${membership?.name ?? slug} 의 구성원과 역할입니다.`}
        actions={
          canManage && (
            <Button onClick={() => setAdding(true)}>
              <UserPlus className="size-4" />
              멤버 추가
            </Button>
          )
        }
      />

      <ErrorNotice error={error ?? members.error} className="mb-4" />

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>이름</TableHead>
              <TableHead>아이디</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>역할</TableHead>
              {canManage && <TableHead className="text-right">작업</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {members.loading && (
              <TableRow>
                <TableCell colSpan={canManage ? 5 : 4} className="text-muted-foreground py-8 text-center">
                  <Loader2 className="mx-auto size-4 animate-spin" />
                </TableCell>
              </TableRow>
            )}

            {!members.loading && rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={canManage ? 5 : 4}
                  className="text-muted-foreground py-8 text-center text-sm"
                >
                  멤버가 없습니다.
                </TableCell>
              </TableRow>
            )}

            {rows.map((member) => (
              <TableRow key={member.user_id}>
                <TableCell className="font-medium">{member.display_name}</TableCell>
                <TableCell className="text-muted-foreground">{member.email}</TableCell>
                <TableCell>
                  <StatusBadge status={member.status} />
                </TableCell>
                <TableCell>
                  {member.role === 'manager' ? (
                    <Badge variant="outline" className="gap-1">
                      <ShieldCheck className="size-3" />
                      부서 관리자
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      멤버
                    </Badge>
                  )}
                </TableCell>
                {canManage && (
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Select
                        value={member.role}
                        onValueChange={(role) =>
                          run(member.user_id, () =>
                            workspacesApi.setRole(slug, member.user_id, role),
                          )
                        }
                      >
                        <SelectTrigger size="sm" className="w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="member">멤버</SelectItem>
                          <SelectItem value="manager">부서 관리자</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busyId === member.user_id}
                        onClick={() =>
                          run(member.user_id, () =>
                            workspacesApi.removeMember(slug, member.user_id),
                          )
                        }
                      >
                        <UserMinus className="size-4" />
                      </Button>
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <AddMemberDialog
        open={adding}
        slug={slug}
        onClose={() => setAdding(false)}
        onAdded={() => {
          setAdding(false)
          members.reload()
        }}
      />
    </div>
  )
}

function AddMemberDialog({
  open,
  slug,
  onClose,
  onAdded,
}: {
  open: boolean
  slug: string
  onClose: () => void
  onAdded: () => void
}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('member')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await workspacesApi.addMember(slug, email, role)
      setEmail('')
      setRole('member')
      onAdded()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('추가에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>멤버 추가</DialogTitle>
          <DialogDescription>
            이미 승인된 계정만 추가할 수 있습니다. 승인 대기 중이면 계정 관리에서 먼저 승인하세요.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="member-email">아이디</Label>
            <Input
              id="member-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="이메일 또는 아이디"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="member-role">역할</Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger id="member-role" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="member">멤버</SelectItem>
                <SelectItem value="manager">부서 관리자</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !email} onClick={submit}>
            추가
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
