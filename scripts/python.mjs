import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { stopChild } from './processes.mjs'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const windows = process.platform === 'win32'
const venv = path.join(root, 'backend', '.venv', windows ? 'Scripts/python.exe' : 'bin/python')
const python = process.env.WINDOPS_PYTHON || (existsSync(venv) ? venv : windows ? 'python' : 'python3')
const child = spawn(python, process.argv.slice(2), { cwd: root, stdio: 'inherit', windowsHide: true })
child.once('error', (error) => {
  console.error(error.message)
  process.exitCode = 1
})
child.once('exit', (code) => {
  process.exitCode = code ?? 1
})
process.on('SIGINT', () => stopChild(child))
process.on('SIGTERM', () => stopChild(child))
