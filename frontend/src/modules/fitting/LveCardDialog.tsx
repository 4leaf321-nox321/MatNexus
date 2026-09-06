/**
 * 선형탄성구간(LVE) 카드 대화상자 — CAE 카드 탭의 「새 카드 만들기」 가 띄운다.
 *
 * 한때 물성 탭에도 이 단추가 있었다. 카드를 만드는 자리가 둘이 되니 「어디서 만드나」
 * 가 둘이 됐다 — CAE 카드 탭 한 곳으로 모았다(2026-09-05).
 */

import { useMemo } from 'react'

import { CardFromDialog } from '@/modules/fitting/CardFromDialog'
import { fittingApi } from '@/modules/fitting/api'
import type { PropertyCard } from '@/modules/fitting/api'
import type { components } from '@/shared/api/schema'
import { Badge } from '@/shared/components/ui/badge'
import { useResource } from '@/shared/hooks/useResource'
import { formatScalar } from '@/shared/units'

type StatisticsGroup = components['schemas']['GroupOut']

export function LveCardDialog({
  materialId,
  group,
  onClose,
  onDone,
}: {
  materialId: string
  group: StatisticsGroup
  onClose: () => void
  onDone: (card: PropertyCard) => void
}) {
  const statOf = (key: string) => group.scalars.find((one) => one.key === key)

  // **함께 실리는 것을 보여 준다.** 「재료 기본 정보 함께 싣기」 를 켜면 무엇이 따라오는지
  // 모른 채 켜게 하지 않는다. 열물성이 어느 값인지는 블록 선언이 안다 — 화면이 키를
  // 적어 두면 새 항목이 붙어도 여기는 모른다.
  const declared = useResource(() => fittingApi.declaredPreview(materialId), [materialId])
  const specs = useResource(() => fittingApi.blocks(), [])
  const carried = useMemo(() => {
    if (!specs.data || !declared.data) return null // 아직 읽는 중
    const thermal = specs.data.find((spec) => spec.key === 'thermal')
    if (!thermal) return []
    const unitOf = new Map(thermal.produces.map((one) => [one.key, one.si_unit]))
    return declared.data.values
      .filter((row) => unitOf.has(row.key) && row.value != null)
      .map((row) => ({
        key: row.key,
        label: row.label,
        text: formatScalar(row.value ?? 0, unitOf.get(row.key) ?? null),
      }))
  }, [specs.data, declared.data])

  return (
    <CardFromDialog
      materialId={materialId}
      title="선형탄성구간(LVE) 카드 만들기"
      description={
        <>
          DMA 변형률 스윕의 <b>선형 구간 저장 탄성률 E′</b> 와 <b>선형 한계 변형률</b>이
          실립니다. 소변형·진동 해석의 탄성계수이고, 한계 변형률 너머에서는 유효하지
          않습니다 — 덱 주석에 그 범위가 적힙니다.
        </>
      }
      preview={
        <ul className="space-y-0.5">
          {(['youngs_modulus', 'lve_strain_limit'] as const).map((key) => {
            const row = statOf(key)
            return row ? (
              <li key={key}>
                {row.label}: {formatScalar(row.mean, row.si_unit, row.dimension)}
                {row.count > 1 && ` (시편 ${row.count}건 평균)`}
              </li>
            ) : null
          })}
          <li>
            {group.test_type_label} · {group.orientation} · 채택 {group.sample_count}건
          </li>
        </ul>
      }
      suggestedLabel={`${group.test_type_label} 선형탄성구간(LVE) · ${group.orientation}`}
      declaredOption={{
        label: '재료 기본 정보 함께 싣기',
        help: '재료에 적어 둔 열팽창계수·열전도도·비열이 열물성 블록으로 따라옵니다. 저장 탄성률은 잰 값 그대로입니다.',
        carried:
          carried === null ? null : carried.length > 0 ? (
            <span className="flex flex-wrap items-center gap-1">
              <span className="text-muted-foreground">함께 실리는 것</span>
              {/* 한 줄 글이 아니라 값마다 표 하나 — 카드 목록의 요약 칩과 같은 모양이다. */}
              {carried.map((one) => (
                <Badge key={one.key} variant="secondary" className="gap-1 font-normal">
                  <span className="text-muted-foreground">{one.label}</span>
                  <span className="font-medium tabular-nums">{one.text}</span>
                </Badge>
              ))}
            </span>
          ) : (
            <span className="text-amber-700 dark:text-amber-500">
              재료에 적어 둔 열물성이 없어 함께 실릴 것이 없습니다 — 물성 탭에서 적어 두면
              따라옵니다.
            </span>
          ),
      }}
      onSubmit={(values) =>
        fittingApi.createLveCard({
          material_id: materialId,
          test_type_key: group.test_type_key,
          orientation: group.orientation,
          ...values,
          include_declared: values.include_declared ?? false,
        })
      }
      onClose={onClose}
      onDone={onDone}
    />
  )
}
