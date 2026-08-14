import { RouterProvider } from 'react-router-dom'

import { router } from '@/routes/router'
import { AuthProvider } from '@/shared/auth/AuthContext'
import { ThemeProvider } from '@/shared/theme/ThemeProvider'

/**
 * AuthProvider가 라우터 **바깥**에 있는 이유: 라우터 안에 두면 로그인 화면과
 * 보호된 화면이 서로 다른 Provider 인스턴스를 보게 되는 구성이 만들어지기 쉽다.
 * 인증 상태는 앱 전체에서 하나여야 한다.
 */
export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  )
}
