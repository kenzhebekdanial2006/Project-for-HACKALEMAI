import { spawn } from 'node:child_process'

// Windows virtual-environment launchers may spawn another Python process.
// Stop only this launcher's own child tree so Ctrl+C also releases the API port.
export function stopChild(child) {
  if (!child?.pid || child.exitCode !== null) return
  if (process.platform === 'win32') {
    const stop = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
      stdio: 'ignore', windowsHide: true,
    })
    stop.on('error', () => child.kill())
  } else child.kill()
}
