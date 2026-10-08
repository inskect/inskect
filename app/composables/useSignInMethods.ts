import type { SignInMethods } from '~~/shared/types/auth'

// The signed-in user's ways to sign in, shared by the Account page's cards: whether there's a
// password to ask for again changes what several of them ask.
export function useSignInMethods() {
  return useFetch<SignInMethods>('/api/account/sign-in-methods', { key: 'sign-in-methods' })
}
