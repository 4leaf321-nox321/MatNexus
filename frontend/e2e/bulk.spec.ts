import { expect, test } from '@playwright/test'

const EMAIL = process.env.MNX_ADMIN_EMAIL ?? 'admin'
const PASSWORD = process.env.MNX_ADMIN_PASSWORD ?? '32167'

test('채널을 여러 개 붙여넣는다', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/')
  await page.getByLabel('아이디').fill(EMAIL)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page.getByRole('banner')).toBeVisible()

  await page.goto('/settings/test-types')
  await page.getByRole('button', { name: /종류 만들기|만들기/ }).first().click()
  const editor = page.getByRole('dialog')
  await expect(editor.getByText('채널 (곡선의 열)')).toBeVisible()

  await editor.getByRole('button', { name: '여러 개 넣기' }).first().click()
  await expect(page.getByText('채널 여러 개 넣기')).toBeVisible()

  // 엑셀에서 복사한 것처럼 탭으로 갈린 여러 줄을 첫 칸에 붙인다.
  const first = page.getByLabel('1번 줄 키')
  await first.click()
  await page.evaluate(async () => {
    await navigator.clipboard.writeText(
      [
        'Angular frequency\t각주파수\tangular_frequency\tY',
        'Storage modulus\t저장탄성률\t응력\t',
        'Temperature\t온도\t온도\t',
        'Bad row\t나쁜 줄\t길이(mm)\t',
      ].join('\n')
    )
  })
  await page.keyboard.press('Control+V')

  // 문제 있는 줄은 말하고, 나머지는 넣는다.
  await expect(page.getByText(/1줄은 못 넣습니다/)).toBeVisible()
  await expect(page.getByText(/길이\(mm\)/)).toBeVisible()

  const add = page.getByRole('button', { name: /3줄 넣기/ })
  await expect(add).toBeVisible()
  await add.click()

  // 실제로 세 줄이 목록에 붙었나.
  for (const key of ['angular_frequency', 'storage_modulus', 'temperature']) {
    await expect(page.getByRole('textbox').filter({ hasText: '' }).and(page.locator(`input[value="${key}"]`))).toHaveCount(1)
  }
  await page.screenshot({ path: 'test-results/bulk-channels.png', fullPage: true })
})
