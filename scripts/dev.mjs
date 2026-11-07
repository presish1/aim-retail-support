import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'

if (!existsSync('.venv/bin/python')) {
  console.error('Run the Python setup in README.md first.'); process.exit(1)
}
const children = [
  spawn('.venv/bin/python', ['-m', 'uvicorn', 'backend.app:app', '--reload', '--reload-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'], { stdio: 'inherit' }),
  spawn('node_modules/.bin/vite', ['--host', '127.0.0.1'], { stdio: 'inherit' }),
]
let stopping = false
function stop(code = 0) { if (stopping) return; stopping = true; children.forEach(c => c.kill('SIGTERM')); setTimeout(() => process.exit(code), 250) }
process.on('SIGINT', () => stop())
process.on('SIGTERM', () => stop())
children.forEach(c => { c.on('error', e => { console.error(e); stop(1) }); c.on('exit', code => { if (!stopping) stop(code ?? 1) }) })
