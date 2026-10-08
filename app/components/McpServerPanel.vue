<script setup lang="ts">
import type { McpServer } from '~~/shared/types/scan'

const props = defineProps<{ server: McpServer }>()

const STATUS_CLASSES: Record<string, string> = {
  active: 'text-safe-ink',
  deprecated: 'text-medium-ink',
  deleted: 'text-critical-ink'
}

// The registry's links are the publisher's to set: only web links become clickable.
function webLink(url: string | null | undefined): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

const details = computed(() => {
  const { server } = props
  const rows: { label: string, value: string, href?: string | null, class?: string }[] = []
  if (server.version) rows.push({ label: 'Version', value: server.is_latest === false ? `${server.version} (not the latest)` : server.version })
  rows.push({ label: 'Status', value: server.status ?? 'Not given', class: STATUS_CLASSES[server.status ?? ''] ?? 'text-muted' })
  if (server.repository?.url) {
    const subfolder = server.repository.subfolder ? ` (${server.repository.subfolder})` : ''
    rows.push({ label: 'Repository', value: server.repository.url + subfolder, href: webLink(server.repository.url) })
  }
  if (server.website_url) rows.push({ label: 'Website', value: server.website_url, href: webLink(server.website_url) })
  if (server.published_at) rows.push({ label: 'Published', value: server.published_at.slice(0, 10) })
  if (server.updated_at && server.updated_at !== server.published_at) rows.push({ label: 'Updated', value: server.updated_at.slice(0, 10) })
  return rows
})
</script>

<template>
  <section
    aria-labelledby="mcp-server-heading"
    class="surface flex flex-col gap-5 px-4 py-4 sm:px-5"
  >
    <div class="flex flex-col gap-1">
      <h2
        id="mcp-server-heading"
        class="flex items-center gap-2 text-lg font-semibold tracking-tight text-highlighted"
      >
        <UIcon
          name="i-lucide-server"
          class="size-5 text-muted"
        />
        <UntrustedText :value="server.title || server.name" />
      </h2>
      <p
        v-if="server.description"
        class="text-sm text-muted"
      >
        {{ server.description }}
      </p>
      <p class="text-sm text-muted">
        Checked from its entry in the MCP Registry: nothing was installed or run.
      </p>
    </div>

    <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-1.5 text-sm">
      <template
        v-for="row in details"
        :key="row.label"
      >
        <dt class="text-muted">
          {{ row.label }}
        </dt>
        <dd class="min-w-0 break-all">
          <ULink
            v-if="row.href"
            :to="row.href"
            target="_blank"
            rel="noopener noreferrer"
            class="text-highlighted hover:underline"
          >
            {{ row.value }}
          </ULink>
          <span
            v-else
            :class="row.class ?? 'text-highlighted'"
          >{{ row.value }}</span>
        </dd>
      </template>
    </dl>

    <div
      v-if="server.packages.length"
      class="flex flex-col gap-2"
    >
      <h3 class="font-semibold text-highlighted">
        Packages
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[34rem] text-sm">
          <thead>
            <tr class="text-left text-xs text-muted">
              <th class="py-2 pr-3 font-medium">
                Package
              </th>
              <th class="py-2 pr-3 font-medium">
                Registry
              </th>
              <th class="py-2 pr-3 font-medium">
                Version
              </th>
              <th class="py-2 pr-3 font-medium">
                SHA-256
              </th>
              <th class="py-2 font-medium">
                Transport
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(pkg, index) in server.packages"
              :key="index"
              class="border-t border-muted"
            >
              <td class="py-2 pr-3 font-mono text-xs break-all text-highlighted">
                {{ pkg.identifier ?? '—' }}
              </td>
              <td class="py-2 pr-3 text-muted">
                {{ pkg.registry_type ?? '—' }}
              </td>
              <td class="py-2 pr-3 font-mono text-xs">
                {{ pkg.version ?? '—' }}
              </td>
              <td class="py-2 pr-3 text-muted">
                {{ pkg.file_sha256 ? 'Given' : '—' }}
              </td>
              <td class="py-2 text-muted">
                {{ pkg.transport_type ?? '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div
      v-if="server.remotes.length"
      class="flex flex-col gap-2"
    >
      <h3 class="font-semibold text-highlighted">
        Remote endpoints
      </h3>
      <ul class="flex flex-col gap-1 text-sm">
        <li
          v-for="(remote, index) in server.remotes"
          :key="index"
          class="flex min-w-0 gap-2"
        >
          <span class="shrink-0 text-muted">{{ remote.type ?? 'remote' }}</span>
          <span class="font-mono text-xs break-all text-highlighted">{{ remote.url ?? '—' }}</span>
        </li>
      </ul>
    </div>

    <UAlert
      v-if="server.unchecked.length"
      color="neutral"
      variant="subtle"
      icon="i-lucide-circle-help"
      :title="`${server.unchecked.length} check${server.unchecked.length === 1 ? '' : 's'} couldn’t run`"
    >
      <template #description>
        <p>The registry entry doesn’t give what they need, so they don’t count towards the verdict.</p>
        <ul class="mt-1 list-disc pl-5">
          <li
            v-for="(item, index) in server.unchecked"
            :key="index"
          >
            {{ item.message }}: <span class="font-mono text-xs break-all"><UntrustedText :value="item.target" /></span>
            <span class="text-dimmed"> ({{ item.id }})</span>
          </li>
        </ul>
      </template>
    </UAlert>
  </section>
</template>
