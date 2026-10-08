// The contributor license agreement check (CLA.md), run by .github/workflows/cla.yml on every pull
// request and on comments to one. Everyone who authored one of its commits signs once, by replying
// with SIGN_PHRASE; signatures are kept in signatures.json on the cla-signatures branch. The "CLA"
// commit status stays failing until every author has signed, and a single comment says who hasn't.
//
// The workflow runs on pull_request_target, with write access: this file is read from the base
// branch, and nothing from the pull request is ever checked out or run.

export const SIGN_PHRASE = 'I have read the Inskect CLA and I agree to its terms.'
export const STATUS_CONTEXT = 'CLA'
export const SIGNATURES_BRANCH = 'cla-signatures'
export const SIGNATURES_FILE = 'signatures.json'
// Marks the bot's own comment, so it's edited rather than posted again.
export const MARKER = '<!-- inskect-cla -->'

export function isBot(login) {
  return login.endsWith('[bot]')
}

// The pull request's commit authors: by GitHub account, and the commits whose author's email isn't
// linked to one, which can't sign until it is.
export function contributors(commits) {
  const people = new Map()
  const unlinked = []
  for (const commit of commits) {
    const author = commit.author
    if (author?.login) people.set(author.id, author.login)
    else unlinked.push({ sha: commit.sha.slice(0, 7), name: commit.commit?.author?.name ?? 'unknown' })
  }
  return { people, unlinked }
}

// Whether a comment is a signature: the sentence, give or take spacing, case and its final period.
export function isSignature(body) {
  const normalize = text => text.trim().replace(/\s+/g, ' ').replace(/\.$/, '').toLowerCase()
  return normalize(body ?? '') === normalize(SIGN_PHRASE)
}

// Who still has to sign: authors neither exempt nor signed. Signatures match by account id, so a
// renamed account stays signed.
export function pending({ people, signatures, allowlist }) {
  const signed = new Set(signatures.map(signature => signature.id))
  const exempt = new Set(allowlist.map(login => login.toLowerCase()))
  return [...people]
    .filter(([id, login]) => !signed.has(id) && !exempt.has(login.toLowerCase()) && !isBot(login))
    .map(([, login]) => login)
    .sort((a, b) => a.localeCompare(b))
}

export function commentBody({ waiting, unlinked, documentUrl }) {
  if (!waiting.length && !unlinked.length) {
    return `${MARKER}\n✅ Everyone who authored these commits has signed the [contributor license agreement](${documentUrl}). Thank you!`
  }
  const lines = [
    MARKER,
    `Thank you for your contribution! Before it can be merged, everyone who authored its commits signs the [contributor license agreement](${documentUrl}), once. It lets the maintainer use contributions under other terms than the AGPL as well; you keep your copyright.`,
    ''
  ]
  if (waiting.length) {
    lines.push(
      'To sign, reply to this pull request with this exact sentence:',
      '',
      '```',
      SIGN_PHRASE,
      '```',
      '',
      `Still to sign: ${waiting.map(login => `@${login}`).join(', ')}`
    )
  }
  if (unlinked.length) {
    if (waiting.length) lines.push('')
    lines.push(
      `These commits' author email isn't linked to a GitHub account, so their author can't sign: ${unlinked.map(commit => `${commit.sha} (${commit.name})`).join(', ')}. Add the email to your GitHub account, or amend the commits with one that is, then comment \`recheck\`.`
    )
  }
  return lines.join('\n')
}

async function readSignatures(github, { owner, repo }) {
  try {
    const { data } = await github.rest.repos.getContent({ owner, repo, path: SIGNATURES_FILE, ref: SIGNATURES_BRANCH })
    return { signatures: JSON.parse(Buffer.from(data.content, 'base64').toString('utf8')), sha: data.sha }
  } catch (error) {
    if (error.status === 404) return { signatures: [], sha: null }
    throw error
  }
}

async function writeSignatures(github, { owner, repo }, signatures, sha, message) {
  const content = `${JSON.stringify(signatures, null, 2)}\n`
  if (sha) {
    await github.rest.repos.createOrUpdateFileContents({
      owner, repo, path: SIGNATURES_FILE, branch: SIGNATURES_BRANCH, sha, message,
      content: Buffer.from(content).toString('base64')
    })
    return
  }
  // The first signature starts the branch, on its own: none of the code's history.
  const tree = await github.rest.git.createTree({
    owner, repo, tree: [{ path: SIGNATURES_FILE, mode: '100644', type: 'blob', content }]
  })
  const commit = await github.rest.git.createCommit({ owner, repo, message, tree: tree.data.sha, parents: [] })
  await github.rest.git.createRef({ owner, repo, ref: `refs/heads/${SIGNATURES_BRANCH}`, sha: commit.data.sha })
}

export default async function run({ github, context, core, allowlist }) {
  const { owner, repo } = context.repo
  const isComment = context.eventName === 'issue_comment'
  if (isComment && !context.payload.issue?.pull_request) return
  const number = isComment ? context.payload.issue.number : context.payload.pull_request.number

  const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: number })
  const commits = await github.paginate(github.rest.pulls.listCommits, { owner, repo, pull_number: number, per_page: 100 })
  const { people, unlinked } = contributors(commits)
  const { signatures, sha } = await readSignatures(github, context.repo)

  // A signature counts from one of the pull request's authors, once.
  const comment = context.payload.comment
  if (isComment && isSignature(comment.body) && people.has(comment.user.id)
    && !signatures.some(signature => signature.id === comment.user.id)) {
    signatures.push({
      login: comment.user.login,
      id: comment.user.id,
      pull_request: number,
      comment: comment.html_url,
      signed_at: comment.created_at
    })
    await writeSignatures(github, context.repo, signatures, sha, `${comment.user.login} signed the CLA in #${number}`)
    core.info(`${comment.user.login} signed the CLA`)
  }

  const waiting = pending({ people, signatures, allowlist })
  const documentUrl = `${context.serverUrl}/${owner}/${repo}/blob/${pr.base.repo.default_branch}/CLA.md`

  // One comment, edited as signatures come in; none at all on a pull request with nothing to sign.
  const comments = await github.paginate(github.rest.issues.listComments, { owner, repo, issue_number: number, per_page: 100 })
  const existing = comments.find(c => isBot(c.user?.login ?? '') && c.body?.startsWith(MARKER))
  const body = commentBody({ waiting, unlinked, documentUrl })
  if (existing) {
    if (existing.body !== body) await github.rest.issues.updateComment({ owner, repo, comment_id: existing.id, body })
  } else if (waiting.length || unlinked.length) {
    await github.rest.issues.createComment({ owner, repo, issue_number: number, body })
  }

  const signedByAll = !waiting.length && !unlinked.length
  await github.rest.repos.createCommitStatus({
    owner, repo, sha: pr.head.sha,
    context: STATUS_CONTEXT,
    state: signedByAll ? 'success' : 'failure',
    target_url: documentUrl,
    description: signedByAll
      ? 'Every author has signed the CLA'
      : `To sign: ${[...waiting, ...unlinked.map(commit => commit.sha)].join(', ')}`.slice(0, 140)
  })
}
