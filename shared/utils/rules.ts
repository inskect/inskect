// skillspector's rule IDs, as its README's "Vulnerability Patterns" tables document them at the
// version the API pins. Generated from https://github.com/NVIDIA/SkillSpector/blob/v2.12.0/README.md:
// regenerate when the skillspector pin changes (rules come and go between versions).

export const SKILLSPECTOR_DOCS = 'https://github.com/NVIDIA/SkillSpector/blob/v2.12.0'

const RULES: Record<string, { name: string, section: string }> = {
  P1: { name: 'Instruction Override', section: 'prompt-injection-6-patterns' },
  P2: { name: 'Hidden Instructions', section: 'prompt-injection-6-patterns' },
  P3: { name: 'Exfiltration Commands', section: 'prompt-injection-6-patterns' },
  P4: { name: 'Behavior Manipulation', section: 'prompt-injection-6-patterns' },
  P5: { name: 'Harmful Content', section: 'prompt-injection-6-patterns' },
  P9: { name: 'Whitespace Padding', section: 'prompt-injection-6-patterns' },
  AR1: { name: 'Refusal Suppression', section: 'anti-refusal-3-patterns' },
  AR2: { name: 'Disclaimer Suppression', section: 'anti-refusal-3-patterns' },
  AR3: { name: 'Safety Policy Nullification', section: 'anti-refusal-3-patterns' },
  E1: { name: 'External Transmission', section: 'data-exfiltration-4-patterns' },
  E2: { name: 'Env Variable Harvesting', section: 'data-exfiltration-4-patterns' },
  E3: { name: 'File System Enumeration', section: 'data-exfiltration-4-patterns' },
  E4: { name: 'Context Leakage', section: 'data-exfiltration-4-patterns' },
  PE1: { name: 'Excessive Permissions', section: 'privilege-escalation-3-patterns' },
  PE2: { name: 'Sudo/Root Execution', section: 'privilege-escalation-3-patterns' },
  PE3: { name: 'Credential Access', section: 'privilege-escalation-3-patterns' },
  SC1: { name: 'Unpinned Dependencies', section: 'supply-chain-10-patterns' },
  SC2: { name: 'External Script Fetching', section: 'supply-chain-10-patterns' },
  SC3: { name: 'Obfuscated Code', section: 'supply-chain-10-patterns' },
  SC4: { name: 'Known Vulnerable Dependencies', section: 'supply-chain-10-patterns' },
  SC5: { name: 'Abandoned Dependencies', section: 'supply-chain-10-patterns' },
  SC6: { name: 'Typosquatting', section: 'supply-chain-10-patterns' },
  SC8: { name: 'Shipped Python Bytecode', section: 'supply-chain-10-patterns' },
  SC9: { name: 'Concealed Executable Artifact', section: 'supply-chain-10-patterns' },
  SC10: { name: 'Dependency Source Redirection', section: 'supply-chain-10-patterns' },
  EA1: { name: 'Unrestricted Tool Access', section: 'excessive-agency-5-patterns' },
  EA2: { name: 'Autonomous Decision Making', section: 'excessive-agency-5-patterns' },
  EA3: { name: 'Scope Creep', section: 'excessive-agency-5-patterns' },
  EA4: { name: 'Unbounded Resource Access', section: 'excessive-agency-5-patterns' },
  OH1: { name: 'Unvalidated Output Injection', section: 'output-handling-3-patterns' },
  OH2: { name: 'Cross-Context Output', section: 'output-handling-3-patterns' },
  OH3: { name: 'Unbounded Output', section: 'output-handling-3-patterns' },
  P6: { name: 'Direct Leakage', section: 'system-prompt-leakage-3-patterns' },
  P7: { name: 'Indirect Extraction', section: 'system-prompt-leakage-3-patterns' },
  P8: { name: 'Tool-Based Exfiltration', section: 'system-prompt-leakage-3-patterns' },
  MP1: { name: 'Persistent Context Injection', section: 'memory-poisoning-3-patterns' },
  MP2: { name: 'Context Window Stuffing', section: 'memory-poisoning-3-patterns' },
  MP3: { name: 'Memory Manipulation', section: 'memory-poisoning-3-patterns' },
  TM1: { name: 'Tool Parameter Abuse', section: 'tool-misuse-3-patterns' },
  TM2: { name: 'Chaining Abuse', section: 'tool-misuse-3-patterns' },
  TM3: { name: 'Unsafe Defaults', section: 'tool-misuse-3-patterns' },
  RA1: { name: 'Self-Modification', section: 'rogue-agent-2-patterns' },
  RA2: { name: 'Session Persistence', section: 'rogue-agent-2-patterns' },
  TR1: { name: 'Overly Broad Trigger', section: 'trigger-abuse-3-patterns' },
  TR2: { name: 'Shadow Command Trigger', section: 'trigger-abuse-3-patterns' },
  TR3: { name: 'Keyword Baiting Trigger', section: 'trigger-abuse-3-patterns' },
  AST1: { name: 'exec() Call', section: 'behavioral-ast-9-patterns' },
  AST2: { name: 'eval() Call', section: 'behavioral-ast-9-patterns' },
  AST3: { name: 'Dynamic Import', section: 'behavioral-ast-9-patterns' },
  AST4: { name: 'subprocess Call', section: 'behavioral-ast-9-patterns' },
  AST5: { name: 'os.system / exec-family', section: 'behavioral-ast-9-patterns' },
  AST6: { name: 'compile() Call', section: 'behavioral-ast-9-patterns' },
  AST7: { name: 'Dynamic getattr()', section: 'behavioral-ast-9-patterns' },
  AST8: { name: 'Dangerous Execution Chain', section: 'behavioral-ast-9-patterns' },
  AST9: { name: 'Reflective getattr() Sink', section: 'behavioral-ast-9-patterns' },
  TT1: { name: 'Direct Taint Flow', section: 'taint-tracking-5-patterns' },
  TT2: { name: 'Variable-Mediated Taint Flow', section: 'taint-tracking-5-patterns' },
  TT3: { name: 'Credential Exfiltration Chain', section: 'taint-tracking-5-patterns' },
  TT4: { name: 'File Read to Network Exfiltration', section: 'taint-tracking-5-patterns' },
  TT5: { name: 'External Input to Code Execution', section: 'taint-tracking-5-patterns' },
  YR1: { name: 'Malware Match', section: 'yara-signatures-4-patterns' },
  YR2: { name: 'Webshell Match', section: 'yara-signatures-4-patterns' },
  YR3: { name: 'Cryptominer Match', section: 'yara-signatures-4-patterns' },
  YR4: { name: 'Hack Tool / Exploit Match', section: 'yara-signatures-4-patterns' },
  LP1: { name: 'Underdeclared Capability', section: 'mcp-least-privilege-4-patterns' },
  LP2: { name: 'Wildcard Permission', section: 'mcp-least-privilege-4-patterns' },
  LP3: { name: 'Missing Permission Declaration', section: 'mcp-least-privilege-4-patterns' },
  LP4: { name: 'Overdeclared Permission', section: 'mcp-least-privilege-4-patterns' },
  TP1: { name: 'Hidden Instructions', section: 'mcp-tool-poisoning-4-patterns' },
  TP2: { name: 'Unicode Deception', section: 'mcp-tool-poisoning-4-patterns' },
  TP3: { name: 'Parameter Description Injection', section: 'mcp-tool-poisoning-4-patterns' },
  TP4: { name: 'Description-Behavior Mismatch', section: 'mcp-tool-poisoning-4-patterns' }
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
  if (RULE_PAGES[ruleId]) return `${SKILLSPECTOR_DOCS}/${RULE_PAGES[ruleId]}`
  const rule = RULES[ruleId]
  return rule ? `${SKILLSPECTOR_DOCS}/README.md#${rule.section}` : null
}

/** The rule's name in skillspector's docs, e.g. "Instruction Override". */
export function ruleName(ruleId: string): string | null {
  return RULES[ruleId]?.name ?? MCP_RULES[ruleId] ?? null
}
