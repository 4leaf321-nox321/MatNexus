/**
 * 클립보드에 쓴다 — **HTTP 로 열어도 되게.**
 *
 * `navigator.clipboard` 는 **보안 컨텍스트에서만 있다** — HTTPS 이거나
 * `localhost` 일 때다. 사내망 IP 로 HTTP 로 열면 그 객체 자체가 없어서, 그것만
 * 쓰면 복사 버튼이 개발 기계에서는 되고 **실제 쓰는 자리에서만 조용히 안 된다.**
 * 그런 종류의 실패가 가장 늦게 발견된다.
 *
 * 그래서 세 갈래로 간다.
 *
 *     1. `navigator.clipboard`      있으면 쓴다 (권한 거부될 수도 있다)
 *     2. `document.execCommand`     낡았지만 HTTP 에서 동작한다
 *     3. 실패                       화면이 "직접 복사하세요" 를 말할 수 있게 알린다
 *
 * 2번은 폐기 예정 API 다. 그래도 두는 이유는 **대안이 없기 때문**이다 — 폐기가
 * 실제로 제거로 이어지면 그때 3번만 남는다.
 */

/** 복사에 성공했는가. **거짓이면 화면이 다른 길을 보여 줘야 한다.** */
export async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 권한 거부·포커스 없음. 아래 길로 내려간다.
    }
  }
  return legacyCopy(text)
}

/**
 * 보이지 않는 상자에 넣고 선택해서 복사한다.
 *
 * `position: fixed` 와 `opacity: 0` 을 쓰는 이유 — 화면 밖(`left: -9999px`)에
 * 두면 iOS 에서 선택이 안 되고, `display: none` 이면 선택 자체가 불가능하다.
 */
function legacyCopy(text: string): boolean {
  if (typeof document === 'undefined') return false
  const box = document.createElement('textarea')
  box.value = text
  box.setAttribute('readonly', '')
  box.style.position = 'fixed'
  box.style.top = '0'
  box.style.left = '0'
  box.style.opacity = '0'
  document.body.appendChild(box)

  const selection = document.getSelection()
  const before = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null
  try {
    box.select()
    // 여러 줄이면 `select()` 만으로 안 잡히는 브라우저가 있다.
    box.setSelectionRange(0, text.length)
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    document.body.removeChild(box)
    // **사람이 잡아 둔 선택을 뺏지 않는다.** 표에서 뭔가 골라 둔 채로 복사를
    // 누르면 그것이 풀린다.
    if (before && selection) {
      selection.removeAllRanges()
      selection.addRange(before)
    }
  }
}
