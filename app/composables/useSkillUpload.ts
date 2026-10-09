// Sends an uploaded skill with the options of its inspection, and returns the inspection queued.
export type UploadSkill = (file: File, options: Record<string, unknown>) => Promise<{ id: string }>

declare module '#app' {
  interface NuxtApp {
    // Provided by a plugin of an app extending this one, to send the file another way, e.g. to
    // object storage first when a request can't carry it (docs/EXTENDING.md): none ships here.
    $uploadSkill?: UploadSkill
  }
}

/** How the scan form uploads a skill: through $uploadSkill if a plugin provides it, otherwise the
 * file and the options in one request to /api/scan/upload. Call it in setup. */
export function useSkillUpload(): UploadSkill {
  const nuxtApp = useNuxtApp()
  return async (file, options) => {
    if (nuxtApp.$uploadSkill) return await nuxtApp.$uploadSkill(file, options)
    const form = new FormData()
    form.append('file', file)
    form.append('options', JSON.stringify(options))
    return await $fetch<{ id: string }>('/api/scan/upload', { method: 'POST', body: form })
  }
}
