"""Writes test.html: runs the workflow's Code nodes against sample data for the fictional example
project (Northwind Solar) in a browser. Serve this folder (python -m http.server 8765) and open
http://127.0.0.1:8765/test.html; every line should start with PASS."""
import json
import os

import js_code as js
import js_v3 as js3
import prompts

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
read = lambda *p: open(os.path.join(REPO, *p), encoding="utf-8").read()
KB = read("projects", "northwind-solar", "knowledge-base.md")
LINK_MAP = read("projects", "northwind-solar", "link-map.json")

codes = {k: getattr(js, k) for k in ["PROJECT", "POST_SETTINGS", "PICK_COMPETITORS", "BRIEF", "QA", "SURGICAL_CLEAN", "BUILD_DOC",
                                     "BUILD_REQUEST_ROW", "CLEAN_KB"]}
codes.update({k: getattr(js3, k) for k in ["SITEMAP_FILES", "PICK_OWN_PAGES", "OWN_EVIDENCE", "VERIFY_GAIN"]})
PROMPTS = {k: getattr(prompts, k) for k in ["WEB_SEARCH_BODY", "COMMODITY_AUDIT", "GAIN_PLANNER", "GAIN_AUDITOR", "OUTLINE_PLANNER",
                                           "BLOG_WRITER", "EDITOR", "SURGICAL_EDITOR", "META"]}

harness = r"""
const out = [];
const log = (name, ok, detail) => out.push(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : ': ' + (typeof detail === 'string' ? detail : JSON.stringify(detail))}`);
const AsyncFn = Object.getPrototypeOf(async function () {}).constructor;
const outputs = {};
const items = arr => arr.map(j => ({ json: j }));
function mk(name, data) { outputs[name] = items(Array.isArray(data) ? data : [data]); }
const $ = n => { if (!outputs[n]) throw new Error('no mock for ' + n); return { first: () => outputs[n][0], all: () => outputs[n] }; };
async function run(name, input, code) {
  // URL is passed as undefined to mimic n8n's Code sandbox, which has no URL class
  const fn = new AsyncFn('$input', '$', '$runIndex', 'URL', '$execution', code || CODES[name]);
  return fn.call({}, { first: () => input[0], all: () => input }, $, 0, undefined, { id: '42' });
}
const withProjects = list => CODES.PROJECT.replace(/const PROJECTS = \[[\s\S]*?\n\];/, 'const PROJECTS = ' + JSON.stringify(list) + ';');
const BASE = 'https://www.northwind-solar.example';

(async () => {
 try {
  // ---------------------------------------------------------------- prompts
  for (const [name, text] of Object.entries(PROMPTS)) {
    log(`prompt ${name}: no unfilled [TOKEN] and no other brand`, !/\[(BRAND|DOMAIN|CONTEXT|SEARCH|COUNTRY|PRICING_RULE|ACRONYMS|TERMS)\]/.test(text) && !/Northwind/.test(text), text.slice(0, 80));
  }
  log('prompts read the brand and market from the Project node', PROMPTS.BLOG_WRITER.includes("$('Project').first().json.brand") && PROMPTS.WEB_SEARCH_BODY.includes("' + $('Project').first().json.market.country + '"), 'missing');

  // ---------------------------------------------------------------- Project node
  mk('Blog Request Form', { Project: 'Northwind Solar' });
  const projErr = await run('PROJECT', items([{}])).then(() => '', e => e.message);
  log('project: the shipped example stops until its Drive file IDs are pasted in', projErr.includes('Northwind Solar is not set up yet'), projErr);
  const NW = { enabled: true, name: 'Northwind Solar', domain: 'northwind-solar.example', base_url: BASE, description: 'a solar installer in Bristol', home_anchor: 'solar panel installation in Bristol',
    case_studies: true, acronyms: ['PV', 'MCS', 'kWh'], terminology: [['solar cells', 'solar panels']], kb_file_id: 'KB1', link_map_file_id: 'LM1',
    claim_rules: [['\\bguarantee[sd]?\\b[^.\\n]{0,40}\\bsavings?\\b', 'gi', 'Never guarantee savings.']], topic_synonyms: [['batter\\w*|storage', ['battery', 'storage'], ['inverter']]] };
  const US = { enabled: true, name: 'Lakeside Roofing Services', domain: 'lakeside-roofing.example', kb_file_id: 'KB2', link_map_file_id: 'LM2', heading_case: 'title', prices_on_request: false,
    market: { country: 'United States', search_label: 'Google US', google_domain: 'google.com', language: 'US English', spelling: 'american', currency: 'USD', currency_symbol: '$' } };
  const LIST = [NW, US, { enabled: false, name: 'Project 3' }];
  const project = async choice => { mk('Blog Request Form', { Project: choice }); return (await run('PROJECT', items([{}]), withProjects(LIST)))[0].json; };
  const nw = await project('Northwind Solar');
  const us = await project('lakeside roofing services');
  const off = await project('Project 3').then(() => '', e => e.message);
  log('project: picked by name, with its own IDs, home, sitemap and defaults', nw.brand === 'Northwind Solar' && nw.kb_file_id === 'KB1' && nw.home === BASE + '/' && nw.sitemap === BASE + '/sitemap_index.xml' && nw.market.currency === 'GBP' && nw.has_case_studies, nw);
  log('project: matched case-insensitively; market settings flow through', us.brand === 'Lakeside Roofing Services' && us.market.spelling === 'american' && us.language_rule === 'US English, USD for all money' && us.heading_word === 'Title Case', us.language_rule);
  log('project: a disabled project is refused with a clear message', off.includes('no enabled project'), off);
  log('project: all your domains are known (never studied as competitors)', nw.all_domains.join() === 'northwind-solar.example,lakeside-roofing.example', nw.all_domains);
  log('project: a brand that is a plain search phrase is not spell-checked', us.brand_check === false && nw.brand_check === true, [us.brand_check, nw.brand_check]);
  log('project: ready-made prompt wording (pricing, acronyms, terms)', nw.pricing_rule.includes('never publishes prices') && nw.pricing_rule.includes('£') && us.pricing_rule.startsWith('Prices may be mentioned only') && nw.acronym_text.startsWith('PV / MCS / kWh') && nw.terms_text === '"solar panels", never "solar cells"', [nw.acronym_text, nw.terms_text]);
  mk('Project', nw);

  // ---------------------------------------------------------------- Post Settings
  const ps = async (form, notes) => { mk('Start', { notes }); mk('Blog Request Form', form); return (await run('POST_SETTINGS', items([{}])))[0].json; };
  const psStd = await ps({ 'Post format': 'Standard guide', 'Use case studies?': 'Yes' }, '');
  const psList = await ps({ 'Post format': 'Standard guide', 'Use case studies?': 'Yes' }, 'Write it as a listicle, and do not use case studies.');
  log('post settings: form choices and typed requirements', psStd.format === 'standard' && psStd.use_case_studies && psList.format === 'listicle' && !psList.use_case_studies, [psStd.format, psList.format]);
  mk('Project', { ...nw, has_case_studies: false, brand: 'Plain Co' });
  const psNone = await ps({ 'Post format': 'Comparison', 'Use case studies?': 'Yes' }, '');
  log('post settings: a project without case studies never uses them', !psNone.use_case_studies && psNone.case_study_rule.includes('Plain Co') && psNone.profile.table === 'required', psNone.case_study_rule.slice(0, 60));
  mk('Project', nw);
  mk('Post Settings', psStd);

  // ---------------------------------------------------------------- competitors
  const reply = { choices: [{ message: { content: JSON.stringify({ organic: [
    { url: BASE + '/blog/how-many-solar-panels-do-i-need', title: 'Ours' }, { url: 'https://www.lakeside-roofing.example/solar', title: 'Also ours' },
    { url: 'https://www.reddit.com/r/solar/x', title: 'Forum' }, { url: 'https://rival-solar.example/cost-guide', title: 'Rival' }], people_also_ask: ['Do I need planning permission?'] }) } }] };
  const comp = (await run('PICK_COMPETITORS', items([reply]))).map(i => i.json);
  log('competitors: your own projects and forums are skipped', comp.length === 1 && comp[0].url === 'https://rival-solar.example/cost-guide', comp.map(c => c.url));

  // ---------------------------------------------------------------- own pages and evidence
  const urls = ['services/solar-panel-installation', 'services/battery-storage', 'services/ev-charger-installation', 'services/inverter-replacement', 'case-studies/east-west-roof-bishopston',
    'case-studies/chew-valley-dairy-farm', 'case-studies/battery-retrofit-clifton', 'contact', 'about', 'bristol-solar-grants', 'bristol-solar-faqs', 'bristol-installers-team'];
  const posts = ['blog/how-many-solar-panels-do-i-need', 'blog/is-a-home-battery-worth-it', 'blog/bristol-solar-costs-2026'];
  const sm = list => `<urlset>${list.map(u => `<url><loc>${BASE}/${u}</loc><lastmod>2026-09-01</lastmod></url>`).join('')}</urlset>`;
  mk('Start', { keyword: 'battery storage Bristol', title_idea: 'Is battery storage worth it in Bristol?', notes: '' });
  const files = (await run('SITEMAP_FILES', items([{ data: `<sitemapindex><sitemap><loc>${BASE}/page-sitemap.xml</loc></sitemap><sitemap><loc>${BASE}/post-sitemap.xml</loc></sitemap></sitemapindex>` }]))).map(i => i.json.url);
  mk('Sitemap Files', files.map(url => ({ url })));
  const own = (await run('PICK_OWN_PAGES', items([{ data: sm(urls) }, { data: sm(posts) }]))).map(i => i.json);
  log('own pages: battery case study and service chosen; "Bristol" (in most addresses) ignored', own[0].url.endsWith('battery-retrofit-clifton') && own.some(p => p.url.endsWith('services/battery-storage')) && !own.some(p => p.url.includes('bristol-')), own.map(p => p.url));
  log('own pages: topic synonyms widen the match ("inverter" counts for a battery post)', own.some(p => p.url.endsWith('inverter-replacement')) || own[0].site_pages.find(p => p.url.endsWith('inverter-replacement')).score > 0, own[0].site_pages.map(p => [p.url.split('/').pop(), p.score]));
  mk('Pick Own Pages', own);
  const page = `<html><body><nav>menu</nav><h1>Battery retrofit, Clifton</h1><article><p>We added a 10 kWh battery to a 2019 system without changing the panels, and the install took one morning.</p><p>"The battery runs the house all evening," said the homeowner.</p></article></body></html>`.padEnd(800, ' ');
  const ev = (await run('OWN_EVIDENCE', items(own.map((p, i) => (i === 0 ? { data: page } : { error: 'blocked' })))))[0].json;
  log('evidence: our page becomes tagged first-hand evidence, menus stripped', ev.sources.length === 1 && ev.sources[0].id === 'E1' && ev.evidence_text.includes('10 kWh battery') && !ev.evidence_text.includes('menu'), ev.evidence_text.slice(0, 120));
  mk('Own Evidence', ev);
  mk('Knowledge Base', { kb: KB });
  mk('Score Commodity', { commodity: [{ claim: 'Batteries store solar power for the evening' }] });
  const gain = (await run('VERIFY_GAIN', items([{ output: { delta_items: [
    { type: 'case_study_data', finding: 'A 10 kWh battery was added to an existing system in one morning.', evidence_id: 'E1', evidence_quote: 'We added a 10 kWh battery to a 2019 system without changing the panels' },
    { type: 'first_hand_process', finding: 'Every quote follows an in-person roof survey.', evidence_id: 'KB', evidence_quote: 'Every quote follows an in-person roof survey.' },
    { type: 'expert_commentary', finding: 'Our installers always recommend two batteries.', evidence_id: 'KB', evidence_quote: 'our installers always recommend two batteries for every home' }] } }])))[0].json;
  log('verify gain: real quotes kept, an invented one dropped and reported', gain.delta_items.length === 2 && gain.gain_notes.some(n => n.includes('Left out before writing') && n.includes('two batteries')), gain.gain_notes);
  mk('Verify Gain', gain);

  // ---------------------------------------------------------------- brief
  mk('Start', { keyword: 'battery storage Bristol', title_idea: 'Is battery storage worth it in Bristol?', notes: '', word_count: 1200, seo_name: 'Sam', date: '2 Nov 2026', reference_url: '' });
  mk('Competitor Digest', { median_competitor_words: 1400, paa: ['Do I need planning permission?'], questions: [], related: [], outlines: '', serp_overview: '' });
  mk('Link Map Text', { link_map_text: LINK_MAP });
  mk('Reference Page', { has_reference: false, reference_outline: [] });
  mk('Post Settings', { ...psStd, use_case_studies: false });
  const brief = (await run('BRIEF', items([{ output: { final_title: 'Is battery storage worth it in Bristol?', supporting_keywords: ['home battery Bristol'], consensus_points: ['How batteries are sized'], title_questions: ['How big a battery?'], paa_to_answer: [], search_intent: 'x', angle: 'y', opening_scene: 'z', recommended_word_count: 1600 } }])))[0].json;
  log('brief: case studies off keeps client names for QA, but not your city or trade words', brief.case_study_tokens.includes('clifton') && brief.case_study_tokens.includes('bishopston') && !brief.case_study_tokens.includes('bristol') && !brief.case_study_tokens.includes('battery'), brief.case_study_tokens);
  mk('Post Settings', psStd);

  // ---------------------------------------------------------------- QA (code checks and safe fixes)
  mk('Brief', { ...brief, primary_keyword: 'battery storage Bristol', supporting_keywords: ['home battery Bristol'], target_word_count: 300, case_study_tokens: ['clifton'] });
  const words = n => Array.from({ length: n }, (_, i) => `word${i}`).join(' ');
  const blog = `# Is battery storage worth it in Bristol?

## TL;DR

Battery storage in Bristol is worth it when you use most of your power in the evening.

Picture a homeowner reading a quote. Battery storage Bristol answer here, with [solar panel installation in Bristol](${BASE}/).

## Is battery storage worth it in Bristol for a small home?

**A small home with low evening use often does better without a battery than with one.**

It may pay back, which might make sense. Our solar cells and the Pv panel and the kwh meter are very amazing things. Read more on [battery storage](${BASE}/services/battery-storage). We guarantee big savings. Our battery costs £4,000 to install. Prices start at $3,000 in US terms. ${words(310)}

## FAQs

### Q?

A.`;
  const qa = (await run('QA', items([{ blog }])))[0].json;
  const has = s => qa.issues.some(i => i.includes(s));
  log('qa: house terminology fixed in code ("solar cells" -> "solar panels")', qa.blog.includes('solar panels') && !qa.blog.includes('solar cells') && qa.fixes.some(f => f.includes('"solar panels"')), qa.fixes);
  log('qa: project acronyms in the wrong case flagged (Pv), lowercase 3+ letters flagged (kwh)', has('Write "PV" exactly like that') && has('Lowercase "kwh"'), qa.issues.filter(i => /PV|kwh/.test(i)));
  log('qa: project claim rules flagged', has('Never guarantee savings'), qa.issues.find(i => i.includes('guarantee')));
  log('qa: own price in the project currency flagged; another currency is not', has('Never state or imply what Northwind Solar charges') && has('£4,000') && !qa.issues.find(i => i.includes('charges')).includes('$3,000'), qa.issues.find(i => i.includes('charges')));
  log('qa: weak wording, link prompts and scene openings flagged', has('"may" and "might"') && has('"make sense"') && has('weak intensifier') && has('vague placeholder') && has('Link prompts found') && has('opening starts with a scene'), qa.issues.length);
  log('qa: long section without a subheading and missing supporting keyword flagged', has('without a subheading') && has('home battery Bristol'), qa.issues.filter(i => /subheading|never appear/.test(i)));
  mk('Project', us);
  const qaUs = (await run('QA', items([{ blog: '# how much does a new roof cost?\n\n## TL;DR\n\nOur colours and the centre of the organised roof.\n\nOpening.\n\n## what drives the cost of a roof in the city?\n\nText.\n\n## FAQs\n\n### Q?\n\nA.' }])))[0].json;
  log('qa: spelling follows the project market (American here)', qaUs.issues.some(i => i.startsWith('Use American') && i.includes('colours')) && qaUs.issues.some(i => i.startsWith('Use American -ize')), qaUs.issues.filter(i => i.startsWith('Use')));
  log('qa: a Title Case project gets every heading recased in code', qaUs.blog.startsWith('# How Much Does a New Roof Cost?') && qaUs.blog.includes('## What Drives the Cost of a Roof in the City?') && qaUs.blog.includes('## TL;DR'), qaUs.blog.split('\n').filter(l => l.startsWith('#')));
  mk('Project', nw);
  mk('Brief', { ...brief, primary_keyword: 'How many solar panels do I need?', supporting_keywords: ['solar panel installation in the UK'], target_word_count: 0, case_study_tokens: [] });
  const qk = (await run('QA', items([{ blog: '# T\n\n## TL;DR\n\nHow many solar panels do I need? Most homes need 8 to 12.\n\nHow many solar panels do I need for a terraced house? It depends on solar panel installation in the UK rules too.\n\n## How many solar panels do I need?\n\n**A bold finding long enough to count here.**\n\nText.\n\n## FAQs\n\n### Q?\n\nA.' }])))[0].json;
  log('qa: question keywords and keywords with linking words match', !qk.issues.some(i => /is missing from|never appear/.test(i)), qk.issues.filter(i => /missing from|never appear/.test(i)));

  // ---------------------------------------------------------------- surgical sign-off guard
  const lines = Array.from({ length: 20 }, (_, i) => `Sentence ${i} explains one specific installation detail clearly.`);
  const audited = '# T\n\n' + lines.join(' ');
  mk('Final QA', { blog: audited });
  const small = (await run('SURGICAL_CLEAN', items([{ text: audited.replace('Sentence 3 explains', 'Sentence 3 now names') }])))[0].json;
  const broad = (await run('SURGICAL_CLEAN', items([{ text: '# T\n\n' + lines.map((s, i) => (i % 2 ? s : s.replace('explains', 'rewrites'))).join(' ') }])))[0].json;
  log('sign-off: a small surgical edit is kept, a broad rewrite is discarded', small.editor_used && !broad.editor_used && broad.blog === audited, [small.surgical_note, broad.surgical_note]);

  // ---------------------------------------------------------------- Doc and Sheet row
  mk('Config', { docs_folder_id: 'FOLDER', sheet_url: 'https://docs.google.com/spreadsheets/d/TEST_SHEET_ID/edit' });
  mk('Brief', { ...brief, final_title: 'Is battery storage worth it in Bristol?', primary_keyword: 'battery storage Bristol', keywords_csv: 'home battery Bristol' });
  mk('Sign-off Result', { blog: '# T\n\n## FAQs\n\n### How long?\n\nOne day.', issues: [], tldr: 'Answer.', word_count: 1200, gain_pct: 30, focus_pct: 100, readability: null, internal_links: 6, external_links: 1, delta_used: [], unanswered_questions: [] });
  mk('QA Check', { fixes: ['Replaced 1 em/spaced dash(es) with commas'] });
  mk('Validate Outline', { outline_notes: [] });
  mk('Reference Page', {});
  const metas = ['Learn when battery storage Bristol homes add pays off, how to size a battery for evening use and what to send Northwind Solar for an accurate quote today.',
    'Find out when battery storage Bristol homeowners add is worth the cost, how to size a battery for evening use and which questions to ask an installer.',
    'Battery storage Bristol.'];
  mk('Meta Generator', { output: { slug: 'battery-storage-bristol', meta_title: 'Battery Storage Bristol | Home Batteries | Northwind Solar', meta_descriptions: metas, category: 'Costs and savings' } });
  const doc = (await run('BUILD_DOC', items([{ html: '<h1>T</h1><p>TLDRBOXPLACEHOLDER</p>' }])))[0].json;
  const ld = JSON.parse(doc.multipart_body.match(/font-size:9pt">([^<]+)<\/p>/)[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));
  log('doc: picks the 140-155 character meta description with the keyword and no brand', doc.meta_description === metas[1], { got: doc.meta_description, len: metas[1].length });
  log('doc: schema uses the project brand, domain and FAQs; Project row', ld[0].publisher.name === 'Northwind Solar' && ld[0].mainEntityOfPage === BASE + '/battery-storage-bristol' && ld[1].mainEntity[0].name === 'How long?' && doc.multipart_body.includes('Northwind Solar (northwind-solar.example)') && doc.status === 'Done', ld[0]);
  const col = (i, name, type) => ({ columnIndex: i, columnName: name, columnType: type });
  const row = (await run('BUILD_REQUEST_ROW', items([{ sheets: [{ properties: { sheetId: 0 }, tables: [{ tableId: 't', columnProperties: [col(0, 'Request ID', 'DOUBLE'), col(1, 'Project', 'TEXT')] }] }] }])))[0].json.body.requests[0].appendCells.rows[0].values;
  log('sheet: the request row records the project', row[1].userEnteredValue.stringValue === 'Northwind Solar', row);

  // ---------------------------------------------------------------- knowledge base file
  const ck = (await run('CLEAN_KB', items([{ kb: KB }])))[0].json;
  log('knowledge base: the example file passes through untouched', !ck.kb_cleaned && ck.kb === KB.replace(/\r\n?/g, '\n'), ck.kb_cleaned);
 } catch (e) {
  out.push('CRASH ' + e.stack);
 }
 document.getElementById('r').textContent = out.join('\n') + `\n\n${out.filter(l => l.startsWith('PASS')).length} passed, ${out.filter(l => !l.startsWith('PASS')).length} failed`;
})();
"""

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Habib's Autoloader tests</title></head><body><pre id="r">running</pre>
<script>const CODES = {json.dumps(codes)}; const PROMPTS = {json.dumps(PROMPTS)}; const KB = {json.dumps(KB)}; const LINK_MAP = {json.dumps(LINK_MAP)};</script>
<script>{harness.replace('</script>', '<\\/script>')}</script></body></html>"""
open(os.path.join(HERE, "test.html"), "w", encoding="utf-8").write(html)
print("ok")
