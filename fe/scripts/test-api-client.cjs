const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

function client(fetcher) {
  const source = fs.readFileSync(path.join(__dirname, '../app/ui/api-client.ts'), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const context = { exports: {}, AbortSignal, fetch: fetcher,
    require: name => { assert.equal(name, './flight-types'); return { API_BASE: '/api/' }; } };
  vm.runInNewContext(code, context);
  return context.exports.apiRequest;
}

test('uses the frontend proxy and preserves POST payload', async () => {
  const request = client(async (url, options) => {
    assert.equal(url, '/api/analytics/run');
    assert.equal(options.method, 'POST');
    assert.equal(options.body, '{"date_from":"2025-01-01"}');
    assert.equal(options.cache, 'no-store');
    assert.ok(options.signal);
    return Response.json({ status: 'completed' });
  });
  assert.equal((await request('/analytics/run', { method: 'POST', body: '{"date_from":"2025-01-01"}' })).status, 'completed');
});

test('keeps a successful not-ready result distinct from a connection error', async () => {
  const request = client(async () => Response.json({ ready: false, output: { items: [], metadata: { reason: 'model_missing' } } }));
  assert.equal((await request('/prediction/results')).output.metadata.reason, 'model_missing');
});

test('exposes a backend service error', async () => {
  const request = client(async () => Response.json({ detail: "Service 'analytics' is unavailable" }, { status: 502 }));
  await assert.rejects(request('/analytics/summary'), /analytics.*unavailable/);
});

test('reports network failures and invalid JSON', async () => {
  await assert.rejects(client(async () => { throw new TypeError('Failed to fetch'); })('/ingestion/raw'), /Không kết nối được API/);
  await assert.rejects(client(async () => new Response('<html>wrong endpoint</html>'))('/ingestion/raw'), /không hợp lệ/);
});

test('preserves caller cancellation', async () => {
  const controller = new AbortController();
  controller.abort();
  const error = new DOMException('Cancelled', 'AbortError');
  const request = client(async () => { throw error; });
  await assert.rejects(request('/ingestion/raw', { signal: controller.signal }), failure => failure === error);
});
