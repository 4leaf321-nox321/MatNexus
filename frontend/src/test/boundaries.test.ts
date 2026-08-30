/**
 * 프론트 모듈 경계 — **백엔드만 막고 있었다.**
 *
 * `backend/tests/architecture/test_boundaries.py` 가 백엔드의 모듈 간 import 를
 * 막는데, 프론트는 아무도 안 봤다. 그래서 지금도 이미 규칙과 다른 배치가 몇 개
 * 있다(아래 `ALLOWED`). 검사가 없으면 그런 예외가 **소리 없이 늘어난다** —
 * 65가 프론트 122파일 평면이 된 경로다.
 *
 * 이 검사는 예외를 금지하지 않는다. **예외를 적게 만든다.** 새 예외가 필요하면
 * 여기 사유와 함께 적어야 하고, 그 순간 "정말 필요한가" 를 한 번 묻게 된다.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

// `import.meta.url` 은 vitest 가 변환한 뒤 file: 스킴이 아니라 실패한다.
// 프로젝트 루트에서 도는 것이 보장되므로 cwd 기준으로 잡는다.
const SRC = path.resolve(process.cwd(), 'src')
const MODULES = path.join(SRC, 'modules')

/**
 * 허용된 모듈 간 참조. **사유 없이 추가하지 않는다.**
 *
 * 공통 규칙(CLAUDE.md): 모듈끼리 직접 부르지 않는다. 로직 공유는 `shared` 를
 * 거친다. 다만 **재료 계층은 시험이 매달리는 축**이라, 시험 화면이 재료를 고르는
 * 것은 도메인상 자연스럽다 — 재료 모듈이 그 선택기를 제공하고 시험이 조립한다.
 */
const ALLOWED: Record<string, { to: string; why: string }[]> = {
  vocabulary: [
    {
      to: 'units',
      why: '단위는 기준정보의 한 칸이다 — 사람이 폼에서 고르는 목록이라는 점에서 같은 것이라, 메뉴에 둘로 세우면 「단위가 기준정보가 아닌가」 를 묻게 된다. 다만 축은 값을 더할 수 있고 단위는 못 고쳐서(환산 계수는 이미 저장된 숫자의 뜻이다) 왼쪽 목록에서 따로 세운다. 표를 그리는 것은 units 의 일이고 기준정보 화면은 자리만 내준다.',
    },
  ],
  tests: [
    {
      to: 'materials',
      why: '시험은 시편에 매달린다. 재료 계층을 고르는 컴포넌트는 재료 모듈이 제공하고 시험 화면은 조립만 한다(SpecimenPicker·MaterialPicker·NewSampleDialog).',
    },
    {
      to: 'workspaces',
      why: '형식 프로파일이 부서 소유다 — 장비는 부서마다 다르고, 남의 부서 파일을 어떻게 읽을지는 그 부서가 안다. 만들 때 소유 부서를 골라야 하므로 부서 선택기를 쓴다.',
    },
    {
      to: 'vocabulary',
      why: '업로드 창이 장비를 기준정보로 받는다(ADR 0010). 장비 이름은 도메인 값이지 공통 부품이 아니라 shared 로 못 올리고, 기준정보 쪽은 화면을 몰라야 해서 반대로도 못 뒤집는다. 재료 모듈이 같은 이유로 기준정보를 부른다.',
    },
    {
      to: 'processing',
      why: '시험 상세가 그 시험의 처리 패널을 끼워 넣는다. 원본 곡선을 보고 나서 "이게 물성으로 어떻게 되는데" 가 이어지는 자리라, 다른 화면으로 보내면 원본과 결과를 나란히 못 본다. 아래 processing → tests 의 반대 방향이고 둘은 한 화면을 나눠 그린다.',
    },
    {
      to: 'viscoelastic',
      why: '시험 상세가 그 시험의 점탄성 탭을 끼워 넣는다. 겹치기는 **한 시험 안의 온도가 다른 스윕 여럿**을 고르는 일이라, 그 시험을 떠나면 무엇을 겹치는지가 사라진다. 바로 위 processing 과 같은 방향·같은 이유고 둘은 한 화면을 나눠 그린다.',
    },
  ],
  viscoelastic: [
    {
      to: 'tests',
      why: '마스터커브도 곡선이라 같은 CurveChart 로 그린다 — 축이 둘 다 로그인 것만 다르고, 그 옵션은 차트가 받는다. 처리·통계·적합이 같은 이유로 tests 를 부른다.',
    },
    {
      to: 'fitting',
      why: '적합에서 물성 카드를 만드는 버튼이 Prony 결과 옆에 있어야 한다 — 계수를 보고 나서 "이걸로 카드" 가 이어지는 자리다. 카드는 fitting 의 것이라 그 API 를 부른다. 반대로 뒤집으면(fitting 이 점탄성을 앎) 경화 카드 화면이 DMA 를 알아야 하고, 새 물성마다 그 목록이 는다 — 그것이 바로 물성 블록으로 걷어낸 결합이다.',
    },
  ],
  statistics: [
    {
      to: 'tests',
      why: '앙상블 곡선도 곡선이라 같은 CurveChart 로 그린다. 처리 모듈이 같은 이유로 tests 를 부르는 것과 같다 — 차트를 shared 로 올리면 공통이 도메인을 알게 된다.',
    },
  ],
  processing: [
    {
      to: 'tests',
      why: '처리 결과도 곡선이라 같은 CurveChart 로 그린다. 차트를 shared 로 올리지 않은 이유: 축 라벨·단위 표기·LTTB 안내 문구가 전부 시험 도메인의 것이라, shared 로 올리면 공통이 도메인을 알게 된다.',
    },
  ],
  fitting: [
    {
      to: 'statistics',
      why: '적합의 입력이 통계의 대표 곡선이다. 어느 묶음을 적합할지 고르려면 묶음 목록(재료+시험종류+방향, 표본 수)이 필요한데, 그것을 아는 것은 통계 모듈이다. 시편 하나로 적합하지 않기 위한 구조라 우회할 수 없다.',
    },
    {
      to: 'tests',
      why: '적합 결과를 대표 곡선과 겹쳐 그린다. 겹쳐 보지 않으면 RMSE 가 작아도 항복 근처만 크게 어긋난 것을 못 본다 — 그것은 숫자가 아니라 모양으로 보인다. 통계·처리가 같은 이유로 CurveChart 를 쓴다.',
    },
  ],
  materials: [
    {
      to: 'vocabulary',
      why: '재료·시료의 속성이 기준정보를 가리킨다(ADR 0010). 제조사·강종은 도메인 값이지 공통 부품이 아니라 shared 로 올릴 수 없고, 기준정보 쪽은 화면을 몰라야 해서 반대로도 못 뒤집는다. 재료 폼이 기준정보 피커를 조립하는 방향이 맞다.',
    },
    {
      to: 'statistics',
      why: '재료 화면이 답해야 하는 질문의 절반이 "이 재료의 물성은 얼마인가" 다. 통계는 재료 단위로 묶이므로(재료+시험종류+방향) 그 자리가 재료 상세다.',
    },
    {
      to: 'tests',
      why: '재료 상세가 시편별 시험 목록을 끼워 넣는다(SpecimenTests). 위의 반대 방향이고, 둘은 한 화면을 나눠 그린다.',
    },
    {
      to: 'fitting',
      why: '재료 상세의 CAE 카드 탭. 카드는 재료 하나의 물성 한 벌이고, 그 입력이 바로 옆 물성 탭의 대표 곡선이다 — 다른 화면으로 보내면 근거와 결론이 떨어진다.',
    },
  ],
  auth: [
    {
      to: 'accounts',
      why: '가입 신청이 계정을 만든다. 로그인 전 화면이라 계정 모듈의 관리 화면과 성격이 다르지만, 만드는 대상은 같은 계정이다.',
    },
    {
      to: 'workspaces',
      why: '가입할 때 소속 부서를 고른다. 부서 트리를 아는 것은 부서 모듈이고, 가입 화면은 그 선택기를 조립만 한다.',
    },
  ],
  accounts: [
    {
      to: 'workspaces',
      why: '가입 승인이 곧 부서 배정이다. 승인 화면에서 부서를 고르지 못하면 승인 뒤 다른 화면에 다시 가야 한다.',
    },
  ],
  workspaces: [
    {
      to: 'tests',
      why: '부서 홈이 **조립만 한다.** 홈은 "무엇을 어디서 하나" 를 말하는 자리라 각 단계의 입구와 남은 일(등록 건수·처리 대기·읽지 못한 파일)을 모아 보여 준다. 워크벤치가 조립만 하는 것과 같은 성격이고, 시험 도메인 로직은 한 줄도 여기 없다.',
    },
    {
      to: 'materials',
      why: '같은 이유로 3·4단계(물성·CAE 카드)의 입구와 재료 수를 보여 준다. 재료는 전사 카탈로그라 부서로 좁히지도 않는다 — 목록을 부르는 것이 전부다.',
    },
    {
      to: 'statistics',
      why: '홈 요약(`OverviewPanel`)을 조립한다. 세는 일은 전부 서버가 하고(`/statistics/overview`) 홈은 받은 숫자를 그린다 — 재료 94개를 세려고 94행을 받는 대신이다. 요약 화면이 통계 모듈에 있는 이유는 재료 목록·기준정보 축 패널과 같다: 내용이 그 도메인의 것이고 홈은 자리만 내준다.',
    },
  ],
}

/**
 * `shared/layout` 은 **껍데기**다. 껍데기가 도메인 위젯을 조립하는 것은 그 일이다
 * — 상단 바의 부서 선택기, 알림 종, 공지 팝업.
 *
 * 나머지 `shared`(api·hooks·lib·components)는 도메인을 몰라야 한다. 거기서
 * 모듈을 부르기 시작하면 방향이 뒤집혀 **공통이 도메인을 알게 되고, 그때부터
 * 모듈을 떼어 낼 수 없다.**
 */
const SHELL = path.join('shared', 'layout')

interface Violation {
  file: string
  from: string
  to: string
}

function walk(dir: string): string[] {
  const found: string[] = []
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry)
    if (statSync(full).isDirectory()) found.push(...walk(full))
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) found.push(full)
  }
  return found
}

function moduleImports(file: string): string[] {
  const source = readFileSync(file, 'utf-8')
  const found = new Set<string>()
  for (const match of source.matchAll(/from\s+'@\/modules\/([^/']+)/g)) {
    found.add(match[1])
  }
  return [...found]
}

describe('모듈 경계', () => {
  it('모듈끼리 직접 부르지 않는다 — 적어 둔 예외만', () => {
    const violations: Violation[] = []

    for (const name of readdirSync(MODULES)) {
      const dir = path.join(MODULES, name)
      if (!statSync(dir).isDirectory()) continue

      const allowed = new Set((ALLOWED[name] ?? []).map((rule) => rule.to))
      for (const file of walk(dir)) {
        for (const target of moduleImports(file)) {
          if (target === name || allowed.has(target)) continue
          violations.push({ file: path.relative(SRC, file), from: name, to: target })
        }
      }
    }

    expect(
      violations,
      violations.length
        ? `모듈을 직접 부르고 있습니다. 로직 공유는 shared 를 거치세요. ` +
            `도메인상 꼭 필요하면 boundaries.test.ts 의 ALLOWED 에 **사유와 함께** 적으세요:\n` +
            violations.map((v) => `  ${v.file}: ${v.from} → ${v.to}`).join('\n')
        : ''
    ).toEqual([])
  })

  it('shared 는 껍데기(layout)에서만 도메인을 부른다', () => {
    const violations: Violation[] = []
    for (const file of walk(path.join(SRC, 'shared'))) {
      const relative = path.relative(SRC, file)
      // 껍데기(layout)만 예외다. 화면을 조립하는 것이 그 파일들의 일이다.
      if (relative.startsWith(SHELL)) continue
      for (const target of moduleImports(file)) {
        violations.push({ file: relative, from: 'shared', to: target })
      }
    }

    expect(
      violations,
      violations.length
        ? `shared 가 도메인 모듈을 부릅니다(껍데기 layout 만 예외):\n` +
            violations.map((v) => `  ${v.file} → ${v.to}`).join('\n')
        : ''
    ).toEqual([])
  })

  it('API 절대주소를 코드에 넣지 않는다', () => {
    // 52는 빌드 시 API 주소를 굽는 방식이라 값이 빠지면 사용자 브라우저가 자기
    // PC를 부르는 사고가 났다. 상대경로면 그 사고 자체가 없다.
    const offenders: string[] = []
    for (const file of [...walk(path.join(SRC, 'modules')), ...walk(path.join(SRC, 'shared'))]) {
      const source = readFileSync(file, 'utf-8')
      if (/https?:\/\/(localhost|127\.0\.0\.1|\d+\.\d+\.\d+\.\d+)/.test(source)) {
        offenders.push(path.relative(SRC, file))
      }
    }
    expect(offenders, `API 절대주소가 있습니다:\n  ${offenders.join('\n  ')}`).toEqual([])
  })
})

/**
 * 본문 폭 — **한 곳에서 정한다.**
 *
 * 전에는 화면마다 `mx-auto max-w-4xl` ~ `max-w-7xl` 을 제각각 달았다. 17개
 * 화면에 5가지 폭이었고, 규칙이 없으니 새 화면은 옆 파일을 베꼈다. 그래서 같은
 * 성격의 표가 화면마다 다른 폭으로 잘렸다.
 *
 * 지금은 `AppShell` 의 `main` 이 정하고, **상한은 없다**(2026-08-30). 상한이 있던
 * 동안에는 그것이 표를 접었고 — 시편 목록의 치수 칸이 두 줄이 됐다 — 넓혀야 할
 * 때마다 경로 목록에 한 줄씩 더해야 했다. **읽는 화면만 자기 안에서 다시 좁힌다** —
 * 공지·알림·VOC 는 글이라 폭이 넓을수록 읽기 나쁘다.
 *
 * 이 검사가 없으면 다음 화면이 또 제 폭을 단다. 65가 프론트 122파일 평면이 된
 * 경로와 같은 종류다 — **규율이 아니라 검사가 막는다.**
 */
const NARROW_BY_DESIGN = new Set([
  path.join('notices', 'NoticesPage.tsx'),
  path.join('notifications', 'NotificationsPage.tsx'),
  path.join('voc', 'VocPage.tsx'),
])

describe('본문 폭', () => {
  it('화면이 제 폭을 정하지 않는다', () => {
    const offenders: string[] = []
    for (const file of walk(MODULES)) {
      const rel = path.relative(MODULES, file)
      if (NARROW_BY_DESIGN.has(rel)) continue
      const source = readFileSync(file, 'utf-8')
      // 주석에 적힌 것은 설명이다. **`className` 안에 있는 것만** 본다.
      for (const match of source.matchAll(/className="[^"]*mx-auto max-w-[^"]*"/g)) {
        offenders.push(`${rel}: ${match[0]}`)
      }
    }
    expect(
      offenders,
      '본문 폭은 AppShell 이 정합니다. 좁아야 하는 화면이면 NARROW_BY_DESIGN 에 ' +
        '사유와 함께 넣으세요.'
    ).toEqual([])
  })

  it('껍데기가 본문 폭을 자르지 않는다', () => {
    // **상한을 다시 달면 여기서 걸린다.** 걷은 이유가 코드에만 남아 있으면 다음
    // 사람이 「넓어 보이니 1600 으로 묶자」 를 되풀이하고, 그때 접히는 것은 표의
    // 한 칸이라 아무도 못 본다.
    const shell = readFileSync(path.join(SRC, SHELL, 'AppShell.tsx'), 'utf-8')
    const body = shell.slice(shell.indexOf('<main'))
    const capped = [...body.matchAll(/className=[^\n]*max-w-\[[^\]]+\]/g)]
    expect(
      capped.map((one) => one[0]),
      '본문에 폭 상한을 다시 달았습니다 — 표는 제 열 폭을 스스로 잡습니다.'
    ).toEqual([])
  })

  it('화면이 뷰포트 폭을 직접 잡지 않는다', () => {
    // 폭은 부모(`main`)를 따른다. 화면이 `w-screen` 을 쓰면 사이드바 밑까지
    // 깔려 가로 스크롤이 생기고, 그 화면만 다른 규칙으로 산다.
    const offenders: string[] = []
    for (const file of walk(MODULES)) {
      const source = readFileSync(file, 'utf-8')
      // 화면이 뷰포트 폭을 직접 잡는 자리. `w-full` 은 부모를 따르므로 괜찮다.
      for (const match of source.matchAll(/className="[^"]*\b(w-screen|max-w-none)\b[^"]*"/g)) {
        offenders.push(`${path.relative(MODULES, file)}: ${match[0]}`)
      }
    }
    expect(offenders, '폭은 부모가 정합니다 — 화면이 뷰포트를 직접 잡지 않습니다.').toEqual([])
  })
})


/**
 * 옆패널 글자 — **사이드바보다 작으면 안 된다.**
 *
 * 사이드바 항목은 `text-sm` 인데 바로 옆 목록이 `text-xs` 였다. 같은 층위의
 * 목록이 사이드바보다 작으면 읽는 사람은 그것을 부속물로 본다 — 실제로는 그
 * 화면에서 **무엇을 볼지 고르는 자리**다. 실사용에서 "글자크기가 너무 작다" 가
 * 나왔다.
 *
 * 참고: ReportArchive 는 사이드바 항목과 그 옆 목록이 둘 다 `text-sm` 이다.
 *
 * ## 무엇을 「고르는 줄」로 보는가
 *
 * `aria-current` 를 단 것. 그 속성이 곧 "지금 이것을 보고 있다" 는 뜻이라,
 * 고르는 줄에만 붙는다 — 처음에는 여백(`px-`·`py-`)으로 짚으려 했는데 이름표와
 * 작은 버튼까지 잡혔다. **곁줄과 이름표는 작아도 된다.**
 */
describe('옆패널 글자', () => {
  it('고르는 줄이 사이드바보다 작지 않다', () => {
    const offenders: string[] = []
    for (const file of walk(MODULES)) {
      const source = readFileSync(file, 'utf-8')
      if (!source.includes('<LeftPanel')) continue
      const rel = path.relative(MODULES, file)
      // `aria-current` 부터 그 요소가 닫히기까지에서 크기 클래스를 본다.
      for (const match of source.matchAll(/aria-current[\s\S]{0,600}?\n\s*>/g)) {
        const found = match[0].match(/\btext-(xs|sm|base|\[\d+px\])\b/)
        if (found && found[1] !== 'sm' && found[1] !== 'base') {
          offenders.push(`${rel}: text-${found[1]}`)
        }
      }
    }
    expect(
      offenders,
      '옆패널에서 고르는 줄(aria-current)은 text-sm 입니다 — 사이드바 항목과 ' +
        '같은 크기여야 합니다. 곁줄과 이름표는 text-xs 로 두세요.'
    ).toEqual([])
  })
})
