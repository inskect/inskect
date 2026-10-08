// MCP servers are scanned by their entry in the official MCP Registry, named
// (io.github.acme/weather) or linked; the API stores the registry API's URL for the entry
// (backend/app/targets.py, which these mirror).
export const MCP_REGISTRY_HOST = 'registry.modelcontextprotocol.io'
const MCP_ENTRY_PREFIX = `https://${MCP_REGISTRY_HOST}/v0/servers/`
// A reverse-DNS namespace, so always with a dot: that tells it from a GitHub owner/repo.
const MCP_SERVER_NAME = /^[a-z0-9-]+(?:\.[a-z0-9-]+)+\/[\w.-]+$/i
const MCP_ENTRY_PATH = /^\/v0(?:\.\d+)?\/servers\/([^/]+)(?:\/versions\/([^/]+))?\/?$/

/** The MCP server a target names or links to in the registry, at a version or "latest"; else null. */
export function parseMcpServer(target: string): { name: string, version: string } | null {
  let name = target.trim()
  let version = 'latest'
  if (name.includes('://')) {
    let url: URL
    try {
      url = new URL(name)
    } catch {
      return null
    }
    const match = url.hostname === MCP_REGISTRY_HOST ? url.pathname.match(MCP_ENTRY_PATH) : null
    if (!match) return null
    try {
      name = decodeURIComponent(match[1]!)
      version = match[2] ? decodeURIComponent(match[2]) : 'latest'
    } catch {
      return null
    }
  }
  return MCP_SERVER_NAME.test(name) ? { name, version } : null
}

/** The target the API stores for an MCP server: its registry entry's URL. */
export function mcpEntryUrl(server: { name: string, version: string }): string {
  return `${MCP_ENTRY_PREFIX}${encodeURIComponent(server.name)}/versions/${encodeURIComponent(server.version)}`
}

// A skill uploaded from the browser is recorded as `upload:<file name>` (backend/app/uploads.py).
const UPLOAD_PREFIX = 'upload:'

export function isUploadTarget(target: string): boolean {
  return target.startsWith(UPLOAD_PREFIX)
}

export function parseScanTarget(target: string): { title: string, isGithub: boolean } {
  if (isUploadTarget(target)) return { title: target.slice(UPLOAD_PREFIX.length), isGithub: false }
  const server = parseMcpServer(target)
  if (server) {
    return { title: server.version === 'latest' ? server.name : `${server.name}@${server.version}`, isGithub: false }
  }

  let url: URL
  try {
    url = new URL(target)
  } catch {
    return { title: target, isGithub: false }
  }

  const segments = url.pathname.split('/').filter(Boolean)

  if (url.hostname === 'github.com' && segments.length >= 2) {
    const [owner, repoRaw = '', kind, ...rest] = segments
    const repo = repoRaw.replace(/\.git$/i, '')
    const path = (kind === 'tree' || kind === 'blob') && rest.length > 1 ? rest.slice(1).join('/') : ''
    return { title: path ? `${owner}/${repo}/${path}` : `${owner}/${repo}`, isGithub: true }
  }

  if (url.hostname === 'raw.githubusercontent.com' && segments.length >= 3) {
    const [owner, repo, , ...rest] = segments
    const path = rest.join('/')
    return { title: path ? `${owner}/${repo}/${path}` : `${owner}/${repo}`, isGithub: true }
  }

  // Folder links elsewhere read like GitHub's: the repository, then the folder, without the ref.
  if (url.hostname === 'gitlab.com') {
    const marker = segments.indexOf('-')
    if (marker >= 2 && segments[marker + 1] === 'tree') {
      return { title: [...segments.slice(0, marker), ...segments.slice(marker + 3)].map(decodeURIComponent).join('/'), isGithub: false }
    }
  }
  if (url.hostname === 'huggingface.co') {
    const at = segments.indexOf('tree')
    if (at >= 2) return { title: [...segments.slice(0, at), ...segments.slice(at + 2)].map(decodeURIComponent).join('/'), isGithub: false }
  }

  return { title: target, isGithub: false }
}

// "org/repo/deep/path/to/SKILL.md" → lead with the distinctive end ("to/SKILL.md") and keep
// "org/repo" as the source; many scans share the same repo prefix, which truncation would keep.
export function splitScanTitle(target: string): { name: string, source?: string } {
  const { title } = parseScanTarget(target)
  const parts = title.split('/')
  if (title.includes('://') || parts.length <= 3) return { name: title }
  return { name: parts.slice(-2).join('/'), source: parts.slice(0, 2).join('/') }
}

export type ScanTargetKind = 'repository' | 'folder' | 'file' | 'archive' | 'mcp'

export type ScanTargetInfo
  = | { ok: true, kind: ScanTargetKind, host: string, title: string }
    | { ok: false, problem: string }

// Mirrors skillspector's input_handler: only these hosts are fetched, only over https, and on
// Git hosts anything that isn't a /blob/, /raw/ or /archive/ link (or a .md/.py/.sh file) is
// `git clone`d as-is. Folder (/tree/) links are cloned at their ref and only the folder scanned:
// skillspector does GitHub's, the API GitLab's and Hugging Face's (backend/app/scan_runner.py).
const GIT_HOSTS: Record<string, string> = {
  'github.com': 'GitHub',
  'gitlab.com': 'GitLab',
  'bitbucket.org': 'Bitbucket'
}
const DOWNLOAD_HOSTS: Record<string, string> = {
  'raw.githubusercontent.com': 'GitHub',
  'huggingface.co': 'Hugging Face'
}
const DIRECT_FILE_SUFFIXES = ['.md', '.py', '.sh']
const SUPPORTED_HOSTS = 'GitHub, GitLab, Bitbucket or Hugging Face'
const MCP_EXAMPLE = 'io.github.acme/weather'

export function describeScanTarget(target: string): ScanTargetInfo | null {
  const value = target.trim()
  if (!value) return null

  const server = parseMcpServer(value)
  if (server) {
    return { ok: true, kind: 'mcp', host: 'MCP Registry', title: parseScanTarget(value).title }
  }

  let url: URL
  try {
    url = new URL(value)
  } catch {
    return { ok: false, problem: `Enter a full URL starting with https://, or an MCP server’s name such as ${MCP_EXAMPLE}` }
  }
  if (url.protocol !== 'https:') {
    return { ok: false, problem: 'Only https:// URLs can be scanned' }
  }

  if (url.hostname === MCP_REGISTRY_HOST) {
    return { ok: false, problem: `Link to one server in the MCP Registry, or enter its name, such as ${MCP_EXAMPLE}` }
  }
  const hostName = GIT_HOSTS[url.hostname] ?? DOWNLOAD_HOSTS[url.hostname]
  if (!hostName) {
    return { ok: false, problem: `Only ${SUPPORTED_HOSTS} URLs can be scanned, or an MCP server by its name` }
  }

  const path = url.pathname.toLowerCase()
  const { title } = parseScanTarget(value)
  const kind: ScanTargetKind = path.endsWith('.zip') || path.includes('/archive/')
    ? 'archive'
    : 'file'

  if (path.includes('/tree/') && url.hostname !== 'bitbucket.org') {
    return { ok: true, kind: 'folder', host: hostName, title }
  }
  if (url.hostname in DOWNLOAD_HOSTS) {
    return { ok: true, kind, host: hostName, title }
  }
  if (['/blob/', '/raw/', '/archive/'].some(part => path.includes(part)) || DIRECT_FILE_SUFFIXES.some(suffix => path.endsWith(suffix))) {
    return { ok: true, kind, host: hostName, title }
  }
  if (url.pathname.split('/').filter(Boolean).length < 2) {
    return { ok: false, problem: `Link to a repository, e.g. https://${url.hostname}/org/repo` }
  }
  return { ok: true, kind: 'repository', host: hostName, title }
}
