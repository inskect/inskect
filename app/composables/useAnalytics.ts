import type { AnalyticsEvents } from '../utils/analytics'

type Track = <Name extends keyof AnalyticsEvents>(name: Name, data?: AnalyticsEvents[Name]) => void

declare module '#app' {
  interface NuxtApp {
    // Provided by an analytics plugin, if the build adds one: none ships with the app.
    $track?: Track
  }
}

/** Track an analytics event; does nothing without an analytics plugin, as by default. Call it in
 * setup, and the function it returns whenever. */
export function useAnalytics(): { track: Track } {
  const nuxtApp = useNuxtApp()
  return { track: (name, data) => nuxtApp.$track?.(name, data) }
}
