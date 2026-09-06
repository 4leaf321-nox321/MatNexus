/**
 * BOM 혼합 덱 — **부품표 붙여넣기 → 사내 카드 우선 매칭 → 한 파일** (이식 2.5단계).
 *
 * 실행 화면은 카드(fitting) 영역에 산다 — 워크벤치 화면은 자기 자원(/workbench/*)만
 * 부를 수 있고(tests/architecture 의 R5 검사, 65의 「워크벤치마다 1,200줄 재작성」
 * 재발 방지), 이 화면은 도메인 API 여섯을 조립한다. 워크벤치에는 이 화면으로
 * 안내하는 워크플로(bom_deck)가 있다 — 입구는 워크벤치, 집은 카드 영역이다.
 *
 * 매칭 규율:
 *   사내 확정 카드(실측)가 있으면 그것이 기본이다 — 실측을 두고 문헌값으로
 *   해석하는 것은 거꾸로다(카드 폴백 규칙과 같은 원칙)
 *   한 번 고른 「BOM 이름 → 재료」 는 기억된다(전사) — 다음 붙여넣기에 자동
 *   사내 재료와 문헌 재료를 함께 고르면 문헌 연결(catalog_links)도 그 자리에서
 */

import { ClipboardPaste, Download, Loader2 } from 'lucide-react'
import { useMemo, useState } from 'react'

import { api } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { useResource } from '@/shared/hooks/useResource'

type MaterialOut = components['schemas']['MaterialOut']
type MaterialPage = components['schemas']['Page_MaterialOut_']
type CardPage = components['schemas']['Page_PropertyCardOut_']
type CatalogMatchRow = components['schemas']['DeckMatchRowOut']
type AliasLookup = components['schemas']['BomAliasLookupOut']
type BomBuilt = components['schemas']['BomDeckOut']
type UnitSystemOut = components['schemas']['UnitSystemOut']

/** 붙여넣은 한 줄의 매칭 상태 — 화면이 들고 있는 전부다. */
interface Row {
  mid: number
  name: string
  /** 사내 매칭 — 카드까지 정해지면 곡선 덱으로 나간다. */
  material: { id: string; code: string; record_name: string } | null
  cardId: string | null
  cardLabel: string | null
  /** 문헌 매칭 — 사내가 없으면 이걸로 메꾸고, 둘 다면 연결도 건다. */
  catalog: { id: string; name: string } | null
  /** 문헌 스칼라로 곡선을 지어 *MAT_024 까지 — 사람이 켜야 켜진다(합성 표지 필수). */
  synthesize: boolean
  fromMemory: boolean
}

/**
 * 부품표 파싱 — 한 열(`이름`)·두 열(`MID, 이름`)·**엑셀 다열**(탭 구분).
 * 다열이면 어느 열이 MID·이름인지 사람이 고른다(열 매핑) — 추측해서 조용히
 * 틀리는 것보다 한 번 묻는 것이 낫다.
 */
function splitColumns(text: string): string[][] {
  return text
    .split('\n')
    .map((line) => line.replace(/\r$/, ''))
    .filter((line) => line.trim() !== '')
    .map((line) => line.split('\t').map((cell) => cell.trim()))
}

function parseRows(cells: string[][], midCol: number | null, nameCol: number): Row[] {
  const rows: Row[] = []
  for (const [index, line] of cells.entries()) {
    let name = line[nameCol]?.trim()
    let rawMid = midCol !== null ? (line[midCol]?.trim() ?? '') : ''
    // 한 열짜리는 서버 파서와 같은 규칙 — `101, SUS304` 의 콤마도 읽는다.
    if (line.length === 1 && name) {
      const comma = name.match(/^(\d+)\s*,\s*(.+)$/)
      if (comma) {
        rawMid = comma[1]
        name = comma[2].trim()
      }
    }
    if (!name) continue
    const mid = rawMid && /^\d+$/.test(rawMid) ? Number(rawMid) : index + 1
    rows.push({
      mid,
      name,
      material: null,
      cardId: null,
      cardLabel: null,
      catalog: null,
      synthesize: false,
      fromMemory: false,
    })
  }
  return rows
}

export default function BomDeckPage() {
  const [pasted, setPasted] = useState('')
  const [midCol, setMidCol] = useState<number | null>(0)
  const [nameCol, setNameCol] = useState(1)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [catalogRows, setCatalogRows] = useState<Map<string, CatalogMatchRow>>(new Map())
  const [units, setUnits] = useState('si')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [built, setBuilt] = useState<BomBuilt | null>(null)

  const systems = useResource(() => api.get<UnitSystemOut[]>('/fitting/unit-systems'), [])

  const columns = useMemo(() => splitColumns(pasted), [pasted])
  const width = Math.max(0, ...columns.map((line) => line.length))

  /** 붙여넣기 → 기억 조회 + 문헌 후보를 한 번에. */
  const match = async () => {
    setBusy(true)
    setError(null)
    setBuilt(null)
    try {
      const parsed = parseRows(
        columns,
        width > 1 ? midCol : null,
        width > 1 ? nameCol : 0
      )
      if (parsed.length === 0) throw new Error('읽을 줄이 없습니다.')

      const [memory, literature] = await Promise.all([
        api.post<AliasLookup>('/workbench/bom-aliases/lookup', {
          queries: parsed.map((row) => row.name),
        }),
        api.post<CatalogMatchRow[]>('/catalog/deck/match', {
          text: parsed.map((row) => `${row.mid}, ${row.name}`).join('\n'),
        }),
      ])
      setCatalogRows(new Map(literature.map((row) => [row.query, row])))

      // 기억된 매칭을 자동 적용 — 사내 재료는 카드·이름을 마저 읽어 온다.
      const applied = await Promise.all(
        parsed.map(async (row, index) => {
          const remembered = memory.found[index]
          const next = { ...row }
          if (remembered?.catalog_material_id) {
            const hit = literature[index]?.candidates.find(
              (one) => one.id === remembered.catalog_material_id
            )
            next.catalog = hit
              ? { id: hit.id, name: hit.name }
              : { id: remembered.catalog_material_id, name: '(기억된 문헌 재료)' }
            next.fromMemory = true
          }
          if (remembered?.material_id) {
            await applyMaterial(next, remembered.material_id)
            next.fromMemory = true
          }
          return next
        })
      )
      setRows(applied)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('매칭하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  /** 사내 재료를 줄에 앉힌다 — 확정 카드가 있으면 자동으로 함께(실측 우선). */
  async function applyMaterial(row: Row, materialId: string) {
    const [material, cards] = await Promise.all([
      api.get<MaterialOut>(`/materials/${materialId}`),
      api.get<CardPage>(`/fitting/cards?material_id=${materialId}&status=published&limit=1`),
    ])
    row.material = {
      id: material.id,
      code: material.code,
      record_name: material.record_name,
    }
    const card = cards.items[0]
    row.cardId = card ? card.id : null
    row.cardLabel = card ? card.label : null
  }

  const ready = (rows ?? []).filter((row) => row.cardId || row.catalog)

  const build = async () => {
    if (!rows) return
    setBusy(true)
    setError(null)
    try {
      const made = await api.post<BomBuilt>('/fitting/decks/bom', {
        rows: rows.map((row) => ({
          mid: row.mid,
          name: row.name,
          // 사내 카드가 있으면 그것 — 없으면 문헌으로 메꾼다.
          card_id: row.cardId,
          catalog_material_id: row.cardId ? null : (row.catalog?.id ?? null),
          synthesize: !row.cardId && row.synthesize,
        })),
        units: units === 'si' ? null : units,
      })
      setBuilt(made)

      // 고른 매칭을 기억하고, 사내+문헌 둘 다면 문헌 연결까지 — 실패해도
      // 덱은 이미 손에 있으므로 조용히 넘어가지 않고 알림만 한다.
      const chores: Promise<unknown>[] = []
      for (const row of rows) {
        if (row.material || row.catalog) {
          chores.push(
            api.put('/workbench/bom-aliases', {
              query: row.name,
              material_id: row.material?.id ?? null,
              catalog_material_id: row.catalog?.id ?? null,
            })
          )
        }
        if (row.material && row.catalog) {
          chores.push(
            api.put(`/catalog/links/${row.material.id}`, {
              catalog_material_id: row.catalog.id,
            })
          )
        }
      }
      const settled = await Promise.allSettled(chores)
      if (settled.some((one) => one.status === 'rejected')) {
        setError(new Error('덱은 만들어졌지만 매칭 기억·문헌 연결 일부를 저장하지 못했습니다.'))
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('덱을 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const download = () => {
    if (!built) return
    const blob = new Blob([built.text], { type: 'text/plain;charset=utf-8' })
    const anchor = document.createElement('a')
    anchor.href = URL.createObjectURL(blob)
    anchor.download = built.filename
    anchor.click()
    URL.revokeObjectURL(anchor.href)
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="BOM 혼합 덱"
        description="부품표를 붙여넣으면 부품마다 사내 확정 카드(실측)를 먼저 찾고, 없는 부품은 문헌 물성으로 메꿔 해석 덱 한 파일을 만듭니다. 값마다 출처가 각주로 남습니다."
      />
      <ErrorNotice error={error} />

      <div className="space-y-2 rounded-md border p-3">
        <div className="text-sm font-medium">1. 부품표 붙여넣기</div>
        <textarea
          className="border-input min-h-28 w-full rounded-md border p-2 font-mono text-sm"
          placeholder={'1, SUS304\n2, SGARC440\n(엑셀 표를 통째로 붙여도 됩니다 — 열을 고르세요)'}
          value={pasted}
          onChange={(event) => setPasted(event.target.value)}
        />
        {width > 1 && (
          <div className="text-muted-foreground flex flex-wrap items-center gap-3 text-xs">
            <span>열 {width}개를 봤습니다 —</span>
            <label className="flex items-center gap-1">
              MID 열
              <select
                className="border-input rounded border px-1 py-0.5"
                value={midCol ?? -1}
                onChange={(event) =>
                  setMidCol(event.target.value === '-1' ? null : Number(event.target.value))
                }
              >
                <option value={-1}>없음(순번 부여)</option>
                {Array.from({ length: width }, (_, index) => (
                  <option key={index} value={index}>
                    {index + 1}열
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1">
              재료명 열
              <select
                className="border-input rounded border px-1 py-0.5"
                value={nameCol}
                onChange={(event) => setNameCol(Number(event.target.value))}
              >
                {Array.from({ length: width }, (_, index) => (
                  <option key={index} value={index}>
                    {index + 1}열
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        <Button size="sm" onClick={() => void match()} disabled={busy || !pasted.trim()}>
          {busy && !rows ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <ClipboardPaste className="size-4" />
          )}
          매칭
        </Button>
      </div>

      {rows && (
        <div className="space-y-2 rounded-md border p-3">
          <div className="text-sm font-medium">
            2. 매칭 확인 — 실을 수 있는 부품 {ready.length} / {rows.length}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground border-b text-left text-xs">
                  <th className="p-2">MID</th>
                  <th className="p-2">BOM 이름</th>
                  <th className="p-2">사내 재료 (카드)</th>
                  <th className="p-2">문헌 재료</th>
                  <th className="p-2">덱에 실릴 것</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <MatchRow
                    key={`${row.mid}-${index}`}
                    row={row}
                    catalog={catalogRows.get(row.name) ?? null}
                    onChange={(next) =>
                      setRows((now) =>
                        now ? now.map((one, at) => (at === index ? next : one)) : now
                      )
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {rows && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border p-3">
          <div className="text-sm font-medium">3. 내보내기</div>
          <label className="text-muted-foreground flex items-center gap-1 text-xs">
            단위계
            <select
              className="border-input rounded border px-1 py-0.5"
              value={units}
              onChange={(event) => setUnits(event.target.value)}
            >
              <option value="si">SI (m·kg·s)</option>
              {(systems.data ?? [])
                .filter((one) => one.key !== 'si')
                .map((one) => (
                  <option key={one.key} value={one.key}>
                    {one.label}
                  </option>
                ))}
            </select>
          </label>
          <Button size="sm" onClick={() => void build()} disabled={busy || ready.length === 0}>
            {busy && rows ? <Loader2 className="size-4 animate-spin" /> : null}덱 만들기
          </Button>
          {built && (
            <>
              <Button size="sm" variant="outline" onClick={download}>
                <Download className="size-4" />
                {built.filename}
              </Button>
              <span className="text-muted-foreground text-xs">
                사내 카드 {built.card_count} · 문헌 {built.literature_count}
                {built.synthetic_count > 0 && ` · 합성 곡선 ${built.synthetic_count}`}
                {built.skipped.length > 0 && ` · 건너뜀 ${built.skipped.length}`}
              </span>
            </>
          )}
        </div>
      )}

      {built && built.skipped.length > 0 && (
        <div className="rounded-md border border-amber-300 p-3 text-sm">
          <div className="mb-1 font-medium">건너뛴 부품 — 조용히 빠지지 않습니다</div>
          <ul className="text-muted-foreground space-y-0.5 text-xs">
            {built.skipped.map((one) => (
              <li key={one.mid}>
                MID {one.mid} · {one.name} — {one.why}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** 한 줄의 매칭 편집 — 사내 검색과 문헌 후보 고르기. */
function MatchRow({
  row,
  catalog,
  onChange,
}: {
  row: Row
  catalog: CatalogMatchRow | null
  onChange: (next: Row) => void
}) {
  const [typed, setTyped] = useState('')
  const [found, setFound] = useState<MaterialOut[]>([])
  const [searching, setSearching] = useState(false)

  const search = async () => {
    setSearching(true)
    try {
      const page = await api.get<MaterialPage>(
        `/materials?q=${encodeURIComponent(typed || row.name)}&limit=5`
      )
      setFound(page.items)
    } finally {
      setSearching(false)
    }
  }

  const pickMaterial = async (material: MaterialOut) => {
    const cards = await api.get<CardPage>(
      `/fitting/cards?material_id=${material.id}&status=published&limit=1`
    )
    const card = cards.items[0]
    onChange({
      ...row,
      material: { id: material.id, code: material.code, record_name: material.record_name },
      cardId: card ? card.id : null,
      cardLabel: card ? card.label : null,
      fromMemory: false,
    })
    setFound([])
  }

  return (
    <tr className="border-b align-top last:border-b-0">
      <td className="p-2 tabular-nums">{row.mid}</td>
      <td className="p-2">
        {row.name}
        {row.fromMemory && (
          <span className="text-muted-foreground ml-1 text-xs" title="지난번에 고른 매칭입니다">
            (기억)
          </span>
        )}
      </td>
      <td className="p-2">
        {row.material ? (
          <div>
            <span className="font-mono text-xs">{row.material.record_name}</span>
            <div className="text-muted-foreground text-xs">
              {row.material.code}
              {row.cardLabel ? ` · 카드: ${row.cardLabel}` : ' · 확정 카드 없음'}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <Input
              className="h-7 w-36 text-xs"
              placeholder="사내 재료 검색"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
            <Button size="sm" variant="outline" onClick={() => void search()} disabled={searching}>
              찾기
            </Button>
          </div>
        )}
        {found.length > 0 && (
          <div className="mt-1 space-y-0.5">
            {found.map((one) => (
              <button
                key={one.id}
                type="button"
                className="hover:bg-muted block w-full rounded border px-2 py-1 text-left text-xs"
                onClick={() => void pickMaterial(one)}
              >
                {one.record_name}
                <span className="text-muted-foreground ml-1">{one.code}</span>
              </button>
            ))}
          </div>
        )}
        {row.material && (
          <Button
            size="sm"
            variant="ghost"
            className="mt-1 h-6 text-xs"
            onClick={() =>
              onChange({ ...row, material: null, cardId: null, cardLabel: null, fromMemory: false })
            }
          >
            바꾸기
          </Button>
        )}
      </td>
      <td className="p-2">
        <select
          className="border-input w-40 rounded border px-1 py-0.5 text-xs"
          value={row.catalog?.id ?? ''}
          onChange={(event) => {
            const hit = catalog?.candidates.find((one) => one.id === event.target.value)
            onChange({
              ...row,
              catalog: hit ? { id: hit.id, name: hit.name } : null,
              fromMemory: false,
            })
          }}
        >
          <option value="">— 없음 —</option>
          {(catalog?.candidates ?? []).map((one) => (
            <option key={one.id} value={one.id}>
              {one.name} (물성 {one.value_count})
            </option>
          ))}
        </select>
        {/* 곡선 합성 — 지어낸 곡선은 지어냈다고 말한다. 사내 카드가 있으면 실측이 이긴다. */}
        {row.catalog && !row.cardId && (
          <label className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              className="accent-primary size-3"
              checked={row.synthesize}
              onChange={(event) => onChange({ ...row, synthesize: event.target.checked })}
            />
            곡선 합성(*MAT_024) — 실측 아님, 덱에 합성 표지
          </label>
        )}
      </td>
      <td className="p-2 text-xs">
        {row.cardId ? (
          <span className="text-emerald-700 dark:text-emerald-500">사내 카드 (곡선)</span>
        ) : row.catalog ? (
          row.synthesize ? (
            <span className="text-amber-700 dark:text-amber-500">문헌 합성 곡선</span>
          ) : (
            <span>문헌 스칼라</span>
          )
        ) : (
          <span className="text-muted-foreground">건너뜀 — 매칭 없음</span>
        )}
      </td>
    </tr>
  )
}
