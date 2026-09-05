/**
 * 커버리지 격자 — **이 카탈로그가 어디에 두껍고 어디가 비었나.**
 *
 * 계통(스마트폰 부품) × 물성 도메인의 값 수. 진하게 칠해진 곳이 두꺼운 곳이고,
 * 빈 칸은 빈 칸으로 보인다 — 찾다가 없어서 아는 것보다 낫다. 칸을 누르면 그
 * 계통의 재료 목록으로 간다.
 */

import { Link } from 'react-router-dom'

import { DOMAIN_LABELS, catalogApi } from '@/modules/catalog/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { useResource } from '@/shared/hooks/useResource'

export default function CatalogCoveragePage() {
  const grid = useResource(() => catalogApi.coverage(), [])
  const data = grid.data
  const top = data
    ? Math.max(
        1,
        ...Object.values(data.cells).flatMap((row) => Object.values(row))
      )
    : 1

  return (
    <div className="space-y-4">
      <PageHeader
        title="카탈로그 커버리지"
        description="부품 계통별로 어느 물성 도메인의 값이 얼마나 있는지를 셉니다. 빈 칸은 카탈로그에 그 조합의 값이 없다는 뜻입니다."
      />
      <ErrorNotice error={grid.error} />

      {data && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="bg-background sticky left-0 p-2 text-left">계통</th>
                {data.domains.map((domain) => (
                  <th key={domain} className="min-w-16 p-2 text-right font-medium">
                    {DOMAIN_LABELS[domain] ?? domain}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.subsystems.map((subsystem) => (
                <tr key={subsystem || '_none'} className="border-b last:border-b-0">
                  <td className="bg-background sticky left-0 p-2">
                    <Link
                      className="hover:underline"
                      to={`/catalog?subsystem=${encodeURIComponent(subsystem)}`}
                    >
                      {subsystem === '' ? '미분류' : subsystem}
                    </Link>
                  </td>
                  {data.domains.map((domain) => {
                    const count = data.cells[subsystem]?.[domain]
                    // 로그 눈금 — 값 수가 자릿수로 갈려서 선형이면 큰 칸만 보인다.
                    const weight = count ? Math.log10(count + 1) / Math.log10(top + 1) : 0
                    return (
                      <td
                        key={domain}
                        className="p-2 text-right tabular-nums"
                        style={{
                          background: count
                            ? `color-mix(in srgb, var(--primary) ${Math.round(weight * 45)}%, transparent)`
                            : undefined,
                        }}
                      >
                        {count ?? <span className="text-muted-foreground">—</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
