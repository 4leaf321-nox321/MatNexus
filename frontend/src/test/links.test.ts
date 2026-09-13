/**
 * 화면의 내부 링크는 **라우터에 있는 주소**로 간다.
 *
 * 재료 상세의 「파일 여러 개 업로드」 가 `/tests/upload` 로 보냈는데 그 주소가 부서
 * 스코프(`/w/:slug/tests/upload`)에만 있어 「없는 페이지」 였다(VOC 2026-09-13). 링크와
 * 라우터가 서로 다른 파일에 있어 한쪽만 고쳐도 아무것도 안 울렸다 — 여기서 대조한다.
 *
 * 보는 것: `to=`·`navigate(`·`href=`·내비 `to:`/`resolve:` 의 `/` 로 시작하는 문자열.
 * 템플릿 조각(`${…}`)은 경로 한 마디로 본다. 쿼리 문자열은 뗀다.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { router } from '@/routes/router'

const SRC = path.resolve(process.cwd(), 'src')

function walkFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) walkFiles(full, out)
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.|\.d\.ts$/.test(name)) out.push(full)
  }
  return out
}

/** 라우터 정의를 평평한 주소 목록으로 — 중첩은 부모 주소에 이어 붙인다. */
function routePaths(): string[] {
  const found: string[] = []
  const walk = (routes: { path?: string; children?: unknown[] }[], base: string) => {
    for (const route of routes) {
      const here = route.path
        ? `${base}/${route.path}`.replace(/\/+/g, '/')
        : base
      if (route.path) found.push(here)
      if (route.children) walk(route.children as typeof routes, here)
    }
  }
  walk(router.routes as { path?: string; children?: unknown[] }[], '')
  return found
}

function matcher(route: string): RegExp {
  const body = route
    .split('/')
    .map((part) => (part.startsWith(':') ? '[^/]+' : part === '*' ? '.*' : part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
    .join('/')
  return new RegExp(`^${body}/?$`)
}

const LINK =
  /(?:\bto=\{?[`'"]|\bnavigate\(\s*[`'"]|\bhref=[`'"]|\bto:\s*[`'"]|\bresolve:\s*\([a-z]+\)\s*=>\s*`)(\/[^`'"]*)/g

describe('내부 링크', () => {
  it('전부 라우터에 있는 주소로 간다', () => {
    const routes = routePaths().filter((one) => one !== '/*')
    const matchers = routes.map(matcher)
    const broken: string[] = []
    for (const file of walkFiles(SRC)) {
      if (file.endsWith(path.join('routes', 'router.tsx'))) continue
      const text = readFileSync(file, 'utf-8')
      for (const found of text.matchAll(LINK)) {
        const raw = found[1]
        const norm = raw.replace(/\$\{[^}]*\}/g, 'x').split('?')[0].split('#')[0]
        if (!matchers.some((rx) => rx.test(norm))) {
          broken.push(`${path.relative(SRC, file)}: ${raw}`)
        }
      }
    }
    expect(broken, `라우터에 없는 주소로 가는 링크:\n${broken.join('\n')}`).toEqual([])
  })
})
