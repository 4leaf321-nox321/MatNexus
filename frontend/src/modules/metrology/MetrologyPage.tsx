/**
 * 측정법 — 물성을 고르면 「무엇으로 재는가」 가 기법별로 펼쳐진다.
 *
 * 좌측 피커는 **잴 수 있는 물성(보유 장비 있음/카탈로그만)과 장비 없는 물성**을
 * 갈라 보여 준다 — 빈 칸을 숨기면 찾다가 없어서 알게 된다. `?key=` 딥링크로
 * 카탈로그 상세의 물성 행에서 바로 온다.
 */

import { useSearchParams } from 'react-router-dom'

import {
  CONFIDENCE_LABELS,
  INSTRUMENT_CATEGORY_LABELS,
  fmtRange,
  fmtTemperature,
  metrologyApi,
} from '@/modules/metrology/api'
import type { MetrologyCoverageRow, MetrologyProperty } from '@/modules/metrology/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { useResource } from '@/shared/hooks/useResource'

// catalog/api.ts 의 DOMAIN_LABELS 와 같은 표 — 모듈끼리 import 하지 않으므로 복사다.
const DOMAIN_LABELS: Record<string, string> = {
  mechanical: '기계',
  thermal: '열',
  physical: '물리',
  chemical: '화학',
  optical: '광학',
  electrical: '전기',
  interface: '계면',
  structure: '구조',
  rheological: '유변',
  magnetic: '자성',
  surface: '표면',
  acoustic: '음향',
}

const dash = <span className="text-muted-foreground">—</span>

export default function MetrologyPage() {
  const [params, setParams] = useSearchParams()
  const selectedKey = params.get('key')

  const summary = useResource(() => metrologyApi.summary(), [])
  const coverage = useResource(() => metrologyApi.coverage(), [])
  const property = useResource(
    () => (selectedKey ? metrologyApi.byProperty(selectedKey) : Promise.resolve(null)),
    [selectedKey]
  )

  const pick = (key: string) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('key', key)
      return next
    })
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="측정법"
        description="물성마다 어떤 기법·규격·장비로 재는지를 보여 줍니다. 장비 카탈로그에 있는 것과 실제 보유 장비를 구별합니다."
      />
      <ErrorNotice error={summary.error} />
      <ErrorNotice error={coverage.error} />

      {summary.data && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded-md border p-3">
            <div className="text-muted-foreground text-xs">장비 (카탈로그)</div>
            <div className="text-xl font-semibold tabular-nums">{summary.data.instruments}</div>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-muted-foreground text-xs">보유 장비</div>
            <div className="text-xl font-semibold tabular-nums">
              {summary.data.instruments_owned}
            </div>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-muted-foreground text-xs">측정 능력</div>
            <div className="text-xl font-semibold tabular-nums">{summary.data.capabilities}</div>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-muted-foreground text-xs">커버된 물성</div>
            <div className="text-xl font-semibold tabular-nums">
              {summary.data.properties_covered}
              <span className="text-muted-foreground text-sm font-normal">
                {' '}
                / {summary.data.properties_total}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_2fr]">
        <div className="space-y-3">
          {coverage.data && (
            <>
              <PropertyList
                title="잴 수 있는 물성"
                rows={coverage.data.covered}
                selectedKey={selectedKey}
                onPick={pick}
              />
              <PropertyList
                title="장비가 없는 물성"
                rows={coverage.data.gaps}
                selectedKey={selectedKey}
                onPick={pick}
                muted
              />
            </>
          )}
        </div>

        <div>
          <ErrorNotice error={property.error} />
          {!selectedKey && (
            <p className="text-muted-foreground rounded-md border p-6 text-sm">
              왼쪽에서 물성을 고르면 측정 기법과 장비가 나옵니다.
            </p>
          )}
          {property.data && <PropertyDetail detail={property.data} />}
        </div>
      </div>
    </div>
  )
}

function PropertyList({
  title,
  rows,
  selectedKey,
  onPick,
  muted,
}: {
  title: string
  rows: MetrologyCoverageRow[]
  selectedKey: string | null
  onPick: (key: string) => void
  muted?: boolean
}) {
  return (
    <div className="rounded-md border">
      <div className="border-b p-2 text-sm font-medium">
        {title} <span className="text-muted-foreground">({rows.length})</span>
      </div>
      <ul className="max-h-[40vh] overflow-y-auto">
        {rows.length === 0 && (
          <li className="text-muted-foreground p-2 text-sm">없습니다.</li>
        )}
        {rows.map((row) => (
          <li key={row.property_key}>
            <button
              type="button"
              onClick={() => onPick(row.property_key)}
              className={`hover:bg-muted/60 flex w-full items-center justify-between gap-2 p-2 text-left text-sm ${
                row.property_key === selectedKey ? 'bg-muted' : ''
              } ${muted ? 'text-muted-foreground' : ''}`}
            >
              <span>
                <span className="text-muted-foreground mr-1 text-xs">
                  {DOMAIN_LABELS[row.domain] ?? row.domain}
                </span>
                {row.name}
              </span>
              <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                {muted
                  ? `값 ${row.value_count}`
                  : `장비 ${row.instrument_count} · 보유 ${row.owned_instrument_count}`}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function PropertyDetail({ detail }: { detail: MetrologyProperty }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">
          {detail.name}
          {detail.symbol && (
            <span className="text-muted-foreground ml-2 text-sm">{detail.symbol}</span>
          )}
        </h2>
        <p className="text-muted-foreground text-sm">
          {DOMAIN_LABELS[detail.domain] ?? detail.domain}
          {detail.si_unit && detail.si_unit !== '1' ? ` · ${detail.si_unit}` : ''}
          {detail.test_standard ? ` · ${detail.test_standard}` : ''}
        </p>
      </div>

      {detail.techniques.length === 0 && (
        <p className="text-muted-foreground rounded-md border p-6 text-sm">
          이 물성을 잴 수 있는 장비가 카탈로그에 없습니다.
        </p>
      )}

      {detail.techniques.map((group) => (
        <div key={group.technique ?? '_none'} className="rounded-md border">
          <div className="border-b p-2 text-sm font-medium">
            {group.technique ?? '기법 미정'}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground border-b text-left text-xs">
                  <th className="p-2">장비</th>
                  <th className="p-2">보유</th>
                  <th className="p-2">규격</th>
                  <th className="p-2">측정 범위</th>
                  <th className="p-2">분해능</th>
                  <th className="p-2">정확도</th>
                  <th className="p-2">시편 온도</th>
                </tr>
              </thead>
              <tbody>
                {group.capabilities.map((cap) => (
                  <tr key={cap.id} className="border-b align-top last:border-b-0">
                    <td className="p-2">
                      <div>
                        {cap.instrument.vendor} {cap.instrument.model}
                        {cap.mapping_confidence && cap.mapping_confidence !== 'high' && (
                          <span
                            className="ml-1 text-amber-600"
                            title={`물성 매핑 확신도: ${CONFIDENCE_LABELS[cap.mapping_confidence] ?? cap.mapping_confidence}`}
                          >
                            ⚠
                          </span>
                        )}
                      </div>
                      <div className="text-muted-foreground text-xs">
                        {INSTRUMENT_CATEGORY_LABELS[cap.instrument.category] ??
                          cap.instrument.category}
                      </div>
                    </td>
                    <td className="p-2">
                      {cap.instrument.owned ? (
                        <span title={cap.instrument.owned_note ?? undefined}>
                          보유
                          {cap.instrument.owner_name ? ` (${cap.instrument.owner_name})` : ''}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">카탈로그만</span>
                      )}
                    </td>
                    <td className="p-2">{cap.standard ?? dash}</td>
                    <td className="p-2 tabular-nums">
                      {fmtRange(cap.range_min, cap.range_max, cap.range_unit)}
                    </td>
                    <td className="p-2 tabular-nums">{cap.resolution ?? dash}</td>
                    <td className="p-2">{cap.accuracy ?? dash}</td>
                    <td className="p-2 tabular-nums">
                      {fmtTemperature(cap.temperature_min_k, cap.temperature_max_k)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
