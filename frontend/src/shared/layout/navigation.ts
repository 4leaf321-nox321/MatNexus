/**
 * 사이드바 메뉴 정의 (개발계획 §5).
 *
 * 메뉴를 컴포넌트에서 분리해 두는 이유: 어떤 화면이 있어야 하는지가 한 곳에
 * 적혀 있어야 라우터·사이드바·권한이 서로 어긋나지 않는다. RA도 같은 형태다.
 *
 * `resolve` 는 부서(workspace) 스코프 경로다. 부서 모델은 Phase 1에서 들어오고,
 * 그전까지는 DEFAULT_WORKSPACE 를 쓴다.
 */

import {
  Bell,
  BookOpen,
  Boxes,
  BookMarked,
  Building2,
  ClipboardList,
  FileCode2,
  FileOutput,
  FileDown,
  FlaskConical,
  Gauge,
  GitCompare,
  Home,
  Layers,
  ListTree,
  Lock,
  Megaphone,
  Package,
  Plug,
  Ruler,
  ScrollText,
  Server,
  ShieldCheck,
  Sigma,
  SlidersHorizontal,
  Split,
  Tags,
  Trash2,
  UserCog,
  Wrench,
  Users,
  Workflow,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** 부서 모델이 없는 동안 쓰는 임시 slug. Phase 1에서 실제 소속 부서로 대체된다. */
export const DEFAULT_WORKSPACE = 'default'

/**
 * 영역 — 사이드바 맨 위에서 갈라지는 두 세계.
 *
 * **재료 물성**은 재료 → 시료 → 시편 → 시험의 사슬이고, **복합 물성**은 여러
 * 층·재료가 결합된 부품 단품에서 나오는 것이다 — 층별 물성을 따로 잴 수 없어
 * 복합체를 시험하고 역공학으로 뽑는 값, 층 하나가 바뀌었을 때의 거동 차이, 시장
 * 불량을 재현하는 시험법(ADR 0026).
 *
 * **한 틀에 넣지 않는다.** 시편 층위에서 이미 이름 규칙·필수 칸(방향)·치수 해석이
 * 다르다. 같은 메뉴에 두면 구성체 시편에 「방향」 을 억지로 채우거나 `NA` 로 두게
 * 된다 — 이관에서 이미 겪은 냄새다. 대신 **엔진**(파일 읽기·곡선·처리·카드·
 * 기준정보·권한)만 공유하고, 화면과 계층은 갈라선다.
 *
 * 영역이 없는 그룹(내 활동·공통·데이터 체계·내 부서·관리)은 양쪽에 다 선다.
 */
export type NavRealm = 'material' | 'composite'

export const REALM_ORDER: NavRealm[] = ['material', 'composite']

export const REALMS: Record<
  NavRealm,
  { label: string; hint: string; home: (slug: string) => string }
> = {
  material: {
    label: '재료 물성',
    hint: '재료 → 시료 → 시편 → 시험 — 잰 값',
    home: (slug) => `/w/${slug}`,
  },
  composite: {
    label: '복합 물성',
    hint: '부품 → 구성체 → 시험법 → 역공학 — 추정값',
    home: () => '/composite',
  },
}

/**
 * 누구에게 보이는가.
 *
 * **없으면 누르고 나서 403 을 본다.** 지금까지 사이드바가 역할을 안 봐서, 평범한
 * 멤버에게도 계정·부서·저장소 정리가 보였다. 눌러야 권한이 없다는 것을 아는
 * 화면은 "할 수 있는 일" 을 알려 주지 못한다.
 *
 * 이것은 **표시**일 뿐 권한이 아니다. 권한은 서버가 판정한다 — 사이드바를 고쳐
 * 우회할 수 있으면 그건 애초에 보안이 아니다.
 */
export type NavAudience = 'everyone' | 'manager' | 'system_admin'

export interface NavItem {
  label: string
  icon: LucideIcon
  /** 고정 경로 */
  to?: string
  /** 부서 스코프 경로 */
  resolve?: (slug: string) => string
  /** NavLink 의 end 옵션 (부모 경로가 자식에도 활성화되지 않게) */
  end?: boolean
  /** 기본은 `everyone`. */
  audience?: NavAudience
  /** 아직 화면이 없다(stub). 사이드바가 「미구현」 표를 단다 — **자리는 보이되
   *  눌러 보고 알게 하지 않는다.** 화면이 생기면 이 표시를 지운다. */
  pending?: boolean
  /** `pending` 인 것이 로드맵의 어느 단계에서 들어오는가. 복합 물성 개요 화면이
   *  이것으로 「무엇이 언제 오는지」 를 그린다 — 사이드바가 곧 로드맵이다. */
  phase?: string
  /** 한 줄 설명. 개요 화면과 stub 화면이 같은 말을 하도록 여기 한 번만 적는다. */
  summary?: string
}

export interface NavGroup {
  /** 없으면 제목 없이 항목만 선다. **한 항목짜리 그룹에는 제목을 안 단다** —
   *  제목은 「여기 여럿이 있다」 는 신호라서, 하나뿐인데 달면 거짓말이 된다. */
  title?: string
  items: NavItem[]
  /** 그룹 전체가 안 보이는 조건. 항목이 하나도 안 보이면 제목도 지운다. */
  audience?: NavAudience
  /** 어느 영역의 것인가. 없으면 양쪽 영역에 다 선다. */
  realm?: NavRealm
}

export const NAV_GROUPS: NavGroup[] = [
  {
    // **제목이 없다.** 「부서」 라는 제목 아래 홈·시험·워크벤치가 있었는데, 셋 다
    // 부서의 것이 아니었다 — 시험은 카탈로그의 사슬이고 워크벤치는 개인 작업대다.
    // 둘을 옮기고 나니 홈만 남았고, 하나짜리에 제목을 달면 「여기 더 있다」 로
    // 읽힌다.
    realm: 'material',
    items: [{ label: '홈', icon: Home, resolve: (s) => `/w/${s}`, end: true }],
  },
  {
    // **데이터 사슬.** 재료 → 시편 → 시험 → 물성 카드 순으로 선다 — 화면의
    // 차례가 데이터가 만들어지는 차례여야 사람이 「다음에 어디로」 를 안 묻는다.
    title: '카탈로그',
    realm: 'material',
    items: [
      { label: '재료', icon: Boxes, to: '/materials' },
      // **규격으로 찾는 자리다.** 규격·방향·치수는 시편에 붙는데(ADR 0010)
      // 시편은 재료를 거쳐야만 닿을 수 있었다 — 그래서 규격으로는 아무것도
      // 못 찾았다. 카드가 `/cards` 를 얻은 것과 같은 이유다.
      { label: '시편', icon: ListTree, to: '/specimens' },
      // **시편 바로 아래다.** 「시험 데이터」 라는 이름으로 부서 그룹에 혼자
      // 있었는데, 시험은 시편에 붙는 것이라 사슬에서 떨어져 있을 이유가 없었다.
      // 이름에서 「데이터」 도 뺐다 — 옆의 재료·시편·물성 카드가 다 명사 하나다.
      //
      // **경로도 전역으로 옮겼다.** `/w/<부서>/tests` 였는데, 그러면 재료는 전부
      // 보이고 시험만 자기 부서 것만 보인다 — 같은 그룹에서 범위가 다르면
      // 「시험이 이것뿐인가」 로 읽힌다. 부서로 좁힌 목록은 홈에서 들어간다.
      { label: '시험', icon: FlaskConical, to: '/tests' },
      // **재료를 거치지 않고 카드를 찾는다.** 재료 상세의 'CAE 카드' 탭은 그
      // 재료의 것만 보므로, "그 카드가 어느 재료였더라" 에 답할 데가 없었다.
      { label: '물성 카드', icon: FileDown, to: '/cards' },
      { label: '물성 분석', icon: GitCompare, to: '/compare' },
      // **문헌 물성 — 실물 없는 재료의 물성 저수지**(ADR 0027, MaterialTwin 이관).
      // 사슬(재료→시편→시험→카드)의 마디가 아니라 사슬 밖의 참고 자료라 맨 뒤에
      // 선다. 사내 재료와는 연결·채택으로 잇는다.
      { label: '문헌 물성', icon: BookMarked, to: '/catalog' },
      // 측정법 — 물성마다 어떤 기법·장비로 재는지. 문헌 물성의 옆 답이다.
      { label: '측정법', icon: Ruler, to: '/metrology' },
    ],
  },

  // ── 복합 물성 영역 ────────────────────────────────────────────────────
  //
  // **동선이 곧 그룹 순서다.** 불량 모드·구성체를 정하고(대상) → 시험법을 만들어
  // 부품을 시험하고(시험 운영) → 역공학과 방법론으로 기준을 세운다(해석). 그룹은
  // 넷을 넘기지 않는다 — 늘어나면 동선이 안 보인다.
  //
  // **전부 「미구현」 이다**(2026-09-05). 화면 자리를 먼저 세워 두고 관계자와 개발
  // 방향을 논의한다 — 스키마(ADR 0026)는 MX 의 현행 시험 데이터 체계를 확인한
  // 뒤 확정된다(플랫폼-요구사항-MX확인요청). 그 전에 만든 화면은 짐작이다.
  {
    realm: 'composite',
    items: [{ label: '홈', icon: Home, to: '/composite', end: true }],
  },
  {
    title: '대상',
    realm: 'composite',
    items: [
      {
        label: '부품',
        icon: Package,
        to: '/composite/parts',
        pending: true,
        phase: '1단계',
        summary: '부품 코드(기준정보) 아래 구성체 목록. 시장 불량과 조인되는 키.',
      },
      {
        // **재료와 나란한 두 번째 뿌리다**(ADR 0026 D1). 층 순서·두께·접합, 그리고
        // 변형체 — 부모와 「무엇이 다른가」 가 1급 데이터다. 판별의 질문이 여기서 선다.
        label: '구성체',
        icon: Layers,
        to: '/composite/assemblies',
        pending: true,
        phase: '1단계',
        summary: '층 구조와 변형체 트리. 변형체 노드에 「무엇이 다른가」 배지.',
      },
    ],
  },
  {
    title: '시험 운영',
    realm: 'composite',
    items: [
      {
        // **시험 종류 위의 개념이다**(ADR 0026 D4). 종류는 데이터의 모양이고,
        // 시험법은 그 종류로 무엇을 어떻게 하는가 — 목적(불량 모드)·시나리오·
        // 지그·판정·성숙도·개정.
        label: '시험법',
        icon: ClipboardList,
        to: '/composite/methods',
        pending: true,
        phase: '1단계',
        summary: '성숙도(초안·시범·검증·규격)별 목록, 버전, 재현율. 시험이 곧 증거.',
      },
      {
        label: '부품 시험',
        icon: FlaskConical,
        to: '/composite/part-tests',
        pending: true,
        phase: '1단계',
        summary: '시험법 버전에 묶인 시험. 시나리오·관찰(사진)·재현 판정.',
      },
      {
        label: '시료 배분',
        icon: Split,
        to: '/composite/allocation',
        pending: true,
        phase: '2단계',
        summary: '해석으로 리스크를 도출하고 제한된 시료를 의미 있는 시험에 배분.',
      },
    ],
  },
  {
    title: '해석',
    realm: 'composite',
    items: [
      {
        label: '역공학 실행',
        icon: Sigma,
        to: '/composite/inverse',
        pending: true,
        phase: '2단계',
        summary: '시험 집합 → 층 물성 추정. 자유·고정 파라미터, 적합도, 잔차 곡선.',
      },
      {
        // **측정값과 다른 칸이다**(ADR 0026 D3). 어느 실행에서, 무엇을 고정하고,
        // 불확실성이 얼마인지가 값에 붙는다. 재료 카드에는 배지로만 나간다.
        label: '추정 물성',
        icon: Gauge,
        to: '/composite/estimated',
        pending: true,
        phase: '2단계',
        summary: '층별 추정값. 출처·가정·불확실성·유효 범위·등급.',
      },
      {
        label: '시뮬레이션 방법론',
        icon: Workflow,
        to: '/composite/methodologies',
        pending: true,
        phase: '2단계',
        summary: '모델링·경계조건·물성 할당의 버전. 어느 시험 집합으로 검증됐나.',
      },
      {
        label: '비교·판별',
        icon: GitCompare,
        to: '/composite/comparison',
        pending: true,
        phase: '2단계',
        summary: '기준 구성체 vs 변형체 — 어느 특징이 갈라놓는가.',
      },
    ],
  },
  {
    // **데이터 체계가 아니라 여기다.** 둘 다 복합 물성 쪽의 규칙이고, 데이터 체계
    // 그룹은 「장비 파일이 어떻게 물성이 되는가」 의 사슬이라 성격이 다르다.
    title: '규칙',
    realm: 'composite',
    items: [
      {
        label: '시험법 승격 기준',
        icon: ShieldCheck,
        to: '/composite/rules/method-gates',
        pending: true,
        phase: '1단계',
        summary: '초안 → 시범 → 검증(N건·재현율 r) → 규격(승인). 숫자는 부서 설정.',
      },
      {
        label: '등급·출처 규칙',
        icon: Lock,
        to: '/composite/rules/classification',
        pending: true,
        phase: '1단계',
        summary: '공개·사업부·전략과제 등급, 내부·업체·문헌 출처. 사업부 간 공유 범위.',
      },
    ],
  },

  {
    title: '내 활동',
    items: [
      // **「내 작업함」 을 뺐다**(2026-09-13). 계획서 §5 의 「내가 한 일을 모아 보는
      // 개인 홈」 이었는데, 그 내용은 그 뒤로 네 자리에 나뉘어 생겼다 — 벌여 놓은
      // 일은 워크벤치, 내 차례인 일은 알림, 어디까지 왔나는 부서 홈, 내가 올린
      // 것은 목록의 등록자 거르개. 모으면 워크벤치와 겹치고, 안 만든 채 두면 눌러도
      // 아무것도 없는 문이 메뉴에 떠 있다 — '통계'·'내보내기' stub 에서 겪은 일이다.
      //
      // **워크플로를 골라 여러 대상을 한 업무로 미는 자리**(ADR 0024·0025). 고정
      // 5탭이 아니라 시나리오 목록이다 — 「오늘 들어온 것 처리」·「DMA 한 벌로
      // 점탄성 계수」 처럼.
      //
      // **부서의 것이 아니라 내 작업대다.** 「부서」 그룹에 있었는데, 여러 시험을
      // 골라 한 줄기로 미는 것은 개인이 벌여 놓는 일이지 부서가 공유하는 목록이
      // 아니다.
      //
      // **'통계'와 '내보내기'는 여기 없다.** 계획서 §5 에는 셋이 나란했는데, 그
      // 둘은 각 도메인 화면이 하는 일이다. 빈 stub 으로 두었더니 재료 상세의
      // '물성'·'CAE 카드' 와 이름이 겹쳐 어느 쪽이 진짜인지 알 수 없었다.
      //
      // **「미구현」 배지를 뗐다.** 목록에서 담을 수 있게 된 뒤에도 배지가 남아
      // 있어서, 담고 나서 **돌아올 자리로 안 읽혔다** — 실제로 그 자리에서 걸렸다.
      { label: '워크벤치', icon: SlidersHorizontal, resolve: (s) => `/w/${s}/workbench` },
      { label: '알림', icon: Bell, to: '/notifications' },
      // 팝업이었다가 화면이 됐다 — 액세스 토큰까지 붙자 팝업이 좁았다.
      { label: '내 정보', icon: UserCog, to: '/me' },
    ],
  },
  {
    title: '공통',
    items: [
      // **한 진입점이다.** 둘로 서 있으면 「어느 쪽에 쓰지」 를 매번 묻는다 —
      // 위에서 내려오는 글과 아래에서 올라가는 글일 뿐, 사람에게는 같은
      // 게시판이다. 화면 안에서 탭으로 갈리고 주소는 그대로다(`SubTabs`).
      { label: '공지 · VOC', icon: Megaphone, to: '/notices' },
      { label: '가이드', icon: BookOpen, to: '/guide' },
      // **고르는 사람이 목록을 볼 수 있어야 한다.** 기준정보는 시스템 관리자에게만
      // 보였는데, 그 값을 매일 드롭다운에서 고르는 것은 멤버다. 못 보면 찾는 값이
      // 없을 때 「아직 없다」 인지 「이름이 다르다」 인지 구별할 수 없다.
      //
      // 서버는 이미 열려 있었다(`GET /vocabularies` 는 `current_user`) — 막고
      // 있던 것은 화면뿐이었다. 고치는 자리는 '관리' 의 「기준정보 편집」 이다.
      // **단위도 이 안에 있다.** 따로 세웠다가 넣었다 — 사람이 폼에서 고르는
      // 목록이라는 점에서 기준정보와 같은 것이고, 메뉴에 둘로 서면 「단위가
      // 기준정보가 아닌가」 를 묻게 된다. 화면 왼쪽 축 목록에서 「고칠 수 없는
      // 것」 으로 따로 세운다 — 축은 값을 더할 수 있고 단위는 못 고친다.
      { label: '기준정보', icon: Tags, to: '/vocabulary' },
    ],
  },
  {
    // **넷은 한 사슬이다.**
    //
    //     장비 커넥터  →  파일 형식   →  시험 종류     →  처리 레시피
    //     파일이 온다     어떻게 읽나   무엇을 잰 건가   어떻게 물성이 되나
    //
    // 「장비가 낸 파일이 어떻게 물성이 되는가」 의 네 마디고, 하나라도 빠지면 그
    // 길이 끊긴다. **설정이 아니라 얼개다** — 값을 켜고 끄는 것이 아니라 데이터가
    // 들어오는 길 자체를 정의한다.
    //
    // 전에는 「부서 설정」 이었다. 그 이름은 **누가 하느냐**로 붙은 것인데(장비를
    // 붙이는 것은 사업부의 일이지 시스템 관리자의 일이 아니다), 권한이 이름이
    // 되자 성격이 다른 것들이 딸려 들어왔다 — 부서 멤버와 변경 이력은 이 사슬과
    // 아무 상관이 없다. 아래 '부서' 로 갈랐다.
    //
    // **모두가 본다.** 서버의 읽기 엔드포인트는 넷 다 이미 `current_user` 였다 —
    // 막고 있던 것은 사이드바뿐이었고, 그래서 실험한 사람이 「내 파일이 왜 안
    // 들어왔나」·「이 장비 형식이 뭘로 잡혀 있나」 를 물을 데가 없었다. 고치는
    // 것은 여전히 부서 관리자다(화면이 쓰기 단추를 가린다, `shared/auth/roles`).
    // **'수집' 을 뗐다**(2026-08-30). 솔버 덱 정의가 들어오면서 이 그룹이 더는
    // 들어오는 쪽만이 아니게 됐다 — 장비 파일 정의가 「어떻게 읽나」 라면 덱 정의는
    // 「어떻게 쓰나」 다. 둘 다 **데이터를 무엇으로 다루나** 라는 한 가지 일이고,
    // 쓰는 사람도 같다. 그룹을 하나 더 두는 대신 이름을 넓혔다.
    title: '데이터 체계',
    items: [
      {
        // **사슬의 첫 마디다.** 아래 넷이 「장비가 낸 파일이 어떻게 물성이
        // 되는가」 인데, 그 앞에 **파일을 내는 실물 장비**가 빠져 있었다.
        // 「장비 파일 정의」 가 장비를 대신 가리키고 있었지만 그건 형식이지
        // 장비가 아니다.
        //
        // **카탈로그 그룹(측정법 옆)에 두지 않았다.** 그 그룹은 `realm: 'material'`
        // 이라 복합 물성 영역에서 안 보이는데, 복합 쪽도 부품 시험에 같은 장비를
        // 쓴다 — 영역 하나에만 있는 자산 목록은 「우리 장비가 이것뿐인가」 로 읽힌다.
        //
        // **'관리' 에도 두지 않았다.** 장비 목록은 실험하는 사람이 매일 보는
        // 것이다. 권한을 이름으로 삼는 실수는 이 그룹이 이미 한 번 되돌렸다.
        label: '보유 장비',
        icon: Wrench,
        to: '/settings/equipment',
      },
      // **차례는 정의 → 정의 → 정의 → 운영이다.** 앞 셋은 「무엇을 어떻게 받고
      // 처리할지」 를 미리 적어 두는 자리고, 커넥터는 그 정의를 따라 **실제로
      // 들어온 파일**을 다루는 자리다. 새로 붙이는 사람은 위 셋을 갖춰 놓고
      // 마지막에 장비를 연결한다.
      {
        // **'관리' 에 두었더니** 부서 관리자가 새 장비를 붙일 때 막혔다 —
        // 프로파일은 만들 수 있는데 그 프로파일이 가리킬 종류를 못 만들었다.
        // 새 장비란 대개 없는 종류를 재는 장비다(ADR 0006).
        //
        // 채널 키가 전사 자산인 것은 그대로다. 그것은 메뉴가 아니라 **서버의
        // 검사**가 지킨다 — 같은 이름은 같은 차원·단위여야 한다.
        label: '시험 정의',
        icon: ListTree,
        to: '/settings/test-types',
      },
      { label: '장비 파일 정의', icon: FileCode2, to: '/settings/formats' },
      {
        // **장비 파일 정의 바로 다음이다.** 읽는 규칙과 쓰는 규칙은 짝이고, 새 솔버를
        // 붙이는 사람은 장비 파일 정의를 만든 그 사람일 때가 많다.
        //
        // 이름이 「솔버 덱 정의」 였다(2026-08-31 개명). 덱은 만드는 사람의 말이고,
        // 쓰는 사람은 **해석에 넣을 물성**을 찾으러 온다.
        label: '해석용 물성 정의',
        icon: FileOutput,
        to: '/settings/export-profiles',
      },
      {
        // **만들 수만 있고 볼 수 없으면 자산이 아니다.** 레시피는 처리 탭에서
        // 만들고 목록에서 거는데, 무엇이 저장돼 있는지 보는 자리가 없었다.
        label: '레시피 목록',
        icon: FlaskConical,
        to: '/settings/recipes',
      },
      {
        // **장비 PC 가 보낸 파일이 어디까지 왔는지.** 앞 셋이 정의라면 여기는
        // 그 정의를 따라 들어온 실물을 다루는 자리다 — 시편을 못 정한 파일을
        // 붙이는 것은 부서 관리자의 일이다.
        label: '장비 커넥터',
        icon: Plug,
        to: '/settings/connectors',
      },
    ],
  },
  {
    // **사슬이 아닌 둘.** 부서 사람과 그 부서에서 무엇이 바뀌었나 — 데이터가
    // 들어오는 길과 아무 상관이 없어서, 한 이름 아래 묶으면 그 이름이 아무것도
    // 안 말하게 된다(그것이 「부서 설정」 이 애매했던 까닭이다).
    //
    // **「내」 를 붙였다.** 그냥 '부서' 로 두면 아래 '관리' 의 '부서 정보'
    // (전사 부서 목록)와 헷갈린다 — 여기는 **내가 속한 부서**의 일이다.
    title: '내 부서',
    audience: 'manager',
    items: [
      { label: '부서 멤버', icon: Users, resolve: (s) => `/w/${s}/members`, audience: 'manager' },
      {
        // **기록만 쌓이고 볼 자리가 없으면 자산이 아니다.** 레시피·프로파일에서
        // 같은 판단을 했다. 여기에는 만들기·고치기·지우기가 없다 — 고칠 수
        // 있으면 감사가 아니다.
        label: '변경 이력',
        icon: ScrollText,
        to: '/settings/audit',
        audience: 'manager',
      },
    ],
  },
  {
    title: '관리',
    audience: 'system_admin',
    items: [
      { label: '계정', icon: UserCog, to: '/admin/accounts', audience: 'system_admin' },
      // **전사 부서 목록이다.** 위 '내 부서' 와 헷갈리지 않게 이름을 가른다 —
      // 이쪽은 부서를 만들고 고치는 자리고, 저쪽은 내 부서의 일이다.
      { label: '부서 정보', icon: Building2, to: '/admin/workspaces', audience: 'system_admin' },
      {
        // **기준정보를 켜 두고 고칠 데가 없으면 절반만 한 것이다.** 오타가 값이
        // 되면 그것을 고르는 다음 사람이 생기고, 오염이 자기 강화된다.
        //
        // **이름에 「편집」 을 붙였다.** 보는 화면이 '공통' 에 따로 생겼는데 둘 다
        // 「기준정보」 면 관리자는 어느 쪽이 진짜인지 모른다 — 전에 '통계'·
        // '내보내기' 를 stub 으로 두었다가 같은 일이 났다.
        label: '기준정보 편집',
        icon: Tags,
        to: '/admin/vocabulary',
        audience: 'system_admin',
      },

      {
        // **화면에서 적은 식이 적합식·처리 단계가 된다**(ADR 0030). 물성 개발자가
        // 파이썬 폴더를 붙이지 않고도 경화식 하나·비율 하나를 더하는 자리다 —
        // 알고리즘(정렬·구간 탐색·회귀)은 여전히 확장 폴더의 일이다.
        label: '계산식',
        icon: Sigma,
        to: '/admin/formulas',
        audience: 'system_admin',
      },
      {
        // **지운 것이 어디로 갔는지 볼 자리.** 삭제가 소프트라 행은 남는데
        // 볼 데가 없어서, 지운 재료가 이름을 붙들고 있는 것을 아무도 설명할
        // 수 없었다(2026-08-28 이관 사고).
        label: '휴지통',
        icon: Trash2,
        to: '/admin/trash',
        audience: 'system_admin',
      },
      {
        // **저장소 정리를 여기 아래로 넣었다.** 둘은 같은 질문의 두 쪽이다 —
        // 「우리가 쌓은 것」(정리)과 「드라이브에 남은 것」(서버). 메뉴에 따로
        // 서 있으면 디스크가 찰 때 한쪽만 보고 「치울 게 없다」 고 결론 낸다.
        // 화면 안에서 탭으로 갈리고 주소는 그대로다.
        label: '서버',
        icon: Server,
        to: '/server',
        audience: 'system_admin',
      },
    ],
  },
]

export function itemHref(item: NavItem, slug: string): string {
  return item.to ?? item.resolve?.(slug) ?? '/'
}

/** 이 사람에게 보이는가. 서버가 최종 판정을 한다 — 여기는 표시일 뿐이다. */
export function canSee(
  audience: NavAudience | undefined,
  viewer: { isSystemAdmin: boolean; isAnyManager: boolean }
): boolean {
  if (audience === 'system_admin') return viewer.isSystemAdmin
  if (audience === 'manager') return viewer.isSystemAdmin || viewer.isAnyManager
  return true
}

/**
 * 볼 수 있는 것만 남긴 메뉴. 빈 그룹은 제목까지 지운다.
 *
 * `realm` 은 **지금 서 있는 영역**이다. 그 영역의 그룹과 영역이 없는 그룹만
 * 남는다 — 다른 영역의 그룹은 숨기는 것이 아니라 **다른 세계**라서 안 보인다.
 */
export function visibleGroups(
  viewer: { isSystemAdmin: boolean; isAnyManager: boolean },
  realm: NavRealm = 'material'
): NavGroup[] {
  return NAV_GROUPS.filter((group) => !group.realm || group.realm === realm)
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => canSee(item.audience, viewer)),
    }))
    .filter((group) => canSee(group.audience, viewer) && group.items.length > 0)
}

/** 한 영역의 그룹만. 개요 화면이 「이 영역에 무엇이 오는가」 를 그릴 때 쓴다. */
export function realmGroups(realm: NavRealm): NavGroup[] {
  return NAV_GROUPS.filter((group) => group.realm === realm)
}
