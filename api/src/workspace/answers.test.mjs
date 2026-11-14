import assert from 'node:assert/strict';
import test from 'node:test';
import { answerQuestion } from './answers.mjs';

const match = { page: 4, snippet: 'Scanned log', signals: ['Keyword'] };
const ranked = {
  results: [match],
  notes: [],
  evidence: [{ page: 4, passages: ['Replacement monitors are in aisle seven.'] }],
};

function provider(content) {
  return async () => Response.json({
    choices: [{ finish_reason: 'stop', message: { content: JSON.stringify(content) } }],
  });
}

test('answers with evidence and returns verified page citations', async () => {
  const result = await answerQuestion('Where are the monitors?', ranked, {
    apiKey: 'test-key',
    fetchAnswer: async (url, request) => {
      assert.equal(url, 'https://openrouter.ai/api/v1/chat/completions');
      assert.equal(request.headers.Authorization, 'Bearer test-key');
      const body = JSON.parse(request.body);
      assert.equal(body.model, 'deepseek/deepseek-v4-flash-20260731');
      assert.deepEqual(JSON.parse(body.messages[1].content).evidence, ranked.evidence);
      return provider({ answer: 'Aisle seven.', pages: [4, 4] })();
    },
  });
  assert.deepEqual(result, {
    results: [match], notes: [], answer: { text: 'Aisle seven.', pages: [4] },
  });
});

test('skips the provider when there is no evidence', async () => {
  let called = false;
  const result = await answerQuestion('What is the address?', { ...ranked, evidence: [] }, {
    apiKey: 'test-key',
    fetchAnswer: async () => { called = true; },
  });
  assert.equal(called, false);
  assert.equal(result.answer, null);
});

test('rejects an invented page citation and preserves the matches', async () => {
  const result = await answerQuestion('Where are the monitors?', ranked, {
    apiKey: 'test-key',
    fetchAnswer: provider({ answer: 'Aisle seven.', pages: [4, 8] }),
  });
  assert.deepEqual(result.results, [match]);
  assert.equal(result.answer, null);
  assert.ok(result.answerError);
});

test('returns matches if there is no configured key or the provider fails', async () => {
  for (const apiKey of ['', 'test-key']) {
    const result = await answerQuestion('Where are the monitors?', ranked, {
      apiKey,
      fetchAnswer: async () => new Response(null, { status: 429 }),
    });
    assert.deepEqual(result.results, [match]);
    assert.equal(result.answer, null);
    assert.ok(result.answerError);
  }
});
