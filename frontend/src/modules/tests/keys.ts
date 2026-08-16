/**
 * 열 이름 → 채널 키. **서버 규칙(`^[a-z][a-z0-9_]*$`)을 화면이 지킨다.**
 *
 * 같은 일을 두 화면이 각자 구현하고 있었고, 둘 다 서버 규칙과 조금씩 달랐다.
 *
 *   프로파일 편집기  숫자로 시작해도 통과 → `1/temperature` 가 `1_temperature`
 *                    가 되어 저장할 때 422. **실제로 그런 열이 있다** — DMA 의
 *                    TTS 마스터 곡선에 `1/temperature` 가 들어 있다
 *   시험종류 편집기  앞의 숫자를 떨어뜨림 (이쪽이 맞았다)
 *
 * 규칙을 한 곳에 둔다. 서버가 최종 판정을 하지만, **거절당할 값을 만들어 보내는
 * 화면은 사람에게 이유를 설명할 수 없다.**
 */

/** 소문자·숫자·밑줄, 첫 글자는 영문. 못 만들면 빈 문자열. */
export function toChannelKey(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^[^a-z]+/, '') // 서버 규칙: 첫 글자는 반드시 영문
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
}

/**
 * 채널 키로 쓸 수 있는가. 화면이 저장 전에 스스로 확인한다.
 *
 * 열 이름이 숫자나 기호로만 되어 있으면 키를 만들 수 없다(`1/temperature` 의
 * 앞 숫자를 떼면 `temperature` 지만, `1/2` 는 아무것도 안 남는다).
 */
export function isValidChannelKey(key: string): boolean {
  return /^[a-z][a-z0-9_]*$/.test(key)
}
