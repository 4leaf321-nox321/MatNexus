/**
 * 물성 표 위의 한 줄 — **이 재료에서 아직 안 겹친 DMA 가 몇인가.**
 *
 * 사람이 물성을 채우려고 있는 곳은 재료 화면이다. 점탄성은 시험 상세의 다른 탭에서
 * 만들어지고 「결과」 를 거치지 않아서, 그 사실을 아무도 말해 주지 않으면 통째로
 * 건너뛴 채 「물성이 왜 비지」 를 묻게 된다. 글로벌 피팅 모달의 「후보가 왜 이것
 * 뿐인가」 에도 같은 문장이 답이 된다.
 *
 * **아무것도 없으면 아무 말도 안 한다.** 인장만 있는 재료에 DMA 이야기를 띄우면
 * 그 줄은 소음이고, 소음이 한 번 생기면 사람은 그 자리를 다시 안 읽는다.
 */

import { groupsApi } from '@/modules/materials/api.groups'
import { masterCurveGap } from '@/modules/materials/masterCurveGap'
import { testsApi } from '@/modules/tests/api'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

export function MasterCurveNotice({
  materialId,
  onGoToTests,
}: {
  materialId: string
  /** 시료·시편 탭으로 데려간다. 말만 하고 찾아가게 두지 않는다. */
  onGoToTests?: () => void
}) {
  // **쓸 수 있는 시험종류는 서버가 푼다.** 선언에 적힌 키만 보면 부서가 만든
  // DMA 종류가 빠진다(`registry.fits`).
  const kinds = useResource(() => groupsApi.kinds(), [])
  const runs = useResource(
    () => testsApi.runs({ material_id: materialId, status: 'parsed', limit: 200 }),
    [materialId]
  )

  const keys = [...new Set((kinds.data ?? []).flatMap((one) => one.applies_to))]
  const gap = masterCurveGap(runs.data?.items ?? [], keys)
  if (gap.ready + gap.pending + gap.unknown === 0) return null

  return (
    <p
      className="text-muted-foreground mb-2 flex flex-wrap items-center gap-x-1.5 text-xs"
      aria-label="마스터커브 현황"
    >
      <span>
        마스터커브가 있는 시험 <b>{gap.ready}건</b>
        {gap.pending > 0 && (
          <>
            {' · '}
            겹칠 수 있는데 아직 안 만든 시험 <b>{gap.pending}건</b>
          </>
        )}
        {/* **못 하는 것은 남은 일이 아니다.** 변형률 스윕은 온도가 한 단이라
            겹칠 것이 없다 — 세지 않되, 왜 목록보다 적은지는 말해 준다. */}
        {gap.cannot > 0 && (
          <span className="opacity-70">
            {' '}
            (온도가 한 단이라 겹칠 수 없는 시험 {gap.cannot}건은 뺐습니다)
          </span>
        )}
        {gap.unknown > 0 && (
          <span className="opacity-70"> · 온도 단 수를 아직 안 센 시험 {gap.unknown}건</span>
        )}
      </span>
      {gap.pending > 0 && onGoToTests && (
        <Button variant="link" className="h-auto p-0 text-xs" onClick={onGoToTests}>
          그 시험 보기
        </Button>
      )}
    </p>
  )
}
