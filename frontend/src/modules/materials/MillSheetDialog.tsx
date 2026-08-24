/**
 * 밀시트 — **적은 값과 잰 값을 한 자리에**(ADR 0016).
 *
 * 밀시트는 「이 로트가 규격에 맞나」를 증명하는 문서지 물리 상수표가 아니다
 * (EN 10204 3.1). 그래서 거기 실린 값은 **재료가 아니라 시료에** 붙는다 —
 * 재료에 적으면 첫 로트의 값이 그 Grade 전체의 값이 되고, 두 번째 로트가
 * 들어오는 순간 둘 중 하나가 조용히 진다.
 *
 * ## 왜 편집과 대조가 같은 창인가
 *
 * 값을 적어 두기만 하면 기록으로 끝난다. 그런데 **같은 물성을 우리 처리 결과가
 * 낸다** — `proof_stress`·`tensile_strength` 가 밀시트의 항복강도·인장강도와
 * 같은 값이다. 그 둘을 다른 화면에 두면 "밀시트가 맞았나" 를 아무도 안 묻게
 * 된다.
 *
 * ## 판정하지 않는다
 *
 * 차이를 비율로 보일 뿐 「맞다/틀리다」를 말하지 않는다. 몇 %부터 문제인지는
 * 규격과 용도가 정하고, 그것을 화면에 상수로 박으면 **그 숫자가 곧 규격 행세를
 * 한다.**
 */

import { FileCheck2 } from 'lucide-react'

import { DeclaredPropertiesCard } from '@/modules/materials/DeclaredPropertiesCard'
import { materialsApi } from '@/modules/materials/api'
import type { Sample } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

export function MillSheetDialog({
  sample,
  open,
  onClose,
  onSaved,
}: {
  sample: Sample
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  // 값을 고치면 대조도 다시 읽는다 — 방금 적은 값이 아래 표에 없으면 두 칸이
  // 서로 다른 이야기를 한다.
  const check = useResource(
    () =>
      open
        ? materialsApi.millCheck(sample.id)
        : Promise.resolve(null),
    [sample.id, open, sample.declared_properties]
  )
  const rows = check.data?.rows ?? []

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileCheck2 className="size-4" />
            밀시트 — {sample.record_name}
          </DialogTitle>
          <DialogDescription>
            <b>이 로트의 값</b>입니다. Grade 가 같으면 같은 값(탄성계수·열물성)은 재료의{' '}
            <b>물성</b> 탭에 적습니다.
          </DialogDescription>
        </DialogHeader>

        <DeclaredPropertiesCard
          level="시료"
          title="밀시트가 준 값"
          hint={
            <>
              <b>로트마다 다른 값</b>입니다 — 항복강도·인장강도·연신율. 같은 물성을 우리
              시험도 재므로, 아래에서 <b>밀시트가 말한 값과 우리가 잰 값</b>을 견줍니다.
            </>
          }
          rows={sample.declared_properties}
          onSave={async (next) => {
            await materialsApi.updateSample(sample.id, { declared_properties: next })
            onSaved()
          }}
        />

        <ErrorNotice error={check.error} />

        {rows.length > 0 && (
          <section className="rounded-md border p-4">
            <h3 className="mb-1 text-sm font-medium">우리가 잰 값과 견주기</h3>
            <p className="text-muted-foreground mb-3 text-xs">
              채택된 처리 결과만 셉니다. <b>맞다·틀리다를 말하지 않습니다</b> — 몇 %부터
              문제인지는 규격과 용도가 정합니다.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground text-left text-xs">
                    <th className="pr-4 pb-1 font-normal">항목</th>
                    <th className="pr-4 pb-1 font-normal">밀시트</th>
                    <th className="pr-4 pb-1 font-normal">우리가 잰 값</th>
                    <th className="pr-4 pb-1 font-normal">차이</th>
                    <th className="pb-1 font-normal">근거 문서</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.item} className="border-t align-top">
                      <td className="py-1 pr-4">{row.label}</td>
                      <td className="py-1 pr-4 tabular-nums">
                        {formatScalar(row.declared, row.si_unit)}
                      </td>
                      <td className="py-1 pr-4 tabular-nums">
                        {row.measured === null || row.measured === undefined ? (
                          // **조용히 빼지 않는다.** 줄이 비면 사람은 잰 값이 0
                          // 이라고 읽거나, 적은 값이 사라진 줄 안다.
                          <span className="text-muted-foreground text-xs">{row.note}</span>
                        ) : (
                          <>
                            {formatScalar(row.measured, row.si_unit)}
                            <span className="text-muted-foreground ml-1 text-xs">
                              n={row.measured_count}
                            </span>
                          </>
                        )}
                      </td>
                      <td className="py-1 pr-4 tabular-nums">
                        {row.difference == null
                          ? '—'
                          : `${row.difference > 0 ? '+' : ''}${(row.difference * 100).toFixed(1)}%`}
                      </td>
                      <td className="text-muted-foreground py-1 text-xs">{row.reference}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </DialogContent>
    </Dialog>
  )
}
