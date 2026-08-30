/**
 * 계정 관리 — 승인 대기 큐가 중심이다.
 *
 * 관리자가 매일 열어 볼 화면이므로 **대기 중인 신청이 먼저 보여야** 한다. 전체
 * 목록을 기본으로 두면 승인이 밀린 것을 놓친다.
 *
 * SMTP 가 없어 임시 비밀번호를 메일로 보낼 수 없다. 발급하면 화면에 한 번 띄우고
 * 관리자가 직접 전달한다(SecretOnceDialog).
 */

import { useState } from 'react'
import {
  KeyRound,
  Loader2,
  ShieldCheck,
  ShieldMinus,
  ShieldOff,
  ShieldPlus,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
} from 'lucide-react'

import { DeleteAccountDialog } from '@/modules/accounts/DeleteAccountDialog'
import { HomeWorkspaceDialog } from '@/modules/accounts/HomeWorkspaceDialog'
import { accountsApi } from '@/modules/accounts/api'
import type { Account, AccountStatus } from '@/modules/accounts/api'
import { workspacesApi } from '@/modules/workspaces/api'
import { useAuth } from '@/shared/auth/AuthContext'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { SecretOnceDialog } from '@/shared/components/SecretOnceDialog'
import { StatusBadge } from '@/shared/components/StatusBadge'
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
import { Tabs, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'

type Tab = 'pending' | 'all'

interface Secret {
  value: string
  subject: string
  title: string
  description: string
}

export default function AccountsAdminPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const [error, setError] = useState<Error | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [secret, setSecret] = useState<Secret | null>(null)
  const [rejecting, setRejecting] = useState<Account | null>(null)
  const [deleting, setDeleting] = useState<Account | null>(null)
  const [creating, setCreating] = useState(false)
  const [homing, setHoming] = useState<Account | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const { user: me } = useAuth()

  const accounts = useResource(
    () => accountsApi.list(tab === 'pending' ? ('pending' as AccountStatus) : undefined),
    [tab],
  )
  const workspaces = useResource(() => workspacesApi.options(), [])

  /** 시스템 관리자 권한 — **주는 것은 되돌리기 어려운 일이라 한 번 묻는다.**
   *
   *  자기 것은 서버가 막는다(마지막 관리자가 스스로 빼면 되돌릴 길이 없다).
   *  화면에서도 자기 줄에는 단추를 안 보인다 — 눌러 보고 409 를 알게 하지 않는다. */
  async function toggleAdmin(account: Account) {
    const grant = !account.is_system_admin
    const asked = window.confirm(
      grant
        ? `'${account.display_name}' 에게 시스템 관리자 권한을 줍니다.
` +
            '계정·부서·기준정보 전체를 만들고 지울 수 있게 됩니다.'
        : `'${account.display_name}' 의 시스템 관리자 권한을 뺍니다.`
    )
    if (!asked) return
    await run(account.id, () => accountsApi.setSystemAdmin(account.id, grant))
  }

  async function run(id: string, action: () => Promise<unknown>) {
    setBusyId(id)
    setError(null)
    try {
      await action()
      accounts.reload()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('처리에 실패했습니다.'))
    } finally {
      setBusyId(null)
    }
  }

  const rows = accounts.data ?? []
  const options = workspaces.data ?? []
  /** slug 를 사람이 읽는 이름으로. 못 찾으면 slug 그대로 — 감추지 않는다. */
  const nameOf = (slug: string) =>
    options.find((item) => item.slug === slug)?.name ?? slug

  return (
    <div>
      <PageHeader
        title="계정 관리"
        description="가입 신청을 승인하고 계정 상태를 관리합니다."
        actions={
          <Button onClick={() => setCreating(true)}>
            <UserPlus className="size-4" />
            계정 직접 생성
          </Button>
        }
      />

      <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)} className="mb-4">
        <TabsList>
          <TabsTrigger value="pending">승인 대기</TabsTrigger>
          <TabsTrigger value="all">전체</TabsTrigger>
        </TabsList>
      </Tabs>

      {notice && (
        <div className="mb-4 flex items-start justify-between gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm text-emerald-700 dark:text-emerald-400">
          <span>{notice}</span>
          <button type="button" className="opacity-60" onClick={() => setNotice(null)}>
            닫기
          </button>
        </div>
      )}

      <ErrorNotice error={error ?? accounts.error} className="mb-4" />

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>아이디</TableHead>
              <TableHead>이름</TableHead>
              <TableHead>상태</TableHead>
              <TableHead>부서</TableHead>
              <TableHead className="text-right">작업</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {accounts.loading && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                  <Loader2 className="mx-auto size-4 animate-spin" />
                </TableCell>
              </TableRow>
            )}

            {!accounts.loading && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-8 text-center text-sm">
                  {tab === 'pending' ? '승인을 기다리는 신청이 없습니다.' : '계정이 없습니다.'}
                </TableCell>
              </TableRow>
            )}

            {rows.map((account) => (
              <TableRow key={account.id}>
                <TableCell className="font-medium">
                  {account.email}
                  {account.is_system_admin && (
                    <span className="text-muted-foreground ml-2 text-xs">시스템 관리자</span>
                  )}
                </TableCell>
                <TableCell>{account.display_name}</TableCell>
                <TableCell>
                  <StatusBadge status={account.status} />
                  {account.decision_note && (
                    <p className="text-muted-foreground mt-1 text-xs">{account.decision_note}</p>
                  )}
                </TableCell>
                <TableCell className="text-sm">
                  <WorkspaceCell
                    account={account}
                    nameOf={nameOf}
                    onEdit={() => setHoming(account)}
                  />
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    {account.status === 'pending' && (
                      <>
                        <Button
                          size="sm"
                          disabled={busyId === account.id}
                          onClick={() =>
                            run(account.id, () =>
                              accountsApi.approve(account.id, null, 'member'),
                            )
                          }
                        >
                          <UserCheck className="size-4" />
                          승인
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === account.id}
                          onClick={() => setRejecting(account)}
                        >
                          <UserX className="size-4" />
                          거절
                        </Button>
                      </>
                    )}

                    {account.status === 'active' && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === account.id}
                          onClick={() =>
                            run(account.id, async () => {
                              const result = await accountsApi.resetPassword(account.id)
                              setSecret({
                                value: result.temporary_password,
                                subject: `${account.display_name} (${account.email})`,
                                title: '임시 비밀번호가 발급되었습니다',
                                description: '본인에게 직접 전달하세요.',
                              })
                            })
                          }
                        >
                          <KeyRound className="size-4" />
                          비밀번호 재설정
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === account.id}
                          onClick={() => run(account.id, () => accountsApi.suspend(account.id))}
                        >
                          <ShieldOff className="size-4" />
                          정지
                        </Button>
                      </>
                    )}

                    {account.status === 'suspended' && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busyId === account.id}
                        onClick={() => run(account.id, () => accountsApi.activate(account.id))}
                      >
                        <ShieldCheck className="size-4" />
                        활성화
                      </Button>
                    )}

                    {account.id !== me?.id &&
                      (account.is_system_admin || account.status === 'active') && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busyId === account.id}
                          onClick={() => void toggleAdmin(account)}
                        >
                          {account.is_system_admin ? (
                            <ShieldMinus className="size-4" />
                          ) : (
                            <ShieldPlus className="size-4" />
                          )}
                          {account.is_system_admin ? '관리자 해제' : '관리자 지정'}
                        </Button>
                      )}

                    {account.status !== 'pending' && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busyId === account.id}
                        onClick={() => setDeleting(account)}
                        aria-label="계정 삭제"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <RejectDialog
        account={rejecting}
        onClose={() => setRejecting(null)}
        onDone={() => {
          setRejecting(null)
          accounts.reload()
        }}
      />

      <DeleteAccountDialog
        account={deleting}
        candidates={rows.filter((row) => row.status === 'active' && row.id !== deleting?.id)}
        onClose={() => setDeleting(null)}
        onDeleted={(summary) => {
          setDeleting(null)
          setNotice(summary)
          accounts.reload()
        }}
      />

      {homing && (
        <HomeWorkspaceDialog
          account={homing}
          workspaces={options}
          onClose={() => setHoming(null)}
          onSaved={(message) => {
            setHoming(null)
            setNotice(message)
            accounts.reload()
          }}
        />
      )}

      <CreateAccountDialog
        open={creating}
        workspaces={(workspaces.data ?? []).map((w) => ({ slug: w.slug, name: w.name }))}
        onClose={() => setCreating(false)}
        onCreated={(result) => {
          setCreating(false)
          setSecret(result)
          accounts.reload()
        }}
      />

      {secret && (
        <SecretOnceDialog
          open
          onClose={() => setSecret(null)}
          title={secret.title}
          description={secret.description}
          secret={secret.value}
          subject={secret.subject}
        />
      )}
    </div>
  )
}

/**
 * 부서 칸 — **대표 소속 하나만 쓰고 나머지는 센다.**
 *
 * 전에는 멤버십을 전부 `, ` 로 이어 붙였다. 시스템 관리자는 모든 부서에 들어
 * 있어서 그 한 칸이 표를 화면 밖으로 밀었고, 「비밀번호 재설정」 을 누르려면
 * 가로로 굴려야 했다 — 실사용에서 그렇게 걸렸다.
 *
 * 이름을 자르지 않고 **개수로 접는다.** `금속재료팀, 고분자팀, 품질보증팀…`
 * 처럼 자르면 잘린 자리에 무엇이 더 있는지 셀 수가 없다. 전부는 `title` 로
 * 남긴다 — 세어 보는 일은 드물고, 그때는 마우스를 올리면 된다.
 */
function WorkspaceCell({
  account,
  nameOf,
  onEdit,
}: {
  account: Account
  nameOf: (slug: string) => string
  onEdit: () => void
}) {
  // 승인 전에는 멤버십이 없다. 보여 줄 것은 **신청한 부서**뿐이고, 대표 소속은
  // 승인이 정한다 — 여기서 고르게 하면 승인 화면이 둘이 된다.
  if (account.status === 'pending') {
    return (
      <span className="text-muted-foreground">
        {account.requested_workspace_slug ? nameOf(account.requested_workspace_slug) : '—'}
      </span>
    )
  }

  if (account.memberships.length === 0) {
    return <span className="text-muted-foreground">—</span>
  }

  const others = account.memberships.filter((slug) => slug !== account.home_workspace_slug)

  return (
    <Button
      variant="ghost"
      size="sm"
      className="h-auto max-w-[13rem] justify-start gap-1.5 px-1.5 py-1 font-normal"
      title={account.memberships.map(nameOf).join('\n')}
      onClick={onEdit}
    >
      <span className="truncate">
        {account.home_workspace_slug ? (
          nameOf(account.home_workspace_slug)
        ) : (
          <span className="text-muted-foreground">대표 소속 없음</span>
        )}
      </span>
      {others.length > 0 && (
        <span className="text-muted-foreground shrink-0 text-xs">외 {others.length}</span>
      )}
    </Button>
  )
}

function RejectDialog({
  account,
  onClose,
  onDone,
}: {
  account: Account | null
  onClose: () => void
  onDone: () => void
}) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    if (!account) return
    setBusy(true)
    setError(null)
    try {
      await accountsApi.reject(account.id, note)
      setNote('')
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('거절에 실패했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={account !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>가입 신청 거절</DialogTitle>
          <DialogDescription>
            {account?.display_name} ({account?.email}) 의 신청을 거절합니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="reject-note">사유</Label>
          <Input
            id="reject-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="예) 부서 확인이 필요합니다"
          />
          {/* 메일이 없으므로 사유가 유일한 기록이자 통보 수단이다. */}
          <p className="text-muted-foreground text-xs">
            메일 발송이 없으므로 사유는 화면에만 남습니다. 신청자에게 직접 알려 주세요.
          </p>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button variant="destructive" disabled={busy || note.trim().length === 0} onClick={submit}>
            거절
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CreateAccountDialog({
  open,
  workspaces,
  onClose,
  onCreated,
}: {
  open: boolean
  workspaces: { slug: string; name: string }[]
  onClose: () => void
  onCreated: (secret: Secret) => void
}) {
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [slug, setSlug] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const result = await accountsApi.create({
        email,
        display_name: displayName,
        workspace_slug: slug,
        role: 'member',
        is_system_admin: false,
      })
      setEmail('')
      setDisplayName('')
      setSlug('')
      onCreated({
        value: result.temporary_password,
        subject: `${result.account.display_name} (${result.account.email})`,
        title: '계정을 만들었습니다',
        description: '임시 비밀번호를 본인에게 전달하세요.',
      })
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
          <DialogTitle>계정 직접 생성</DialogTitle>
          <DialogDescription>
            승인 절차 없이 바로 활성 계정을 만듭니다. 임시 비밀번호가 한 번 표시됩니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="new-email">아이디</Label>
            <Input id="new-email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-name">이름</Label>
            <Input
              id="new-name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-workspace">부서</Label>
            <Select value={slug} onValueChange={setSlug}>
              <SelectTrigger id="new-workspace" className="w-full">
                <SelectValue placeholder="부서를 선택하세요" />
              </SelectTrigger>
              <SelectContent>
                {workspaces.map((item) => (
                  <SelectItem key={item.slug} value={item.slug}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !email || !displayName || !slug} onClick={submit}>
            만들기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
