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

const EMAIL = process.env.MNX_ADMIN_EMAIL ?? 'admin'
const PASSWORD = process.env.MNX_ADMIN_PASSWORD ?? '32167'

/** 인장 원본. 시드에 인장 종류가 있어 프로파일 없이도 읽힌다. */
const TRA = path.resolve(
  fileURLToPath(new URL('../../backend/tests/fixtures/Example.tra', import.meta.url))
)

/** 실행마다 다른 재료를 만든다. 같은 이름은 서버가 거절한다(그게 맞다). */
const RUN_ID = `E2E${Date.now().toString().slice(-8)}`

test.describe.configure({ mode: 'serial' })

test('로그인부터 곡선까지', async ({ page }) => {
  await test.step('로그인', async () => {
    await page.goto('/')
    await page.getByLabel('아이디').fill(EMAIL)
    await page.getByLabel('비밀번호').fill(PASSWORD)
    await page.getByRole('button', { name: '로그인' }).click()
    // 껍데기가 떴다는 것은 인증·라우팅·토큰 보관이 다 통했다는 뜻이다.
    await expect(page.getByRole('banner')).toBeVisible()
  })

  await test.step('재료 등록', async () => {
    await page.goto('/materials')
    await page.getByRole('button', { name: '재료 등록' }).click()
    await page.getByLabel('Family').fill('Metal')
    await page.getByLabel('Category').fill('Steel')
    await page.getByLabel('Grade').fill(RUN_ID)
    await page.getByLabel('스펙 두께 (mm)').fill('1.0')
    await page.getByRole('button', { name: '등록', exact: true }).click()
    await expect(page.getByRole('dialog')).toBeHidden()

    // **목록을 훑지 않고 찾는다.** 재료는 이름순으로 정렬되고 한 페이지가
    // 50개다. 스모크가 실행마다 재료를 하나씩 남기므로, 훑는 방식은 언젠가
    // "만들었는데 목록에 없다" 로 깨진다 — 그때 원인이 페이지 넘김이라는 것을
    // 알아내기가 어렵다.
    await page.getByPlaceholder('이름 · 별칭 · Grade 로 찾기').fill(RUN_ID)
    await expect(page.getByText(RUN_ID).first()).toBeVisible()
  })

  await test.step('시료 추가', async () => {
    await page.getByText(RUN_ID).first().click()
    await page.getByRole('button', { name: '시료 추가' }).click()
    await page.getByRole('button', { name: '추가', exact: true }).click()
    await expect(page.getByRole('dialog')).toBeHidden()
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
    await page.getByText(RUN_ID).first().click()

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

  await page.getByRole('link', { name: '파일 형식' }).click()
  await expect(page).toHaveURL(/\/settings\/formats$/)
  await expect(page.getByRole('link', { name: '프로파일 만들기' })).toBeVisible()

  // 목록이 실제로 채워지는지까지 — 빈 표는 "왜 없지" 로 읽힌다.
  await expect(page.locator('tbody tr').first()).toBeVisible()
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
