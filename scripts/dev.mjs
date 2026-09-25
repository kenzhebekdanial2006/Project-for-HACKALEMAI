import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { stopChild } from './processes.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const windows = process.platform === 'win32'
const venv = path.join(root, 'backend', '.venv', windows ? 'Scripts/python.exe' : 'bin/python')
const python = process.env.WINDOPS_PYTHON || (existsSync(venv) ? venv : windows ? 'python' : 'python3')
const check = spawn(python, ['-c', 'import fastapi, uvicorn, catboost, pandas, requests, dotenv, openai'], {
  cwd: root,
  stdio: 'ignore',
  windowsHide: true,
})
check.once('error', () => {
  console.error('Python is unavailable. Set WINDOPS_PYTHON to your Python interpreter.')
  process.exitCode = 1
})
check.once('exit', async (code) => {
  if (code !== 0) {
    console.error(
      'Install the backend dependencies first: python -m venv backend/.venv, then use that environment to install -r backend/requirements.txt. See README.md.',
    )
    process.exitCode = 1
    return
  }
  const api = spawn(
    python,
    ['-m', 'uvicorn', 'backend.windops.api.app:app', '--host', '127.0.0.1', '--port', '8000'],
    { cwd: root, stdio: 'inherit', windowsHide: true },
  )
  let web
  let closing = false
  const close = (code) => {
    if (closing) return
    closing = true
    stopChild(api)
    stopChild(web)
    process.exitCode = typeof code === 'number' ? code : 0
  }
  process.on('SIGINT', () => close(0))
  process.on('SIGTERM', () => close(0))
  api.on('error', (error) => {
    console.error(error.message)
    close(1)
  })
  api.on('exit', (code) => close(code))
  for (let attempt = 0; attempt < 60 && !closing; attempt++) {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/health', { signal: AbortSignal.timeout(1000) })
      if (response.ok && !closing) {
        web = spawn(
          process.execPath,
          [path.join(root, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1'],
          { cwd: root, stdio: 'inherit', windowsHide: true },
        )
        web.on('error', (error) => {
          console.error(error.message)
          close(1)
        })
        web.on('exit', (code) => close(code))
        return
      }
    } catch {
      /* Wait for the local server before opening the frontend. */
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  if (!closing) {
    console.error('The backend did not start in time.')
    close(1)
  }
})
