// Links from a finding to its line on the code host the scan fetched it from.

function encodePath(path: string): string {
  return path.split('/').filter(Boolean).map(encodeURIComponent).join('/')
}

function join(...parts: (string | undefined)[]): string {
  return parts.filter(Boolean).join('/').replace(/\/+/g, '/')
}

/**
 * The scanned skill's root on its code host, as a URL that `file` (relative to it) and a line can be
 * added to. For a single-file target, the root is the file's folder. Null for archives and other
 * hosts. Without a ref in the target, links follow the default branch (HEAD; Hugging Face: main).
 */
function sourceRoot(target: string): { base: string, line: (n: number) => string } | null {
  let url: URL
  try {
    url = new URL(target)
  } catch {
    return null
  }
  const s = url.pathname.split('/').filter(Boolean)
  const githubLine = (n: number) => `#L${n}`

  if (url.hostname === 'github.com' && s.length >= 2) {
    const [owner, repo = ''] = s
    const name = repo.replace(/\.git$/i, '')
    if (s[2] === 'archive') return null
    if ((s[2] === 'tree' || s[2] === 'blob') && s[3]) {
      // A /blob/ target is one file: its folder is the root.
      const rest = s.slice(4)
      const folder = s[2] === 'blob' ? rest.slice(0, -1) : rest
      return { base: `https://github.com/${owner}/${name}/blob/${join(s[3], ...folder)}`, line: githubLine }
    }
    return { base: `https://github.com/${owner}/${name}/blob/HEAD`, line: githubLine }
  }
  if (url.hostname === 'raw.githubusercontent.com' && s.length >= 4) {
    const [owner, repo, ref, ...path] = s
    return { base: `https://github.com/${owner}/${repo}/blob/${join(ref, ...path.slice(0, -1))}`, line: githubLine }
  }
  if (url.hostname === 'gitlab.com') {
    const marker = s.indexOf('-')
    if (marker < 0) return s.length >= 2 ? { base: `https://gitlab.com/${s.join('/').replace(/\.git$/i, '')}/-/blob/HEAD`, line: githubLine } : null
    const [kind, ref, ...rest] = s.slice(marker + 1)
    if (!ref || !['blob', 'raw', 'tree'].includes(kind!)) return null
    const folder = kind === 'tree' ? rest : rest.slice(0, -1)
    return { base: `https://gitlab.com/${join(...s.slice(0, marker))}/-/blob/${join(ref, ...folder)}`, line: githubLine }
  }
  if (url.hostname === 'bitbucket.org' && s.length >= 2) {
    const [owner, repo = ''] = s
    return { base: `https://bitbucket.org/${owner}/${repo.replace(/\.git$/i, '')}/src/HEAD`, line: n => `#lines-${n}` }
  }
  if (url.hostname === 'huggingface.co') {
    const kindAt = s.findIndex(segment => segment === 'resolve' || segment === 'blob' || segment === 'tree')
    if (kindAt >= 2 && s[kindAt + 1]) {
      // A /tree/ target is a folder, the root itself; the others are one file, in theirs.
      const folder = s[kindAt] === 'tree' ? s.slice(kindAt + 2) : s.slice(kindAt + 2, -1)
      return { base: `https://huggingface.co/${join(...s.slice(0, kindAt))}/blob/${join(s[kindAt + 1], ...folder)}`, line: githubLine }
    }
    const repoEnd = s[0] === 'spaces' || s[0] === 'datasets' ? 3 : 2
    if (s.length === repoEnd) return { base: `https://huggingface.co/${s.join('/')}/blob/main`, line: githubLine }
  }
  return null
}

/**
 * A link to `file` (as skillspector reports it, relative to the scanned skill) at `line`, or null
 * when the target isn't on a code host. `skillPath` is the skill's folder in a repository holding
 * several (#96).
 */
export function codeLink(target: string, file: string, line?: number | null, skillPath?: string): string | null {
  const root = sourceRoot(target)
  if (!root || !file) return null
  const path = encodePath(join(skillPath, file))
  return `${root.base}/${path}${line ? root.line(line) : ''}`
}
