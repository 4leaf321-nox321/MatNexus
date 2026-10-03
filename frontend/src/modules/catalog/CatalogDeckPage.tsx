/**
 * 카탈로그 → 솔버 덱 — **BOM 붙여넣기 3단계** (MaterialTwin 이식 2단계).
 *
 *   ① 붙여넣기      `MID, 재료명` 또는 `재료명` 줄들
 *   ② 매칭 확인     줄마다 후보 중 하나를 사람이 고른다 (적합도·물성 수 표시)
 *   ③ 덱           미리보기 · 복사 · 내려받기 — 값마다 출처 각주가 $ 주석으로
 *
 * 카탈로그 재료는 스칼라뿐이라 낼 수 있는 것은 탄성·열물성 덱이다 — 솔버는 서버가 판정한
 * 목록에서 고른다(LS-DYNA · Abaqus · ANSYS · Nastran · OptiStruct · Radioss, 해석용 물성
 * 정의까지). 문헌 값은 **사내 물성 매핑을 거쳐** 실린다(2026-09-28). 곡선이 필요한 덱은
 * 시험→카드 경로에서 나온다. 모자란 재료는 덱에서 조용히 빠지지 않고 「무엇이 없는지」 와
 * 함께 아래에 선다.
 */

import { Check, Copy, Download, FileCode2 } from 'lucide-react'
import { useState } from 'react'

import { catalogApi } from '@/modules/catalog/api'
import type { DeckBuilt, DeckMatchRow } from '@/modules/catalog/api'
import { chosenSystem, unitSystemsApi } from '@/shared/api/unitSystems'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Textarea } from '@/shared/components/ui/textarea'
import { useResource } from '@/shared/hooks/useResource'
import { copyText } from '@/shared/lib/clipboard'

interface Row {
  query: string
  mid: number
  choice: string | null
  candidates: DeckMatchRow['candidates']
}

export default function CatalogDeckPage() {
  const [text, setText] = useState('')
  const [rows, setRows] = useState<Row[] | null>(null)
  // 형식 목록은 서버가 판정한다. 고르기 전에는 LS-DYNA 탄성(전의 기본), 없으면 첫 것.
  const formats = useResource(() => catalogApi.deckFormats(), [])
  const [picked, setPicked] = useState<string | null>(null)
  const format =
    picked ??
    formats.data?.find((one) => one.key === 'dyna_elastic')?.key ??
    formats.data?.[0]?.key ??
    'dyna_elastic'
  // 계 목록과 기본은 서버가 준다(ADR 0036) — 전에는 붙박이 둘을 적어 두고 SI 가 첫째라,
  // 부서가 만든 계는 못 골랐고 기본은 해석이 쓰는 계가 아니었다.
  const systems = useResource(() => unitSystemsApi.list(), [])
  const [units, setUnits] = useState<string | null>(null)
  const system = chosenSystem(systems.data ?? [], units)
  const [built, setBuilt] = useState<DeckBuilt | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  /** 복사 결과. **막혔으면 그렇다고 말한다** — 「복사됨」 만 뜨면 빈 칸을 붙여 넣는다. */
  const [copied, setCopied] = useState<'yes' | 'no' | null>(null)

  async function match() {
    setBusy(true)
    setError(null)
    setBuilt(null)
    try {
      const matched = await catalogApi.deckMatch(text)
      // MID 가 없는 줄은 이어지는 번호를 자동으로 준다 — 자동인지 지정인지 보인다.
      let next = 1
      const taken = new Set(matched.map((one) => one.mid).filter((mid) => mid !== null))
      setRows(
        matched.map((one) => {
          let mid = one.mid
          if (mid === null) {
            while (taken.has(next)) next += 1
            mid = next
            taken.add(next)
          }
          return {
            query: one.query,
            mid,
            choice: one.candidates[0] ? String(one.candidates[0].id) : null,
            candidates: one.candidates,
          }
        })
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('매칭하지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  async function build() {
    if (!rows) return
    setBusy(true)
    setError(null)
    try {
      const items = rows
        .filter((row) => row.choice)
        .map((row) => ({ mid: row.mid, catalog_material_id: row.choice as string }))
      setBuilt(
        await catalogApi.deckBuild({ items, format, units: system?.key ?? null })
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('덱을 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function download() {
    if (!built) return
    const blob = new Blob([built.text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = built.filename
    anchor.click()
    // **곧바로 풀지 않는다**(2026-10-04) — 저장이 시작되기 전에 주소가 사라지는 브라우저가
    // 있다. `downloadFile`(shared/api/client) 과 같은 규칙이다.
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }

  const unmatched = (rows ?? []).filter((row) => !row.choice)

  return (
    <div className="space-y-4">
      <PageHeader
        title="문헌 덱 생성"
        description="해석 모델은 부품마다 재료가 필요합니다. 부품표(BOM)의 재료명들을 통째로 붙여넣으면 문헌 카탈로그와 매칭해 재료 카드 덱을 한 번에 만듭니다 — 하나씩 값을 찾아 손으로 옮기는 일의 일괄판입니다. 모델에서 쓰는 재료 번호(MID)를 줄 앞에 적으면 만들어진 카드가 그 번호로 나가 기존 모델에 그대로 꽂히고, 안 적으면 자동으로 매깁니다. 덱의 모든 값 옆에 출처·등급 각주가 $ 주석으로 들어갑니다."
      />
      <ErrorNotice error={error} />

      {/* 혼합 덱이 이 화면의 확장판이다 — 문헌 전용이 필요한 경우(열물성 덱 등)만 여기. */}
      <p className="text-muted-foreground rounded-md border border-dashed p-2 text-xs">
        사내 시험 카드(실측)가 있는 재료는{' '}
        <a className="underline" href="/cards/bom-deck">
          워크벤치의 BOM 혼합 덱
        </a>
        이 실측을 우선으로 싣습니다 — 이 화면은 문헌값 전용입니다.
      </p>

      <section className="space-y-2 rounded-md border p-3">
        <p className="text-sm font-semibold">
          ① 붙여넣기
          <span className="text-muted-foreground ml-2 text-xs font-normal">
            한 줄에 재료 하나 — 「MID, 재료명」 또는 「재료명」. 한 건만 필요하면 한 줄만.
          </span>
        </p>
        <Textarea
          aria-label="재료 목록"
          placeholder={'101, SUS304\nFR-4\nSGARC440'}
          rows={5}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <Button onClick={() => void match()} disabled={busy || !text.trim()}>
          매칭
        </Button>
      </section>

      {rows && (
        <section className="space-y-2 rounded-md border p-3">
          <p className="text-sm font-semibold">② 매칭 확인 — 고르는 것은 사람입니다</p>
          {rows.map((row, index) => (
            <div key={`${row.query}-${index}`} className="flex flex-wrap items-center gap-2">
              <Input
                aria-label={`${row.query} 의 MID`}
                className="w-24 tabular-nums"
                type="number"
                value={row.mid}
                onChange={(event) => {
                  const mid = Number(event.target.value)
                  setRows((now) =>
                    (now ?? []).map((one, at) => (at === index ? { ...one, mid } : one))
                  )
                }}
              />
              <span className="min-w-32 text-sm font-medium">{row.query}</span>
              {row.candidates.length === 0 ? (
                <span className="text-sm text-amber-700 dark:text-amber-500">
                  맞는 문헌 재료가 없습니다 — 이 줄은 덱에서 빠집니다.
                </span>
              ) : (
                <select
                  aria-label={`${row.query} 의 문헌 재료`}
                  className="border-input bg-background h-9 min-w-72 rounded-md border px-2 text-sm"
                  value={row.choice ?? ''}
                  onChange={(event) => {
                    const choice = event.target.value || null
                    setRows((now) =>
                      (now ?? []).map((one, at) => (at === index ? { ...one, choice } : one))
                    )
                  }}
                >
                  {row.candidates.map((one) => (
                    <option key={one.id} value={String(one.id)}>
                      {one.name} · 물성 {one.value_count}
                      {one.score === 3 ? ' · 정확' : one.score === 2 ? ' · 앞부분' : ''}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ))}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <select
              aria-label="덱 형식"
              className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              value={format}
              onChange={(event) => setPicked(event.target.value)}
            >
              {(formats.data ?? []).map((one) => (
                <option key={one.key} value={one.key}>
                  {one.label}
                </option>
              ))}
            </select>
            <select
              aria-label="단위계"
              className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              value={system?.key ?? ''}
              onChange={(event) => setUnits(event.target.value)}
            >
              {(systems.data ?? []).map((one) => (
                <option key={one.key} value={one.key}>
                  {one.label}
                </option>
              ))}
            </select>
            <Button
              onClick={() => void build()}
              disabled={busy || rows.every((row) => !row.choice)}
            >
              <FileCode2 className="size-4" />덱 생성
            </Button>
            {unmatched.length > 0 && (
              <span className="text-muted-foreground text-xs">
                매칭 안 된 {unmatched.length}줄은 빠집니다.
              </span>
            )}
          </div>
        </section>
      )}

      {built && (
        <section className="space-y-2 rounded-md border p-3">
          <p className="text-sm font-semibold">
            ③ 덱 — 재료 {built.material_count}종
            <span className="text-muted-foreground ml-2 text-xs font-normal">
              {built.filename}
            </span>
          </p>
          {built.skipped.length > 0 && (
            <div className="rounded-md border border-amber-500 px-3 py-2 text-sm">
              <p className="font-medium text-amber-700 dark:text-amber-500">
                물성이 모자라 덱에 못 실은 재료 {built.skipped.length}건
              </p>
              {built.skipped.map((one) => (
                <p key={one.mid} className="text-muted-foreground text-xs">
                  MID {one.mid} · {one.name} — 없는 것: {one.missing.join(', ')}
                </p>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                // **`navigator.clipboard` 를 바로 부르지 않는다**(2026-10-04). 사내 http 주소에서는
                // 그 객체가 없어 TypeError 가 났고, 거절돼도 「복사됨」 이 떴다.
                const ok = await copyText(built.text)
                setCopied(ok ? 'yes' : 'no')
                if (ok) setTimeout(() => setCopied(null), 1600)
              }}
            >
              {copied === 'yes' ? <Check className="size-4" /> : <Copy className="size-4" />}
              {copied === 'yes' ? '복사됨' : '복사'}
            </Button>
            <Button variant="outline" size="sm" onClick={download}>
              <Download className="size-4" />
              다운로드
            </Button>
            {copied === 'no' && (
              <span role="status" className="text-destructive self-center text-xs">
                브라우저가 복사를 막았습니다 — 아래 글을 직접 골라 복사하거나 다운로드하세요.
              </span>
            )}
          </div>
          <pre className="bg-muted/40 max-h-[480px] overflow-auto rounded-md border p-3 text-xs">
            {built.text}
          </pre>
          {built.notes.length > 0 && (
            <ul className="text-muted-foreground list-disc pl-5 text-xs">
              {built.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
