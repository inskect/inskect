import { describe, expect, it } from 'vitest'
import { apiErrorMessage } from '../app/utils/apiError'

describe('apiErrorMessage', () => {
  it('shows the API’s own message, including when to retry after a rate limit', () => {
    const err = { data: { statusMessage: 'You’ve started a lot of scans — try again in 40 seconds' }, response: { status: 429 } }

    expect(apiErrorMessage(err, 'Failed')).toBe('You’ve started a lot of scans — try again in 40 seconds')
  })

  it('explains a rate limit that came without a message, such as a firewall rule', () => {
    const err = { data: '<html>Too Many Requests</html>', response: { status: 429 } }

    expect(apiErrorMessage(err, 'Failed')).toBe('Too many requests — wait a minute and try again.')
  })

  it('falls back when there is nothing better to say', () => {
    expect(apiErrorMessage({ data: undefined, response: { status: 500 } }, 'Failed')).toBe('Failed')
  })
})
