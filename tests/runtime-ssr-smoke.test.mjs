import assert from 'node:assert/strict';
import test, { after } from 'node:test';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { createServer } from 'vite';

const vite = await createServer({
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'error',
});

after(async () => {
  await vite.close();
});

async function renderModule(path, elementFactory) {
  const mod = await vite.ssrLoadModule(path);
  return renderToString(elementFactory(mod));
}

test('app shell renders the splash brand in SSR smoke', async () => {
  const html = await renderModule('/App.tsx', (mod) => React.createElement(mod.default));

  assert.ok(html.includes('PRISM'));
  assert.ok(html.includes('(食鉴)'));
  assert.ok(html.includes('透视美食本质'));
});

test('register view exposes the compliance entries in SSR smoke', async () => {
  const html = await renderModule('/components/views/RegisterView.tsx', (mod) => React.createElement(mod.default, {
    onViewChange: () => {},
    onRegisterSuccess: () => {},
    onOpenCompliance: () => {},
  }));

  for (const required of ['《用户协议》', '《隐私政策》', '《AI 使用说明》', '《健康免责声明》']) {
    assert.ok(html.includes(required), `Missing register compliance entry: ${required}`);
  }
});

test('compliance view renders the five legal documents in SSR smoke', async () => {
  const html = await renderModule('/components/views/ComplianceView.tsx', (mod) => React.createElement(mod.default, {
    activeDocument: 'terms',
    onDocumentChange: () => {},
    onClose: () => {},
  }));

  assert.ok(html.includes('用户协议'));
  assert.ok(html.includes('使用 Prism 前，请理解服务边界、账号责任和内容限制。'));
});
