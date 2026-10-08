<script setup lang="ts">
const { session, refresh } = useAuth()

const status = computed(() => session.value?.claude_key ?? null)
const editing = ref(false)
const apiKey = ref('')
const saving = ref(false)
const removing = ref(false)
const errorMessage = ref('')
const notice = ref('')

async function save() {
  saving.value = true
  errorMessage.value = ''
  notice.value = ''
  try {
    await $fetch('/api/account/claude', { method: 'PUT', body: { apiKey: apiKey.value.trim() } })
    notice.value = status.value ? 'Key replaced.' : 'Connected. Your AI reviews now use this key.'
    apiKey.value = ''
    editing.value = false
    await refresh()
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to save your key')
  } finally {
    saving.value = false
  }
}

async function disconnect() {
  removing.value = true
  errorMessage.value = ''
  notice.value = ''
  try {
    await $fetch('/api/account/claude', { method: 'DELETE' })
    notice.value = 'Disconnected. The key was deleted from this server.'
    await refresh()
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to disconnect')
  } finally {
    removing.value = false
  }
}
</script>

<template>
  <UCard>
    <div class="flex flex-col gap-4">
      <div class="flex flex-col gap-1">
        <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <h2 class="sheet-title text-highlighted">
            Claude key
          </h2>
          <span
            class="inline-flex shrink-0 items-center gap-1.5 px-2 py-1 text-xs font-semibold"
            :class="status ? 'bg-safe-tint text-safe-ink ring-1 ring-safe-line' : 'bg-elevated text-muted ring-1 ring-default'"
          >
            <UIcon
              :name="status ? 'i-lucide-plug' : 'i-lucide-unplug'"
              class="size-3.5"
            />
            {{ status ? 'Connected' : 'Not connected' }}
          </span>
        </div>
        <p class="text-sm text-muted">
          Your own Anthropic API key, used for your inspections' AI review without pasting it each time.
          It's checked with Anthropic, stored encrypted, and never shown again.
        </p>
      </div>

      <p
        v-if="status && !editing"
        class="text-sm text-default"
      >
        Key <code class="bg-muted px-1.5 py-0.5 font-mono text-xs text-highlighted">{{ status.hint }}</code>,
        saved <NuxtTime
          :datetime="status.updated_at * 1000"
          relative
        />.
      </p>

      <UButton
        v-if="!status && !editing"
        color="primary"
        icon="i-lucide-plug"
        class="self-start"
        @click="editing = true; notice = ''"
      >
        Connect a key
      </UButton>

      <form
        v-else-if="editing"
        class="flex flex-col gap-3"
        @submit.prevent="save"
      >
        <UFormField
          label="Anthropic API key"
          description="Starts with sk-ant-. Create one on console.anthropic.com."
        >
          <template #hint>
            <ULink
              to="https://console.anthropic.com/settings/keys"
              target="_blank"
              class="text-xs"
            >
              Get a key
            </ULink>
          </template>
          <PasswordInput
            id="claude-api-key"
            v-model="apiKey"
            autofocus
            subject="API key"
            autocomplete="off"
            placeholder="sk-ant-…"
            class="w-full"
            required
          />
        </UFormField>
        <div class="flex flex-wrap gap-2">
          <UButton
            type="submit"
            color="primary"
            icon="i-lucide-plug"
            :loading="saving"
            :disabled="!apiKey.trim()"
          >
            {{ status ? 'Replace key' : 'Connect' }}
          </UButton>
          <UButton
            color="neutral"
            variant="ghost"
            @click="editing = false; apiKey = ''"
          >
            Cancel
          </UButton>
        </div>
      </form>

      <div
        v-else
        class="flex flex-wrap gap-2"
      >
        <UButton
          color="neutral"
          variant="outline"
          icon="i-lucide-refresh-cw"
          @click="editing = true; notice = ''"
        >
          Replace
        </UButton>
        <UButton
          color="error"
          variant="outline"
          icon="i-lucide-unplug"
          :loading="removing"
          @click="disconnect"
        >
          Disconnect
        </UButton>
      </div>

      <UAlert
        v-if="notice"
        color="success"
        variant="subtle"
        icon="i-lucide-check-circle-2"
        :title="notice"
      />
      <UAlert
        v-if="errorMessage"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="errorMessage"
      />
    </div>
  </UCard>
</template>
