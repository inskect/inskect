// Every 2 seconds at first; slower once a scan has been running a while, since it's then likely to
// run a while longer.
const DELAYS_MS: { after: number, delay: number }[] = [
  { after: 120_000, delay: 5000 },
  { after: 30_000, delay: 3500 },
  { after: 0, delay: 2000 }
]

/**
 * Runs `poll` again and again while `active()` holds: every 2 seconds at first, slowing to 5. It
 * pauses while the tab is hidden, and polls as soon as the tab is shown again. `start()` begins
 * (or resumes, once active again); nothing runs on the server.
 */
export function usePoll(poll: () => Promise<unknown>, active: () => boolean) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let startedAt = 0
  let polling = false

  function schedule() {
    clearTimeout(timer)
    if (!active() || document.hidden) return
    const elapsed = Date.now() - startedAt
    timer = setTimeout(tick, DELAYS_MS.find(step => elapsed >= step.after)!.delay)
  }

  async function tick() {
    if (polling) return
    polling = true
    try {
      await poll()
    } finally {
      polling = false
    }
    schedule()
  }

  function onVisibilityChange() {
    clearTimeout(timer)
    if (!document.hidden && active()) tick()
  }

  function start() {
    if (import.meta.server) return
    if (!startedAt) startedAt = Date.now()
    schedule()
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', onVisibilityChange)
    start()
  })
  onUnmounted(() => {
    clearTimeout(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { start }
}
