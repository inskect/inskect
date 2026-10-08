<script setup lang="ts">
import type { DirectoryUser } from '~~/shared/types/backoffice'
import type { UserRole } from '~~/shared/types/auth'

useSeoMeta({ title: 'Users — Backoffice — Inskect' })

const search = ref('')
// Search as the admin types, without a request per keystroke.
const query = ref('')
let debounce: ReturnType<typeof setTimeout> | undefined
watch(search, (value) => {
  clearTimeout(debounce)
  debounce = setTimeout(() => {
    query.value = value
  }, 250)
})
const { data: users, error, status, refresh } = await useFetch<DirectoryUser[]>('/api/admin/users', {
  key: 'admin-users',
  query: computed(() => (query.value.trim() ? { query: query.value.trim() } : {}))
})

type Filter = 'all' | 'admin' | 'suspended'
const filter = ref<Filter>('all')
const visible = computed(() => (users.value ?? []).filter((user) => {
  if (filter.value === 'admin') return user.role === 'admin'
  if (filter.value === 'suspended') return user.status === 'suspended'
  return true
}))

const adding = ref(false)
const email = ref('')
const password = ref('')
const role = ref<UserRole>('user')
const saving = ref(false)
const addError = ref('')

async function addUser() {
  saving.value = true
  addError.value = ''
  try {
    const created = await $fetch<{ id: string }>('/api/admin/users', {
      method: 'POST',
      body: { email: email.value.trim(), password: password.value, role: role.value }
    })
    adding.value = false
    email.value = ''
    password.value = ''
    role.value = 'user'
    await refresh()
    await navigateTo(`/admin/users/${created.id}`)
  } catch (err) {
    addError.value = apiErrorMessage(err, 'Failed to add the user')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <BackofficeHeader
      title="Users"
      lead="Everyone who can sign in. Users see only their own inspections; admins see everything and run the backoffice."
    >
      <UButton
        color="primary"
        icon="i-lucide-user-plus"
        size="lg"
        @click="adding = true; addError = ''"
      >
        Add user
      </UButton>
    </BackofficeHeader>

    <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div
        role="group"
        aria-label="Filter users"
        class="flex flex-wrap gap-1.5"
      >
        <button
          v-for="option in (['all', 'admin', 'suspended'] as const)"
          :key="option"
          type="button"
          :aria-pressed="filter === option"
          class="h-10 cursor-pointer border px-3.5 text-sm font-semibold capitalize transition-colors"
          :class="filter === option ? 'border-inverted bg-inverted text-inverted' : 'border-default bg-default text-highlighted hover:bg-muted'"
          @click="filter = option"
        >
          {{ option === 'all' ? 'All' : option === 'admin' ? 'Admins' : 'Suspended' }}
        </button>
      </div>
      <UInput
        v-model="search"
        type="search"
        icon="i-lucide-search"
        placeholder="Search by email"
        aria-label="Search users by email"
        size="lg"
        class="md:w-80"
        :loading="status === 'pending'"
      />
    </div>

    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      :title="apiErrorMessage(error, 'Failed to load users')"
    />

    <div
      v-else
      class="sheet overflow-hidden"
    >
      <table class="w-full table-fixed text-sm">
        <thead>
          <tr class="eyebrow border-b border-default text-left text-muted">
            <th
              scope="col"
              class="px-4 py-3.5 font-bold sm:px-5"
            >
              User
            </th>
            <th
              scope="col"
              class="w-36 px-4 py-3.5 font-bold max-sm:hidden"
            >
              Inspections
            </th>
            <th
              scope="col"
              class="w-36 px-4 py-3.5 font-bold max-md:hidden"
            >
              Last sign-in
            </th>
            <th
              scope="col"
              class="w-32 px-4 py-3.5 font-bold max-lg:hidden"
            >
              Joined
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="user in visible"
            :key="user.id"
            class="border-b border-muted transition-colors last:border-b-0 hover:bg-muted"
          >
            <td class="px-4 py-3.5 sm:px-5">
              <NuxtLink
                :to="`/admin/users/${user.id}`"
                class="flex min-w-0 flex-col gap-1"
              >
                <span class="truncate font-semibold text-highlighted">{{ user.email }}</span>
                <UserBadges
                  :role="user.role"
                  :status="user.status"
                />
              </NuxtLink>
            </td>
            <td class="px-4 py-3.5 font-mono text-highlighted tabular-nums max-sm:hidden">
              {{ user.scan_count }}
            </td>
            <td
              class="px-4 py-3.5 whitespace-nowrap text-muted max-md:hidden"
              :title="user.last_login_at ? formatDate(user.last_login_at) : undefined"
            >
              <NuxtTime
                v-if="user.last_login_at"
                :datetime="user.last_login_at * 1000"
                relative
              />
              <template v-else>
                Never
              </template>
            </td>
            <td
              class="px-4 py-3.5 whitespace-nowrap text-muted max-lg:hidden"
              :title="formatDate(user.created_at)"
            >
              <NuxtTime
                :datetime="user.created_at * 1000"
                relative
              />
            </td>
          </tr>
        </tbody>
      </table>
      <p
        v-if="!visible.length"
        class="px-5 py-6 text-sm text-muted"
      >
        No users match.
      </p>
    </div>

    <UModal
      v-model:open="adding"
      title="Add a user"
      description="They sign in with this email and password. Share the password with them securely; they can change it from their account."
    >
      <template #body>
        <form
          id="add-user-form"
          class="flex flex-col gap-4"
          @submit.prevent="addUser"
        >
          <UFormField label="Email">
            <UInput
              id="new-user-email"
              v-model="email"
              type="email"
              autocomplete="off"
              class="w-full"
              required
            />
          </UFormField>
          <UFormField
            label="Password"
            description="At least 10 characters."
          >
            <PasswordInput
              id="new-user-password"
              v-model="password"
              autocomplete="new-password"
              class="w-full"
              required
            />
          </UFormField>
          <UFormField label="Role">
            <USelect
              id="new-user-role"
              v-model="role"
              :items="[{ label: 'User — runs and sees their own inspections', value: 'user' }, { label: 'Admin — everything, including the backoffice', value: 'admin' }]"
              value-key="value"
              class="w-full"
            />
          </UFormField>
          <UAlert
            v-if="addError"
            color="error"
            variant="subtle"
            :title="addError"
          />
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            variant="ghost"
            color="neutral"
            @click="adding = false"
          >
            Cancel
          </UButton>
          <UButton
            type="submit"
            form="add-user-form"
            color="primary"
            icon="i-lucide-user-plus"
            :loading="saving"
            :disabled="!email.trim() || password.length < 10"
          >
            Add user
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
