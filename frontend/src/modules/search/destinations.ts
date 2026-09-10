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
    case 'guide_document':
      return { href: `/guide/${hit.id}`, approximate: true }
    // 핸드북 절은 문서 키·절 키로 열린다(`/guide/:documentKey/:sectionKey`). 검색이
    // 든 것은 UUID 라 그대로는 못 연다 — 목록에서 찾게 보낸다. 문서 키까지 실어
    // 오게 하려면 서버가 절마다 문서를 한 번 더 읽어야 해서, 값에 비해 비싸다.
    case 'guide_section':
      return { href: '/guide', approximate: true }

    // 품은 것으로 데려간다 — 제 화면이 없다. **다만 그 자리까지 데려간다.**
    // 재료 화면에 떨어뜨려 놓기만 하면 사람은 시료를 하나씩 열어 그 시편을
    // 눈으로 찾아야 했다(2026-09-11 지적).
    case 'sample':
      return hit.parent_id
        ? { href: `/materials/${hit.parent_id}?tab=samples&sample=${hit.id}` }
        : { href: '/specimens', approximate: true }
    // 시편은 시료를 한 번 더 거쳐야 자리가 정해진다 — 검색이 든 것은 재료뿐이라
    // 그 문(`/specimens/:id`)이 한 번 읽어 자리를 찾아 준다.
    case 'specimen':
      return { href: `/specimens/${hit.id}` }
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
  // 3단계 — 글자는 안 겹치는데 뜻이 가깝다. **이 표시가 없으면 엉뚱한 결과로 읽힌다.**
  meaning: '뜻이 가까움',
  both: '글자·뜻 둘 다',
}
