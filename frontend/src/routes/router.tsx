/**
 * 라우트 표.
 *
 * 사이드바(navigation.ts)에 있는 항목은 여기에 대응 경로가 있어야 한다. 아직
 * 구현되지 않은 화면은 Placeholder로 두되 **어느 단계에서 들어오는지 명시**한다.
 *
 * `/login` 과 `/force-password-change` 만 가드 밖에 있고 나머지는 전부
 * ProtectedRoute 아래에 둔다 — 새 화면을 추가할 때 가드를 깜빡할 자리가 없도록.
 */

import { lazy } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'

import ForcePasswordChangePage from '@/modules/auth/ForcePasswordChangePage'
import LoginPage from '@/modules/auth/LoginPage'
import MaterialDetailPage from '@/modules/materials/MaterialDetailPage'
import MaterialsPage from '@/modules/materials/MaterialsPage'
import SpecimensPage from '@/modules/materials/SpecimensPage'
import NotificationsPage from '@/modules/notifications/NotificationsPage'
import TestRunDetailPage from '@/modules/tests/TestRunDetailPage'
import TestRunsPage from '@/modules/tests/TestRunsPage'
import { useAuth } from '@/shared/auth/AuthContext'
import { ProtectedRoute } from '@/shared/auth/ProtectedRoute'
import { Placeholder } from '@/shared/components/Placeholder'
import { AppShell } from '@/shared/layout/AppShell'
import { DEFAULT_WORKSPACE } from '@/shared/layout/navigation'

/**
 * **화면 대부분을 나눠 싣는다.**
 *
 * 한 덩이로 묶으니 702 kB 가 되어 번들 예산(§8.5, `chunkSizeWarningLimit` 700)을
 * 넘겼다. 처리·통계·적합 패널이 재료 상세와 시험 상세에 붙으면서 커진 것인데,
 * 그 화면들은 **로그인해서 목록을 볼 때는 필요 없다.**
 *
 * 매일 밟는 길(로그인·목록·재료 상세·시험 상세·알림)은 처음에 싣고, 가끔 들어가는
 * 화면만 그때 받는다.
 *
 * **상세 두 개를 나누지 않은 이유:** 나눠 보니 목록에서 상세로 넘어갈 때 청크를
 * 받는 동안 **이전 화면이 그대로 남아 있었다**(React 전환의 정상 동작 — 깜빡임을
 * 막으려고 예전 UI 를 유지한다). 주소는 바뀌었는데 화면은 목록이라, 누른 사람은
 * 아무 일도 안 일어난 것처럼 본다. 실제로 스모크가 목록을 상세로 착각해 깨졌다.
 * 늘 밟는 길에서 그 대가를 치를 이유가 없다 — 둘을 합쳐도 예산의 절반이다.
 */
const AccountsAdminPage = lazy(() => import('@/modules/accounts/AccountsAdminPage'))
const AuditPage = lazy(() => import('@/modules/audit/AuditPage'))
const CardsPage = lazy(() => import('@/modules/fitting/CardsPage'))
const BatchUploadPage = lazy(() => import('@/modules/tests/BatchUploadPage'))
const FormatProfileEditorPage = lazy(
  () => import('@/modules/tests/FormatProfileEditorPage')
)
const FormatProfilesPage = lazy(() => import('@/modules/tests/FormatProfilesPage'))
const MembersPage = lazy(() => import('@/modules/workspaces/MembersPage'))
const NoticesPage = lazy(() => import('@/modules/notices/NoticesPage'))
const RecipesPage = lazy(() => import('@/modules/processing/RecipesPage'))
const SignupPage = lazy(() => import('@/modules/auth/SignupPage'))
const StoragePage = lazy(() => import('@/modules/tests/StoragePage'))
const TrashPage = lazy(() => import('@/modules/trash/TrashPage'))
const ConnectorsPage = lazy(() => import('@/modules/pipelines/ConnectorsPage'))
const GuidePage = lazy(() => import('@/modules/guide/GuidePage'))
const ProfilePage = lazy(() => import('@/modules/auth/ProfilePage'))
const TestTypesPage = lazy(() => import('@/modules/tests/TestTypesPage'))
const UnitsPage = lazy(() => import('@/modules/units/UnitsPage'))
const VocabularyAdminPage = lazy(
  () => import('@/modules/vocabulary/VocabularyAdminPage')
)
const VocPage = lazy(() => import('@/modules/voc/VocPage'))
const WorkspaceHomePage = lazy(() => import('@/modules/workspaces/WorkspaceHomePage'))
const WorkspacesAdminPage = lazy(() => import('@/modules/workspaces/WorkspacesAdminPage'))

const stub = (title: string, phase: string, description?: string) => ({
  element: <Placeholder title={title} phase={phase} description={description} />,
})

/**
 * 첫 화면 — **내 부서로 보낸다.**
 *
 * 여태 `/w/default` 로 고정이었다. 서버는 `home_workspace_slug` 를 이미 주고
 * 있었는데 화면이 안 썼다 — 그래서 개발본부 사람이 로그인하면 사이드바의
 * '시험 데이터' 가 `default` 부서를 가리켰고, 목록이 비어 보였다. 자기 부서
 * 데이터를 못 찾는 것과 구별이 안 된다.
 */
function HomeRedirect() {
  const { user } = useAuth()
  const slug = user?.home_workspace_slug ?? user?.memberships[0]?.slug ?? DEFAULT_WORKSPACE
  return <Navigate to={`/w/${slug}`} replace />
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: '/force-password-change', element: <ForcePasswordChangePage /> },
      {
        path: '/',
        element: <AppShell />,
        children: [
          { index: true, element: <HomeRedirect /> },

          // 카탈로그 (전사)
          { path: 'materials', element: <MaterialsPage /> },
          // **재료를 거치지 않고 시편을 찾는다.** `/cards` 가 있는 이유와 같다.
          { path: 'specimens', element: <SpecimensPage /> },
          // **재료를 거치지 않고 카드를 찾는 자리.** 재료 상세의 'CAE 카드'
          // 탭은 그 재료의 것만 본다.
          { path: 'cards', element: <CardsPage /> },
          { path: 'materials/:id', element: <MaterialDetailPage /> },
          { path: 'test-runs/:id', element: <TestRunDetailPage /> },
          { path: 'compare', ...stub('물성 분석', 'Phase 3') },

          // 내 활동
          { path: 'personal', ...stub('내 작업함', 'Phase 1') },
          { path: 'notifications', element: <NotificationsPage /> },
          { path: 'me', element: <ProfilePage /> },

          // 공통
          { path: 'notices', element: <NoticesPage /> },
          { path: 'voc', element: <VocPage /> },
          // 물성 핸드북 — 배포 없이 갱신된다. 누구나 초안, 검토자가 승인(ADR 0022).
          { path: 'guide', element: <GuidePage /> },
          { path: 'guide/:documentKey', element: <GuidePage /> },
          { path: 'guide/:documentKey/:sectionKey', element: <GuidePage /> },

          // 부서 설정 — **`admin/` 아래가 아니다.** 형식 프로파일은 부서 관리자가
          // 만든다. 주소가 `admin/` 이면 메뉴 이름('부서 설정')과 어긋나고, 사람은
          // 주소줄을 보고도 "이건 내 일이 아니구나" 로 읽는다.
          //
          // 라우터가 정적 구간을 동적 구간보다 먼저 고르므로 `new` 는 `:key` 에
          // 먹히지 않는다. 순서에 기대지 않도록 적어 둔다.
          { path: 'settings/test-types', element: <TestTypesPage /> },
          { path: 'settings/recipes', element: <RecipesPage /> },
          { path: 'settings/audit', element: <AuditPage /> },
          { path: 'settings/formats', element: <FormatProfilesPage /> },
          { path: 'settings/formats/new', element: <FormatProfileEditorPage /> },
          { path: 'settings/formats/:key', element: <FormatProfileEditorPage /> },
          // **장비 커넥터는 부서 설정이다.** 장비를 붙이는 것은 사업부의 일이고,
          // 시편을 못 정한 파일을 붙이는 것도 부서 관리자가 한다(ADR 0021).
          { path: 'settings/connectors', element: <ConnectorsPage /> },

          // 관리 (전사)
          { path: 'admin/accounts', element: <AccountsAdminPage /> },
          { path: 'admin/workspaces', element: <WorkspacesAdminPage /> },
          { path: 'admin/units', element: <UnitsPage /> },
          { path: 'admin/vocabulary', element: <VocabularyAdminPage /> },
          { path: 'admin/storage', element: <StoragePage /> },
          { path: 'admin/trash', element: <TrashPage /> },
          { path: 'server', ...stub('서버', 'Phase 1') },

          // 부서 스코프
          {
            path: 'w/:slug',
            children: [
              { index: true, element: <WorkspaceHomePage /> },
              { path: 'tests', element: <TestRunsPage /> },
              { path: 'tests/upload', element: <BatchUploadPage /> },
              {
                path: 'workbench',
                ...stub('워크벤치', 'Phase 3~4', 'Data → Process → Stats → Fit → Export.'),
              },
              // 부서 스코프 `statistics`·`exports` 는 뺐다. 워크벤치의 3번·5번
              // 탭과 같은 것이고, 결과 열람은 재료 상세의 '물성'·'CAE 카드' 다
              // — 같은 이름의 빈 화면이 남아 있으면 어느 쪽이 진짜인지 알 수 없다.
              { path: 'members', element: <MembersPage /> },
            ],
          },

          { path: '*', ...stub('없는 페이지', '—', '주소를 확인해 주세요.') },
        ],
      },
    ],
  },
])
