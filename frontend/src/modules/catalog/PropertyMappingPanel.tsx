/**
 * 물성 매핑 — **물성 하나가 세 층에서 어떻게 불리는가.**
 *
 *     문헌 키(정본)                 사람이 적는 항목        시험이 재는 값
 *     mechanical.yield_strength    항복강도              proof_stress ← 오프셋 항복강도
 *
 * 같은 물성이 세 이름으로 살고, 그것이 이어져 있는지는 코드를 열어야 알 수 있었다
 * (2026-09-12). 여기서 한 표로 본다. **빈 칸이 정보다** — 사내 항목인데 문헌 키에
 * 안 이어진 것은 값으로 찾기와 다른 시스템(TestScope)과의 매핑에서 **조용히 빠진다.**
 * 그 수를 위에 크게 센다.
 *
 * ## 누가 무엇을 편집하나
 *
 * 둘째 열(사내 항목)만 여기서 잇고 푼다. 셋째 열(잰 값)은 계산이 선언한 것이라
 * 코드에 있고(`Produced.property_key`), 다른 시스템의 열은 그 시스템이 자기 안에서
 * 잇는다 — 허브 키 하나를 두고 각자 스포크를 갖는다. 그래서 **사전 내려받기**가
 * 있다: 저쪽이 자기 매핑의 키가 실재하는지 이 파일로 검사한다.
 *
 * ## 눈금
 *
 * 「경도」 는 하나인데 문헌은 비커스·브리넬·로크웰이 다른 키다. 눈금 없이 이으면
 * HRC 60 이 비커스 검색에 섞인다 — 서버가 눈금 있는 항목은 눈금 없이 못 잇게 막고,
 * 여기서는 그 눈금을 고르게 한다.
 *
 * ## 문헌 물성 추가
 *
 * MaterialTwin 에 없는 물성은 여기서 만든다(2026-09-12). 키는 서버가 `local.` 으로
 * 시작하게 만들고, 그 뒤로는 이관해 온 것과 같은 물성이다 — 값을 달고, 사내 항목에
 * 잇고, 사전에 실린다. 값·매핑·별칭이 하나도 없을 때만 지운다.
 *
 * ## 키는 지우는 대신 폐기한다
 *
 * 값·매핑이 걸린 키, 사전이 이미 나간 키는 못 지운다 — 받아 간 시스템이 그 키로
 * 잇고 있다. 「폐기」 는 「그만 쓰고 저 키를 써라」 는 표시다: 새 값을 못 달고,
 * 채우기에서 빠지고, 이름 풀기에서 뒤로 밀리며 후속 키를 함께 알려 준다.
 *
 * 기준정보 화면(`VocabularyAdminPage`)이 자리만 내준다 — 표는 catalog 의 것이다.
 */

import { useMemo, useState } from 'react'
import {
  Archive,
  ArchiveRestore,
  ArrowRightToLine,
  Download,
  FilePlus2,
  Link2,
  Link2Off,
  Plus,
  Trash2,
} from 'lucide-react'

import { DOMAINS, DOMAIN_LABELS, catalogApi } from '@/modules/catalog/api'
import type {
  CatalogPropertyCreate,
  PropertyLinkCreate,
  PropertyMapping,
  PropertyMappingRow,
  PropertyUnlinkedItem,
} from '@/modules/catalog/api'
import { downloadFile } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
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

const KIND_LABELS: Record<string, string> = {
  same_as: '같은 것',
  narrower: '더 좁은 것',
  related: '관련',
}

export function PropertyMappingPanel({
  mapping,
  canEdit,
  onChanged,
}: {
  mapping: PropertyMapping
  /** 시스템 관리자만 잇고 푼다 — 매핑은 모든 부서의 값 검색에 걸린다. */
  canEdit: boolean
  onChanged: () => void
}) {
  const [domain, setDomain] = useState('')
  const [mode, setMode] = useState<Mode>('all')
  const [q, setQ] = useState('')
  const [linking, setLinking] = useState<{
    row?: PropertyMappingRow
    item?: PropertyUnlinkedItem
  } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [adding, setAdding] = useState(false)
  const [retiring, setRetiring] = useState<PropertyMappingRow | null>(null)

  const domains = useMemo(
    () => [...new Set(mapping.rows.map((one) => one.domain))].sort(),
    [mapping.rows]
  )
  const needle = q.trim().toLowerCase()
  const rows = useMemo(
    () =>
      mapping.rows.filter((one) => {
        if (domain && one.domain !== domain) return false
        if (!MODES[mode].keep(one)) return false
        if (!needle) return true
        return (
          one.name.toLowerCase().includes(needle) ||
          one.key.toLowerCase().includes(needle) ||
          one.links.some((link) => link.item.toLowerCase().includes(needle)) ||
          one.measured.some((m) => m.scalar_key.toLowerCase().includes(needle))
        )
      }),
    [mapping.rows, domain, mode, needle]
  )

  async function unlink(linkId: string) {
    setBusy(linkId)
    setError(null)
    try {
      await catalogApi.unlinkProperty(linkId)
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('풀지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  /**
   * 폐기된 키의 값·매핑·별칭을 후속 키로. **미리보기를 먼저 보이고 묻는다** —
   * 값은 출처·조건과 한 몸이라 옮기는 판단은 사람이 한다. 이관해 온 값은 안 옮겨진다.
   */
  async function migrateProperty(row: PropertyMappingRow) {
    setBusy(row.key)
    setError(null)
    try {
      const plan = await catalogApi.migrateProperty(row.key, { dry_run: true })
      const lines = [
        `'${row.name}' → ${plan.to_key}`,
        `직접 넣은 값 ${plan.values}건 · 사내 항목 매핑 ${plan.links}건 · 별칭 ${plan.aliases}건을 옮깁니다.`,
        plan.values_imported > 0
          ? `이관해 온 값 ${plan.values_imported}건은 못 옮깁니다 — 원본(MaterialTwin)이 정본입니다.`
          : null,
        plan.converted ? `단위를 환산합니다: ${plan.converted}` : null,
        '',
        '옮길까요?',
      ].filter((one): one is string => one !== null)
      if (!window.confirm(lines.join('\n'))) return
      await catalogApi.migrateProperty(row.key, { dry_run: false })
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('옮기지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  async function restoreProperty(row: PropertyMappingRow) {
    setBusy(row.key)
    setError(null)
    try {
      await catalogApi.undeprecateProperty(row.key)
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('되돌리지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  async function removeProperty(row: PropertyMappingRow) {
    if (!window.confirm(`'${row.name}' (${row.key}) 을 지울까요? 값·매핑이 없을 때만 지워집니다.`))
      return
    setBusy(row.key)
    setError(null)
    try {
      await catalogApi.deleteProperty(row.key)
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('지우지 못했습니다.'))
    } finally {
      setBusy(null)
    }
  }

  const { summary } = mapping

  return (
    <section className="mt-8 space-y-4" aria-label="물성 매핑">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold">물성 매핑</h2>
          <p className="text-muted-foreground text-sm">
            물성 하나가 문헌 키 · 사내 항목 · 시험이 재는 값으로 어떻게 이어져 있는가.
            문헌 키가 시스템끼리 쓰는 공용 이름표입니다.
          </p>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => setAdding(true)}>
            <FilePlus2 className="size-4" />
            문헌 물성 추가
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            downloadFile('/catalog/properties/dictionary', 'matnexus_property_dictionary.json')
          }
        >
          <Download className="size-4" />
          사전 내려받기
        </Button>
      </div>

      {/* **수를 먼저 보이고, 누르면 그것으로 거른다.** 「안 이어진 사내 항목」 이
          0 이 아니면 그것부터다 — 그 칸은 표가 아니라 아래 목록을 가리킨다. */}
      <div className="flex flex-wrap gap-2 text-sm" role="group" aria-label="무엇을 볼까">
        <Stat label="문헌 물성" value={summary.keys} active={mode === 'all'} onClick={() => setMode('all')} />
        <Stat
          label="사내 항목과 이어짐"
          value={summary.linked_keys}
          active={mode === 'linked'}
          onClick={() => setMode('linked')}
        />
        <Stat
          label="시험으로 재는 것"
          value={summary.measured_keys}
          active={mode === 'measured'}
          onClick={() => setMode('measured')}
        />
        <Stat
          label="사내에서 안 쓰는 것"
          value={summary.keys - mapping.rows.filter((one) => one.links.length > 0 || one.measured.length > 0).length}
          active={mode === 'unused'}
          onClick={() => setMode('unused')}
        />
        <Stat
          label="안 이어진 사내 항목"
          value={summary.unlinked_items}
          tone={summary.unlinked_items > 0 ? 'warn' : undefined}
        />
      </div>

      <ErrorNotice error={error} />

      {mapping.unlinked_items.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950">
          <p className="mb-2 font-medium">
            문헌 키에 안 이어진 사내 항목 {mapping.unlinked_items.length}개 — 값으로 찾기와 다른
            시스템과의 매핑에서 빠집니다.
          </p>
          <ul className="flex flex-wrap gap-2">
            {mapping.unlinked_items.map((item) => (
              <li key={item.term_id} className="flex items-center gap-1">
                <Badge variant="outline">{item.item}</Badge>
                {canEdit && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2"
                    aria-label={`${item.item} 잇기`}
                    onClick={() => setLinking({ item })}
                  >
                    <Link2 className="size-3.5" />
                    잇기
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="도메인으로 거르기"
          className="border-input bg-background h-9 rounded-md border px-2 text-sm"
          value={domain}
          onChange={(event) => setDomain(event.target.value)}
        >
          <option value="">모든 도메인</option>
          {domains.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
        <Input
          aria-label="물성 찾기"
          className="w-full sm:ml-auto sm:w-64"
          placeholder="이름·키·항목으로 찾기"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
      </div>

      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>문헌 물성</TableHead>
              <TableHead className="w-64">사내 항목</TableHead>
              <TableHead className="w-64">시험이 재는 값</TableHead>
              <TableHead className="w-36">규격</TableHead>
              <TableHead className="w-20 text-right">문헌값</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground py-8 text-center">
                  거른 조건에 맞는 물성이 없습니다.
                </TableCell>
              </TableRow>
            )}
            {rows.map((row) => (
              <TableRow key={row.key}>
                <TableCell>
                  <div className="flex items-center gap-1.5 font-medium">
                    {row.name}
                    {/* 직접 만든 물성은 그렇게 보인다 — 값·매핑이 없으면 지울 수 있다. */}
                    {row.origin === 'local' && (
                      <Badge variant="outline" title="MatNexus 에서 직접 만든 물성">
                        직접 만듦
                      </Badge>
                    )}
                    {row.deprecated && (
                      <Badge
                        variant="outline"
                        className="border-amber-500 text-amber-700 dark:text-amber-500"
                        title={row.deprecation_note ?? '폐기된 키 — 새 값을 못 달고 채우기에서 빠집니다'}
                      >
                        폐기{row.superseded_by ? ` → ${row.superseded_by}` : ''}
                      </Badge>
                    )}
                    {canEdit && !row.deprecated && (
                      <button
                        type="button"
                        aria-label={`${row.name} 폐기`}
                        title="지우지 않고 「그만 쓰고 저 키를 써라」 로 표시"
                        className="text-muted-foreground hover:text-foreground rounded p-0.5"
                        disabled={busy === row.key}
                        onClick={() => setRetiring(row)}
                      >
                        <Archive className="size-3.5" />
                      </button>
                    )}
                    {canEdit &&
                      row.deprecated &&
                      row.superseded_by &&
                      (row.links.length > 0 || row.value_count > 0) && (
                        <button
                          type="button"
                          aria-label={`${row.name} 의 값·매핑을 ${row.superseded_by} 로 옮기기`}
                          title="직접 넣은 값·매핑·별칭을 후속 키로 옮깁니다 (미리보기 뒤 확인)"
                          className="text-muted-foreground hover:text-foreground rounded p-0.5"
                          disabled={busy === row.key}
                          onClick={() => migrateProperty(row)}
                        >
                          <ArrowRightToLine className="size-3.5" />
                        </button>
                      )}
                    {canEdit && row.deprecated && (
                      <button
                        type="button"
                        aria-label={`${row.name} 폐기 취소`}
                        className="text-muted-foreground hover:text-foreground rounded p-0.5"
                        disabled={busy === row.key}
                        onClick={() => restoreProperty(row)}
                      >
                        <ArchiveRestore className="size-3.5" />
                      </button>
                    )}
                    {canEdit &&
                      row.origin === 'local' &&
                      row.links.length === 0 &&
                      row.value_count === 0 && (
                        <button
                          type="button"
                          aria-label={`${row.name} 지우기`}
                          className="text-muted-foreground hover:text-destructive rounded p-0.5"
                          disabled={busy === row.key}
                          onClick={() => removeProperty(row)}
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      )}
                  </div>
                  <div className="text-muted-foreground font-mono">{row.key}</div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap items-center gap-1">
                    {row.links.map((link) => (
                      <span key={link.id} className="inline-flex items-center gap-0.5">
                        <Badge
                          variant="secondary"
                          title={`${KIND_LABELS[link.kind] ?? link.kind}${link.note ? ` · ${link.note}` : ''}`}
                        >
                          {link.item}
                          {link.scale && <span className="ml-1 opacity-70">({link.scale})</span>}
                        </Badge>
                        {canEdit && (
                          <button
                            type="button"
                            aria-label={`${row.name} ↔ ${link.item}${link.scale ? ` (${link.scale})` : ''} 풀기`}
                            className="text-muted-foreground hover:text-foreground rounded p-0.5"
                            disabled={busy === link.id}
                            onClick={() => unlink(link.id)}
                          >
                            <Link2Off className="size-3.5" />
                          </button>
                        )}
                      </span>
                    ))}
                    {canEdit && (
                      <button
                        type="button"
                        aria-label={`${row.name} 에 사내 항목 잇기`}
                        className="text-muted-foreground hover:text-foreground rounded border border-dashed px-1.5 py-0.5"
                        onClick={() => setLinking({ row })}
                      >
                        <Plus className="inline size-3" />
                      </button>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  {row.measured.length === 0 ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <ul className="space-y-0.5">
                      {row.measured.map((m) => (
                        <li key={`${m.plugin_id}.${m.scalar_key}`}>
                          <span className="font-mono">{m.scalar_key}</span>{' '}
                          <span className="text-muted-foreground">← {m.plugin_label}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </TableCell>
                <TableCell>
                  {row.test_standard ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="text-right tabular-nums">{row.value_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <LinkDialog
        open={linking !== null}
        preset={linking ?? {}}
        mapping={mapping}
        onClose={() => setLinking(null)}
        onDone={() => {
          setLinking(null)
          onChanged()
        }}
      />
      <AddPropertyDialog
        open={adding}
        onClose={() => setAdding(false)}
        onDone={() => {
          setAdding(false)
          onChanged()
        }}
      />
      <DeprecateDialog
        row={retiring}
        mapping={mapping}
        onClose={() => setRetiring(null)}
        onDone={() => {
          setRetiring(null)
          onChanged()
        }}
      />
    </section>
  )
}

/**
 * 폐기 — **후속 키를 고른다.** 후속은 살아 있는 키여야 한다(폐기된 키는 목록에서
 * 뺀다). 후속 없이 폐기할 수도 있다 — 그때는 새 값을 달 곳이 없다는 뜻이다.
 */
function DeprecateDialog({
  row,
  mapping,
  onClose,
  onDone,
}: {
  row: PropertyMappingRow | null
  mapping: PropertyMapping
  onClose: () => void
  onDone: () => void
}) {
  const [query, setQuery] = useState('')
  const [successor, setSuccessor] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [openedFor, setOpenedFor] = useState<string | null>(null)
  if (row && openedFor !== row.key) {
    setOpenedFor(row.key)
    setQuery('')
    setSuccessor(null)
    setNote('')
    setError(null)
  }
  if (!row && openedFor !== null) setOpenedFor(null)

  const needle = query.trim().toLowerCase()
  const candidates = useMemo(
    () =>
      needle && row
        ? mapping.rows
            .filter(
              (one) =>
                one.key !== row.key &&
                !one.deprecated &&
                (one.name.toLowerCase().includes(needle) ||
                  one.key.toLowerCase().includes(needle))
            )
            .slice(0, 12)
        : [],
    [mapping.rows, needle, row]
  )
  const chosen = successor ? mapping.rows.find((one) => one.key === successor) : null

  async function submit() {
    if (!row) return
    setSaving(true)
    setError(null)
    try {
      await catalogApi.deprecateProperty(row.key, { superseded_by: successor, note: note || null })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('폐기하지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={row !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{row ? `'${row.name}' 폐기` : '폐기'}</DialogTitle>
          <DialogDescription>
            지우지 않습니다. 새 값을 못 달고, 채우기에서 빠지고, 이름을 풀 때 뒤로 밀리며 후속
            키를 함께 알려 줍니다. 사전을 받아 간 시스템은 후속 키로 옮깁니다.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="space-y-1.5">
            <Label>대신 쓸 키 (없어도 됨)</Label>
            {chosen ? (
              <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                <span className="font-medium">{chosen.name}</span>
                <span className="text-muted-foreground font-mono">{chosen.key}</span>
                <Button size="sm" variant="ghost" className="ml-auto h-7" onClick={() => setSuccessor(null)}>
                  바꾸기
                </Button>
              </div>
            ) : (
              <>
                <Input
                  aria-label="후속 물성 찾기"
                  placeholder="이름이나 키로 쳐서 찾기"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
                {candidates.length > 0 && (
                  <ul className="max-h-48 overflow-y-auto rounded-md border">
                    {candidates.map((one) => (
                      <li key={one.key}>
                        <button
                          type="button"
                          className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                          onClick={() => setSuccessor(one.key)}
                        >
                          <span className="font-medium">{one.name}</span>
                          <span className="text-muted-foreground font-mono">{one.key}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
          <div className="grid gap-1">
            <Label htmlFor="deprecate-note">왜</Label>
            <Input
              id="deprecate-note"
              value={note}
              placeholder="이름을 잘못 지음 · 저쪽 키와 겹침 …"
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
          <ErrorNotice error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={submit} disabled={saving}>
            폐기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * 문헌 물성 추가 — **키는 서버가 만든다**(`local.<domain>.<slug>`).
 *
 * 이름·별칭이 같은 물성이 이미 있으면 서버가 그 키를 알려 주고 거절한다 — 그
 * 메시지를 그대로 보인다. 단위는 SI 정본으로 적는다(값은 이 단위로 환산돼 저장).
 */
function AddPropertyDialog({
  open,
  onClose,
  onDone,
}: {
  open: boolean
  onClose: () => void
  onDone: () => void
}) {
  const [form, setForm] = useState<CatalogPropertyCreate>({
    name: '',
    domain: 'mechanical',
    slug: '',
    si_unit: '',
    symbol: '',
    test_standard: '',
    description: '',
    value_type: 'numeric',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  function set<K extends keyof CatalogPropertyCreate>(key: K, value: CatalogPropertyCreate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  async function submit() {
    setSaving(true)
    setError(null)
    try {
      await catalogApi.createProperty({
        ...form,
        symbol: form.symbol || null,
        test_standard: form.test_standard || null,
        description: form.description || null,
      })
      setForm({
        name: '',
        domain: 'mechanical',
        slug: '',
        si_unit: '',
        symbol: '',
        test_standard: '',
        description: '',
        value_type: 'numeric',
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('만들지 못했습니다.'))
    } finally {
      setSaving(false)
    }
  }

  const slugOk = /^[a-z][a-z0-9_]{1,60}$/.test(form.slug)
  const ready = form.name.trim() !== '' && slugOk && (form.si_unit ?? '').trim() !== ''

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>문헌 물성 추가</DialogTitle>
          <DialogDescription>
            문헌 카탈로그에 없는 물성을 만듭니다. 키는{' '}
            <span className="font-mono">local.{form.domain}.{form.slug || '…'}</span> 가 되고,
            한 번 만들면 바뀌지 않습니다.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label htmlFor="new-prop-name">이름</Label>
            <Input
              id="new-prop-name"
              value={form.name}
              placeholder="습윤 굴곡탄성률"
              onChange={(event) => set('name', event.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="new-prop-domain">도메인</Label>
              <select
                id="new-prop-domain"
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={form.domain}
                onChange={(event) => set('domain', event.target.value)}
              >
                {DOMAINS.map((one) => (
                  <option key={one} value={one}>
                    {DOMAIN_LABELS[one] ?? one} ({one})
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-prop-slug">키 조각 (영문 snake_case)</Label>
              <Input
                id="new-prop-slug"
                value={form.slug}
                placeholder="flexural_modulus_wet"
                className="font-mono"
                onChange={(event) => set('slug', event.target.value.trim())}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="new-prop-unit">SI 단위 (무차원은 1)</Label>
              <Input
                id="new-prop-unit"
                value={form.si_unit ?? ''}
                placeholder="Pa"
                className="font-mono"
                onChange={(event) => set('si_unit', event.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-prop-symbol">기호</Label>
              <Input
                id="new-prop-symbol"
                value={form.symbol ?? ''}
                placeholder="E_f"
                onChange={(event) => set('symbol', event.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="new-prop-standard">시험 규격</Label>
            <Input
              id="new-prop-standard"
              value={form.test_standard ?? ''}
              placeholder="ISO 178"
              onChange={(event) => set('test_standard', event.target.value)}
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="new-prop-desc">설명</Label>
            <Input
              id="new-prop-desc"
              value={form.description ?? ''}
              onChange={(event) => set('description', event.target.value)}
            />
          </div>
          <ErrorNotice error={error} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={submit} disabled={!ready || saving}>
            만들기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 표를 무엇으로 거를까. 요약 칸이 곧 거르개다. */
type Mode = 'all' | 'linked' | 'measured' | 'unused'

const MODES: Record<Mode, { keep: (row: PropertyMappingRow) => boolean }> = {
  all: { keep: () => true },
  linked: { keep: (row) => row.links.length > 0 },
  measured: { keep: (row) => row.measured.length > 0 },
  // 문헌에만 있고 사내에서는 적지도 재지도 않는 것 — 매핑을 늘릴 후보다.
  unused: { keep: (row) => row.links.length === 0 && row.measured.length === 0 },
}

function Stat({
  label,
  value,
  tone,
  active,
  onClick,
}: {
  label: string
  value: number
  tone?: 'warn'
  active?: boolean
  onClick?: () => void
}) {
  const body = (
    <>
      <span className="text-muted-foreground block text-xs">{label}</span>
      <span className="font-medium tabular-nums">{value}</span>
    </>
  )
  const frame = `rounded-md border px-3 py-1.5 text-left ${
    tone === 'warn' && value > 0
      ? 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950'
      : active
        ? 'border-primary bg-primary/10'
        : ''
  }`
  if (!onClick) return <div className={frame}>{body}</div>
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={`${frame} hover:bg-muted`}>
      {body}
    </button>
  )
}

/**
 * 잇는 창 — 문헌 물성 하나와 사내 항목 하나(눈금이 있으면 눈금까지).
 *
 * 문헌 쪽이 정해져 있으면(표의 「+」) 항목만 고르고, 항목 쪽이 정해져 있으면
 * (안 이어진 목록의 「잇기」) 문헌 물성을 쳐서 찾는다 — 271개를 펼쳐 놓고 눈으로
 * 찾게 하지 않는다.
 */
function LinkDialog({
  open,
  preset,
  mapping,
  onClose,
  onDone,
}: {
  open: boolean
  preset: { row?: PropertyMappingRow; item?: PropertyUnlinkedItem }
  mapping: PropertyMapping
  onClose: () => void
  onDone: () => void
}) {
  const [keyQuery, setKeyQuery] = useState('')
  const [key, setKey] = useState<string | null>(null)
  const [termId, setTermId] = useState<string>('')
  const [scale, setScale] = useState('')
  const [kind, setKind] = useState('same_as')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [openedFor, setOpenedFor] = useState<string | null>(null)

  // 열릴 때 미리 정해진 쪽을 채운다. 렌더마다 채우면 고른 것이 되돌아간다.
  const presetId = `${preset.row?.key ?? ''}|${preset.item?.term_id ?? ''}`
  if (open && openedFor !== presetId) {
    setOpenedFor(presetId)
    setKey(preset.row?.key ?? null)
    setKeyQuery('')
    setTermId(preset.item?.term_id ?? '')
    setScale('')
    setKind('same_as')
    setError(null)
  }
  if (!open && openedFor !== null) setOpenedFor(null)

  const chosenItem = mapping.items.find((one) => one.term_id === termId) ?? null
  const needle = keyQuery.trim().toLowerCase()
  const keyCandidates = useMemo(
    () =>
      needle
        ? mapping.rows
            .filter(
              (one) =>
                one.name.toLowerCase().includes(needle) || one.key.toLowerCase().includes(needle)
            )
            .slice(0, 12)
        : [],
    [mapping.rows, needle]
  )
  const chosenRow = key ? mapping.rows.find((one) => one.key === key) : null
  const needsScale = (chosenItem?.scales.length ?? 0) > 0
  const ready = Boolean(key && termId && (!needsScale || scale))

  async function submit() {
    if (!key || !chosenItem) return
    setBusy(true)
    setError(null)
    const payload: PropertyLinkCreate = {
      property_key: key,
      item: chosenItem.item,
      kind,
      scale: needsScale ? scale : null,
    }
    try {
      await catalogApi.linkProperty(payload)
      onDone()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('잇지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>사내 항목을 문헌 물성에 잇기</DialogTitle>
          <DialogDescription>
            이어 두면 값으로 찾기가 사내 값까지 보고, 다른 시스템이 같은 키로 만납니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>문헌 물성</Label>
            {chosenRow ? (
              <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                <span className="font-medium">{chosenRow.name}</span>
                <span className="text-muted-foreground font-mono">{chosenRow.key}</span>
                {!preset.row && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto h-7"
                    onClick={() => setKey(null)}
                  >
                    바꾸기
                  </Button>
                )}
              </div>
            ) : (
              <>
                <Input
                  aria-label="문헌 물성 찾기"
                  autoFocus
                  placeholder="이름이나 키로 쳐서 찾기 — 항복, yield…"
                  value={keyQuery}
                  onChange={(event) => setKeyQuery(event.target.value)}
                />
                {keyCandidates.length > 0 && (
                  <ul className="max-h-48 overflow-y-auto rounded-md border">
                    {keyCandidates.map((one) => (
                      <li key={one.key}>
                        <button
                          type="button"
                          className="hover:bg-muted flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
                          onClick={() => setKey(one.key)}
                        >
                          <span className="font-medium">{one.name}</span>
                          <span className="text-muted-foreground font-mono">{one.key}</span>
                          <span className="text-muted-foreground ml-auto tabular-nums">
                            {one.value_count}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="link-item">사내 항목</Label>
            <select
              id="link-item"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              value={termId}
              onChange={(event) => {
                setTermId(event.target.value)
                setScale('')
              }}
              disabled={Boolean(preset.item)}
            >
              <option value="">고르세요</option>
              {mapping.items.map((one) => (
                <option key={one.term_id} value={one.term_id}>
                  {one.item}
                </option>
              ))}
            </select>
          </div>

          {needsScale && chosenItem && (
            <div className="space-y-1.5">
              <Label htmlFor="link-scale">눈금</Label>
              <select
                id="link-scale"
                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                value={scale}
                onChange={(event) => setScale(event.target.value)}
              >
                <option value="">고르세요</option>
                {chosenItem.scales.map((one) => (
                  <option key={one} value={one}>
                    {one}
                  </option>
                ))}
              </select>
              <p className="text-muted-foreground text-xs">
                「{chosenItem.item}」 은 눈금을 갖는 항목입니다 — 어느 눈금의 값이 이 문헌
                물성인지 정해야 다른 눈금 값이 검색에 섞이지 않습니다.
              </p>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="link-kind">관계</Label>
            <select
              id="link-kind"
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              {mapping.kinds.map((one) => (
                <option key={one} value={one}>
                  {KIND_LABELS[one] ?? one}
                </option>
              ))}
            </select>
          </div>
        </div>

        <ErrorNotice error={error} />

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button disabled={busy || !ready} onClick={submit}>
            <Link2 className="size-4" />
            잇기
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
