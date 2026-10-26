/**
 * 用 CDP 精确控制 Edge：1280x720 视口 + 滚动到指定位置截真实页面。
 * 为什么不用 --screenshot：整页截图会让视口高度变化，某些区块布局随之改变，
 * 截出来的图就和「别人用浏览器打开的样子」不一致了。
 *
 * 用法：
 *   node scripts/shoot_web_shots.mjs --probe              # 只打印各区块 y 坐标
 *   node scripts/shoot_web_shots.mjs --out DIR --plan P   # 按计划截图
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9333;
const W = 1280, H = 720;

const argv = process.argv.slice(2);
const arg = (k, d = null) => {
  const i = argv.indexOf(k);
  return i >= 0 ? argv[i + 1] : d;
};
const PROBE = argv.includes('--probe');
const OUT = arg('--out', '.tmp/vid/shots');
const URL_ = arg('--url', 'file:///E:/Agent/career-loop/docs/standalone.html?s=0');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function launch() {
  const child = spawn(EDGE, [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--no-first-run',
    '--no-default-browser-check',
    `--remote-debugging-port=${PORT}`,
    `--window-size=${W},${H}`,
    'about:blank',
  ], { stdio: 'ignore', detached: false });
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (r.ok) return child;
    } catch { /* 还没起来 */ }
    await sleep(250);
  }
  throw new Error('Edge 调试端口没起来');
}

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      const p = this.pending.get(msg.id);
      if (p) {
        this.pending.delete(msg.id);
        msg.error ? p.reject(new Error(msg.error.message)) : p.resolve(msg.result);
      }
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
}

async function connect() {
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  const page = list.find((t) => t.type === 'page');
  if (!page) throw new Error('没有 page target');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true });
    ws.addEventListener('error', rej, { once: true });
  });
  return new CDP(ws);
}

const evalJS = async (cdp, expression) => {
  const r = await cdp.send('Runtime.evaluate', {
    expression, returnByValue: true, awaitPromise: true,
  });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' + expression);
  return r.result.value;
};

async function main() {
  const child = await launch();
  const cdp = await connect();
  try {
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: W, height: H, deviceScaleFactor: 1, mobile: false,
    });
    await cdp.send('Page.navigate', { url: URL_ });
    await sleep(2500);

    // 等页面把示例跑完（结果区有 .9% 这种字样），再等动画收敛
    for (let i = 0; i < 30; i++) {
      const ready = await evalJS(cdp, `(()=>{
        const t=document.body.innerText||'';
        return /\\d+\\.\\d%/.test(t) && readyState();
        function readyState(){ return document.readyState === 'complete'; }
      })()`);
      if (ready) break;
      await sleep(400);
    }
    await sleep(1500);

    if (PROBE) {
      const info = await evalJS(cdp, `(()=>{
        const out=[];
        document.querySelectorAll('h2,h3').forEach(el=>{
          const r=el.getBoundingClientRect();
          if (r.height>0 && r.width>0) out.push({
            tag: el.tagName,
            text: (el.innerText||'').replace(/\\s+/g,' ').slice(0,28),
            top: Math.round(r.top + window.scrollY),
          });
        });
        return JSON.stringify({ height: document.documentElement.scrollHeight, anchors: out });
      })()`);
      console.log(info);
      return;
    }

    const plan = JSON.parse(fs.readFileSync(arg('--plan'), 'utf8'));
    fs.mkdirSync(OUT, { recursive: true });
    for (const shot of plan) {
      if (shot.prep) await evalJS(cdp, shot.prep);
      await evalJS(cdp, `window.scrollTo(0, ${shot.y}); 1`);
      await sleep(700);
      const { data } = await cdp.send('Page.captureScreenshot', { format: 'png' });
      const file = path.join(OUT, `${shot.name}.png`);
      fs.writeFileSync(file, Buffer.from(data, 'base64'));
      console.log(`✓ ${file}  y=${shot.y}`);
    }
  } finally {
    try { await cdp.send('Browser.close'); } catch { /* ignore */ }
    child.kill();
  }
}

main().catch((e) => { console.error('✗', e.message); process.exit(1); });
