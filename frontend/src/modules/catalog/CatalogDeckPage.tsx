/**
 * 카탈로그 → LS-DYNA 덱 — **BOM 붙여넣기 3단계** (MaterialTwin 이식 2단계).
 *
 *   ① 붙여넣기      `MID, 재료명` 또는 `재료명` 줄들
 *   ② 매칭 확인     줄마다 후보 중 하나를 사람이 고른다 (적합도·물성 수 표시)
 *   ③ 덱           미리보기 · 복사 · 내려받기 — 값마다 출처 각주가 $ 주석으로
 *
 * 카탈로그 재료는 스칼라뿐이라 낼 수 있는 것은 탄성·열물성 덱이다. 곡선이
 * 필요한 덱(*MAT_024)은 시험→카드 경로에서 나온다. 모자란 재료는 덱에서
 * 조용히 빠지지 않고 「무엇이 없는지」 와 함께 아래에 선다.
 */

import { Check, Copy, Download, FileCode2 } from 'lucide-react'
import { useState } from 'react'

import { DECK_FORMATS, DECK_UNITS, catalogApi } from '@/modules/catalog/api'
import type { DeckBuilt, DeckMatchRow } from '@/modules/catalog/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Textarea } from '@/shared/components/ui/textarea'

interface Row {
  query: string
  mid: number
  choice: string | null
  candidates: DeckMatchRow['candidates']
}

export default function CatalogDeckPage() {
  const [text, setText] = useState('')
  const [rows, setRows] = useState<Row[] | null>(null)
  const [format, setFormat] = useState<string>(DECK_FORMATS[0].key)
  const [units, setUnits] = useState<string>(DECK_UNITS[0].key)
  const [built, setBuilt] = useState<DeckBuilt | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [copied, setCopied] = useState(false)

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
      setBuilt(await catalogApi.deckBuild({ items, format, units }))
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('덱을 만들지 못했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  function download() {
    if (!built) return
    const blob = new Blob([built.text], { type: 'text/plain;charset=utf-8' })
    const anchor = document.createElement('a')
    anchor.href = URL.createObjectURL(blob)
    anchor.download = built.filename
    anchor.click()
    URL.revokeObjectURL(anchor.href)
  }

  const unmatched = (rows ?? []).filter((row) => !row.choice)

  return (
    <div className="space-y-4">
      <PageHeader
        title="문헌 덱 만들기"
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
              onChange={(event) => setFormat(event.target.value)}
            >
              {DECK_FORMATS.map((one) => (
                <option key={one.key} value={one.key}>
                  {one.label}
                </option>
              ))}
            </select>
            <select
              aria-label="단위계"
              className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              value={units}
              onChange={(event) => setUnits(event.target.value)}
            >
              {DECK_UNITS.map((one) => (
                <option key={one.key} value={one.key}>
                  {one.label}
                </option>
              ))}
            </select>
            <Button
              onClick={() => void build()}
              disabled={busy || rows.every((row) => !row.choice)}
            >
              <FileCode2 className="size-4" />덱 만들기
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
              onClick={() => {
                void navigator.clipboard.writeText(built.text)
                setCopied(true)
                setTimeout(() => setCopied(false), 1600)
              }}
            >
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
              {copied ? '복사됨' : '복사'}
            </Button>
            <Button variant="outline" size="sm" onClick={download}>
              <Download className="size-4" />
              내려받기
            </Button>
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
