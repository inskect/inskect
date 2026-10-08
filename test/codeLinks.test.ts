import { describe, expect, it } from 'vitest'
import { codeLink } from '../shared/utils/codeLinks'
import { ruleDocsLink, ruleName } from '../shared/utils/rules'

describe('codeLink', () => {
  it.each([
    ['https://github.com/acme/skills', 'SKILL.md', 12, undefined, 'https://github.com/acme/skills/blob/HEAD/SKILL.md#L12'],
    ['https://github.com/acme/skills.git', 'scripts/run.sh', 3, undefined, 'https://github.com/acme/skills/blob/HEAD/scripts/run.sh#L3'],
    ['https://github.com/anthropics/skills/tree/main/skills/pdf', 'SKILL.md', 19, undefined, 'https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md#L19'],
    ['https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf/SKILL.md', 'SKILL.md', 5, undefined, 'https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md#L5'],
    ['https://github.com/anthropics/skills', 'SKILL.md', 7, 'skills/docx', 'https://github.com/anthropics/skills/blob/HEAD/skills/docx/SKILL.md#L7'],
    ['https://gitlab.com/group/sub/proj', 'SKILL.md', 2, undefined, 'https://gitlab.com/group/sub/proj/-/blob/HEAD/SKILL.md#L2'],
    ['https://gitlab.com/group/proj/-/raw/v1/dir/SKILL.md', 'SKILL.md', 2, undefined, 'https://gitlab.com/group/proj/-/blob/v1/dir/SKILL.md#L2'],
    ['https://bitbucket.org/acme/skill', 'SKILL.md', 4, undefined, 'https://bitbucket.org/acme/skill/src/HEAD/SKILL.md#lines-4'],
    ['https://huggingface.co/acme/skill', 'SKILL.md', 1, undefined, 'https://huggingface.co/acme/skill/blob/main/SKILL.md#L1'],
    ['https://huggingface.co/spaces/acme/app/resolve/main/SKILL.md', 'SKILL.md', 9, undefined, 'https://huggingface.co/spaces/acme/app/blob/main/SKILL.md#L9'],
    ['https://gitlab.com/group/proj/-/tree/main/skills/pdf', 'scripts/fill.py', 3, undefined, 'https://gitlab.com/group/proj/-/blob/main/skills/pdf/scripts/fill.py#L3'],
    ['https://huggingface.co/spaces/acme/app/tree/main/skills/pdf', 'SKILL.md', 9, undefined, 'https://huggingface.co/spaces/acme/app/blob/main/skills/pdf/SKILL.md#L9'],
    ['https://huggingface.co/spaces/acme/app/tree/main/skills', 'SKILL.md', 2, 'pdf', 'https://huggingface.co/spaces/acme/app/blob/main/skills/pdf/SKILL.md#L2'],
    ['https://github.com/acme/skills', 'docs/my file.md', null, undefined, 'https://github.com/acme/skills/blob/HEAD/docs/my%20file.md']
  ])('%s + %s:%s', (target, file, line, skillPath, expected) => {
    expect(codeLink(target, file, line, skillPath)).toBe(expected)
  })

  it('has no link for archives and other hosts', () => {
    expect(codeLink('https://github.com/acme/skills/archive/refs/heads/main.zip', 'SKILL.md', 1)).toBeNull()
    expect(codeLink('https://example.com/skill.zip', 'SKILL.md', 1)).toBeNull()
  })
})

describe('ruleDocsLink', () => {
  it('points to the rule in skillspector\'s docs at the pinned version', () => {
    expect(ruleDocsLink('P1')).toBe('https://github.com/NVIDIA/SkillSpector/blob/v2.12.0/README.md#prompt-injection-6-patterns')
    expect(ruleName('TR3')).toBe('Keyword Baiting Trigger')
    expect(ruleDocsLink('AS3')).toBe('https://github.com/NVIDIA/SkillSpector/blob/v2.12.0/docs/AS3_SELF_REFERENCES.md')
  })

  it('has none for rules the docs don\'t list', () => {
    expect(ruleDocsLink('AE1')).toBeNull()
  })

  it('names the MCP Registry posture checks, which the docs don\'t list', () => {
    expect(ruleName('MCP-PACKAGE-VERSION')).toBe('Unpinned Package Version')
    expect(ruleDocsLink('MCP-PACKAGE-VERSION')).toBeNull()
  })
})
