#!/usr/bin/env node
/**
 * npx ephe — one-command install wrapper (R20).
 * macOS/Linux: runs install.sh from the tag that matches this package
 * (override with EPHE_INSTALL_URL).
 * Windows: runs install.ps1 through PowerShell, with `scoop install ephe` as the fallback.
 */
const { spawn } = require('node:child_process')
const { version } = require('./package.json')

const RELEASE_BASE = `https://raw.githubusercontent.com/bemlerlabs/ephe/v${version}`
const INSTALL_SH = process.env.EPHE_INSTALL_URL || `${RELEASE_BASE}/install.sh`
const INSTALL_PS1 = `${RELEASE_BASE}/install.ps1`
const args = process.argv.slice(2)

console.log('◑ Ephe — one-command install')

if (process.platform === 'win32') {
  const child = spawn(
    'powershell.exe',
    ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', `irm ${INSTALL_PS1} | iex`],
    { stdio: 'inherit' },
  )
  child.on('exit', (code) => {
    if (code !== 0) {
      console.error('Ephe install failed. You can also install it with: scoop install ephe')
    }
    process.exit(code ?? 1)
  })
} else {
  // install.sh fetches the release and installs into ~/Documents/Ephe itself, so the wrapper
  // leaves no clone behind in the caller's working directory.
  const child = spawn(
    'bash',
    ['-c', 'curl -fsSL "${EPHE_INSTALL_URL}" | bash -s -- "$@"', '--', ...args],
    { stdio: 'inherit', env: { ...process.env, EPHE_INSTALL_URL: INSTALL_SH } },
  )
  child.on('exit', (code) => process.exit(code ?? 1))
}
