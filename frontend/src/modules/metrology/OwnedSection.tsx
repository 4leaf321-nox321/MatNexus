/**
 * 「이 물성을 잴 우리 장비」 — **서버가 TestScope 에 그때 묻는다**(보유 장비 · 교정의 정본, ADR 0069).
 *
 * 측정 지도와 따로 읽는다. TestScope 가 느리거나 꺼져 있어도 위의 기법 · 장비 모델 표는 바로 선다.
 *
 * ## 「모름」 과 「없음」 을 같은 얼굴로 두지 않는다
 *
 * TestScope 에 그 물성의 시험 항목 연결이 없으면 장비가 0 으로 온다. 그것을 「없음」 으로 보이면 사람은
 * 「우리는 못 잰다」 로 읽는다. 상태(`unlinked` · `none` …)가 먼저고, 문장은 서버가 정한다.
 */

import { metrologyApi } from '@/modules/metrology/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { useResource } from '@/shared/hooks/useResource'

const dash = <span className="text-muted-foreground">—</span>

function overdue(day: string | null | undefined): boolean {
  return Boolean(day) && new Date(`${day}T23:59:59`) < new Date()
}

export function OwnedSection({ propertyKey }: { propertyKey: string }) {
  const owned = useResource(() => metrologyApi.owned(propertyKey), [propertyKey])
  const data = owned.data

  return (
    <section aria-label="우리 장비" className="rounded-md border">
      <div className="flex items-baseline justify-between gap-2 border-b p-2 text-sm font-medium">
        <span>우리 장비 (TestScope)</span>
        {data?.link && (
          <a
            href={data.link}
            target="_blank"
            rel="noreferrer"
            className="text-primary text-xs font-normal underline-offset-2 hover:underline"
          >
            TestScope 열기
          </a>
        )}
      </div>
      <ErrorNotice error={owned.error} />
      {owned.loading && !data && (
        <p className="text-muted-foreground p-2 text-sm">TestScope 에 묻는 중…</p>
      )}
      {data && data.state !== 'found' && (
        <p
          className={`p-2 text-sm ${data.state === 'none' ? '' : 'text-muted-foreground'}`}
          role="status"
        >
          {data.message}
        </p>
      )}
      {data?.suggested && (
        <p className="p-2 text-xs text-amber-700">
          이 물성과 시험 항목의 연결 일부가 TestScope 에서 아직 사람이 확인하지 않은 기계 제안입니다.
        </p>
      )}
      {data && data.state === 'found' && (
        <div className="overflow-x-auto">
          <p className="text-muted-foreground px-2 pt-2 text-xs">{data.message}</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted-foreground border-b text-left text-xs">
                <th className="p-2">장비</th>
                <th className="p-2">자산번호</th>
                <th className="p-2">부서</th>
                <th className="p-2">위치</th>
                <th className="p-2">담당</th>
                <th className="p-2">시험 항목</th>
                <th className="p-2">교정 만료</th>
              </tr>
            </thead>
            <tbody>
              {data.equipment.map((one) => (
                <tr key={one.equipment_id} className="border-b last:border-b-0">
                  <td className="p-2">
                    <a
                      href={one.link}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {one.name}
                    </a>
                  </td>
                  <td className="p-2 tabular-nums">{one.asset_no || dash}</td>
                  <td className="p-2">{one.workspace ?? dash}</td>
                  <td className="p-2">
                    {[one.site, one.location].filter(Boolean).join(' · ') || dash}
                  </td>
                  <td className="p-2">{one.contact ?? dash}</td>
                  <td className="p-2">{one.test_item}</td>
                  <td className="p-2 tabular-nums">
                    {one.calibration_due_on ? (
                      <span className={overdue(one.calibration_due_on) ? 'text-red-600' : ''}>
                        {one.calibration_due_on}
                        {overdue(one.calibration_due_on) && ' (지남)'}
                      </span>
                    ) : (
                      dash
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(data.equipment_total ?? 0) > data.equipment.length && (
            <p className="text-muted-foreground p-2 text-xs">
              외 {(data.equipment_total ?? 0) - data.equipment.length}대 —{' '}
              {data.link ? (
                <a
                  href={data.link}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline-offset-2 hover:underline"
                >
                  TestScope 에서 전체 보기
                </a>
              ) : (
                'TestScope 에서 전체 보기'
              )}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
