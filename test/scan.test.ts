import { describe, expect, it } from 'vitest'
import { describeScanTarget, isUploadTarget, mcpEntryUrl, parseMcpServer, parseScanTarget, splitScanTitle } from '../shared/utils/scan'

const ENTRY = 'https://registry.modelcontextprotocol.io/v0/servers/io.github.acme%2Fweather/versions/latest'

describe('parseScanTarget', () => {
  it('shortens a GitHub repo URL to owner/repo', () => {
    expect(parseScanTarget('https://github.com/NVIDIA/skillspector.git')).toEqual({ title: 'NVIDIA/skillspector', isGithub: true })
  })

  it('keeps the path of a GitHub tree or blob URL, without the ref', () => {
    expect(parseScanTarget('https://github.com/acme/skills/tree/main/pdf/SKILL.md')).toEqual({ title: 'acme/skills/pdf/SKILL.md', isGithub: true })
  })

  it('keeps the path of a raw.githubusercontent.com URL, without the ref', () => {
    expect(parseScanTarget('https://raw.githubusercontent.com/acme/skills/main/pdf/SKILL.md')).toEqual({ title: 'acme/skills/pdf/SKILL.md', isGithub: true })
  })

  it('leaves other URLs and GitHub URLs without a repo untouched', () => {
    expect(parseScanTarget('https://example.com/skill.zip')).toEqual({ title: 'https://example.com/skill.zip', isGithub: false })
    expect(parseScanTarget('https://github.com/acme')).toEqual({ title: 'https://github.com/acme', isGithub: false })
  })

  it('returns unparseable input as-is', () => {
    expect(parseScanTarget('not a url')).toEqual({ title: 'not a url', isGithub: false })
  })
})

describe('describeScanTarget', () => {
  it('ignores empty input', () => {
    expect(describeScanTarget('   ')).toBeNull()
  })

  it.each([
    ['https://github.com/acme/skills', 'repository', 'GitHub', 'acme/skills'],
    ['https://gitlab.com/acme/skills.git', 'repository', 'GitLab', 'https://gitlab.com/acme/skills.git'],
    ['https://github.com/acme/skills/blob/main/pdf/SKILL.md', 'file', 'GitHub', 'acme/skills/pdf/SKILL.md'],
    ['https://raw.githubusercontent.com/acme/skills/main/pdf/SKILL.md', 'file', 'GitHub', 'acme/skills/pdf/SKILL.md'],
    ['https://github.com/acme/skills/archive/refs/heads/main.zip', 'archive', 'GitHub', 'acme/skills'],
    ['https://huggingface.co/acme/skill/resolve/main/skill.zip', 'archive', 'Hugging Face', 'https://huggingface.co/acme/skill/resolve/main/skill.zip'],
    ['https://github.com/anthropics/skills/tree/main/skills/pdf', 'folder', 'GitHub', 'anthropics/skills/skills/pdf'],
    ['https://gitlab.com/group/sub/proj/-/tree/main/skills/pdf', 'folder', 'GitLab', 'group/sub/proj/skills/pdf'],
    ['https://huggingface.co/spaces/acme/demo/tree/main/skills/pdf', 'folder', 'Hugging Face', 'spaces/acme/demo/skills/pdf'],
    ['io.github.acme/weather', 'mcp', 'MCP Registry', 'io.github.acme/weather'],
    [ENTRY, 'mcp', 'MCP Registry', 'io.github.acme/weather'],
    ['https://registry.modelcontextprotocol.io/v0.1/servers/io.github.acme%2Fweather/versions/1.0.0', 'mcp', 'MCP Registry', 'io.github.acme/weather@1.0.0']
  ])('accepts %s as a %s on %s', (target, kind, host, title) => {
    expect(describeScanTarget(target)).toEqual({ ok: true, kind, host, title })
  })

  it.each([
    ['github.com/acme/skills', 'full URL'],
    ['http://github.com/acme/skills', 'https://'],
    ['https://example.com/skill.zip', 'GitHub, GitLab, Bitbucket or Hugging Face'],
    ['https://github.com/acme', 'Link to a repository'],
    // A GitHub owner/repo isn't an MCP server's name: those have a reverse-DNS namespace.
    ['acme/skills', 'MCP server’s name'],
    ['https://registry.modelcontextprotocol.io/v0/servers', 'one server in the MCP Registry']
  ])('rejects %s', (target, problem) => {
    const info = describeScanTarget(target)
    expect(info?.ok).toBe(false)
    expect(info && !info.ok && info.problem).toContain(problem)
  })
})

describe('splitScanTitle', () => {
  it('leads with the end of a deep path and keeps the repo as the source', () => {
    expect(splitScanTitle('https://github.com/acme/skills/blob/main/tools/pdf/SKILL.md')).toEqual({ name: 'pdf/SKILL.md', source: 'acme/skills' })
  })

  it('keeps short titles whole', () => {
    expect(splitScanTitle('https://github.com/acme/skills')).toEqual({ name: 'acme/skills' })
    expect(splitScanTitle('https://example.com/skill.zip')).toEqual({ name: 'https://example.com/skill.zip' })
  })
})

describe('MCP servers', () => {
  it('reads a server and its version from a name or a registry link', () => {
    expect(parseMcpServer(' io.github.acme/weather ')).toEqual({ name: 'io.github.acme/weather', version: 'latest' })
    expect(parseMcpServer('https://registry.modelcontextprotocol.io/v0/servers/io.github.acme%2Fweather')).toEqual({ name: 'io.github.acme/weather', version: 'latest' })
    expect(parseMcpServer('https://evil.example/v0/servers/io.github.acme%2Fweather')).toBeNull()
    expect(parseMcpServer('https://github.com/acme/weather')).toBeNull()
  })

  it('stores a named server as the API does, so the history finds it again', () => {
    expect(mcpEntryUrl(parseMcpServer('io.github.acme/weather')!)).toBe(ENTRY)
  })

  it('titles a scan by the server, shown whole in the history', () => {
    expect(parseScanTarget(ENTRY)).toEqual({ title: 'io.github.acme/weather', isGithub: false })
    expect(splitScanTitle(ENTRY)).toEqual({ name: 'io.github.acme/weather' })
  })
})

describe('uploads', () => {
  it('titles an uploaded skill by its file name', () => {
    expect(isUploadTarget('upload:my skill.zip')).toBe(true)
    expect(isUploadTarget('https://github.com/acme/skills')).toBe(false)
    expect(parseScanTarget('upload:my skill.zip')).toEqual({ title: 'my skill.zip', isGithub: false })
    expect(splitScanTitle('upload:SKILL.md')).toEqual({ name: 'SKILL.md' })
  })
})
