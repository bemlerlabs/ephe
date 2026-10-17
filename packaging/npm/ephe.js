#!/usr/bin/env node
/**
 * npx ephe — one-command-install wrapper (R20).
 * Delegates to install.sh (macOS/Linux). Windows users: install.ps1
 * (or scoop — see packaging/scoop/).
 */
const { spawn } = require('node:child_process')
const os = require('node:os')

if (os.platform() === 'win32') {
  console.error('Windows: nutze install.ps1 aus dem Repo (oder scoop install ephe).')
  process.exit(1)
}

const repo = process.env.EPHE_EPHE_REPO || 'https://github.com/bemlerlabs/ephe.git'
console.log(`◑ Ephe — One-command install (repo: ${repo})`)

const child = spawn('bash', ['-c', `git clone --depth 1 ${repo} ephe 2>/dev/null || true && cd ephe && ./install.sh "$@"`, '--', ...process.argv.slice(2)], {
  stdio: 'inherit',
})
child.on('exit', (code) => process.exit(code ?? 1))
