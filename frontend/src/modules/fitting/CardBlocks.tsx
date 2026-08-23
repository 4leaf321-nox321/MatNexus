/**
 * 물성 카드의 내용 — **선언만으로 그린다.**
 *
 * 전에는 이 화면이 `elastic.youngs_modulus`·`hardening.relative_rmse` 를 이름으로
 * 알고 있었다. 점탄성을 더하려면 여기에도 갈래를 하나 더 넣어야 했고, 초탄성이면
 * 또 하나였다 — 폴리머 점탄성에서 D7 이 못 미친 45%(저장·API·화면) 중 화면 몫이
 * 정확히 이것이다.
 *
 * 지금은 `GET /fitting/blocks` 가 준 선언으로 그린다. **이 파일은 물성의 이름을
 * 하나도 모른다.** 새 물성이 붙어도 여기는 안 고친다.
 *
 * ## 표는 접는다
 *
 * 소성 표 하나가 수천 점이다. 다 그리면 카드 목록이 못 쓰게 된다. 대신 **몇 행을
 * 감췄는지 말한다** — 조용히 자르면 그것이 전부인 줄 안다.
 */

import type { BlockSpec, Produced, PropertyCard } from '@/modules/fitting/api'
import { Badge } from '@/shared/components/ui/badge'
import { formatScalar } from '@/shared/units'

/** 표를 이만큼만 편다. 나머지는 몇 행인지 말한다. */
const ROW_LIMIT = 6

/**
 * 값이 어디서 왔는가. **7850 이 실측인지 관례값인지 화면만 봐서는 모른다.**
 *
 * 규약은 `<키>_source` 다(`matcore.cards` 참조) — 새 블록이 저절로 따라온다.
 */
const SOURCE_LABELS: Record<string, string> = {
  measured: '실측',
  sample: '시료 실측',
  material: '재료 공칭',
  manual: '직접 입력',
  prony: 'Prony 적합',
}

function cell(value: unknown, siUnit: string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return formatScalar(value, siUnit)
  if (typeof value === 'boolean') return value ? '예' : '아니오'
  return String(value)
}

function Values({ spec, values }: { spec: BlockSpec; values: Record<string, unknown> }) {
  const shown = spec.produces.filter((one) => values[one.key] !== undefined)
  if (shown.length === 0) return null
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
      {shown.map((one) => {
        const origin = SOURCE_LABELS[String(values[`${one.key}_source`] ?? '')]
        return (
          <div key={one.key}>
            <dt className="text-muted-foreground text-xs" title={one.help ?? undefined}>
              {one.label}
            </dt>
            <dd className="tabular-nums">
              {cell(values[one.key], one.si_unit)}
              {/* **값과 함께 출처를 보인다.** 나중에 "이 물성 어디서 났나" 를
                  묻는 자리에서 그 오해가 제일 비싸다. */}
              {origin && (
                <span className="text-muted-foreground ml-1 text-xs">({origin})</span>
              )}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}

function Rows({ columns, rows }: { columns: Produced[]; rows: Record<string, unknown>[] }) {
  if (rows.length === 0) return null
  const shown = rows.slice(0, ROW_LIMIT)
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="text-xs">
        <thead>
          <tr className="text-muted-foreground">
            {columns.map((one) => (
              <th key={one.key} className="pr-4 pb-0.5 text-left font-normal">
                {one.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, index) => (
            <tr key={index} className="border-t">
              {columns.map((one) => (
                <td key={one.key} className="py-0.5 pr-4 tabular-nums">
                  {/* **행이 자기 단위를 들면 그것이 이긴다** — 경화식 파라미터는
                      식마다 단위가 다르다. */}
                  {cell(row[one.key], (row.si_unit as string | undefined) ?? one.si_unit)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > shown.length && (
        <p className="text-muted-foreground mt-1 text-xs">
          …그 아래 {rows.length - shown.length}행은 접었습니다. 내보내면 전부 나갑니다.
        </p>
      )}
    </div>
  )
}

export function CardBlocks({ specs, card }: { specs: BlockSpec[]; card: PropertyCard }) {
  const blocks = (card.blocks ?? {}) as Record<string, Record<string, unknown>>
  const present = specs.filter((spec) => blocks[spec.key])

  return (
    <div className="mt-2 space-y-3">
      {/* **없던 일로 하지 않는다.** 이 카드를 만든 계산이 지금 코드에 없다. */}
      {card.problem && (
        <p className="text-amber-700 text-xs dark:text-amber-500">{card.problem}</p>
      )}

      {present.map((spec) => {
        const payload = blocks[spec.key]
        const values = (payload.values ?? {}) as Record<string, unknown>
        const rows = (payload.rows ?? []) as Record<string, unknown>[]
        const notes = (payload.notes ?? []) as string[]
        return (
          <section key={spec.key}>
            <div className="mb-1 flex items-center gap-1.5">
              <h4 className="text-sm font-medium" title={spec.help}>
                {spec.label}
              </h4>
              {/* **실리지 않는다고 쓸모없는 것이 아니라 실리는 자리가 다르다** —
                  경화식은 표로 나가고 식은 덱 주석에 남는다. */}
              {!spec.in_deck && (
                <Badge variant="outline" className="text-xs">
                  덱에 안 실림
                </Badge>
              )}
            </div>
            <Values spec={spec} values={values} />
            <Rows columns={spec.rows} rows={rows} />
            {notes.map((note, index) => (
              <p key={index} className="text-muted-foreground mt-1 text-xs">
                {note}
              </p>
            ))}
          </section>
        )
      })}
    </div>
  )
}
