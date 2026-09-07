import assert from "node:assert/strict";
import test from "node:test";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

test("renders development preview metadata", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  const response = await worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/html\b/i,
  );
  assert.match(await response.text(), developmentPreviewMeta);
});

test('production serves task form and hides the development-only mobile harness', async () => {
  const {default:worker}=await import('../dist/server/index.js');
  const env={ASSETS:{fetch:async()=>new Response('Not found',{status:404})}};
  const ctx={waitUntil(){},passThroughOnException(){}};
  const page=await worker.fetch(new Request('http://localhost/'),env,ctx);
  assert.equal(page.status,200);
  const html=await page.text();
  assert.match(html,/Что нужно сделать/);
  assert.match(html,/Добавить/);
  assert.match(html,/lang="ru"/);
  const qa=await worker.fetch(new Request('http://localhost/qa/mobile'),env,ctx);
  assert.equal(qa.status,404);
});
