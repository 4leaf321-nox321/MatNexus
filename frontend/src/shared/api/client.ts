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

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody
  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    // 오류 응답이 JSON이 아니면 규약 밖이다 — 그 사실 자체를 드러낸다.
    body = {
      error: {
        code: 'MNX-CLIENT-0001',
        message: `서버가 예상하지 못한 응답을 보냈습니다 (HTTP ${response.status})`,
      },
    }
  }
  return new ApiError(response.status, body)
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
 * 파일 내려받기. **`<a href>` 로는 안 된다.**
 *
 * access 토큰은 메모리에만 있고(XSS 방어) 쿠키가 아니므로, 브라우저가 스스로
 * 여는 링크에는 실리지 않는다. 그래서 평범한 링크는 항상 401 이 나는데, 그 오류는
 * 새 탭에서 나므로 **화면에는 아무 표시도 안 뜬다** — 사용자는 아무 일도 안
 * 일어난 것처럼 본다. 토큰을 붙여 받아 온 뒤 브라우저에 넘긴다.
 */
export async function downloadFile(path: string, filename: string): Promise<void> {
  let response = await send(path)
  if (response.status === 401 && !path.startsWith('/auth/')) {
    if (await tryRefresh()) response = await send(path)
    else onSessionLost?.()
  }
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
