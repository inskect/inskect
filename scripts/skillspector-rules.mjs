// Regenerates shared/utils/rules.ts from skillspector's README at a version:
//   node scripts/skillspector-rules.mjs v2.12.0
// Run it when the skillspector pin in backend/pyproject.toml changes.
import { writeFileSync } from 'node:fs'

const version = process.argv[2]
if (!version) {
  console.error('usage: node scripts/skillspector-rules.mjs <skillspector tag, e.g. v2.12.0>')
  process.exit(2)
}

const response = await fetch(`https://raw.githubusercontent.com/NVIDIA/SkillSpector/${version}/README.md`)
if (!response.ok) throw new Error(`README for ${version}: HTTP ${response.status}`)
const readme = await response.text()

const start = readme.indexOf('## Vulnerability Patterns')
const end = readme.indexOf('\n## ', start + 5)
if (start < 0) throw new Error('No "Vulnerability Patterns" section in the README')

const rules = []
let section = null
for (const line of readme.slice(start, end).split('\n')) {
  const heading = line.match(/^### (.+)$/)
  if (heading) {
    // GitHub's anchor for the heading.
    section = heading[1].trim().toLowerCase().replace(/[^\w\- ]/g, '').trim().replace(/ /g, '-')
    continue
  }
  const row = line.match(/^\|\s*`?([A-Z]{1,4}\d+)`?\s*\|\s*([^|]+?)\s*\|\s*[A-Z]+\s*\|/)
  if (row && section) rules.push(`  ${row[1]}: { name: '${row[2].replace(/'/g, '\\\'')}', section: '${section}' }`)
}

const docs = `https://github.com/NVIDIA/SkillSpector/blob/${version}`
writeFileSync('shared/utils/rules.ts', `// skillspector's rule IDs, as its README's "Vulnerability Patterns" tables document them at the
// version the API pins. Generated from ${docs}/README.md:
// regenerate when the skillspector pin changes (rules come and go between versions).

export const SKILLSPECTOR_DOCS = '${docs}'

const RULES: Record<string, { name: string, section: string }> = {
${rules.join(',\n')}
}

// Rules documented on a page of their own.
const RULE_PAGES: Record<string, string> = {
  AS3: 'docs/AS3_SELF_REFERENCES.md'
}

// skillspector's MCP Registry posture checks (its mcp_registry.py), which its README doesn't list.
const MCP_RULES: Record<string, string> = {
  'MCP-PACKAGE-VERSION': 'Unpinned Package Version',
  'MCP-PACKAGE-SHA256': 'Invalid Package Hash',
  'MCP-REPOSITORY': 'Missing Repository',
  'MCP-OFFICIAL-STATUS': 'Server Not Active',
  'MCP-PLAIN-HTTP': 'Plain HTTP Endpoint'
}

/** Where skillspector documents a rule, or null for one its docs don't list. */
export function ruleDocsLink(ruleId: string): string | null {
  if (RULE_PAGES[ruleId]) return \`\${SKILLSPECTOR_DOCS}/\${RULE_PAGES[ruleId]}\`
  const rule = RULES[ruleId]
  return rule ? \`\${SKILLSPECTOR_DOCS}/README.md#\${rule.section}\` : null
}

/** The rule's name in skillspector's docs, e.g. "Instruction Override". */
export function ruleName(ruleId: string): string | null {
  return RULES[ruleId]?.name ?? MCP_RULES[ruleId] ?? null
}
`)
console.log(`${rules.length} rules from skillspector ${version}`)
