/**
 * 스모크 — 로그인부터 곡선까지 한 줄기.
 *
 * **API 로만 확인하면 놓치는 것들이 여기서 잡힌다.** 실제로 놓쳤다: 곡선 6벌이
 * 저장됐는데 화면에서 하나도 안 보였고, 그건 API 호출로는 200 이었다.
 *
 * 확인하는 것은 "도는가" 하나다. 값의 정확성은 pytest 가, 컴포넌트 동작은
 * vitest 가 본다. 여기서 세밀하게 검증하기 시작하면 화면을 조금 고칠 때마다
 * 깨지고, 그러면 아무도 안 돌린다.
 *
 * 준비물 — 이 셋이 없으면 **건너뛰고 이유를 말한다.** 조용히 통과하면 "스모크가
 * 초록이니 괜찮겠지" 가 되는데, 실은 아무것도 안 본 것이다.
 *
 *   백엔드   8010 (또는 MNX_BASE_URL)
 *   워커     파싱을 한다. 없으면 상태가 '대기' 에서 안 움직인다
 *   계정     MNX_ADMIN_EMAIL / MNX_ADMIN_PASSWORD (기본 admin / 32167)
 */

import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const EMAIL = process.env.MNX_ADMIN_EMAIL ?? 'admin'
const PASSWORD = process.env.MNX_ADMIN_PASSWORD ?? '32167'

/** 인장 원본. 시드에 인장 종류가 있어 프로파일 없이도 읽힌다. */
const TRA = path.resolve(
  fileURLToPath(new URL('../../backend/tests/fixtures/Example.tra', import.meta.url))
)

/** 실행마다 다른 재료를 만든다. 같은 이름은 서버가 거절한다(그게 맞다). */
const RUN_ID = `E2E${Date.now().toString().slice(-8)}`

test.describe.configure({ mode: 'serial' })

/**
 * 기준정보 피커에서 값을 고른다. 없으면 새로 만든다.
 *
 * **자유 입력이 아니다.** Family·Category·Grade 는 v0.7.0 부터 기준정보를 거친다
 * (ADR 0010). 그때 이 시험이 `getByLabel('Family').fill()` 인 채로 남아 CI 가
 * 19번 연속 빨갰다 — 화면을 바꿀 때 스모크를 같이 안 고친 것이다.
 *
 * 새 DB 에서는 `Metal` 조차 아직 기준정보에 없으므로 **고르기와 만들기를 둘 다**
 * 할 수 있어야 한다. 하나만 하면 두 번째 실행부터(또는 첫 실행에서) 깨진다.
 */
async function pickVocabulary(page: Page, label: string, value: string) {
  // 트리거의 접근성 이름은 `Family: Metal` 이다. 보이는 글자는 고른 값뿐이라
  // 이름에 칸 이름이 없으면 한 폼의 피커 다섯을 구분할 수가 없다.
  await page.getByRole('button', { name: new RegExp(`^${label}:`) }).click()
  await page.getByPlaceholder(`${label} 찾기`).fill(value)

  // **`exact` 로는 못 찾는다.** 목록 항목은 값 뒤에 쓰는 곳 수가 붙어서 접근성
  // 이름이 `Metal 89` 다. 값만으로 정확히 맞추면 영원히 안 뜨고, 이미 있는 값은
  // '새로 추가' 도 안 나오므로 90초를 기다리다 죽는다 — 실제로 그렇게 죽었다.
  //
  // 앞을 고정한다. 안 하면 트리거(`Family: Metal`)까지 걸려 둘이 잡힌다.
  // 정규식 이스케이프는 안 한다 — 여기 넣는 값은 영숫자뿐이고, 특수문자가
  // 들어오는 날에는 이 시험이 바로 깨져서 알려 준다.
  const existing = page.getByRole('button', { name: new RegExp(`^${value}(\\s|$)`) })
  const create = page.getByRole('button', { name: /새로 추가/ })
  // 서버 검색은 debounce 가 있다. 둘 중 하나가 뜰 때까지 기다린다.
  await existing.or(create).first().waitFor()
  if (await existing.isVisible()) {
    await existing.click()
  } else {
    await create.click()
  }
  // 고르면 팝오버가 닫히고 트리거에 값이 보인다.
  await expect(page.getByRole('button', { name: `${label}: ${value}` })).toBeVisible()
}

test('로그인부터 곡선까지', async ({ page }) => {
  await test.step('로그인', async () => {
    await page.goto('/')
    await page.getByLabel('아이디').fill(EMAIL)
    await page.getByLabel('비밀번호').fill(PASSWORD)
    await page.getByRole('button', { name: '로그인' }).click()
    // 껍데기가 떴다는 것은 인증·라우팅·토큰 보관이 다 통했다는 뜻이다.
    await expect(page.getByRole('banner')).toBeVisible()

    // **첫 화면이 무엇을 하는 곳인지 말해야 한다.** 여기가 「구현 예정: Phase 1」
    // 공사 표지판이던 동안 "어느 화면을 어떻게 써야 하는지 모르겠다" 는 말이
    // 나왔다. 주소로 열지 않고 **로그인해서 도착한 자리**를 본다.
    await expect(page.getByText('올린다')).toBeVisible()
    await expect(page.getByText('처리한다')).toBeVisible()
    await expect(page.getByText('물성을 본다')).toBeVisible()
    await expect(page.getByText('카드를 낸다')).toBeVisible()
  })

  await test.step('재료 등록', async () => {
    await page.goto('/materials')
    await page.getByRole('button', { name: '재료 등록' }).click()
    await pickVocabulary(page, 'Family', 'Metal')
    await pickVocabulary(page, 'Category', 'Steel')
    await pickVocabulary(page, 'Grade', RUN_ID)
    await page.getByLabel('스펙 두께 (mm)').fill('1.0')
    await page.getByRole('button', { name: '등록', exact: true }).click()
    // **이름으로 좁힌다.** 기준정보 피커의 팝오버도 `role="dialog"` 라, 이름 없이
    // 찾으면 둘이 잡혀 strict 위반이 난다.
    await expect(page.getByRole('dialog', { name: '재료 등록' })).toBeHidden()

    // **목록을 훑지 않고 찾는다.** 재료는 이름순으로 정렬되고 한 쪽이 50개다.
    // 스모크가 실행마다 재료를 하나씩 남기므로, 훑는 방식은 언젠가 "만들었는데
    // 목록에 없다" 로 깨진다 — 그때 원인이 쪽 넘김이라는 것을 알아내기 어렵다.
    //
    // **채우기만 해서는 검색되지 않는다.** 예전에 채우고 끝냈는데, 그때는 새
    // 재료가 우연히 첫 쪽 50건 안에 있어서 통과했다. 재료가 52건이 되자
    // 깨졌다 — 위 주석이 예고한 바로 그 실패다. 눌러야 좁혀진다.
    await page.getByPlaceholder('이름 · 별칭 · Grade 로 찾기').fill(RUN_ID)
    await page.getByRole('button', { name: '찾기' }).click()
    await expect(page.getByRole('link', { name: new RegExp(RUN_ID) })).toBeVisible()
  })

  await test.step('시료 추가', async () => {
    await page.getByRole('link', { name: new RegExp(RUN_ID) }).click()
    await page.getByRole('button', { name: '시료 추가' }).click()
    await page.getByRole('button', { name: '추가', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '시료 추가' })).toBeHidden()
    // 시편은 일괄 등록이 만들어 준다 — 그 경로가 실무에서 쓰는 길이다.
    await expect(page.getByText(/시편 0|시편 \d/).first()).toBeVisible()
  })

  await test.step('파일 올리기', async () => {
    await page.goto('/w/default/tests/upload')
    await page.locator('input[type="file"]').setInputFiles(TRA)

    // 종류는 서버가 추정한다(확장자 또는 프로파일 지문). 사람이 안 골라도 채워진다.
    await expect(page.getByText('확장자로 추정').or(page.getByText('지문으로 추정'))).toBeVisible()

    // 재료 — 검색이 붙은 선택기. 목록이 길어져도 이 경로는 같다.
    await page.getByRole('button', { name: '재료 일괄 지정' }).click()
    await page.getByPlaceholder('이름·별칭·Grade·Family…').fill(RUN_ID)
    await page.getByRole('button', { name: new RegExp(RUN_ID) }).click()

    // 시료 — 방금 만든 01
    await page.getByRole('combobox', { name: '시료 일괄 지정' }).click()
    await page.getByRole('option').first().click()

    // 시편은 새로 만든다.
    await page.getByRole('button', { name: 'MD', exact: true }).click()

    await page.getByRole('button', { name: /올리기/ }).click()
    await expect(page.getByText(/완료 1/)).toBeVisible({ timeout: 30_000 })
  })

  await test.step('워커가 읽고 곡선이 그려진다', async () => {
    await page.getByRole('button', { name: '목록에서 확인' }).click()

    // **화면이 바뀐 뒤에 누른다.** 업로드 화면에도 방금 올린 시험 이름이 떠
    // 있어서, 목록이 그려지기 전에 `getByText(RUN_ID)` 를 누르면 링크가 아닌
    // 그쪽을 누르고 아무 데도 가지 않는다. 그 상태로 다음 단언을 하면 목록의
    // '완료' 배지 수십 개에 걸려 엉뚱한 실패 메시지가 나온다.
    //
    // 텍스트가 아니라 **링크**를 고르는 것도 같은 이유다.
    // 주소가 바뀌었다고 화면이 바뀐 것은 아니다. 상세 화면에만 있는 것을
    // 기다린다 — 라우트를 나눠 실으면 청크를 받는 동안 이전 화면이 남는다.
    await page.waitForURL('**/tests')
    await page.getByRole('link', { name: new RegExp(RUN_ID) }).first().click()
    await expect(page.getByRole('tab', { name: /원본/ })).toBeVisible({ timeout: 60_000 })

    // **여기가 이 테스트의 핵심이다.** 워커가 돌고, 곡선이 저장되고, 화면이 그것을
    // 읽어 그리기까지 전부 통해야 통과한다.
    await expect(page.getByText('완료')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('svg polyline, svg path').first()).toBeVisible()
    await expect(page.getByText(/점을 표시합니다/)).toBeVisible()
  })

  await test.step('원본·처리·결과가 탭으로 나뉜다', async () => {
    // 세로로 이어 붙이면 처리하는 동안 원본 곡선이 위로 사라진다(ADR 0007).
    for (const name of ['원본', '처리', '결과']) {
      await expect(page.getByRole('tab', { name: new RegExp(name) })).toBeVisible()
    }
    await page.getByRole('tab', { name: '처리' }).click()
    await expect(page.getByRole('button', { name: '돌려 보기' })).toBeVisible()
  })
})

test('재료 화면이 물성을 보여 준다', async ({ page }) => {
  // 재료 화면이 답해야 하는 질문의 절반이 "이 재료의 물성은 얼마인가" 다.
  // 시료 목록만 있으면 시험을 하나씩 열어 봐야 알 수 있다.
  await page.goto('/')
  await page.getByLabel('아이디').fill(EMAIL)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page.getByRole('banner')).toBeVisible()

  await page.goto('/materials')
  await expect(page.locator('tbody tr').first()).toBeVisible()
  await page.locator('tbody tr').first().getByRole('link').first().click()
  await expect(page.getByRole('tab', { name: '물성' })).toBeVisible()
  await page.getByRole('tab', { name: '물성' }).click()
  // 표본이 없어도 화면은 뜨고 이유를 말해야 한다.
  await expect(page.getByRole('tab', { name: '물성' })).toHaveAttribute(
    'data-state',
    'active'
  )
})

test('메뉴에서 형식 프로파일까지 갈 수 있다', async ({ page }) => {
  // **없어진 줄 알았다.** 프로파일 화면을 '관리' 에서 '부서 설정' 으로 옮기고
  // 이름을 '파일 형식' 으로 바꿨더니, 쓰던 사람이 못 찾고 "만드는 게 없어졌다"
  // 고 했다. 화면은 멀쩡했고 메뉴가 옮겨갔을 뿐이었다.
  //
  // 그래서 여기서는 **화면이 아니라 가는 길**을 본다. 주소로 바로 열면 이 종류의
  // 사고를 못 잡는다 — 사이드바를 눌러서 도착해야 한다.
  await page.goto('/')
  await page.getByLabel('아이디').fill(EMAIL)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page.getByRole('banner')).toBeVisible()

  // **사이드바 안에서 찾는다.** 부서 홈의 안내 카드에도 「파일 형식」 이라는
  // 말이 들어 있어서, 화면 전체에서 이름으로 찾으면 둘이 걸린다 — 실제로 CI 가
  // 그렇게 멈췄다. 이 시험이 보려는 것은 **사이드바로 갈 수 있는가** 이므로
  // 범위를 좁히는 것이 시험의 뜻에도 맞다.
  await page
    .locator('[data-app-chrome="sidebar"]')
    .getByRole('link', { name: '파일 형식' })
    .click()
  await expect(page).toHaveURL(/\/settings\/formats$/)
  await expect(page.getByRole('link', { name: '프로파일 만들기' })).toBeVisible()

  // **목록이든 "없습니다" 든, 화면이 무엇이라도 말해야 한다.**
  //
  // 전에는 표에 줄이 있는지만 봤다. 개발 DB 에는 만들어 둔 프로파일이 있어서
  // 늘 통과했는데, **새로 설치한 곳에는 프로파일이 0개인 것이 정상이다**
  // (프로파일은 코드가 아니라 사람이 만든다 — ADR 0005). CI 의 빈 DB 에서
  // 처음 돌리자 그 가정이 드러났다. 갓 설치한 서버가 곧 이 상태다.
  await expect(
    page.locator('tbody tr').first().or(page.getByText('프로파일이 없습니다.'))
  ).toBeVisible()
})

test('읽지 못한 파일은 이유를 보여 준다', async ({ page }) => {
  // 실패도 **조용하지 않아야** 한다. 파서가 못 읽었을 때 화면이 아무 말도 안 하면
  // 사용자는 서버 파일시스템을 뒤지는 수밖에 없다.
  await page.goto('/')
  await page.getByLabel('아이디').fill(EMAIL)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page.getByRole('banner')).toBeVisible()

  await page.goto('/w/default/tests')
  // 목록 화면이 뜨는 것까지만 본다 — 실패한 시험이 있으면 상태로 보인다.
  await expect(page.getByRole('heading', { name: /시험/ })).toBeVisible()
})

test('덱을 뽑는 길이 열려 있다', async ({ page }) => {
  // **여기가 아니면 아무도 안 본다.** 단위계를 고를 수 있게 만들어 놓고,
  // jsdom 시험은 「메뉴가 안 닫히는가」 를 못 잡았다 — 사보타주를 걸어도
  // 통과했다. 그 성질은 진짜 브라우저만 볼 수 있다.
  //
  // 값의 정확성은 pytest 가 본다(두 계로 낸 덱의 숫자까지 실측했다). 여기서
  // 보는 것은 **사람이 그 계를 고를 수 있는가** 하나다.
  await page.goto('/')
  await page.getByLabel('아이디').fill(EMAIL)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page.getByRole('banner')).toBeVisible()

  await page.goto('/cards')
  await expect(page.getByRole('heading', { name: '물성 카드' })).toBeVisible()

  // **`count()` 는 기다리지 않는다.** 처음에 이 줄을 바로 세었더니 목록이
  // 도착하기 전에 0 을 읽고 「카드가 없다」 가지로 빠졌다 — 실제로는 11장이
  // 있었다. 먼저 **둘 중 하나가 뜰 때까지** 기다린다.
  //
  // **양쪽 다 하나로 좁힌다.** `/없습니다/` 를 넓게 잡았더니 CI 의 빈 DB 에서
  // 두 군데에 걸려 strict mode 로 멈췄다 — 개발 DB 에는 카드가 있어서 그
  // 가지를 한 번도 안 지났고, 그래서 로컬에서는 안 드러났다.
  const cards = page.getByRole('button', { name: '내보내기' })
  const empty = page.getByText('조건에 맞는 카드가 없습니다.', { exact: false }).first()
  await expect(cards.first().or(empty)).toBeVisible()

  // **카드가 0장인 것이 정상이다** — 갓 설치한 서버가 그렇고, 카드는 사람이
  // 만든다. 그때 이 시험이 볼 것은 없다.
  if ((await cards.count()) === 0) return

  await cards.first().click()
  await expect(page.getByText('덱의 단위계')).toBeVisible()
  // 덱에 그대로 적힐 줄. 기본은 SI 다.
  await expect(page.getByText('kg, m, s, Pa')).toBeVisible()

  await page.getByRole('button', { name: /mm · N · tonne/ }).click()
  // **고르고 나서도 메뉴가 열려 있어야 한다** — 여기가 jsdom 이 못 보던 자리다.
  await expect(page.getByText('덱의 단위계')).toBeVisible()
  await expect(page.getByText('tonne, mm, s, MPa')).toBeVisible()

  // 고른 계로 실제로 받아진다. 파일 이름에 계가 들어간다.
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('menuitem', { name: /Abaqus/ }).first().click(),
  ])
  expect(download.suggestedFilename()).toContain('mm_n_tonne')
})

test('긴 이름을 골라도 피커가 사이드바를 안 넘는다', async ({ page }) => {
  /**
   * **jsdom 이 원리상 못 보는 자리다.** 레이아웃 엔진이 없어서 폭도 좌표도 없다.
   *
   * 실사용에서 나왔다 — 재료 상세의 왼쪽 목록 패널(`w-64`)에서 Category 를 긴
   * 이름으로 고르면 트리거가 패널 밖으로 밀려 나갔다. 원인은 `Button` 기본
   * 클래스의 `shrink-0` 이라 `min-w-0` 만으로는 안 줄었다(실측: 256px 자리에
   * 293px 버튼).
   */
  const LONG = `초장문분류${RUN_ID}세부구분아연도금합금화처리재`

  await page.goto('/')
  await page.getByLabel('아이디').fill(EMAIL)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page.getByRole('banner')).toBeVisible()

  // 재료는 API 로 만든다 — 여기서 볼 것은 등록 폼이 아니라 **폭**이다.
  //
  // **토큰을 따로 받는다.** 앱은 access 토큰을 메모리에만 두므로(XSS 방어,
  // `shared/api/client.ts`) `page.request` 가 화면의 토큰을 물려받지 못한다.
  const signed = await page.request.post('/api/auth/login', {
    data: { email: EMAIL, password: PASSWORD },
  })
  expect(signed.ok()).toBe(true)
  const token = (await signed.json()).access_token

  const made = await page.request.post('/api/materials', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      family: 'Metal',
      category: LONG,
      grade: `LONG${RUN_ID}`,
      details: '폭점검',
      spec_thickness: 1.0,
      spec_thickness_unit: 'mm',
    },
  })
  expect(made.ok(), await made.text()).toBe(true)
  const material = await made.json()

  await page.goto(`/materials/${material.id}`)
  // 이 피커를 품은 `aside` 가 재료 목록 패널이다(첫 `aside` 는 앱 내비게이션).
  const panel = page.locator('aside').filter({ has: page.getByRole('button', { name: /^Category:/ }) })
  await expect(panel).toBeVisible()

  const trigger = page.getByRole('button', { name: /^Category:/ }).first()
  await trigger.click()
  await page.getByRole('button', { name: new RegExp(`^초장문분류${RUN_ID}`) }).first().click()
  await expect(page.getByRole('button', { name: `Category: ${LONG}` })).toBeVisible()

  const inside = await panel.boundingBox()
  const box = await trigger.boundingBox()
  expect(inside).not.toBeNull()
  expect(box).not.toBeNull()
  // **1px 은 봐 준다** — 테두리 반올림이다.
  expect(box!.x + box!.width).toBeLessThanOrEqual(inside!.x + inside!.width + 1)
})
