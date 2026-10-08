import { describe, expect, it, vi } from 'vitest'
import run, { MARKER, SIGN_PHRASE, commentBody, contributors, isSignature, pending } from '../scripts/cla.mjs'

const commit = (sha: string, author: { id: number, login: string } | null, name = 'Someone') =>
  ({ sha, author, commit: { author: { name } } })

describe('the CLA check', () => {
  it('finds the commit authors, and the commits no GitHub account claims', () => {
    const { people, unlinked } = contributors([
      commit('aaaaaaa1', { id: 1, login: 'alice' }),
      commit('bbbbbbb2', { id: 1, login: 'alice' }),
      commit('ccccccc3', null, 'Bob')
    ])
    expect([...people]).toEqual([[1, 'alice']])
    expect(unlinked).toEqual([{ sha: 'ccccccc3'.slice(0, 7), name: 'Bob' }])
  })

  it('takes the sentence as a signature, give or take spacing, case and its period', () => {
    expect(isSignature(SIGN_PHRASE)).toBe(true)
    expect(isSignature('  i have read the Inskect CLA and I agree   to its terms ')).toBe(true)
    expect(isSignature('I have read the Inskect CLA')).toBe(false)
    expect(isSignature(`> ${SIGN_PHRASE}`)).toBe(false)
  })

  it('asks only who neither signed nor is exempt: signed by account id, so a rename stays signed', () => {
    const people = new Map([[1, 'alice-renamed'], [2, 'bob'], [3, 'MaelBel'], [4, 'dependabot[bot]']])
    const signatures = [{ id: 1, login: 'alice' }]
    expect(pending({ people, signatures, allowlist: ['maelbel'] })).toEqual(['bob'])
  })

  it('says who still has to sign and how, or thanks everyone', () => {
    const asking = commentBody({ waiting: ['bob'], unlinked: [{ sha: 'ccccccc', name: 'Carol' }], documentUrl: 'https://x/CLA.md' })
    expect(asking.startsWith(MARKER)).toBe(true)
    expect(asking).toContain(SIGN_PHRASE)
    expect(asking).toContain('@bob')
    expect(asking).toContain('ccccccc (Carol)')
    expect(commentBody({ waiting: [], unlinked: [], documentUrl: 'https://x/CLA.md' })).toContain('Everyone')
  })
})

// A fake GitHub API, as much of it as the check uses.
function fakeGitHub({ commits, signatures = null as object[] | null, comments = [] as object[] }) {
  const calls: Record<string, unknown[]> = {}
  const record = (name: string, result: unknown = {}) => vi.fn(async (args: unknown) => {
    ;(calls[name] ??= []).push(args)
    return typeof result === 'function' ? result(args) : result
  })
  const rest = {
    pulls: {
      get: record('pulls.get', { data: { head: { sha: 'head-sha' }, base: { repo: { default_branch: 'main' } } } }),
      listCommits: 'pulls.listCommits'
    },
    issues: { listComments: 'issues.listComments', createComment: record('createComment'), updateComment: record('updateComment') },
    repos: {
      getContent: record('getContent', () => {
        if (!signatures) throw Object.assign(new Error('Not Found'), { status: 404 })
        return { data: { sha: 'file-sha', content: Buffer.from(JSON.stringify(signatures)).toString('base64') } }
      }),
      createOrUpdateFileContents: record('createOrUpdateFileContents'),
      createCommitStatus: record('createCommitStatus')
    },
    git: {
      createTree: record('createTree', { data: { sha: 'tree-sha' } }),
      createCommit: record('createCommit', { data: { sha: 'commit-sha' } }),
      createRef: record('createRef')
    }
  }
  const paginate = vi.fn(async (method: string) => method === 'pulls.listCommits' ? commits : comments)
  return { github: { rest, paginate }, calls }
}

const core = { info: vi.fn() }
const prEvent = { eventName: 'pull_request_target', repo: { owner: 'inskect', repo: 'inskect' }, serverUrl: 'https://github.com', payload: { pull_request: { number: 7 } } }
const signing = (user: { id: number, login: string }, body = SIGN_PHRASE) => ({
  eventName: 'issue_comment',
  repo: { owner: 'inskect', repo: 'inskect' },
  serverUrl: 'https://github.com',
  payload: { issue: { number: 7, pull_request: {} }, comment: { body, user, html_url: 'https://c', created_at: '2026-10-07T00:00:00Z' } }
})

describe('running the CLA check', () => {
  it('fails the status and asks a new contributor to sign', async () => {
    const { github, calls } = fakeGitHub({ commits: [commit('a1b2c3d4', { id: 2, login: 'bob' })] })
    await run({ github, context: prEvent, core, allowlist: ['maelbel'] })
    expect(calls.createCommitStatus).toEqual([expect.objectContaining({ sha: 'head-sha', context: 'CLA', state: 'failure', target_url: 'https://github.com/inskect/inskect/blob/main/CLA.md' })])
    expect(calls.createComment).toHaveLength(1)
  })

  it('records a signature, starting the branch with it, and passes', async () => {
    const { github, calls } = fakeGitHub({ commits: [commit('a1b2c3d4', { id: 2, login: 'bob' })], comments: [{ id: 9, user: { login: 'github-actions[bot]' }, body: `${MARKER}\nold` }] })
    await run({ github, context: signing({ id: 2, login: 'bob' }), core, allowlist: [] })
    expect(calls.createCommit).toEqual([expect.objectContaining({ parents: [] })])
    expect(calls.createRef).toEqual([expect.objectContaining({ ref: 'refs/heads/cla-signatures', sha: 'commit-sha' })])
    expect(JSON.parse((calls.createTree![0] as { tree: { content: string }[] }).tree[0]!.content)).toEqual([expect.objectContaining({ id: 2, login: 'bob', pull_request: 7 })])
    expect(calls.updateComment).toHaveLength(1)
    expect(calls.createCommitStatus).toEqual([expect.objectContaining({ state: 'success' })])
  })

  it('ignores the sentence from someone who authored none of the commits', async () => {
    const { github, calls } = fakeGitHub({ commits: [commit('a1b2c3d4', { id: 2, login: 'bob' })], signatures: [] })
    await run({ github, context: signing({ id: 5, login: 'mallory' }), core, allowlist: [] })
    expect(calls.createOrUpdateFileContents).toBeUndefined()
    expect(calls.createCommitStatus).toEqual([expect.objectContaining({ state: 'failure' })])
  })

  it('passes the maintainer\'s own pull request without a comment', async () => {
    const { github, calls } = fakeGitHub({ commits: [commit('a1b2c3d4', { id: 1, login: 'maelbel' })], signatures: [] })
    await run({ github, context: prEvent, core, allowlist: ['maelbel'] })
    expect(calls.createComment).toBeUndefined()
    expect(calls.createCommitStatus).toEqual([expect.objectContaining({ state: 'success' })])
  })
})
