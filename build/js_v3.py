"""Code nodes added in v3 (information gain protocol)."""

SCORE_COMMODITY = r"""// Step 1 of the information gain protocol: anything two or more ranking pages say is
// commodity content. Figures repeated across pages count as commodity too.
const digest = $('Competitor Digest').first().json;
const pages = digest.page_texts || [];
const claims = ($input.first().json.output?.claims || []).filter(c => c && c.claim);
const pageCount = pages.length;

const valid = c => [...new Set((c.pages || []).map(Number).filter(n => n >= 1 && n <= pageCount))];
const commodity = [];
const competitor_unique = [];
for (const c of claims) {
  const ps = valid(c);
  const entry = { claim: String(c.claim).trim(), type: c.type || 'point', pages: ps };
  if (ps.length >= 2) commodity.push(entry);
  else if (ps.length === 1) competitor_unique.push(entry);
}

// Figures (money, percentages, sizes, durations, counts) that appear on 2+ pages
const FIG = /\p{Sc}\s?\d[\d,.]*k?|\b\d[\d,.]*\s?(?:%|mm\b|m\b|metres?\b|meters?\b|kw\b|watts?\b|w\b|hours?\b|hrs?\b|days?\b|weeks?\b|guests?\b|people\b|delegates?\b|channels?\b|seats?\b)/giu;
const normFig = f => f.toLowerCase().replace(/\s+/g, '').replace(/,/g, '').replace(/metres?|meters?/, 'm').replace(/hrs?|hours?/, 'h').replace(/s$/, '');
const figPages = new Map();
pages.forEach((p, i) => {
  for (const f of new Set((p.text.match(FIG) || []).map(normFig))) {
    if (!figPages.has(f)) figPages.set(f, new Set());
    figPages.get(f).add(i + 1);
  }
});
const commodity_stats = [...figPages.entries()].filter(([, s]) => s.size >= 2).map(([f, s]) => `${f} (pages ${[...s].join(', ')})`).slice(0, 20);

// Questions searchers ask that no ranking page answers: no matching question heading and
// no single page that contains most of the question's meaningful words
const STOP = new Set('a an and are as at be best by can do does for from how i in is it my of on or should the to what when where which who why will with you your'.split(' '));
const sig = s => [...new Set((String(s).toLowerCase().match(/[a-z0-9]+/g) || []).filter(w => w.length > 2 && !STOP.has(w)))];
const pageQuestions = (digest.questions || []).map(sig);
const pageWords = pages.map(p => new Set(sig(p.text)));
const asked = [...new Set([...(digest.paa || []), ...(digest.related || []).filter(r => /\?$/.test(r))])];
const unanswered_questions = asked.filter(q => {
  const w = sig(q);
  if (!w.length) return false;
  const headingHit = pageQuestions.some(pq => w.filter(x => pq.includes(x)).length / w.length >= 0.6);
  const textHit = pageWords.some(set => w.filter(x => set.has(x)).length / w.length >= 0.8);
  return !headingHit && !textHit;
});

const commodity_text = [
  ...commodity.slice(0, 25).map(c => `- ${c.claim} (pages ${c.pages.join(', ')})`),
  ...(commodity_stats.length ? [`- Figures repeated across pages: ${commodity_stats.join('; ')}`] : []),
].join('\n') || '- No commodity content identified (no competitor pages could be read).';

return [{ json: { commodity, commodity_stats, competitor_unique, unanswered_questions, commodity_text, pages_analysed: pageCount } }];"""

SITEMAP_FILES = r"""// The sitemap index lists the child sitemaps; keep the page, post and product sitemaps
const site = $('Project').first().json;
const xml = String($input.first().json.data || '');
const locs = [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map(m => m[1]);
let maps = locs.filter(u => /(page|post|products?)-sitemap\d*\.xml$/i.test(u));
if (!maps.length) maps = [`${site.base}/page-sitemap.xml`, `${site.base}/post-sitemap.xml`];
return maps.map(url => ({ json: { url } }));"""

PICK_OWN_PAGES = r"""// Read every URL in the site's sitemaps, then pick the case studies and service pages that
// best match this blog's topic as first-hand evidence
const BASE = $('Project').first().json.base;
const start = $('Start').first().json;
// Page type comes from the sitemap a URL is listed in: posts are blog posts; pages are
// case studies (under /case-studies/) or service and company pages
const files = $('Sitemap Files').all().map(i => i.json.url);
const SKIP_PAGES = /^(|blog|case-studies|contact|contact-us|get-a-callback|products|[\w-]*policy|terms[\w-]*|disclaimer|sitemap)$/;
const site = [];
$input.all().forEach((item, i) => {
  const fromPosts = /post-sitemap/i.test(files[i] || '');
  const xml = String(item.json.data || '');
  for (const m of xml.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
    const loc = (m[1].match(/<loc>\s*([^<\s]+)\s*<\/loc>/) || [])[1];
    const lastmod = (m[1].match(/<lastmod>\s*([^<\s]+)\s*<\/lastmod>/) || [])[1] || '';
    if (!loc || !loc.startsWith(BASE)) continue;
    const slug = loc.replace(BASE, '').replace(/^\/+|\/+$/g, '');
    const kind = fromPosts ? 'post' : /^case-studies\/./.test(slug) ? 'case_study' : SKIP_PAGES.test(slug) ? 'other' : 'service';
    site.push({ url: loc, lastmod, kind });
  }
});

const slugOf = u => u.replace(BASE, '').replace(/^\/+|\/+$/g, '');
const titleOf = u => { const s = slugOf(u).split('/').pop().replace(/-/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1); };

// Topic words, widened with the project's own synonym groups (Project node: topic_synonyms) so a
// keyword such as "battery storage" also finds pages about inverters. Core words score 2, looser ones 1.
const SYN = ($('Project').first().json.topic_synonyms || []).map(([trigger, core, loose]) => [new RegExp(`\\b(${trigger})\\b`), core || [], loose || []]);
const STOP = new Set('a an and are for from how in of on the to what with your choose choosing right best guide'.split(' '));
// Words found in a large share of the site's page addresses (its city, its trade) say nothing
// about this topic, so they are ignored whatever the industry
const slugWords = site.map(p => new Set(slugOf(p.url).toLowerCase().match(/[a-z0-9]+/g) || []));
const df = new Map();
slugWords.forEach(s => s.forEach(w => df.set(w, (df.get(w) || 0) + 1)));
const common = w => site.length >= 10 && (df.get(w) || 0) / site.length > 0.2;
const topicText = `${start.keyword} ${start.title_idea} ${start.notes || ''}`.toLowerCase();
const weight = new Map((topicText.match(/[a-z0-9]+/g) || []).filter(w => w.length > 1 && !STOP.has(w) && !common(w)).map(w => [w, 2]));
for (const [re, core, loose] of SYN) {
  if (!re.test(topicText)) continue;
  core.forEach(w => weight.set(w, 2));
  loose.forEach(w => { if (!weight.has(w)) weight.set(w, 1); });
}
const score = u => (slugOf(u).toLowerCase().match(/[a-z0-9]+/g) || []).reduce((n, w) => n + (weight.get(w) || 0), 0);

const caseStudies = site.filter(p => p.kind === 'case_study');
const services = site.filter(p => p.kind === 'service');
const byScore = list => list.map(p => ({ ...p, score: score(p.url) })).sort((a, b) => b.score - a.score || b.lastmod.localeCompare(a.lastmod));

// When the SEO turned case studies off, the evidence comes from service pages only
const useCases = $('Post Settings').first().json.use_case_studies !== false;
let pickedCases = useCases ? byScore(caseStudies).filter(p => p.score > 0).slice(0, 3) : [];
if (useCases && !pickedCases.length) pickedCases = [...caseStudies].sort((a, b) => b.lastmod.localeCompare(a.lastmod)).slice(0, 3);
const pickedServices = byScore(services).filter(p => p.score > 0).slice(0, useCases ? 2 : 3);

const site_pages = site.filter(p => p.kind !== 'other').map(p => ({ url: p.url, kind: p.kind, title: titleOf(p.url), score: score(p.url) }));
const picked = [...pickedCases.map(p => ({ ...p, kind: 'case_study' })), ...pickedServices.map(p => ({ ...p, kind: 'service' }))];
if (!picked.length) return [{ json: { url: '', kind: 'none', title: '', site_pages } }];
return picked.map((p, i) => ({ json: { url: p.url, kind: p.kind, title: titleOf(p.url), id: `E${i + 1}`, site_pages } }));"""

OWN_EVIDENCE = r"""// Turn the fetched pages from our own site into a tagged evidence pack (E1-E5) of first-hand detail
const MAX_WORDS = { case_study: 700, service: 400 };
const picked = $('Pick Own Pages').all().map(i => i.json);
const pages = $input.all();
const decode = s => s.replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
  .replace(/&quot;/gi, '"').replace(/&#0*39;|&#x27;|&rsquo;|&lsquo;|&apos;/gi, "'").replace(/&ldquo;|&rdquo;/gi, '"')
  .replace(/&ndash;/gi, '-').replace(/&mdash;/gi, ', ').replace(/&pound;/gi, '£').replace(/&euro;/gi, '€').replace(/&hellip;/gi, '...')
  .replace(/&#(\d+);/g, (m, d) => String.fromCharCode(Number(d)));
const toText = h => decode(String(h).replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|h[1-6]|li|tr|div|section)>/gi, '\n').replace(/<[^>]+>/g, ' '))
  .replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();

const sources = [];
pages.forEach((item, i) => {
  const meta = picked[i] || {};
  let html = item.json?.data;
  if (!meta.url || typeof html !== 'string' || html.length < 500) return;
  html = html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<(script|style|noscript|svg|iframe|template|nav|header|footer|aside|form)\b[\s\S]*?<\/\1>/gi, ' ');
  const main = (html.match(/<article\b[\s\S]*<\/article>/i) || html.match(/<main\b[\s\S]*<\/main>/i) || [html])[0];
  const title = toText(html.match(/<h1\b[^>]*>([\s\S]*?)<\/h1>/i)?.[1] || meta.title);
  const text = toText(main).split(/\s+/).slice(0, MAX_WORDS[meta.kind] || 400).join(' ');
  sources.push({ id: `E${sources.length + 1}`, url: meta.url, kind: meta.kind, title, text });
});

const evidence_text = sources.length
  ? sources.map(s => `[${s.id}] ${s.kind === 'case_study' ? 'CASE STUDY' : 'SERVICE PAGE'}: ${s.title} (${s.url})\n${s.text}`).join('\n\n---\n\n')
  : 'No pages from our own site could be read this time. Use the knowledge base only.';

return [{ json: { evidence_text, sources, site_pages: picked[0]?.site_pages || [] } }];"""

VERIFY_GAIN = r"""// Step 2: keep only delta items whose evidence quote really exists in one of our own pages or the
// knowledge base, and which are not just a restatement of commodity content
const analysis = $input.first().json.output || {};
const evidence = $('Own Evidence').first().json;
const commodity = $('Score Commodity').first().json.commodity || [];
const kb = String($('Knowledge Base').first().json.kb || '');

const squash = s => String(s || '').toLowerCase().replace(/[^\p{L}\p{N}\p{Sc}%]+/gu, ' ').trim();
const STOP = new Set('a an and are as at be by for from has have in is it its of on or that the this to was we were with our you your'.split(' '));
const sig = s => [...new Set(squash(s).split(' ').filter(w => w.length > 2 && !STOP.has(w)))];
const corpus = { KB: squash(kb) };
for (const s of evidence.sources || []) corpus[s.id] = squash(`${s.title} ${s.text}`);
const everything = Object.values(corpus).join(' ');

const quoteFound = (id, quote) => {
  const q = squash(quote);
  if (q.split(' ').length < 4) return false;
  const hay = corpus[String(id || '').toUpperCase()] || everything;
  if (hay.includes(q)) return true;
  const words = q.split(' ');
  return words.filter(w => hay.includes(w)).length / words.length >= 0.9 && hay.includes(words.slice(0, 4).join(' '));
};
const commodityOverlap = finding => {
  const f = sig(finding);
  return commodity.some(c => { const cw = sig(c.claim); const shared = f.filter(w => cw.includes(w)).length; return shared / Math.max(1, Math.min(f.length, cw.length)) >= 0.7; });
};

const useCases = $('Post Settings').first().json.use_case_studies !== false;
const kept = [];
const dropped = [];
for (const d of analysis.delta_items || []) {
  if (!d || !d.finding) continue;
  if (!useCases && d.type === 'case_study_data') { dropped.push(`Case study (case studies are off for this post): ${d.finding}`); continue; }
  if (!quoteFound(d.evidence_id, d.evidence_quote)) { dropped.push(`Unverified (quote not found in ${d.evidence_id}): ${d.finding}`); continue; }
  if (commodityOverlap(d.finding)) { dropped.push(`Commodity, not new: ${d.finding}`); continue; }
  kept.push({ ...d, id: `D${kept.length + 1}`, source_url: (evidence.sources || []).find(s => s.id === String(d.evidence_id).toUpperCase())?.url || 'knowledge base' });
}

const gain_notes = [];
const types = new Set(kept.map(d => d.type));
if (kept.length < 3) gain_notes.push(`CHECK: Low information gain. Only ${kept.length} verified first-hand points were found; consider adding ${useCases ? 'a case study or ' : ''}insider detail for this topic.`);
if (useCases && !types.has('case_study_data')) gain_notes.push('CHECK: No verified case-study data was available for this topic.');
if (!types.has('contrarian') && !types.has('first_hand_process')) gain_notes.push('CHECK: No verified contrarian or first-hand process point was available.');
dropped.forEach(x => gain_notes.push('Left out before writing (not in the post): ' + x));

const information_gain = kept.map(d => `${d.id} (${d.type}): ${d.finding} Evidence ${d.evidence_id}: "${String(d.evidence_quote).trim()}"`);
const scene = useCases ? kept.find(d => d.type === 'case_study_data') : null;
return [{
  json: {
    output: { ...analysis, information_gain },
    delta_items: kept,
    gain_notes,
    opening_detail: scene ? `${scene.finding} (from ${scene.source_url}: "${String(scene.evidence_quote).trim()}")` : '',
  },
}];"""

# GAIN_SCORE is used twice: after QA Check and after Final QA. build.py fills in QA_NODE.
GAIN_SCORE = r"""// Measure information gain: share of body words in paragraphs the auditor labelled as new
// (delta, or half of mixed), then turn shortfalls into issues for the editor
const QA_NODE = '__QA_NODE__';
const qa = $(QA_NODE).first().json;
const audit = $input.first().json.output || {};
const deltaItems = $('Verify Gain').first().json.delta_items || [];
const paragraphs = qa.paragraphs || [];

const labels = new Map((audit.paragraphs || []).map(p => [Number(p.n), p]));
let total = 0, gainWords = 0, running = 0, earlyGain = false, fillerWords = 0, offWords = 0;
const used = new Set((audit.delta_used || []).map(String));
const filler = [], offTopic = [];
paragraphs.forEach((p, i) => {
  const words = (p.match(/\S+/g) || []).length;
  const l = labels.get(i + 1) || {};
  const label = String(l.label || '').toLowerCase();
  (l.delta_ids || []).forEach(id => used.add(String(id)));
  total += words;
  if (label === 'delta') gainWords += words;
  if (label === 'mixed') gainWords += words / 2;
  if (running < 200 && (label === 'delta' || label === 'mixed')) earlyGain = true;
  if (label === 'filler') { filler.push(p.split(/\s+/).slice(0, 8).join(' ') + '...'); fillerWords += words; }
  // Paragraphs that retell one of our jobs without helping the reader answer the title
  if (l.serves_title === false) { offTopic.push(p.split(/\s+/).slice(0, 8).join(' ') + '...'); offWords += words; }
  running += words;
});
const gain_pct = total ? Math.round((gainWords / total) * 100) : 0;
const focus_pct = total ? 100 - Math.round((offWords / total) * 100) : 100;
const unused = deltaItems.filter(d => !used.has(d.id));

const issues = [...(qa.issues || [])];
const brand = $('Project').first().json.brand;
// Without case studies there is less first-hand material to draw on, so the floor is lower
const useCases = $('Post Settings').first().json.use_case_studies !== false;
const floor = useCases ? 15 : 10;
if (gain_pct < floor) issues.push(`Information gain is about ${gain_pct}% of the body (target 20-35%). Weave in these unused first-hand points as concrete detail that supports each section's answer: ${unused.map(d => `${d.id}: ${d.finding} (evidence: "${d.evidence_quote}")`).join(' | ') || `add more specific first-hand ${brand} detail from the evidence${useCases ? '' : ` (how ${brand} works, never case studies or client names)`}`}.`);
if (!earlyGain && paragraphs.length) issues.push(`The first 200 words carry no unique information. Open with the direct answer to the title and state the key finding (a specific fact, figure or first-hand detail) within the first 150 words; cut any scene-setting before it.`);
// Balance: the post must answer the title, with case studies as proof rather than the subject
if (offTopic.length && offWords / Math.max(1, total) > 0.12) issues.push(`About ${100 - focus_pct}% of the body does not help the reader answer the title (retold jobs, sales lines or general statements). Rewrite these paragraphs so each gives practical guidance on its section's question, cutting each case study to a short supporting example of two to four sentences (keep its real figures, links and quotes): "${offTopic.slice(0, 5).join('", "')}"`);
const unanswered = (audit.unanswered_questions || []).filter(Boolean).slice(0, 4);
if (unanswered.length) issues.push(`The post does not clearly answer these reader questions about the title: ${unanswered.join('; ')}. Add a direct, practical answer to each in the most relevant body section (general guidance first, ${brand} detail only as proof).`);
// Reflective story beats are part of the voice, so only flag filler when it is a real share of the body
if (filler.length && fillerWords / Math.max(1, total) > 0.15) issues.push(`About ${Math.round((fillerWords / total) * 100)}% of the body adds no information. Tighten these paragraphs so each says something specific, keeping the voice: "${filler.slice(0, 4).join('", "')}"`);
const missing = (audit.missing_consensus || []).filter(Boolean).slice(0, 4);
if (missing.length) issues.push(`Searchers also expect these topics: ${missing.join('; ')}. Cover each in a sentence or two as general market context (what readers should check or expect). These come from competitor pages, so never present them as ${brand} claims or services unless the knowledge base says so.`);

return [{ json: { ...qa, issues, has_issues: issues.length > 0, gain_pct, focus_pct, unanswered_questions: unanswered, delta_used: [...used].filter(id => deltaItems.some(d => d.id === id)), unused_delta: unused.map(d => d.id) } }];"""
