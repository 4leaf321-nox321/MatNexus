/**
 * AI 도구 등록 안내 — **토큰이 없어도 형식을 보여 주고, 있으면 채워 준다.**
 *
 * 무는 것 셋:
 *   토큰 전에도 명령이 보인다      「먼저 발급하세요」 만 띄우면 무엇을 받는지 모른다
 *   발급하면 그 값이 들어간다      평문은 다시 못 보므로 그 자리에서 완성돼야 한다
 *   도구마다 다른 것을 준다        Desktop 은 명령이 아니라 JSON 항목이다
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { McpSetup, TOKEN_PLACEHOLDER } from '@/shared/components/McpSetup'

describe('McpSetup', () => {
  it('토큰이 없으면 자리표시자를 넣은 형식을 보여 준다', () => {
    render(<McpSetup />)
    const command = screen.getByText(/claude mcp add/)
    expect(command.textContent).toContain(TOKEN_PLACEHOLDER)
    expect(command.textContent).toContain('/mcp')
  })

  it('발급된 토큰이 명령에 채워진다', () => {
    render(<McpSetup token="mnx_pat_abc123" />)
    const command = screen.getByText(/claude mcp add/)
    expect(command.textContent).toContain('Authorization: Bearer mnx_pat_abc123')
    expect(command.textContent).not.toContain(TOKEN_PLACEHOLDER)
  })

  it('Claude Desktop 은 명령이 아니라 설정 항목을 준다', async () => {
    render(<McpSetup token="mnx_pat_abc123" />)
    await userEvent.click(screen.getByRole('tab', { name: 'Claude Desktop' }))

    const entry = await screen.findByText(/"matnexus"/)
    // stdio 만 받는 도구라 브리지를 거친다.
    expect(entry.textContent).toContain('mcp-remote')
    // **헤더 값은 env 로 넣는다** — 공백(`Bearer …`)이 args 에서 잘리는 것을 막는다.
    expect(entry.textContent).toContain('Authorization:${AUTH}')
    expect(entry.textContent).toContain('"AUTH": "Bearer mnx_pat_abc123"')
    // 바깥 래퍼까지 주면 이미 있는 설정을 덮어쓴다.
    expect(entry.textContent).not.toContain('"mcpServers"')
  })

  it('Codex 는 TOML 로 준다', async () => {
    render(<McpSetup token="mnx_pat_abc123" />)
    await userEvent.click(screen.getByRole('tab', { name: 'Codex CLI' }))

    const entry = await screen.findByText(/\[mcp_servers\.matnexus\]/)
    expect(entry.textContent).toContain('AUTH = "Bearer mnx_pat_abc123"')
  })
})
