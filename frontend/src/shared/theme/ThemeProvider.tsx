/**
 * 라이트/다크 전환.
 *
 * shadcn이 `.dark` 클래스에 색 토큰을 걸어 두었으므로, 여기서는 클래스만
 * 붙였다 뗀다. 색을 이 파일에서 직접 다루지 않는다 — 65가 전역 CSS 1,683개
 * 클래스를 화면들이 공유하다 깨진 원인이 '색이 여러 곳에서 정의되는 것'이었다.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

type Theme = 'light' | 'dark'

const STORAGE_KEY = 'matnexus.theme'

interface ThemeContextValue {
  theme: Theme
  toggle: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

function initialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  const toggle = useCallback(() => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'))
  }, [])

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme 는 ThemeProvider 안에서만 쓸 수 있습니다')
  return value
}
