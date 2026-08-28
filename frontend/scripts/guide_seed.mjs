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
    sections.push({
      key: slug(label ? `${label}-${sectionTitle}` : sectionTitle, `section-${index + 1}`).slice(0, 78),
      title: (label ? `${label} · ` : '') + sectionTitle,
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
