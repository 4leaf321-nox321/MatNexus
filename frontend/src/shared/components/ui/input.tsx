import * as React from "react"

import { cn } from "@/shared/lib/utils"

/**
 * **날짜 칸의 연도는 네 자리까지.** `max` 가 없으면 브라우저가 연도를 여섯 자리(275760년)까지
 * 받는다 — 시료 생산일에 여섯 자리 연도가 들어갔다(2026-09-29 지적). 날짜 칸이 여러 화면에
 * 있어 칸마다 적으면 새 칸에서 또 빠진다. 부르는 쪽이 `max` 를 주면 그것이 이긴다.
 */
const DATE_MAX: Record<string, string> = {
  date: "9999-12-31",
  "datetime-local": "9999-12-31T23:59",
  month: "9999-12",
}

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      max={type ? DATE_MAX[type] : undefined}
      data-slot="input"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Input }
