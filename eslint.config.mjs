// @ts-check
import withNuxt from './.nuxt/eslint.config.mjs'

export default withNuxt({
  files: ['app/**', 'server/**', 'shared/**'],
  rules: {
    // In an app that extends this one as a Nuxt layer, `~` and `~~` are that app's directories, not
    // this one's (docs/EXTENDING.md): import this app's own files by relative path.
    'no-restricted-imports': ['error', {
      patterns: [{ regex: '^~~?/', message: 'Import by relative path: in an app extending this one, ~ and ~~ are its directories.' }]
    }]
  }
})
