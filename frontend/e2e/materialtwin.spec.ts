/**
 * 스모크 — MaterialTwin 이식 한 줄기 (문헌 물성 → 사내 등록 → 채우기 → 혼합 덱).
 *
 * smoke.spec 과 같은 철학이다: **도는가만 본다.** 값의 정확성은 pytest 가,
 * 컴포넌트 동작은 vitest 가 이미 본다. 여기서는 진짜 브라우저 + 진짜 서버로
 * 이식 기능들이 한 줄기로 이어지는지를 밟는다.
 *
 *   문헌 카탈로그   검색 → 상세 (읽기 전용 저수지)
 *   사내 등록      「사내 재료로 등록」 → 재료 상세 도착 + 고유 번호(M-…) + 문헌 연결
 *   채우기         물성 탭의 문헌 채우기 → 「담았습니다」 (공칭 강도 포함 경로)
 *   측정법        물성 → 기법·장비 표
 *   혼합 덱       BOM 붙여넣기 → 매칭 → 덱 파일
 *   워크벤치      bom_deck 워크플로가 목록에 선다
 *
 * 준비물은 smoke.spec 과 같다 — 백엔드(MNX_BASE_URL, 기본 8010) + 계정.
 * 워커는 필요 없다(파일 파싱이 없는 줄기다).
 */

import { expect, test } from '@playwright/test'

const EMAIL = process.env.MNX_ADMIN_EMAIL ?? 'admin'
const PASSWORD = process.env.MNX_ADMIN_PASSWORD ?? '32167'

/** 실행마다 다른 Grade — 같은 이름은 서버가 거절한다(그게 맞다). */
const RUN_ID = `E2EMT${Date.now().toString().slice(-8)}`

test.describe.configure({ mode: 'serial' })

test('문헌 물성부터 혼합 덱까지', async ({ page }) => {
  await test.step('로그인', async () => {
    await page.goto('/')
    await page.getByLabel('아이디').fill(EMAIL)
    await page.getByLabel('비밀번호').fill(PASSWORD)
    await page.getByRole('button', { name: '로그인' }).click()
    await expect(page.getByRole('banner')).toBeVisible()
  })

  await test.step('문헌 카탈로그 — 검색과 상세', async () => {
    await page.goto('/catalog')
    await expect(page.getByText('문헌 물성', { exact: true }).first()).toBeVisible()
    await page.getByPlaceholder('재료 이름으로 검색').fill('SAC305')
    // 디바운스 검색 — 목록에 뜰 때까지.
    await page.getByRole('link', { name: /SAC305/ }).first().click()
    // 상세: 채우기·등록 입구와 값 표가 선다.
    await expect(page.getByRole('button', { name: '사내 재료에 채우기' })).toBeVisible()
    await expect(page.getByRole('button', { name: '사내 재료로 등록' })).toBeVisible()
  })

  await test.step('사내 재료로 등록 — 세 겹 지칭', async () => {
    await page.getByRole('button', { name: '사내 재료로 등록' }).click()
    const dialog = page.getByRole('dialog', { name: '사내 재료로 등록' })
    await expect(dialog).toBeVisible()
    // Grade 를 실행 고유값으로 — 별칭(원본 이름)은 프리필된 그대로 둔다.
    await dialog.getByRole('textbox').nth(2).fill(RUN_ID)
    await dialog.getByRole('button', { name: '만들고 연결' }).click()

    // 재료 상세에 도착: 이름·불변 번호(M-…)·문헌 연결이 함께 보인다.
    await expect(page.getByRole('banner')).toBeVisible()
    await expect(page.getByText(new RegExp(RUN_ID)).first()).toBeVisible()
    await expect(page.getByText(/M-\d{6}/).first()).toBeVisible()
  })

  await test.step('문헌에서 채우기 — 물성 탭', async () => {
    // 사이드바의 영역 탭(「재료 물성」·「복합 물성」)도 tab 이라 exact 로 집는다.
    await page.getByRole('tab', { name: '물성', exact: true }).click()
    // 연결이 걸려 있으므로 「채우기」 가 바로 있다.
    await page.getByRole('button', { name: '채우기', exact: true }).click()
    const adopt = page.getByRole('dialog', { name: /채우기/ })
    await expect(adopt).toBeVisible()
    // 기본 선택(대표값) 그대로 담는다 — 공칭 강도(항복·인장)가 담기는 경로다.
    await adopt.getByRole('button', { name: /건 담기/ }).click()
    await expect(adopt.getByText('담았습니다.')).toBeVisible()
    await adopt.getByRole('button', { name: '닫기' }).click()
  })

  await test.step('측정법 — 물성에서 장비까지', async () => {
    await page.goto('/metrology')
    await expect(page.getByText('보유 장비', { exact: true })).toBeVisible()
    // 잴 수 있는 물성 하나를 고르면 기법별 표가 선다.
    await page
      .getByRole('button', { name: /탄성계수/ })
      .first()
      .click()
    await expect(page.getByRole('columnheader', { name: '장비' }).first()).toBeVisible()
  })

  await test.step('BOM 혼합 덱 — 붙여넣기부터 파일까지', async () => {
    await page.goto('/cards/bom-deck')
    await page.getByPlaceholder(/SUS304/).fill('1, SAC305')
    await page.getByRole('button', { name: '매칭', exact: true }).click()
    await expect(page.getByText(/매칭 확인/)).toBeVisible()

    // 이 줄이 아직 실릴 수 없으면(기억 없음) 문헌 후보를 고른다 — 후보는
    // 반드시 있다(위에서 상세까지 봤던 그 재료다).
    const row = page.getByRole('row').filter({ hasText: 'SAC305' }).first()
    if (await row.getByText('건너뜀 — 매칭 없음').isVisible()) {
      const picker = row.getByRole('combobox')
      await picker.selectOption({ index: 1 })
    }
    await expect(row.getByText(/사내 카드 \(곡선\)|문헌 스칼라/)).toBeVisible()

    await page.getByRole('button', { name: '덱 만들기' }).click()
    // 파일 버튼이 뜨면 빌드·각주·합본이 끝에 닿은 것이다.
    await expect(page.getByRole('button', { name: /bom_deck_.*\.k/ })).toBeVisible()
  })

  await test.step('워크벤치 — 입구가 서 있다', async () => {
    // 워크벤치는 부서 아래 산다 — 사이드바 링크를 그대로 밟는다.
    await page.getByRole('link', { name: '워크벤치' }).click()
    await expect(page.getByText('BOM 혼합 덱').first()).toBeVisible()
  })
})
