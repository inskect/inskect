<script setup lang="ts">
const { site } = useAppConfig()
const siteUrl = useSiteUrl()

// What people search for: whether a skill is safe, for which agents, against which threats.
const title = 'Is this AI agent skill safe? Scan skills and MCP servers — Inskect'
const description = 'Scan Claude Code, Codex and other AI agent skills, and MCP servers, for prompt injection, data exfiltration and dangerous code before you install them. Open source.'
useSeoMeta({ title, description, ogTitle: title, ogDescription: description })

// Structured data, for search engines to tell what the site is.
useHead({
  script: [{
    type: 'application/ld+json',
    innerHTML: JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'WebApplication',
      'name': site.name,
      'url': `${siteUrl}/`,
      description,
      'applicationCategory': 'SecurityApplication',
      'operatingSystem': 'Any',
      'browserRequirements': 'Requires JavaScript',
      'image': `${siteUrl}${site.ogImage.path}`
    })
  }]
})

// With accounts on, signed-out visitors get the landing page instead of the scanner. Each is its own
// chunk, so a page loads the code of only the one it shows.
const { accounts, user } = useAuth()
</script>

<template>
  <LazyLandingPage v-if="accounts && !user" />
  <LazyHomeScanner v-else />
</template>
