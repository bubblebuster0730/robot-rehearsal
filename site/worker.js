// worker.js — 계산 엔진. Pyodide(브라우저용 CPython 3.12)로 simulate.py 원본을 그대로 실행한다.
const base = new URL('./', self.location.href).href;
let py = null, W = null;
const post = (m) => self.postMessage(m);
// 게시 서버는 .zip을 내보내지 않으므로 zip 두 개(표준 라이브러리, 시뮬레이터 묶음)를 base64 텍스트로 받아 바이트로 되돌린다.
const _fetch = self.fetch.bind(self);
async function b64bytes(url) {
  const r = await _fetch(url);
  if (!r.ok) throw new Error(url.split('/').pop() + '을 받지 못했습니다 (' + r.status + ')');
  const bin = atob((await r.text()).trim());
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return u8;
}
self.fetch = async (input, init) => {
  const url = typeof input === 'string' ? input : (input && input.url) || String(input);
  if (url.endsWith('python_stdlib.zip')) return new Response(await b64bytes(base + 'py/python_stdlib.txt'), { headers: { 'Content-Type': 'application/zip' } });
  return _fetch(input, init);
};

async function boot() {
  try {
    post({ type: 'status', stage: 1, msg: '계산 엔진 내려받는 중 (약 16 MB, 처음 한 번)' });
    importScripts(base + 'py/pyodide.js');
    py = await self.loadPyodide({ indexURL: base + 'py/', stdout: () => {}, stderr: () => {} });
    post({ type: 'status', stage: 2, msg: '파이썬 시작, 시뮬레이터 불러오는 중' });
    py.unpackArchive(await b64bytes(base + 'lib.txt'), 'zip', { extractDir: '/sim' });
    py.runPython("import sys; sys.path.insert(0, '/sim')");
    W = py.pyimport('sim_web');
    W.init('/sim/data');
    post({ type: 'ready', version: py.runPython('import sys; sys.version.split()[0]') + ' · Pyodide ' + py.version });
  } catch (e) {
    post({ type: 'error', where: 'boot', msg: String((e && e.message) || e).slice(-600) });
  }
}

self.onmessage = (ev) => {
  const m = ev.data;
  if (!W) { post({ type: 'error', id: m.id, where: 'run', msg: '계산 엔진이 아직 준비되지 않았습니다.' }); return; }
  if (m.type === 'run') {
    try {
      const t = performance.now();
      const json = W.run(JSON.stringify(m.cfg), (d, n) => post({ type: 'progress', id: m.id, done: d, total: n }));
      post({ type: 'result', id: m.id, json, ms: Math.round(performance.now() - t) });
    } catch (e) {
      post({ type: 'error', id: m.id, where: 'run', msg: String((e && e.message) || e).slice(-600) });
    }
  } else if (m.type === 'source') {
    try {
      post({ type: 'source', text: py.runPython("open('/sim/simulate.py', encoding='utf-8').read()") });
    } catch (e) { post({ type: 'source', text: '코드를 읽지 못했습니다: ' + e }); }
  }
};

boot();
