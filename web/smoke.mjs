import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'

const OUT = path.join(process.cwd(), 'smoke-shots')
const SAMPLES = path.resolve(process.cwd(), '..', 'samples')
fs.mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })

const errors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text())
})
page.on('pageerror', (err) => errors.push(String(err)))

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' })
await page.waitForSelector('text=PlagCheck')
await page.screenshot({ path: path.join(OUT, '01-initial.png') })
console.log('step 1: initial page rendered')

const input = page.locator('input[type="file"]')
await input.setInputFiles([
  path.join(SAMPLES, 'sample_a.txt'),
  path.join(SAMPLES, 'sample_b.txt'),
  path.join(SAMPLES, 'sample_code_a.py'),
  path.join(SAMPLES, 'sample_code_b.py'),
])
await page.waitForSelector('text=sample_a.txt')
await page.screenshot({ path: path.join(OUT, '02-files-selected.png') })
console.log('step 2: 4 files selected')

await page.getByRole('radio', { name: 'All' }).click()
await page.getByRole('button', { name: /^Scan 4 files$/ }).click()

await page.waitForSelector('text=Results', { timeout: 30000 })
await page.waitForTimeout(600)
await page.screenshot({ path: path.join(OUT, '03-results.png'), fullPage: true })
console.log('step 3: results + heatmap rendered')

const cells = page.locator('.heatmap-cell-flagged')
const flaggedCount = await cells.count()
console.log('flagged cells:', flaggedCount)
if (flaggedCount > 0) {
  await cells.first().click()
  await page.waitForSelector('.inspector-panel', { timeout: 15000 })
  await page.waitForSelector('.inspector-pane', { timeout: 15000 })
  await page.waitForTimeout(500)
  await page.screenshot({ path: path.join(OUT, '04-inspector.png') })
  const marks = await page.locator('.inspector-pane mark').count()
  console.log('step 4: inspector open, highlighted spans:', marks)
} else {
  console.log('step 4 SKIPPED: no flagged cells to click')
}

console.log('CONSOLE_ERRORS:', JSON.stringify(errors))
await browser.close()
