import { describe, expect, it } from 'vitest'
import { aiReviewText } from '../app/utils/aiReview'

describe('aiReviewText', () => {
  it('names the providers this server allows', () => {
    expect(aiReviewText(['anthropic', 'openai', 'ollama'])).toContain('with Claude, OpenAI or Ollama, through your own key or endpoint')
    expect(aiReviewText(['openai'], false)).toContain('with OpenAI, through your own key.')
  })

  it('says where the skill goes when only Claude, with your own key, is allowed', () => {
    expect(aiReviewText(['anthropic'], false)).toContain('your own Claude key')
    expect(aiReviewText(['anthropic'], false)).toContain('goes to Anthropic')
  })

  it('falls back to the usual providers when the server is unknown', () => {
    expect(aiReviewText(undefined)).toContain('with Claude, OpenAI or Ollama')
  })
})
