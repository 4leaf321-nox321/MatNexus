/**
 * 장비 커넥터 — **장비 PC 가 보낸 파일이 어디까지 왔는지.**
 *
 * ## 세 탭
 *
 *     커넥터   어느 PC 가 살아 있나. 마지막 보고가 오래되면 색으로 말한다.
 *     수집함   시편을 못 정한 파일 — **사람이 붙인다.** 이 화면의 본업이다.
 *     실패     읽지 못한 파일. 프로파일을 고친 뒤 「다시 읽기」.
 *
 * ## 판단은 화면이 하지 않는다
 *
 * 후보도, 왜 후보가 없는지도 서버가 실어 준다. 화면이 스스로 고르면 엉뚱한 시편에
 * 곡선이 붙고, 그것은 조용히 틀리는 자리다 — 통계가 그 시편의 것으로 센다.
 *
 * ## 못 하는 이유를 적는다
 *
 * 후보가 없을 때 단추를 그냥 끄지 않는다. **왜 없는지와 무엇을 먼저 해야 하는지**를
 * 그 자리에 적는다(재료가 없다 → 재료를 만들어라).
 */

import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Trash2 } from 'lucide-react'

import { INBOX_STATUSES, STATUS_LABELS, pipelinesApi } from '@/modules/pipelines/api'
import type { Connector, InboxItem, InboxItemDetail, SpecimenChoice } from '@/modules/pipelines/api'
import { AccessTokens } from '@/shared/components/AccessTokens'
import { CopyId } from '@/shared/components/CopyId'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { useAuth } from '@/shared/auth/AuthContext'
import { isAnyManager } from '@/shared/auth/roles'
import { PageHeader } from '@/shared/components/PageHeader'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
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
import { stamp } from '@/shared/lib/datetime'

type Tab = 'all' | 'connectors' | 'inbox' | 'failed' | 'setup'
const TABS: readonly Tab[] = ['all', 'connectors', 'inbox', 'failed', 'setup']

/** 마지막 보고가 얼마나 오래됐나. **하루 넘으면 빨강, 두 시간 넘으면 주황.** */
export function seenTone(lastSeen: string | null | undefined, now = Date.now()): string {
  if (!lastSeen) return 'text-muted-foreground'
  const hours = (now - new Date(lastSeen).getTime()) / 3_600_000
  if (hours > 24) return 'text-destructive'
  if (hours > 2) return 'text-amber-600'
  return ''
}

function statusBadge(status: string) {
  const label = STATUS_LABELS[status as keyof typeof STATUS_LABELS] ?? status
  const tone =
    status === 'suggested'
      ? 'border-sky-500 text-sky-700'
      : status === 'needs_specimen'
      ? 'border-amber-500 text-amber-700'
      : status === 'failed'
        ? 'border-destructive text-destructive'
        : status === 'registered'
          ? 'border-emerald-600 text-emerald-700'
          : ''
  return (
    <Badge variant="outline" className={tone}>
      {label}
    </Badge>
  )
}

export default function ConnectorsPage() {
  const canEdit = isAnyManager(useAuth().user)
  const [params, setParams] = useSearchParams()
  const wanted = params.get('tab')
  const tab: Tab = TABS.includes(wanted as Tab) ? (wanted as Tab) : 'all'
  const [open, setOpen] = useState<string | null>(null)

  return (
    <div>
      <PageHeader
        title="장비 커넥터"
        description="장비 PC 가 보낸 파일이 어디까지 왔는지. 시편을 못 정한 파일은 여기서 붙인다."
      />
      <Tabs value={tab} onValueChange={(value) => setParams({ tab: value })} className="mb-4">
        <TabsList>
          <TabsTrigger value="all">전체</TabsTrigger>
          <TabsTrigger value="connectors">커넥터</TabsTrigger>
          <TabsTrigger value="inbox">수집함</TabsTrigger>
          <TabsTrigger value="failed">실패</TabsTrigger>
          {/* **연결 정보는 자격 증명이다.** 서버 주소·토큰·부서 id 를 모아 둔
              자리라, 다른 탭과 달리 보는 것부터 부서 관리자만이다 — 나머지는
              「내 파일이 들어왔나」 를 누구나 물을 수 있어야 해서 열었다. */}
          {canEdit && <TabsTrigger value="setup">연결 정보</TabsTrigger>}
        </TabsList>
      </Tabs>

      {tab === 'all' && <InboxTab status="" onOpen={setOpen} />}
      {tab === 'connectors' && <ConnectorsTab />}
      {tab === 'inbox' && <InboxTab status="suggested" onOpen={setOpen} />}
      {tab === 'failed' && <InboxTab status="failed" onOpen={setOpen} />}
      {tab === 'setup' && canEdit && <SetupTab />}

      {open && <ItemDialog id={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

// --- 연결 정보 -----------------------------------------------------------------

/**
 * MatPylon 마법사가 요구하는 셋을 **한 자리에** 모은다 — 서버 주소 · 토큰 · 부서 id.
 * 각각 제자리(내 프로필·부서 관리)에도 있지만, 장비를 붙이는 사람은 셋을 같이
 * 본다. 흩어져 있으면 세 화면을 오가며 하나씩 옮겨 적는다.
 */
function SetupTab() {
  const { data, error, loading } = useResource(() => pipelinesApi.workspaces(), [])
  const server = window.location.origin
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="space-y-2">
        <h2 className="font-semibold">1. 서버 주소</h2>
        <p className="text-muted-foreground text-sm">
          마법사의 「서버」 칸. 장비 PC 에서 이 주소로 닿아야 합니다.
        </p>
        <CopyId value={server} label="서버 주소" />
      </section>
      <section className="space-y-2">
        <h2 className="font-semibold">2. 부서 ID</h2>
        <p className="text-muted-foreground text-sm">
          커넥터가 속할 부서. 이 부서의 시험이 됩니다 — 토큰 주인이 그 부서 구성원이어야
          합니다.
        </p>
        <ErrorNotice error={error} />
        {loading && !data && <p className="text-muted-foreground text-sm">불러오는 중…</p>}
        {data && (
          <ul className="divide-y rounded-md border text-sm">
            {data.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
              >
                <span>
                  <span className="font-medium">{row.name}</span>
                  <span className="text-muted-foreground ml-1 font-mono text-xs">{row.slug}</span>
                </span>
                <CopyId value={row.id} label="부서 ID" />
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="space-y-2 lg:col-span-2">
        <h2 className="font-semibold">3. 액세스 토큰</h2>
        <AccessTokens />
      </section>
    </div>
  )
}

// --- 커넥터 -----------------------------------------------------------------

function ConnectorsTab() {
  const canEdit = isAnyManager(useAuth().user)
  const [removing, setRemoving] = useState<Connector | null>(null)
  const { data, error, loading, reload } = useResource(() => pipelinesApi.connectors(), [])
  const [busy, setBusy] = useState<string | null>(null)
  const [failed, setFailed] = useState<Error | null>(null)

  async function remove(row: Connector) {
    setBusy(row.id)
    setFailed(null)
    try {
      await pipelinesApi.removeConnector(row.id)
      setRemoving(null)
      reload()
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('커넥터를 치우지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  async function toggleAuto(row: Connector) {
    if (
      !row.auto_register &&
      !window.confirm(
        `'${row.name}' 가 후보 하나면 승인 없이 바로 시험을 만듭니다.\n` +
          '대조 열이 한동안 전부 맞은, 규칙이 검증된 커넥터만 켜세요.'
      )
    ) {
      return
    }
    setBusy(row.id)
    setFailed(null)
    try {
      await pipelinesApi.updateConnector(row.id, { auto_register: !row.auto_register })
      reload()
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(null)
    }
  }

  async function toggle(row: Connector) {
    setBusy(row.id)
    setFailed(null)
    try {
      await pipelinesApi.updateConnector(row.id, { is_active: !row.is_active })
      reload()
    } catch (caught) {
      setFailed(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(null)
    }
  }

  if (loading && !data) return <p className="text-muted-foreground text-sm">불러오는 중…</p>
  return (
    <div>
      <ErrorNotice error={error ?? failed} className="mb-3" />
      {data && data.length === 0 && (
        <p className="text-muted-foreground text-sm">
          등록된 커넥터가 없습니다. 장비 PC 에 MatPylon 을 설치하고 이 서버 주소와 개인 액세스
          토큰을 넣으면 여기 나타납니다.
        </p>
      )}
      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>이름</TableHead>
                <TableHead>호스트</TableHead>
                <TableHead>부서</TableHead>
                <TableHead>마지막 보고</TableHead>
                <TableHead className="text-right">대기</TableHead>
                <TableHead className="text-right">실패</TableHead>
                <TableHead className="text-right">사람 대기</TableHead>
                <TableHead>자동 등록</TableHead>
                <TableHead>버전</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((row) => (
                <TableRow key={row.id} className={row.is_active ? '' : 'opacity-60'}>
                  <TableCell className="font-medium">{row.name}</TableCell>
                  <TableCell className="font-mono text-xs">{row.hostname}</TableCell>
                  <TableCell>{row.workspace_name ?? '—'}</TableCell>
                  <TableCell className={seenTone(row.last_seen_at)}>
                    {row.last_seen_at ? stamp(row.last_seen_at) : '아직 없음'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{row.pending}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.failed}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.waiting ?? 0}</TableCell>
                  <TableCell>
                    {/* 기본은 승인 대기다. 규칙이 「틀리게 맞으면」 엉뚱한 시편에
                        시험이 붙는다 — 대조 열이 한동안 전부 맞은 커넥터만 켠다. */}
                    {/* **끄고 켜는 것은 부서 관리자다.** 상태를 보는 것은
                        누구나 해야 한다 — 「내 장비가 살아 있나」 는 실험하는
                        사람이 먼저 묻는다. 바꾸는 것은 다른 일이다. */}
                    {canEdit ? (
                      <Button
                        size="sm"
                        variant={row.auto_register ? 'secondary' : 'outline'}
                        disabled={busy === row.id}
                        onClick={() => toggleAuto(row)}
                      >
                        {row.auto_register ? '켜짐' : '승인 대기'}
                      </Button>
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        {row.auto_register ? '켜짐' : '승인 대기'}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {row.app_version ?? '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    {canEdit ? (
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy === row.id}
                          onClick={() => toggle(row)}
                        >
                          {row.is_active ? '끄기' : '켜기'}
                        </Button>
                        {/* **끄기와 다르다.** 끄는 것은 「잠시 안 받는다」 이고
                            이것은 「더 안 쓴다」 다 — 바꾼 장비·반납한 PC 가
                            쌓이면 살아 있는 커넥터를 그 사이에서 골라야 한다. */}
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy === row.id}
                          title="목록에서 치웁니다. 수집함은 그대로 남고, 휴지통에서 되살릴 수 있습니다."
                          onClick={() => setRemoving(row)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        {row.is_active ? '켜짐' : '꺼짐'}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* **무엇이 남는지 함께 말한다.** 「지웁니다」 만으로는 수집함까지 사라지는
          줄 알고 못 누른다 — 실제로는 커넥터 행 하나만 감춘다. */}
      <ConfirmDialog
        open={removing !== null}
        title="이 커넥터를 목록에서 치울까요?"
        confirmLabel="치우기"
        busy={busy === removing?.id}
        body={
          <>
            <b>{removing?.name}</b> ({removing?.hostname}) 가 목록에서 사라집니다.
            <br />
            <b>이미 들어온 파일과 그것으로 만든 시험은 그대로 남습니다.</b> 같은 PC 를
            다시 붙이면 새 커넥터가 서고, 이 커넥터는 휴지통에서 되살릴 수 있습니다.
          </>
        }
        onConfirm={() => removing && void remove(removing)}
        onClose={() => setRemoving(null)}
      />
    </div>
  )
}

// --- 수집함 -----------------------------------------------------------------

function InboxTab({ status, onOpen }: { status: string; onOpen: (id: string) => void }) {
  const canEdit = isAnyManager(useAuth().user)
  const [filter, setFilter] = useState(status)
  useEffect(() => setFilter(status), [status])
  const { data, error, loading, reload } = useResource(
    // 빈 필터 = 전체. 서버에 status 를 안 보낸다.
    () => pipelinesApi.inbox({ ...(filter ? { status: filter } : {}), limit: 100 }),
    [filter]
  )
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [said, setSaid] = useState<string | null>(null)
  useEffect(() => setPicked(new Set()), [filter, data])

  function togglePick(id: string) {
    setPicked((now) => {
      const next = new Set(now)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function approvePicked() {
    setBusy(true)
    setSaid(null)
    try {
      const result = await pipelinesApi.approveMany([...picked])
      const blocked = Object.entries(result.failed)
      setSaid(
        `${result.approved.length}건 등록` +
          (blocked.length ? ` · 막힘 ${blocked.length}건 — ${blocked[0][1]}` : '')
      )
      reload()
    } catch (caught) {
      setSaid(caught instanceof Error ? caught.message : '알 수 없는 오류')
    } finally {
      setBusy(false)
    }
  }

  // **고르는 칸과 묶음 승인이 이 깃발 하나에 달려 있다.** 여기서 막으면 체크칸도
  // 함께 사라진다 — 고를 수는 있는데 승인 단추가 없으면 무엇을 하라는 건지 모른다.
  //
  // 목록 자체는 모두에게 보인다. 「내 파일이 들어왔나」 는 실험한 사람이 먼저
  // 묻는 것이고, 붙이는 일만 부서 관리자다.
  const pickable = canEdit && filter === 'suggested'

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1">
        <Button
          size="sm"
          variant={filter === '' ? 'default' : 'outline'}
          onClick={() => setFilter('')}
        >
          전체
        </Button>
        {INBOX_STATUSES.map((one) => (
          <Button
            key={one}
            size="sm"
            variant={filter === one ? 'default' : 'outline'}
            onClick={() => setFilter(one)}
          >
            {STATUS_LABELS[one]}
          </Button>
        ))}
      </div>
      <ErrorNotice error={error} className="mb-3" />
      {said && <p className="text-muted-foreground mb-2 text-sm">{said}</p>}
      {pickable && data && data.items.length > 0 && (
        <div className="mb-2 flex items-center gap-2">
          <Button size="sm" disabled={busy || picked.size === 0} onClick={approvePicked}>
            고른 {picked.size}건 승인
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              setPicked((now) =>
                now.size === data.items.length ? new Set() : new Set(data.items.map((r) => r.id))
              )
            }
          >
            전체 고르기/해제
          </Button>
        </div>
      )}
      {loading && !data && <p className="text-muted-foreground text-sm">불러오는 중…</p>}
      {data && data.items.length === 0 && (
        <p className="text-muted-foreground text-sm">
          {filter
            ? `「${STATUS_LABELS[filter as keyof typeof STATUS_LABELS] ?? filter}」 인 항목이 없습니다.`
            : '아직 받은 파일이 없습니다.'}
        </p>
      )}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                {pickable && <TableHead className="w-8" />}
                <TableHead>받은 시각</TableHead>
                <TableHead>파일</TableHead>
                <TableHead>커넥터</TableHead>
                <TableHead>종류</TableHead>
                <TableHead>힌트</TableHead>
                <TableHead>상태</TableHead>
                <TableHead>왜</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((row) => (
                <InboxRow
                  key={row.id}
                  row={row}
                  onOpen={onOpen}
                  picked={pickable ? picked.has(row.id) : undefined}
                  onPick={pickable ? () => togglePick(row.id) : undefined}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {data && data.total > data.items.length && (
        <p className="text-muted-foreground mt-2 text-xs">
          {data.total}건 중 {data.items.length}건만 보입니다.
        </p>
      )}
    </div>
  )
}

function hintText(hints: Record<string, string | undefined>): string {
  return Object.entries(hints)
    .filter(([, value]) => value)
    .map(([key, value]) => `${key}=${value}`)
    .join(' · ')
}

function InboxRow({
  row,
  onOpen,
  picked,
  onPick,
}: {
  row: InboxItem
  onOpen: (id: string) => void
  picked?: boolean
  onPick?: () => void
}) {
  return (
    <TableRow className="cursor-pointer" onClick={() => onOpen(row.id)}>
      {onPick !== undefined && (
        <TableCell onClick={(event) => event.stopPropagation()}>
          <input
            type="checkbox"
            checked={picked ?? false}
            onChange={onPick}
            aria-label={`${row.filename} 고르기`}
          />
        </TableCell>
      )}
      <TableCell className="whitespace-nowrap">{stamp(row.received_at)}</TableCell>
      <TableCell className="font-medium">
        {row.test_run_name ?? row.filename}
        {row.test_run_name && (
          <span className="text-muted-foreground ml-1 text-xs">({row.filename})</span>
        )}
      </TableCell>
      <TableCell>{row.connector_name ?? '—'}</TableCell>
      <TableCell>{row.test_type_label ?? row.test_type_key ?? '—'}</TableCell>
      <TableCell className="text-muted-foreground max-w-xs truncate text-xs">
        {hintText(row.hints as Record<string, string | undefined>)}
      </TableCell>
      <TableCell>{statusBadge(row.status)}</TableCell>
      <TableCell className="max-w-md text-sm">
        {row.status === 'suggested'
          ? '후보 1 — 승인만 남았습니다'
          : row.status === 'needs_specimen' && row.candidate_count > 1
            ? `후보 ${row.candidate_count}개 — 골라 주세요`
            : (row.error ?? '')}
      </TableCell>
    </TableRow>
  )
}

// --- 항목 하나 ----------------------------------------------------------------

function ItemDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const { user } = useAuth()
  const [item, setItem] = useState<InboxItemDetail | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [query, setQuery] = useState('')
  const [found, setFound] = useState<SpecimenChoice[]>([])

  useEffect(() => {
    let cancelled = false
    pipelinesApi
      .item(id)
      .then((value) => {
        if (!cancelled) setItem(value)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
      })
    return () => {
      cancelled = true
    }
  }, [id])

  // 시편 검색. **재료를 거치지 않고** 찾는다 — 붙일 시편이 어느 재료인지는 파일이
  // 말해 주지 않을 때도 있다.
  useEffect(() => {
    if (query.trim().length < 2) {
      setFound([])
      return
    }
    let cancelled = false
    pipelinesApi
      .findSpecimens(query.trim())
      .then((rows) => {
        if (!cancelled) setFound(rows)
      })
      .catch(() => {
        if (!cancelled) setFound([])
      })
    return () => {
      cancelled = true
    }
  }, [query])

  async function act(run: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await run()
      onClose()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  const done = item ? item.status === 'registered' || item.status === 'discarded' : true
  // **상세는 누구나 본다. 손대는 것만 부서 관리자다.** 파일이 왜 안 붙었는지는
  // 그 시험을 한 사람이 먼저 묻고, 그 답이 여기 있다 — 후보·오류·요약이 그것이다.
  const canAct = !done && isAnyManager(user)
  const summary = (item?.summary ?? {}) as {
    channels?: string[]
    row_count?: number
    curve_count?: number
    identity?: Record<string, string>
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{item?.filename ?? '…'}</DialogTitle>
          <DialogDescription>
            {item ? (
              <>
                {item.connector_name ?? '커넥터'} · {stamp(item.received_at)} ·{' '}
                <span className="font-mono text-xs">{item.client_path}</span>
              </>
            ) : (
              '불러오는 중…'
            )}
          </DialogDescription>
        </DialogHeader>
        <ErrorNotice error={error} />

        {item && (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              {statusBadge(item.status)}
              <span>{item.test_type_label ?? item.test_type_key ?? '종류 미정'}</span>
              {item.profile_key && (
                <span className="text-muted-foreground text-xs">형식 {item.profile_key}</span>
              )}
              {summary.row_count !== undefined && (
                <span className="text-muted-foreground text-xs">
                  {summary.row_count}행 · 채널 {(summary.channels ?? []).join(', ') || '—'}
                </span>
              )}
            </div>

            {item.error && (
              <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900">
                {item.error}
              </p>
            )}

            {item.test_run_name && (
              <p>
                시험 <span className="font-medium">{item.test_run_name}</span> 이 됐습니다.
              </p>
            )}

            {canAct && item.status === 'suggested' && item.candidates.length === 1 && (
              <section className="rounded-md border border-sky-300 bg-sky-50 p-3">
                <div className="mb-2 text-sm text-sky-900">
                  <span className="font-medium">{item.candidates[0].specimen_name}</span> 에 붙일
                  준비가 됐습니다 — {item.candidates[0].reason}
                </div>
                <Button disabled={busy} onClick={() => act(() => pipelinesApi.approve(item.id))}>
                  승인 — 시험으로 등록
                </Button>
              </section>
            )}

            {canAct && item.status !== 'suggested' && item.candidates.length > 0 && (
              <section>
                <h3 className="mb-1 font-medium">후보 — 서버가 좁힌 것</h3>
                <ul className="divide-y rounded-md border">
                  {item.candidates.map((one) => (
                    <li
                      key={one.specimen_id}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <div>
                        <div className="font-medium">{one.specimen_name}</div>
                        <div className="text-muted-foreground text-xs">
                          {one.material_name} · {one.sample_name} · {one.reason}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          act(() =>
                            pipelinesApi.assign(item.id, {
                              specimen_id: one.specimen_id,
                            })
                          )
                        }
                      >
                        이 시편에 붙이기
                      </Button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {canAct && item.status !== 'failed' && (
              <section>
                <h3 className="mb-1 font-medium">다른 시편 찾기</h3>
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="시편 이름·재료·로트로 찾기 (2글자 이상)"
                  aria-label="시편 찾기"
                />
                {found.length > 0 && (
                  <ul className="mt-2 divide-y rounded-md border">
                    {found.map((one) => (
                      <li key={one.id} className="flex items-center justify-between px-3 py-2">
                        <div>
                          <div className="font-medium">{one.record_name}</div>
                          <div className="text-muted-foreground text-xs">
                            {one.material_name} · {one.sample_name}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() =>
                            act(() =>
                              pipelinesApi.assign(item.id, {
                                specimen_id: one.id,
                              })
                            )
                          }
                        >
                          붙이기
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}

            {canAct && (
              <section className="flex flex-wrap items-end gap-2 border-t pt-3">
                {item.status === 'failed' && (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => act(() => pipelinesApi.retry(item.id))}
                  >
                    다시 읽기
                  </Button>
                )}
                <div className="flex flex-1 items-end gap-2">
                  <div className="flex-1">
                    <Input
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      placeholder="버리는 이유 (필수)"
                      aria-label="버리는 이유"
                    />
                  </div>
                  <Button
                    variant="destructive"
                    disabled={busy || reason.trim().length === 0}
                    onClick={() => act(() => pipelinesApi.discard(item.id, reason.trim()))}
                  >
                    버리기
                  </Button>
                </div>
              </section>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
