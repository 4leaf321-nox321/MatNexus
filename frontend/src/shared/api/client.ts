/**
 * API 클라이언트.
 *
 * 절대 주소를 갖지 않는다. 개발에서는 Vite 프록시가, 배포에서는 같은 프로세스가
 * `/api` 를 받는다. 52는 빌드 시 API 주소를 굽는 방식이라 값이 빠지면 사용자
 * 브라우저가 자기 PC를 부르는 사고가 났고, 그걸 막으려고 빌드 산출물을 검사하는
 * 단계를 따로 두어야 했다. 상대경로면 그 사고 자체가 없다.
 *
 * **access 토큰은 여기 메모리에만 둔다.** localStorage에 두면 XSS 한 번에
 * 탈취된다. 새로고침하면 사라지지만, refresh 쿠키(httpOnly)로 다시 받아온다.
 */

const BASE = '/api'

/** 백엔드 오류 규약 (app/shared/errors.py 와 짝) */
export interface ApiErrorBody {
  error: {
    code: string
    message: string
    request_id?: string
    details?: Record<string, unknown>
  }
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly requestId: string | undefined
  readonly details: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.error.code
    this.requestId = body.error.request_id
    this.details = body.error.details ?? {}
  }
}

let accessToken: string | null = null
let onSessionLost: (() => void) | null = null

export const session = {
  setToken(token: string | null) {
    accessToken = token
  },
  getToken() {
    return accessToken
  },
  /** 갱신까지 실패했을 때 호출된다 — AuthContext가 로그인 화면으로 보낸다. */
  onLost(handler: (() => void) | null) {
    onSessionLost = handler
  },
}

/** 봉투인가. **모양을 확인하고 나서 읽는다**(ADR 0001 의 오류 규약). */
function isEnvelope(value: unknown): value is ApiErrorBody {
  const error = (value as ApiErrorBody | null)?.error
  return typeof error?.code === 'string' && typeof error?.message === 'string'
}

/**
 * 서버가 봉투 대신 무언가를 말했다면 **그 말을 살린다.**
 *
 * FastAPI·Starlette 은 `{"detail": "..."}` 로 낸다. 그것을 버리고 "예상하지 못한
 * 응답" 만 띄우면 무엇이 잘못됐는지가 통째로 사라진다.
 */
function said(value: unknown): string {
  const detail = (value as { detail?: unknown } | null)?.detail
  return typeof detail === 'string' && detail ? ` — ${detail}` : ''
}

/**
 * 오류 응답을 `ApiError` 로. **여기서 오류가 나면 안 된다.**
 *
 * **실사용에서 걸렸다.** 서버가 봉투가 아닌 JSON(`{"detail": ...}`)을 내자
 * `body.error.message` 가 터졌고, 화면에는 원인 대신
 * `Cannot read properties of undefined (reading 'message')` 가 떴다 — 사람은
 * 요청이 왜 실패했는지가 아니라 **프론트가 깨졌다**고 읽는다.
 *
 * 전에도 이 자리는 "규약 밖이면 그 사실을 드러낸다" 고 적어 두었는데, 막고 있던
 * 것은 **JSON 이 아닌 경우뿐**이었다. 파싱은 되는데 모양이 다른 쪽이 남아 있었고,
 * 실제로 온 것은 그쪽이다.
 */
async function parseError(response: Response): Promise<ApiError> {
  let parsed: unknown = null
  try {
    parsed = await response.json()
  } catch {
    // JSON 도 아니다 — HTML 오류 페이지나 빈 본문.
  }
  if (isEnvelope(parsed)) return new ApiError(response.status, parsed)
  return new ApiError(response.status, {
    error: {
      code: 'MNX-CLIENT-0001',
      message: `서버가 예상하지 못한 응답을 보냈습니다 (HTTP ${response.status})${said(parsed)}`,
    },
  })
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  // FormData 일 때 Content-Type 을 직접 넣으면 **안 된다.** multipart 는 본문에
  // boundary 문자열이 필요한데, 브라우저가 헤더를 만들 때 그것을 붙여 준다.
  // 우리가 'multipart/form-data' 만 적으면 boundary 가 빠져 서버가 못 읽는다.
  const isForm = init?.body instanceof FormData
  return fetch(`${BASE}${path}`, {
    ...init,
    credentials: 'same-origin', // refresh 쿠키
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(init?.headers ?? {}),
    },
  })
}

/** 조용한 갱신. 성공하면 새 access 토큰을 보관한다. */
export async function tryRefresh(): Promise<boolean> {
  const response = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    credentials: 'same-origin',
  })
  if (!response.ok) return false
  const body = (await response.json()) as { access_token: string }
  accessToken = body.access_token
  return true
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response = await send(path, init)

  // access 는 12시간이면 만료된다. 사용자가 그 순간 하던 일을 잃지 않도록
  // 한 번만 조용히 갱신하고 재시도한다. /auth/* 는 제외 — 갱신 자체가 실패한
  // 상황에서 무한 재귀가 된다.
  if (response.status === 401 && !path.startsWith('/auth/')) {
    if (await tryRefresh()) {
      response = await send(path, init)
    } else {
      onSessionLost?.()
    }
  }

  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/**
 * 토큰을 실어 받아 온다. **브라우저가 스스로 여는 요청은 이것을 못 한다.**
 *
 * `<a href>` · `<img src>` · `<iframe>` 처럼 브라우저가 직접 여는 주소에는
 * Authorization 헤더가 안 실린다 — access 토큰은 메모리에만 있고 쿠키가 아니라서다
 * (XSS 방어). 그래서 그런 자리에는 **여기서 받아 만든 blob 주소**를 넣는다.
 *
 * 실측(2026-08-29): 핸드북 그림 75개가 전부 안 나왔다. 본문이 `<img
 * src="/api/guide/assets/…">` 였고 서버는 401 을 냈다. 아래 `downloadFile` 이 이미
 * 같은 함정을 적어 두었는데, 그림을 붙일 때 그 교훈을 안 썼다.
 */
export async function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  // **`/api` 로 시작하면 이미 붙어 있는 것이다.** 본문에 저장된 그림 주소가
  // `/api/guide/assets/<id>` 라서 그대로 넘기면 `send` 가 앞에 `/api` 를 한 번 더
  // 붙여 `/api/api/…` 가 되고, 라우트에 안 닿아 **404** 가 난다(2026-08-29 실측 —
  // 401 을 고치고 나니 이번엔 404 였다). 부르는 쪽이 매번 떼게 두면 잊는다.
  const relative = path.startsWith(`${BASE}/`) ? path.slice(BASE.length) : path
  let response = await send(relative, init)
  if (response.status === 401 && !relative.startsWith('/auth/')) {
    // **다시 보낼 때도 같은 요청이어야 한다.** 몸통을 빼고 다시 보내면 갱신 뒤
    // 요청이 조용히 GET 이 되고, 그때 서버는 405 나 빈 결과를 낸다.
    if (await tryRefresh()) response = await send(relative, init)
    else onSessionLost?.()
  }
  return response
}

/**
 * 파일 내려받기. **`<a href>` 로는 안 된다.**
 *
 * access 토큰은 메모리에만 있고(XSS 방어) 쿠키가 아니므로, 브라우저가 스스로
 * 여는 링크에는 실리지 않는다. 그래서 평범한 링크는 항상 401 이 나는데, 그 오류는
 * 새 탭에서 나므로 **화면에는 아무 표시도 안 뜬다** — 사용자는 아무 일도 안
 * 일어난 것처럼 본다. 토큰을 붙여 받아 온 뒤 브라우저에 넘긴다.
 */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetchWithAuth(path)
  if (!response.ok) throw await parseError(response)

  const url = URL.createObjectURL(await response.blob())
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
  } finally {
    // 즉시 해제하면 저장이 시작되기 전에 사라지는 브라우저가 있다.
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }
}

/**
 * 몸통을 보내고 파일을 받는다 — 묶음 내보내기처럼 **고른 것이 여럿일 때.**
 *
 * `downloadFile` 은 GET 이라 고른 카드 목록을 주소에 실어야 하는데, 100장이면
 * 주소가 길이 제한에 걸린다. 그리고 「무엇을 골랐나」 는 서버 로그에 남기기에도
 * 주소보다 몸통이 맞다.
 */
export async function downloadPostFile(
  path: string,
  body: unknown,
  filename: string
): Promise<void> {
  const response = await fetchWithAuth(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!response.ok) throw await parseError(response)

  const url = URL.createObjectURL(await response.blob())
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) }),
  /** 파일 업로드. 토큰 갱신·오류 규약을 JSON 요청과 똑같이 탄다. */
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),
  /** 정의처럼 '한 벌을 통째로 갈아 끼우는' 자원에 쓴다. */
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) }),
  // DELETE 에도 본문을 허용한다 — 계정 삭제는 "누구에게 승계할지"를 함께 받는다.
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'DELETE',
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
}
