/**
 * 클립보드에 글자를 넣는다 — **두 길을 두고, 순서가 중요하다.**
 *
 * `navigator.clipboard` 는 보안 컨텍스트(https 또는 localhost)에서만 있다.
 * 사내에서 개발 서버를 IP 로 열어 쓰는 일이 흔한데(`http://10.x.x.x:5190`),
 * 그때 이 객체가 아예 없거나 있어도 거절한다. **버튼을 눌러도 아무 일이 안
 * 일어나고 오류도 안 난다** — 사람은 복사가 됐다고 믿고 엑셀에서 빈 칸을 붙여
 * 넣는다.
 *
 * ## 실제로 안 되던 이유 둘 (2026-08-26)
 *
 * 되돌아 갈 길을 만들어 뒀는데도 안 됐다. 둘이 겹쳐 있었다.
 *
 * **하나 — 숨은 칸을 `body` 에 붙였다.** 복사 단추는 모달 안에 있다. Radix
 * 다이얼로그는 열릴 때 바깥 형제들에 `aria-hidden`/inert 를 걸고 초점을 가둔다.
 * `body` 에 붙인 `textarea` 는 그 가려진 쪽에 들어가서, `select()` 가 쓸 수 있는
 * 선택을 못 만든다 — `execCommand('copy')` 가 빈 것을 복사한다.
 *
 * **둘 — 되돌아 가기 전에 `await` 했다.** `execCommand` 는 **사용자 몸짓과 같은
 * 작업 안에서만** 동작한다. `navigator.clipboard.writeText` 를 기다렸다가
 * 거절당한 뒤에 부르면 그 작업은 이미 끝나 있어서, 두 번째 길도 막힌다.
 *
 * 그래서 **보안 컨텍스트가 아니면 비동기 API 를 아예 안 건드린다.**
 */

/**
 * 숨은 칸을 어디에 붙일까.
 *
 * 모달이 열려 있으면 **그 안에** 붙인다 — 바깥은 `aria-hidden`/inert 라서
 * 선택이 안 잡힌다. 열린 모달이 없으면 `body` 로 충분하다.
 */
function container(): HTMLElement {
  const active = document.activeElement
  const inside =
    active instanceof Element ? active.closest('dialog, [role="dialog"]') : null
  return (inside as HTMLElement | null) ?? document.body
}

/** 숨은 칸으로 복사한다. **동기다** — 사용자 몸짓과 같은 작업 안에서 끝내야 한다. */
function copyByTextarea(text: string): boolean {
  const host = container()
  const box = document.createElement('textarea')
  box.value = text
  // 화면 밖에 두되 `display:none` 은 안 된다 — 안 보이는 요소는 선택이 안 된다.
  box.style.position = 'fixed'
  box.style.top = '-1000px'
  box.style.opacity = '0'
  box.setAttribute('readonly', '')
  // 모달의 초점 가둠이 이 칸을 되돌려 보내지 않게 한다.
  box.setAttribute('aria-hidden', 'true')
  host.appendChild(box)
  try {
    box.focus()
    box.select()
    box.setSelectionRange(0, text.length)
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    host.removeChild(box)
  }
}

export async function copyText(text: string): Promise<boolean> {
  // **보안 컨텍스트가 아니면 비동기 API 를 안 건드린다.** 거절을 기다리는
  // 순간 사용자 몸짓이 끝나고, 그러면 되돌아 갈 길까지 막힌다.
  if (!window.isSecureContext || !navigator.clipboard?.writeText) {
    return copyByTextarea(text)
  }
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // 권한이 거절됐다. 몸짓은 이미 끝났을 수 있지만 한 번은 해 본다 —
    // 브라우저에 따라 아직 되는 경우가 있다.
    return copyByTextarea(text)
  }
}
