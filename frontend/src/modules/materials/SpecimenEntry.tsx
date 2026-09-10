/**
 * 시편 하나로 들어가는 문 — **시편에는 제 화면이 없다.**
 *
 * 시편은 재료 상세의 「시료·시편」 탭 안에 산다. 그래서 검색 결과에서 시편을
 * 눌러도 갈 데가 없었다 — 재료 화면으로만 보내고 나면, 사람은 시료를 하나씩
 * 열어 그 시편을 눈으로 찾아야 했다(2026-09-11 지적: *"시편을 선택해서 들어갈
 * 수 없다"*).
 *
 * ## 왜 주소를 하나 두는가
 *
 * 그 시편을 **가리키는 말**이 필요하다. 재료·시료 식별자를 아는 쪽(시편 목록)은
 * 완성된 주소로 바로 가면 되지만, 검색 결과가 든 것은 시편 식별자 하나뿐이다.
 * 그 하나로 갈 수 있는 주소가 없으면 「시편으로 가라」 를 아무도 못 적는다 —
 * 링크를 남에게 보낼 수도 없다.
 *
 * 여기서 한 번 읽어 재료·시료를 알아낸 다음 그 자리로 **바꿔 준다**(`replace`).
 * 뒤로 가기가 이 문으로 되돌아오면 다시 같은 곳으로 튕겨, 사람은 뒤로 갈 수
 * 없게 된다.
 */

import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { materialsApi } from '@/modules/materials/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { useResource } from '@/shared/hooks/useResource'

/** 이 시편이 서 있는 자리. 목록처럼 식별자를 이미 아는 쪽이 그대로 쓴다. */
export function specimenHref(one: {
  id: string
  sample_id: string
  material_id: string
}): string {
  const query = new URLSearchParams({
    tab: 'samples',
    sample: one.sample_id,
    specimen: one.id,
  })
  return `/materials/${one.material_id}?${query.toString()}`
}

export default function SpecimenEntry() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const specimen = useResource(() => materialsApi.specimen(id), [id])
  const found = specimen.data

  useEffect(() => {
    if (found) navigate(specimenHref(found), { replace: true })
  }, [found, navigate])

  if (specimen.error) return <ErrorNotice error={specimen.error} className="m-4" />
  // 여는 동안은 빈 화면이다. 한 번 읽고 바로 옮겨 가므로 「불러오는 중」 을
  // 그리면 그것이 깜빡이는 것으로만 보인다.
  return null
}
