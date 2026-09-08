/**
 * 찾은 것을 **어디로 데려갈까.**
 *
 * 종류마다 갈 곳이 다르고, 몇몇은 제 화면이 아예 없다 — 시료·시편·처리결과는
 * 재료 상세와 시험 상세 안에 산다. 그래서 서버가 그 셋에는 품은 것(`parent_*`)을
 * 함께 준다.
 *
 * **이 표가 프론트에 있는 이유:** 주소는 화면의 것이다. 백엔드가 `/materials/:id`
 * 를 알면 라우트를 바꿀 때마다 서버를 함께 고쳐야 하고, 그러면 언젠가 한쪽만
 * 고쳐진 채 「눌렀는데 404」 가 된다.
 *
 * 목록으로 보내는 종류가 있다(시험법·기준정보·조직 …). 상세 화면이 없는 것들이라
 * 그 목록에서 눈으로 찾게 된다 — 완전하진 않지만 **아무 데도 못 가는 것보다 낫다.**
 */

export interface Destination {
  /** 갈 주소. `null` 이면 갈 곳이 없다(그때는 이름만 보여 준다). */
  href: string | null
  /** 목록으로만 데려가는가 — 화면에 「목록에서 찾으세요」 를 띄운다. */
  approximate?: boolean
}

export interface SearchHit {
  kind: string
  id: string
  name: string
  score: number
  matched: string
  parent_kind?: string | null
  parent_id?: string | null
}

export function destinationOf(hit: SearchHit): Destination {
  switch (hit.kind) {
    case 'material':
      return { href: `/materials/${hit.id}` }
    case 'test_run':
      return { href: `/test-runs/${hit.id}` }
    case 'catalog_material':
      return { href: `/catalog/${hit.id}` }
    case 'equipment_unit':
      return { href: `/settings/equipment/${hit.id}` }

    // 품은 것으로 데려간다 — 제 화면이 없다.
    case 'sample':
    case 'specimen':
      return hit.parent_id
        ? { href: `/materials/${hit.parent_id}` }
        : { href: '/specimens', approximate: true }
    case 'processing_result':
      return hit.parent_id
        ? { href: `/test-runs/${hit.parent_id}` }
        : { href: '/tests', approximate: true }

    // 목록까지만.
    case 'property_card':
      return { href: '/cards', approximate: true }
    case 'test_type':
      return { href: '/settings/test-types', approximate: true }
    case 'property':
      return { href: '/catalog/coverage', approximate: true }
    case 'instrument':
      return { href: '/metrology', approximate: true }
    case 'term':
      return { href: '/vocabulary', approximate: true }
    case 'workspace':
      return { href: '/admin/workspaces', approximate: true }
    default:
      return { href: null }
  }
}

/** 왜 걸렸는지를 사람 말로. 「비슷」 이 왜 떴는지 안 보이면 결과가 엉뚱해 보인다. */
export const MATCH_LABELS: Record<string, string> = {
  exact: '정확히 일치',
  prefix: '앞이 일치',
  contains: '포함',
  similar: '비슷함',
}
