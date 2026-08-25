/**
 * 클립보드에 글자를 넣는다 — **두 길을 둔다.**
 *
 * `navigator.clipboard` 는 보안 컨텍스트(https 또는 localhost)에서만 있다.
 * 사내에서 개발 서버를 IP 로 열어 쓰는 일이 흔한데, 그때 이 객체가 아예
 * `undefined` 라서 **버튼을 눌러도 아무 일도 안 일어난다.** 오류도 안 난다 —
 * 사람은 복사가 됐다고 믿고 엑셀에서 빈 칸을 붙여 넣는다.
 *
 * 그래서 없으면 숨은 `textarea` 로 떨어진다. `execCommand` 는 낡았지만 이
 * 상황에서 유일하게 되는 길이고, 되는지 여부를 돌려준다.
 */

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 권한이 거절됐다. 아래 길로 한 번 더 해 본다.
  }

  const box = document.createElement('textarea')
  box.value = text
  // 화면 밖에 두되 `display:none` 은 안 된다 — 안 보이는 요소는 선택이 안 된다.
  box.style.position = 'fixed'
  box.style.top = '-1000px'
  box.setAttribute('readonly', '')
  document.body.appendChild(box)
  try {
    box.select()
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(box)
  }
}
