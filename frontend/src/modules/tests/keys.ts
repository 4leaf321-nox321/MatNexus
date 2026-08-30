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
 * **매핑을 안 한 열의 키.** 서버가 그렇게 만든다(`matcore/readers/profile.py` 의
 * `slug`) — `key = mapping.channel or slug(name)`.
 *
 * `toChannelKey` 와 다르다. 이쪽은 **서버가 실제로 무엇을 저장할지 예측**하는
 * 것이라 서버 규칙을 그대로 옮긴다: 한글을 남기고(국산 장비 라벨이 통째로
 * 지워지면 둘이 서로 덮는다), 앞의 숫자도 남긴다(`1/temperature` →
 * `1_temperature`). 저쪽은 **사람이 새로 만들 채널 키**라 서버의 채널 규칙
 * (`^[a-z][a-z0-9_]*$`)을 따른다.
 *
 * 둘을 한 함수로 합치면 안 된다 — 예측이 틀리면 화면이 「이 열은 `temperature`
 * 로 들어갑니다」 라고 적어 놓고 실제로는 `1_temperature` 로 저장된다.
 */
export function toFallbackKey(text: string): string {
  const key = text
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_]+/gu, '_')
    .replace(/^_+|_+$/g, '')
  return key || 'unnamed'
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
