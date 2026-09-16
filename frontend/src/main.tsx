import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from '@/App'
import '@/index.css'

// **청크를 못 받으면 한 번 새로고침한다.** 화면을 열어 둔 채 배포가 지나가면 브라우저의
// 옛 index.html 이 사라진 청크(해시 이름)를 부르고, 그 화면은 "Failed to fetch
// dynamically imported module" 로 안 열린다. 새로고침하면 새 index 를 받아 되므로 그것을
// 사람 대신 한다. 짧은 사이에 두 번은 안 한다 — 서버가 내려간 동안(배포 재시작)이라면
// 무한히 돌기 때문이다. 그때는 오류가 그대로 보이고, 사람이 잠시 뒤 새로고침한다.
const RELOAD_KEY = 'mnx:chunk-reload-at'
const RELOAD_GAP_MS = 30_000
window.addEventListener('vite:preloadError', (event) => {
  let allowed = false
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0)
    allowed = Date.now() - last > RELOAD_GAP_MS
    if (allowed) sessionStorage.setItem(RELOAD_KEY, String(Date.now()))
  } catch {
    // 저장소가 막힌 브라우저 — 되풀이를 막을 길이 없으니 한 번도 안 한다.
  }
  if (!allowed) return
  event.preventDefault()
  window.location.reload()
})

const container = document.getElementById('root')
if (!container) throw new Error('#root 를 찾을 수 없습니다')

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
