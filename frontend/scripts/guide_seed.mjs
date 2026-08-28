/**
 * 규격 HTML → 핸드북 씨앗(JSON).
 *
 *     node scripts/guide_seed.mjs ../규격 ../backend/seeds/guide
 *
 * 원본은 문서 하나에 `<section id="sN"><h2>…</h2>…</section>` 이 열 개다. 절마다
 * 편집기 문서(ProseMirror JSON)로 바꾼다 — **편집기가 HTML 을 읽는 그 코드**로
 * 바꾸므로(`@tiptap/html`), 화면에서 붙여 넣은 것과 같은 결과가 나온다.
 *
 * 그림(inline SVG)은 파일로 빼고 본문에는 `asset:<이름>` 자리표시를 둔다. 적재
 * 스크립트(`backend/scripts/import_guides.py`)가 올리면서 진짜 주소로 바꾼다.
 *
 * 문서마다 제 `<style>` 이 있었다 — 버린다. 서식은 앱이 한 벌로 정한다.
 */

import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { basename, join } from 'node:path'

import Image from '@tiptap/extension-image'
import { TableKit } from '@tiptap/extension-table'
import { generateJSON } from '@tiptap/html'
import StarterKit from '@tiptap/starter-kit'
import * as cheerio from 'cheerio'

const [, , sourceDir = '../규격', outDir = '../backend/seeds/guide'] = process.argv

/** 파일 이름 → 문서 키·종류·대상. **키는 바뀌지 않는다** — 앱이 이것으로 가리킨다. */
const CATALOG = {
  'astm-tensile-specimens-KR': { key: 'tensile-specimens', kind: 'specimen', topic: 'tensile' },
  'dma-specimens-KR': { key: 'dma-specimens', kind: 'specimen', topic: 'dma' },
  'compression-bending-shear-KR': { key: 'compression-bending-shear-specimens', kind: 'specimen', topic: 'compression' },
  'hardness-specimens-KR': { key: 'hardness-specimens', kind: 'specimen', topic: 'hardness' },
  'impact-specimens-KR': { key: 'impact-specimens', kind: 'specimen', topic: 'impact' },
  'adhesive-joint-specimens-KR': { key: 'adhesive-joint-specimens', kind: 'specimen', topic: 'adhesive' },
  'corrosion-specimens-KR': { key: 'corrosion-specimens', kind: 'specimen', topic: 'corrosion' },
  'electrical-residual-stress-specimens-KR': { key: 'electrical-residual-stress-specimens', kind: 'specimen', topic: 'electrical' },
  'sheet-formability-specimens-KR': { key: 'sheet-formability-specimens', kind: 'specimen', topic: 'formability' },
  'thermal-property-specimens-KR': { key: 'thermal-property-specimens', kind: 'specimen', topic: 'thermal' },
  'tensile-plasticity-guide-KR': { key: 'tensile-plasticity', kind: 'calculation', topic: 'tensile' },
  'dma-prony-viscoelasticity-guide-KR': { key: 'dma-prony', kind: 'calculation', topic: 'dma' },
  'creep-guide-KR': { key: 'creep', kind: 'calculation', topic: 'creep' },
  'fatigue-guide-KR': { key: 'fatigue', kind: 'calculation', topic: 'fatigue' },
  'fracture-guide-KR': { key: 'fracture', kind: 'calculation', topic: 'fracture' },
  'tma-thermal-expansion-guide-KR': { key: 'tma-thermal-expansion', kind: 'calculation', topic: 'tma' },
  'aging-guide-KR': { key: 'aging', kind: 'method', topic: 'aging' },
  'wear-guide-KR': { key: 'wear', kind: 'method', topic: 'wear' },
  'longlife-test-property-map-KR': { key: 'longlife-property-map', kind: 'method', topic: 'longlife' },
}

/**
 * 절 제목의 명사형 대응표 — 원본의 서술형 제목(「전극이 물성을 정한다」)을 명사형으로.
 * **키(slug)는 원래 제목에서 나온 그대로 둔다** — 주소가 바뀌면 링크가 깨진다.
 * 자리는 (문서 키, 절 순번).
 */
const TITLE_OVERRIDES = {
  'adhesive-joint-specimens': { 1: '측정 대상 — 이음과 재료의 구분', 7: '코히시브 존 모델 조립' },
  aging: { 1: '전체 파이프라인', 4: '물성 선택과 수명 판정' },
  'compression-bending-shear-specimens': { 1: '지그와 시편 형상' },
  'corrosion-specimens': {
    3: '환경 규격과 시편 형상',
    5: '입계부식 — 절차별 측정 대상',
    6: '염수분무와 실환경 환산의 한계',
    7: 'SCC — 문턱값 판정',
    8: 'CAE · 설계 연계',
  },
  creep: { 1: '전체 파이프라인', 10: '카드 검증 세 단계' },
  'dma-prony': {
    1: '전체 파이프라인',
    2: '점탄성의 기초',
    7: '마스터커브의 (g, τ) 변환',
    9: '솔버별 물성 카드 작성',
    10: '카드 검증 세 단계',
  },
  'dma-specimens': {
    1: '클램프 기준의 시편 규정',
    6: '스팬과 블랭크 길이의 구분',
    7: '클램프 치수 — 실제 한계',
  },
  'electrical-residual-stress-specimens': {
    1: '전극 배치와 물성 정의',
    3: '지수와 물성의 구분',
    4: '비파괴 E · G · ν 동시 측정',
    6: '잔류응력의 솔버 입력',
    7: '수소취화 — 감시자로서의 시편',
  },
  fatigue: {
    1: '전체 파이프라인',
    2: 'S-N 과 ε-N 의 선택',
    6: '진폭 외 요인 보정',
    7: '시편-실물 보정',
    8: '하중 이력의 사이클 계수',
  },
  fracture: { 1: '전체 파이프라인', 9: '메시 수렴과 검증' },
  'hardness-specimens': { 1: '거리 기준의 시편 규정', 7: '경도-강도 환산과 역해석의 한계' },
  'impact-specimens': { 1: '노치와 물성 정의', 7: 'ASTM · ISO 단위 차이' },
  'longlife-property-map': {
    1: '전체 지도',
    2: '장기수명 물성의 특수성',
    6: '시간 경과에 따른 물성 변화',
    7: '결함 가정 접근',
    9: '가속시험의 함정',
    10: '시작 순서',
  },
  'sheet-formability-specimens': {
    1: '폭 시리즈 규격 체계',
    6: 'r · n · FLC 의 CAE 연계',
    7: 'FLC 의 경로 의존성',
  },
  'tensile-plasticity': {
    1: '전체 파이프라인',
    2: '인장시험의 실제 측정량',
    4: '공칭 → 진응력 변환',
    5: '네킹 이후의 외삽',
    6: '변형률 속도 효과',
    7: '이방성 — 압연 방향 효과',
    8: '파단 판정',
    9: '솔버별 물성 카드 작성',
    10: '카드 검증 세 단계',
  },
  'tensile-specimens': { 1: '세 갈래 기호 체계', 2: '기호의 위치' },
  'thermal-property-specimens': {
    2: '두께와 반감시간 — 제곱 법칙',
    3: '직접 측정 방법',
    5: '시편 길이 전략 — 짧게 vs 길게',
    7: 'CAE 열 카드 연계',
    8: 'HDT · Vicat 의 한계',
  },
  'tma-thermal-expansion': {
    1: '전체 파이프라인',
    2: 'TMA 의 실제 측정량',
    3: 'CTE 의 두 정의',
    5: '장비 간 편차의 원인',
    6: '같은 이름의 두 온도',
    8: '솔버별 물성 카드 작성',
    9: '카드 검증 세 단계',
  },
  wear: {
    1: '전체 파이프라인',
    2: '마모 예측의 난점',
    4: '물성 추출 지점',
    6: '속도 법칙의 영향',
    7: '부식 속도의 신속 측정',
    9: 'CAE 반영 가능 항목과 한계',
  },
}

const extensions = [
  StarterKit.configure({ heading: { levels: [2, 3, 4] }, underline: false }),
  TableKit.configure({ table: { resizable: false } }),
  Image.configure({ inline: false, allowBase64: false }),
]

function slug(text, fallback) {
  const cleaned = text
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return cleaned || fallback
}

function convert(file, catalog) {
  const html = readFileSync(file, 'utf-8')
  const $ = cheerio.load(html)
  // `<h1>ASTM 인장시편<br>규격과…</h1>` — 줄바꿈이 띄어쓰기다.
  $('h1 br').replaceWith(' ')
  const title = $('h1').first().text().replace(/\s+/g, ' ').trim()
  const summary = $('.dek, .lede').first().text().replace(/\s+/g, ' ').trim().slice(0, 500)
  const assets = []
  const sections = []

  $('section').each((index, element) => {
    const section = $(element)
    const heading = section.find('h2').first()
    // 「00 / 구조」 같은 번호표는 절 순서가 되고, 제목은 그 뒤다.
    const num = heading.find('.num').text().trim()
    heading.find('.num').remove()
    const sectionTitle = heading.text().replace(/\s+/g, ' ').trim() || `절 ${index + 1}`
    heading.remove()

    // 그림은 파일로. 본문에는 자리표시만.
    section.find('svg').each((n, svg) => {
      const name = `${catalog.key}-${index + 1}-${n + 1}.svg`
      const alt = $(svg).attr('aria-label') || sectionTitle
      assets.push({ name, alt, svg: $.html(svg) })
      $(svg).replaceWith(`<img src="asset:${name}" alt="${alt.replace(/"/g, '&quot;')}">`)
    })
    // 주의·함정 상자는 인용(안내 상자)으로. 편집기가 허용하는 것이 그것이다.
    section.find('.note, .fbox').each((_, box) => {
      $(box).replaceWith(`<blockquote>${$(box).html()}</blockquote>`)
    })
    // 카드의 h4 는 작은 제목으로 남는다 — 편집기가 h4 까지 허용한다.
    section.find('.eqn').each((_, eq) => {
      $(eq).replaceWith(`<pre><code>${$(eq).text().trim()}</code></pre>`)
    })
    section.find('script, style, nav').remove()

    const doc = generateJSON(section.html(), extensions)
    const label = num.replace(/\s*\/.*$/, '').trim()
    // 키는 **원래 제목**에서 — 명사형으로 바꿔도 주소는 그대로다.
    const shown = TITLE_OVERRIDES[catalog.key]?.[index + 1] ?? sectionTitle
    sections.push({
      key: slug(label ? `${label}-${sectionTitle}` : sectionTitle, `section-${index + 1}`).slice(0, 78),
      title: (label ? `${label} · ` : '') + shown,
      position: index + 1,
      body: doc,
    })
  })

  return {
    key: catalog.key,
    kind: catalog.kind,
    topic: catalog.topic,
    title,
    summary,
    source_filename: basename(file),
    sections,
    assets,
  }
}

mkdirSync(join(outDir, 'assets'), { recursive: true })
const report = []
for (const name of readdirSync(sourceDir)) {
  const stem = name.replace(/\.html$/, '')
  const catalog = CATALOG[stem]
  if (!name.endsWith('.html') || !catalog) continue // `_1`·`_2` 복사본과 옛 이름은 건너뛴다
  const seed = convert(join(sourceDir, name), catalog)
  for (const asset of seed.assets) {
    writeFileSync(join(outDir, 'assets', asset.name), asset.svg, 'utf-8')
  }
  const out = { ...seed, assets: seed.assets.map(({ name: n, alt }) => ({ name: n, alt })) }
  writeFileSync(join(outDir, `${seed.key}.json`), JSON.stringify(out), 'utf-8')
  report.push(`${seed.key.padEnd(42)} ${String(seed.sections.length).padStart(2)}절  그림 ${seed.assets.length}`)
}
console.log(report.join('\n'))
