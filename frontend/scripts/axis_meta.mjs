#!/usr/bin/env node
/**
 * 문헌 조건 칸 목록(정본) → 화면의 축 이름표(`src/modules/catalog/axisMeta.ts`).
 *
 *   node scripts/axis_meta.mjs                       (frontend 에서)
 *   node scripts/axis_meta.mjs <씨앗 json> <만들 ts>
 *
 * 전에는 화면에 축 이름 · 단위 표(`AXIS_META`)를 손으로 따로 두어, 서버 목록에 ΔK 를 더해도 화면은 키
 * 이름(`delta_k_pa_sqrt_m (delta_k_pa_sqrt_m)`)을 그대로 보였다(2026-10-26). 이제 씨앗 하나만 고치고 이것을
 * 돌린다 — CI 가 만든 파일이 씨앗과 다르면 멈춘다(가이드 씨앗과 같은 자리).
 *
 * 단위는 화면 단위 표(`shared/units.ts`)의 키로 옮긴다 — `Pa·m^0.5` → `Pa.m0.5`, 무차원 `1` 은 없음.
 */

import { readFileSync, writeFileSync } from 'node:fs'

const [, , source = '../backend/seeds/catalog/condition-fields.json', target = 'src/modules/catalog/axisMeta.ts'] =
  process.argv

/** 씨앗의 단위 → 화면 단위 표의 키. */
function displayKey(unit) {
  if (!unit || unit === '1') return null
  return unit.replaceAll('·', '.').replaceAll('^', '')
}

const fields = JSON.parse(readFileSync(source, 'utf8'))
const meta = fields.map((one) => `  ${JSON.stringify(one.key)}: [${JSON.stringify(one.label)}, ${JSON.stringify(displayKey(one.unit))}],`)
const logs = fields.filter((one) => one.scale === 'log').map((one) => `  ${JSON.stringify(one.key)},`)

const text = `/**
 * 축 이름표 — **만든 파일이다. 손으로 고치지 않는다.**
 *
 * 정본은 \`backend/seeds/catalog/condition-fields.json\`(문헌 조건 칸 목록, ADR 0071)이다. 씨앗을 고치고
 * frontend 에서 \`node scripts/axis_meta.mjs\` 로 다시 만든다 — CI 가 어긋남을 막는다.
 *
 * 키 → [이름, 저장 단위(화면 단위 표의 키)]. 표시는 \`shared/units\` 가 정한다(K → °C).
 */

export const AXIS_META: Record<string, [string, string | null]> = {
${meta.join('\n')}
}

/** 자릿수로 펼쳐 보는 축 — 씨앗의 \`"scale": "log"\`. */
export const LOG_AXES = new Set<string>([
${logs.join('\n')}
])
`

writeFileSync(target, text, 'utf8')
console.log(`${target}: 축 ${fields.length}개 · 로그 축 ${logs.length}개`)
