PICK_COMPETITORS = r"""// Turn the OpenRouter web search reply into the top competitor pages to study
const MAX_PAGES = 5;
const SKIP = /(^|\.)(youtube\.com|reddit\.com|quora\.com|facebook\.com|instagram\.com|linkedin\.com|tiktok\.com|twitter\.com|x\.com|pinterest\.[a-z.]+|yelp\.[a-z.]+|trustpilot\.com|checkatrade\.com|amazon\.[a-z.]+|ebay\.[a-z.]+|google\.[a-z.]+)$/;

const reply = $input.first().json;
const content = String(reply.choices?.[0]?.message?.content || '');
let parsed = {};
try {
  parsed = JSON.parse(content.replace(/^\s*```(?:json)?\s*/i, '').replace(/\s*```\s*$/, ''));
} catch {
  const m = content.match(/\{[\s\S]*\}/);
  if (m) { try { parsed = JSON.parse(m[0]); } catch {} }
}

const cleanUrl = u => String(u || '').trim().replace(/[)\],.;'"]+$/, '');
const isUrl = u => /^https?:\/\/[^\s/]+\.[^\s]+$/i.test(cleanUrl(u));
const list = Array.isArray(parsed.organic) ? parsed.organic : Array.isArray(parsed.results) ? parsed.results : [];
const organic = list
  .map(r => (typeof r === 'string' ? { url: r } : r || {}))
  .map(r => ({ ...r, url: cleanUrl(r.url || r.link || r.href) }))
  .filter(r => isUrl(r.url))
  .map((r, i) => ({ pos: i + 1, url: r.url, title: r.title || '', desc: r.desc || r.description || r.snippet || '' }));

// Fall back to the search citations, then to any URLs written in the reply text
const citations = [
  ...(Array.isArray(reply.citations) ? reply.citations : []),
  ...(reply.choices?.[0]?.message?.annotations || []).map(a => a?.url_citation?.url),
  ...(content.match(/https?:\/\/[^\s"'<>)\]]+/g) || []),
].map(cleanUrl).filter(isUrl);
for (const url of citations) {
  if (organic.length >= 10) break;
  if (!organic.some(r => r.url === url)) organic.push({ pos: organic.length + 1, url, title: '', desc: '' });
}
if (!organic.length) throw new Error('The web search returned no result URLs for this keyword.');

// n8n's Code sandbox has no URL class, so read the hostname with a regex
const domainOf = u => (String(u || '').trim().match(/^https?:\/\/(?:[^@\/?#]*@)?([^\/?#:]+)/i)?.[1] || '').replace(/^www\./i, '').toLowerCase();
const strings = v => (Array.isArray(v) ? v : []).map(q => (typeof q === 'string' ? q : q?.question || q?.query || '')).map(s => s.trim()).filter(Boolean);
const paa = strings(parsed.people_also_ask);
const related = strings(parsed.related_searches);

const competitor_domains = [...new Set(organic.map(r => domainOf(r.url)).filter(Boolean))];
const serp_overview = organic.slice(0, 10)
  .map(r => `${r.pos}. ${r.title || ''} (${domainOf(r.url)})${r.desc ? ' - ' + r.desc : ''}`)
  .join('\n');

// Prefer real articles; if the search only found social / forum pages, use those rather than
// stopping. Pages from any of your own projects are never studied as competitors; if nothing
// else came back, carry on without competitor pages.
const OWN = $('Project').first().json.all_domains || [];
const notOwn = organic.filter(r => !OWN.some(d => domainOf(r.url) === d || domainOf(r.url).endsWith('.' + d)));
let picked = notOwn.filter(r => !SKIP.test(domainOf(r.url))).slice(0, MAX_PAGES);
if (!picked.length) picked = notOwn.slice(0, MAX_PAGES);
if (!picked.length) picked = [{ url: '', title: '', pos: 0 }];

return picked.map(r => ({
  json: {
    url: r.url,
    title: r.title || '',
    position: r.pos,
    domain: domainOf(r.url),
    paa: [...new Set(paa)].slice(0, 10),
    related: [...new Set(related)].slice(0, 10),
    competitor_domains,
    serp_overview,
  },
}));"""

COMPETITOR_DIGEST = r"""// Clean each scraped competitor page down to its outline and main text (pages labelled P1-P5)
const MAX_WORDS_PER_PAGE = 2000;
const picked = $('Pick Competitors').all().map(i => i.json);
const pages = $input.all();

const decode = s => s
  .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
  .replace(/&quot;/gi, '"').replace(/&#0*39;|&#x27;|&rsquo;|&lsquo;|&apos;/gi, "'")
  .replace(/&ldquo;|&rdquo;/gi, '"').replace(/&ndash;|&mdash;/gi, '-').replace(/&hellip;/gi, '...')
  .replace(/&#(\d+);/g, (m, d) => String.fromCharCode(Number(d)))
  .replace(/&#x([0-9a-f]+);/gi, (m, h) => String.fromCharCode(parseInt(h, 16)));
const toText = h => decode(String(h)
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|h[1-6]|li|tr|div|section|td|th)>/gi, '\n')
    .replace(/<[^>]+>/g, ' '))
  .replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
const words = t => (t.match(/\S+/g) || []).length;
const stripChrome = h => h.replace(/<(nav|header|footer|aside|form)\b[\s\S]*?<\/\1>/gi, ' ');

const results = [];
pages.forEach((item, i) => {
  const meta = picked[i] || {};
  let html = item.json?.data;
  if (typeof html !== 'string' || html.length < 500) return; // fetch failed or the site blocked it
  html = html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<(script|style|noscript|svg|iframe|template)\b[\s\S]*?<\/\1>/gi, ' ');

  const title = toText(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] || meta.title || '');
  const metaDesc = decode(html.match(/<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)/i)?.[1] || '');

  // Prefer the article / main element; fall back to the whole page if that is too thin
  let body = stripChrome((html.match(/<article\b[\s\S]*<\/article>/i) || html.match(/<main\b[\s\S]*<\/main>/i) || [html])[0]);
  if (words(toText(body)) < 300) body = stripChrome(html);

  const headings = [...body.matchAll(/<h([1-3])\b[^>]*>([\s\S]*?)<\/h\1>/gi)]
    .map(m => ({ level: Number(m[1]), text: toText(m[2]) }))
    .filter(h => h.text)
    .slice(0, 40)
    .map(h => `${'  '.repeat(h.level - 1)}H${h.level}: ${h.text}`);
  const text = toText(body);

  // Real questions the page answers: question headings and FAQ / accordion toggles
  const questions = [...body.matchAll(/<(h[2-4]|summary|dt|button)\b[^>]*>([\s\S]*?)<\/\1>/gi)]
    .map(m => toText(m[2]).replace(/\s+/g, ' ').trim())
    .filter(q => q.endsWith('?') && q.length >= 12 && q.length <= 150);

  results.push({
    position: meta.position,
    url: meta.url,
    domain: meta.domain,
    title,
    metaDesc,
    total_words: words(text),
    headings,
    questions,
    excerpt: text.split(/\s+/).slice(0, MAX_WORDS_PER_PAGE).join(' '),
  });
});

const first = picked[0] || {};
const seenQ = new Set();
const questions = results.flatMap(r => r.questions).filter(q => {
  const key = q.toLowerCase().replace(/[^a-z0-9 ]/g, '');
  if (seenQ.has(key)) return false;
  seenQ.add(key);
  return true;
}).slice(0, 25);
results.forEach((r, i) => { r.label = `P${i + 1}`; });
const header = r => `### [${r.label}] ${r.title} (${r.domain}) - about ${r.total_words} words\nURL: ${r.url}`;
// If every site blocked the fetch, carry on with just the search results list
const NONE = 'No competitor pages could be read (the sites blocked automated access). Rely on the search results list above.';
const outlines = results.map(r => `${header(r)}\n${r.headings.join('\n') || '(no headings found)'}`).join('\n\n') || NONE;
const competitor_digest = results.length ? results.map(r => [
  header(r),
  r.metaDesc ? `Meta description: ${r.metaDesc}` : '',
  'Outline:',
  r.headings.join('\n') || '(no headings found)',
  'Main text (excerpt):',
  r.excerpt,
].filter(Boolean).join('\n')).join('\n\n---\n\n') : NONE;

const counts = results.map(r => r.total_words).filter(n => n > 200).sort((a, b) => a - b);

return [{
  json: {
    competitor_digest,
    outlines,
    page_texts: results.map(r => ({ label: r.label, url: r.url, text: `${r.headings.join('\n')}\n${r.excerpt}` })),
    pages_analysed: results.length,
    median_competitor_words: counts.length ? counts[Math.floor(counts.length / 2)] : 0,
    paa: first.paa || [],
    questions,
    related: first.related || [],
    competitor_domains: first.competitor_domains || [],
    serp_overview: first.serp_overview || '',
  },
}];"""

BRIEF = r"""// Gather everything the outline planner and the writer need in one place
const start = $('Start').first().json;
const analysis = $input.first().json.output || {};
const digest = $('Competitor Digest').first().json;

let map;
try { map = JSON.parse($('Link Map Text').first().json.link_map_text); }
catch (e) { throw new Error(`The ${$('Project').first().json.brand} link map file in Drive is not valid JSON: ` + e.message); }

// The live sitemap keeps links current: every case study, plus the service pages and blog
// posts that match this topic, become linkable without editing the link map file
const evidence = $('Own Evidence').first().json;
const sitePages = evidence.site_pages || [];
const trim = u => String(u).replace(/\/+$/, '');
const have = new Set(['service_pages', 'case_studies', 'blog_posts', 'conversion'].flatMap(g => (map[g] || []).map(p => trim(p.url))));
const addTo = (group, pages) => pages.forEach(p => {
  if (have.has(trim(p.url))) return;
  have.add(trim(p.url));
  map[group] = map[group] || [];
  map[group].push({ topic: p.title, url: p.url, anchor: p.title.toLowerCase() });
});
const relevant = (kind, n) => sitePages.filter(p => p.kind === kind && p.score > 0).sort((a, b) => b.score - a.score).slice(0, n);
addTo('case_studies', sitePages.filter(p => p.kind === 'case_study'));
addTo('service_pages', relevant('service', 8));
addTo('blog_posts', relevant('post', 12));
map.site_urls = sitePages.map(p => p.url);

// Case studies switched off: no case-study links, and the distinctive words of every
// case-study name (client, venue) are kept so QA can spot one creeping into the post
const settings = $('Post Settings').first().json;
const GENERIC = new Set([...'case studies study project projects client clients customer customers service services install installation installed hire rental company team staff world global international national annual the and for with from about after before their'.split(' '),
  ...$('Project').first().json.brand.toLowerCase().split(/\s+/)]);
const caseNames = [...(map.case_studies || []).map(p => `${p.topic || ''} ${p.url}`), ...sitePages.filter(p => p.kind === 'case_study').map(p => p.url)];
const wordsOf = t => String(t).replace(/^https?:\/\/[^/]+\/(case-studies\/)?/, '').toLowerCase().match(/[a-z]+/g) || [];
// Words that are not names: ones in the site's service-page addresses (its city, its trade) and
// ones shared by three or more case-study names (conference, summit...)
const serviceWords = new Set(sitePages.filter(p => p.kind === 'service').flatMap(p => wordsOf(p.url)));
const caseCount = new Map();
[...new Set(sitePages.filter(p => p.kind === 'case_study').map(p => p.url))].forEach(u => new Set(wordsOf(u)).forEach(w => caseCount.set(w, (caseCount.get(w) || 0) + 1)));
const case_study_tokens = [...new Set(caseNames.flatMap(wordsOf)
  .filter(w => w.length >= 5 && !GENERIC.has(w) && !serviceWords.has(w) && (caseCount.get(w) || 0) < 3 && !/^(https|www)$/.test(w)))];
if (!settings.use_case_studies) {
  map.case_studies = [];
  map.site_urls = map.site_urls.filter(u => !/\/case-studies\//.test(u));
}

// Form value wins; otherwise a little above the competitors (and above the reference page the
// SEO wants to outrank), within 1,500-3,000
const recommended = Number(analysis.recommended_word_count) || 1800;
const ref = $('Reference Page').first().json;
const beatRef = ref.has_reference ? Math.round((Number(ref.reference_words) || 0) * 1.1) : 0;
const target_word_count = start.word_count > 0
  ? Math.min(5000, Math.max(800, start.word_count))
  : Math.min(3000, Math.max(1500, recommended, beatRef));

const line = p => `- ${p.topic}: ${p.url} (anchor idea: "${p.anchor}")`;
const link_menu = [
  `HOMEPAGE (main money page, link it once): ${map.homepage.url} (anchor ideas: ${map.homepage.anchors.map(a => `"${a}"`).join(', ')})`,
  'SERVICE PAGES:', ...map.service_pages.map(line),
  'CASE STUDIES:', ...map.case_studies.map(line),
  'BLOG POSTS AND GUIDES:', ...map.blog_posts.map(line),
  'CONVERSION PAGES (closing CTA):', ...map.conversion.map(line),
].join('\n');

const list = v => (Array.isArray(v) ? v.map(x => String(typeof x === 'string' ? x : x?.keyword || x?.question || '').trim()).filter(Boolean) : []);
const primaryLc = start.keyword.toLowerCase();
const supporting = [...new Set(list(analysis.supporting_keywords))]
  .filter(k => k.toLowerCase() !== primaryLc)
  .slice(0, 8);

// Questions: the analyst's picks first, then search PAA and the competitors' own questions
const seen = new Set();
const paa_questions = [...list(analysis.paa_to_answer), ...list(digest.paa), ...list(digest.questions)]
  .filter(q => { const k = q.toLowerCase().replace(/[^a-z0-9 ]/g, ''); if (seen.has(k)) return false; seen.add(k); return true; })
  .slice(0, 8);

// The writer gets knowledge base sections 1-6 (facts, proof, claim rules, voice, spelling);
// headings, anatomy, links and metadata are covered by the prompt itself
const kb = String($('Knowledge Base').first().json.kb || '');
const parts = kb.split(/^(?=## \d+\.)/m);
const kept = parts.filter(p => { const n = Number((p.match(/^## (\d+)\./) || [])[1]); return n >= 1 && n <= 6; });
const writer_kb = (kept.length ? kept.join('\n') : kb).trim();

return [{
  json: {
    // The H1 follows the site's house style
    final_title: (t => $('Project').first().json.heading_case === 'sentence' ? t : titleCase(t))(String(analysis.final_title || start.title_idea).trim()),
    primary_keyword: start.keyword,
    supporting_keywords: supporting,
    keywords_csv: supporting.join(', '),
    search_intent: analysis.search_intent || '',
    content_format: analysis.content_format || '',
    consensus_points: list(analysis.consensus_points),
    information_gain: list(analysis.information_gain),
    paa_questions,
    angle: analysis.angle || '',
    opening_scene: analysis.opening_scene || '',
    title_questions: list(analysis.title_questions).slice(0, 12),
    opening_detail: $('Verify Gain').first().json.opening_detail || '',
    evidence_text: evidence.evidence_text || '',
    target_word_count,
    link_menu,
    link_map: map,
    writer_kb,
    competitor_domains: digest.competitor_domains || [],
    case_study_tokens,
  },
}];"""

PROJECT = r"""// =====================================================================================
//  YOUR PROJECTS: edit this list. Up to 5 websites (projects) can share this workflow.
// =====================================================================================
// For each project you use:
//   1. Fill in its settings below and set enabled: true.
//   2. Upload its knowledge base (.md) and link map (.json) to Google Drive as plain files
//      (templates are in the repo's projects/ folder) and paste their file IDs below.
//   3. Make sure the form's "Project" dropdown has an option written exactly like `name`.
// Anything you leave out falls back to DEFAULTS further down.
const PROJECTS = [
  {
    enabled: true,
    name: 'Northwind Solar',                      // brand name, used in posts and the form
    domain: 'northwind-solar.example',            // no https://, no www.
    base_url: 'https://www.northwind-solar.example',
    sitemap_url: '',                              // blank = base_url + '/sitemap_index.xml'
    description: 'a solar panel and battery installation company for homes and small businesses in Bristol',
    search_context: 'a solar panel installer in Bristol',   // tells the web search which meaning of the keyword fits
    home_anchor: 'solar panel installation in Bristol',     // link text for the homepage link
    author: { name: 'Alex Morgan', jobTitle: 'Head of Installations' },   // or null for the brand
    categories: ['Solar guides', 'Costs and savings', 'Installation tips'],
    case_studies: true,                           // does the site publish case studies?
    heading_case: 'sentence',                     // 'sentence', 'title' (all headings) or 'title_h1'
    prices_on_request: true,                      // true = posts never state your own prices
    quote_details: 'the property type, roof size and direction, yearly electricity use and postcode',
    market: { country: 'United Kingdom', search_label: 'Google UK', google_domain: 'google.co.uk',
              language: 'UK English', spelling: 'british', currency: 'GBP', currency_symbol: '£' },
    acronyms: ['PV', 'MCS', 'EPC', 'kWh'],        // always written exactly like this
    terminology: [['solar cells', 'solar panels'], ['inverter box', 'inverter']],   // [avoid, use]: fixed automatically
    word_preferences: 'Use "install" rather than "fit" and "battery storage" rather than "power bank".',
    // Optional: when a keyword matches a trigger, these words also find relevant pages on your own site
    topic_synonyms: [['batter\\w*|storage', ['battery', 'batteries', 'storage'], ['inverter']]],
    claim_rules: [                                // [regex, flags, message]: flagged for the editor
      ['\\bguarantee[sd]?\\b[^.\\n]{0,40}\\bsavings?\\b', 'gi', 'Never guarantee savings. Give the factors that decide them.'],
    ],
    sources_hint: 'government and regulator sites, standards bodies and equipment manufacturers',
    kb_file_id: 'PASTE_DRIVE_FILE_ID',
    link_map_file_id: 'PASTE_DRIVE_FILE_ID',
  },
  { enabled: false, name: 'Project 2' },
  { enabled: false, name: 'Project 3' },
  { enabled: false, name: 'Project 4' },
  { enabled: false, name: 'Project 5' },
];

// Settings every project starts from
const DEFAULTS = {
  sitemap_url: '', description: 'a business', search_context: '', home_anchor: '', author: null, categories: ['Guides'],
  case_studies: false, heading_case: 'sentence', prices_on_request: true,
  quote_details: 'the details a supplier needs to give an accurate quote',
  market: { country: 'United Kingdom', search_label: 'Google UK', google_domain: 'google.co.uk',
            language: 'UK English', spelling: 'british', currency: 'GBP', currency_symbol: '£' },
  acronyms: [], terminology: [], word_preferences: '', claim_rules: [], topic_synonyms: [],
  sources_hint: 'government and regulator sites, standards bodies and manufacturers',
};

// ----- nothing below needs editing -----
const choice = String($('Blog Request Form').first().json['Project'] || '').trim().toLowerCase();
const active = PROJECTS.filter(p => p.enabled);
if (!active.length) throw new Error('No project is enabled yet: open the Project node, fill in a project and set enabled: true.');
const picked = active.find(p => p.name.toLowerCase() === choice)
  || PROJECTS.find((p, i) => choice === `project ${i + 1}` && p.enabled)
  || (active.length === 1 ? active[0] : null);
if (!picked) throw new Error(`The form chose "${choice}", but no enabled project in the Project node has that name.`);
const p = { ...DEFAULTS, ...picked, market: { ...DEFAULTS.market, ...(picked.market || {}) } };
const unset = v => !v || /^PASTE/i.test(String(v));
if (unset(p.kb_file_id) || unset(p.link_map_file_id)) {
  throw new Error(`${p.name} is not set up yet: paste the Drive file IDs of its knowledge base and link map into the Project node.`);
}
const base = String(p.base_url || `https://www.${p.domain}`).replace(/\/+$/, '');
const m = p.market;
// Brand spelled wrongly (any other capitalisation of the same words)
const brandRe = p.name.split(' ').map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+');
// A brand that is also an ordinary search phrase ("Solar Panel Repairs") is not spell-checked
const brandIsPhrase = /\b(hire|rental|services?|repairs?|installers?)\b/i.test(p.name);
const acronymText = p.acronyms.length ? p.acronyms.join(', ') : 'acronyms';
const CASE = {
  sentence: `sentence case (capitalise only the first word, proper nouns and acronyms such as ${acronymText})`,
  title: `Title Case (capitalise every main word; short joining words such as a, and, for, in, of, the, to stay lower case unless they start the heading; acronyms such as ${acronymText} as written)`,
};
const h1Title = p.heading_case !== 'sentence';
const subTitle = p.heading_case === 'title';
return [{
  json: {
    key: p.name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    brand: p.name, domain: p.domain, base, home: base + '/', sitemap: p.sitemap_url || base + '/sitemap_index.xml',
    context: p.description, search_context: p.search_context || p.description, home_anchor: p.home_anchor || p.name,
    author: p.author, categories: p.categories, has_case_studies: p.case_studies, heading_case: p.heading_case,
    brand_check: !brandIsPhrase, brand_re: brandRe, rules: p.claim_rules,
    kb_file_id: p.kb_file_id, link_map_file_id: p.link_map_file_id,
    market: m, acronyms: p.acronyms, terminology: p.terminology, topic_synonyms: p.topic_synonyms || [],
    all_domains: PROJECTS.filter(x => x.domain).map(x => x.domain),
    // Ready-made wording the prompts drop in
    acronym_text: p.acronyms.length ? `${p.acronyms.join(' / ')} written exactly like that` : 'acronyms in capitals',
    language_rule: `${m.language}, ${m.currency} for all money`,
    terms_text: p.terminology.length ? p.terminology.map(([a, b]) => `"${b}", never "${a}"`).join('; ') : 'none',
    word_preferences: p.word_preferences || `Use the words people in ${m.country} actually search with.`,
    pricing_rule: p.prices_on_request
      ? `${p.name} never publishes prices; costs only come in a personal quote. Never state, imply or estimate what ${p.name} charges. Only if a cost is genuinely essential, give a broad general ${m.country} market range in ${m.currency}, clearly framed as the wider market, never tied to ${p.name}, followed by the point that the real cost depends on the brief and comes from a quote. No ${m.currency_symbol} figures in the TL;DR or headings.`
      : `Prices may be mentioned only as they appear in the knowledge base, in ${m.currency}. Never invent or estimate a price. No ${m.currency_symbol} figures in the TL;DR or headings.`,
    prices_on_request: p.prices_on_request,
    quote_details: p.quote_details, sources_hint: p.sources_hint,
    h1_case: CASE[h1Title ? 'title' : 'sentence'], h1_word: h1Title ? 'Title Case' : 'sentence case',
    sub_case: CASE[subTitle ? 'title' : 'sentence'], heading_word: subTitle ? 'Title Case' : 'sentence case',
  },
}];"""

# Title Case for headings, shared by Brief (the H1) and QA (every heading the site puts in Title Case)
TITLE_CASE = r"""// Title Case: main words capitalised; short joining words lower case unless they open the
// heading or follow a colon, question mark or number; acronyms and words like ExCeL or 4K kept
const SMALL = new Set('a an and as at but by for from in into nor of on or per the to vs via with'.split(' '));
const titleCase = h => String(h).split(/(\s+)/).map((w, i, all) => {
  if (!/[a-z]/i.test(w)) return w;
  const prev = all.slice(0, i).join('').trim();
  const opens = !prev || /[:?!.]$/.test(prev);
  return w.split('-').map((part, j) => {
    const core = part.replace(/^[^A-Za-z0-9]+/, '');
    if (/[A-Z]/.test(core.slice(1)) || /^\d/.test(core)) return part;
    if (SMALL.has(core.toLowerCase().replace(/[^a-z]/g, '')) && !(opens && j === 0)) return part.toLowerCase();
    return part.replace(/[A-Za-z]/, c => c.toUpperCase());
  }).join('-');
}).join('');
"""

POST_SETTINGS = r"""// One place for what the SEO asked for: the post format and whether the project's case studies are used.
// The form's dropdowns win; if they are left at the default, the typed requirements can still switch them.
const start = $('Start').first().json;
const form = $('Blog Request Form').first().json;
const notes = String(start.notes || '').toLowerCase();

const FORMATS = { 'standard guide': 'standard', 'listicle': 'listicle', 'how-to steps': 'how_to', 'comparison': 'comparison' };
let format = FORMATS[String(form['Post format'] || '').trim().toLowerCase()] || 'standard';
if (format === 'standard') {
  if (/\blisticle\b|\blist[- ](?:post|blog|article|format|style)\b|\b(?:top|best)\s+\d+\b|\b\d+\s+(?:ways|tips|ideas|reasons|things|questions|mistakes|signs|steps|checks)\b/.test(notes)) format = 'listicle';
  else if (/\bstep[- ]by[- ]step\b|\bhow[- ]to (?:format|post|guide|style)\b/.test(notes)) format = 'how_to';
  else if (/\bcomparison (?:post|blog|article|format|style)\b|\bcompare (?:the )?options\b/.test(notes)) format = 'comparison';
}
const site = $('Project').first().json;
const caseAnswer = String(form['Use case studies?'] ?? '').trim().toLowerCase();
const typedNoCases = /\b(?:no|without|avoid|skip|exclude|don'?t (?:use|include|mention|add)|do not (?:use|include|mention|add)|never (?:use|include|mention))\b[^.\n]{0,40}\bcase[- ]?stud/.test(notes);
// A site with no published case studies never uses them, whatever the form says
const use_case_studies = !site.has_case_studies || caseAnswer === 'no' ? false : !typedNoCases;

const HOME_LINK = 'Must carry the homepage link.';
const CTA_LINK = 'Must carry the contact-us or get-a-callback link.';
const TLDR = '1. section_type "tldr": section_name "TL;DR", section_word_count 50. A plain, direct answer to the H1 with the primary keyword. No links.';
const FAQ = n => `section_type "faq": section_name "FAQs", 200-400 words, ${n} questions from QUESTIONS SEARCHERS ASK that the body does not answer in full. List them in faq_questions.`;
const PROFILES = {
  standard: {
    label: 'Standard guide',
    heading_style: 'question', bold_opener: true, table: 'required', lists_allowed: true,
    spine: 'title_questions: 4-6 practical questions a reader who searched the title needs answered to act on it, in a logical order. These are the spine of the post: together they must fully answer the title (e.g. for "How many solar panels do I need?": how yearly electricity use sets the size; how roof area and direction limit it; when a battery changes the answer; when a smaller system is the better choice; how to brief an installer).',
    structure_text: [
      TLDR,
      `2. section_type "intro": section_name "Opening", 100-180 words. The first one or two sentences answer the H1 directly and use the primary keyword (never a scene, a "Picture..." moment or a definition); then one real supporting detail at most, and what the post covers. ${HOME_LINK}`,
      '3. section_type "body": 4-6 sections, 200-400 words each (a section over 300 words names one or two "### " sub-topics in its overview_idea). section_name is a short GEO/AEO search question in sentence case, at most 12 words, phrased the way people ask it, ending with "?", containing the primary keyword or one of its supporting keywords where that reads naturally. Examples: "What does solar panel installation in Bristol cost?" and "How does roof direction change the number of panels?". No story fragment, client or job name in the heading. Each body section answers one READER QUESTION (set "answers" to it): practical, general guidance any organiser can use comes first, and the D items are the proof and the insider detail that make that answer better than the competitors\'. A case study is a short example inside a section (two to four sentences), never the subject of a section, and no single case study may appear in more than two sections. One body section carries the contrarian D item if there is one. A D item that does not help answer a reader question can be left out. Commodity points get one or two sentences each. Exactly ONE body section has include_table true (a comparison where it genuinely helps the reader decide).',
      `4. section_type "closing": a short heading, 100-160 words: the clear next step (what to prepare, measure or send, and why) with a soft, unhurried invitation. ${CTA_LINK}`,
      `5. ${FAQ('4-6')}`,
    ].join('\n'),
    body_line: 'Directly under the heading: one bold, declarative sentence (max 30 words) that answers the reader question as practical advice. Then the guidance, with the first-hand detail below as proof (any case study as a short example of two to four sentences, not the subject).',
    writer_rules: [
      '2. Every body and closing section starts with "## " and its heading from the outline (a short question of at most 12 words; if the outline gives a longer one, shorten it and keep its keyword). Use "### " H3s for sub-topics inside a section, so no more than 300 words sit under one heading.',
      '3. INFORMATION BLOCKS: in every body section (not the closing or FAQs), the first line after the heading is ONE bold, declarative sentence of at most 30 words that directly answers the section\'s reader question, written as **sentence.** It is advice the reader can use, not a description of one of our jobs. The bold line plus the next sentence must answer the heading\'s search phrase; then the practical detail, with first-hand evidence as proof.',
      '4. Short bullet or numbered lists (3-7 items, at most three in the body) where they make information easier to scan, such as checklists or the details to send for a quote. The single section marked include_table gets one markdown comparison table.',
    ].join('\n'),
    editor_note: 'TL;DR, opening, body sections with short question headings each starting with a bold finding, one comparison table, a closing and FAQs.',
  },
  listicle: {
    label: 'Listicle',
    heading_style: 'numbered', bold_opener: false, table: 'optional', lists_allowed: true,
    spine: 'title_questions: the 5-12 items of the list, each a short phrase naming one tip, option, idea or check that answers the title, in a sensible order (most useful first, or a logical sequence). These are the spine of the post: one numbered section per item.',
    structure_text: [
      TLDR,
      `2. section_type "intro": section_name "Opening", 100-180 words. The first one or two sentences answer the H1 directly with the primary keyword (no scene or "Picture..." moment), then say plainly what the list covers and who it is for. ${HOME_LINK}`,
      '3. section_type "body": one section per LIST ITEM (5-12 sections), 120-250 words each, in the order of the list. section_name is the numbered item in sentence case: "1. " followed by the item, optionally a colon and a few words on why it matters (e.g. "1. Check your roof first: direction decides more than size"). At least one item heading contains the primary keyword or a supporting keyword naturally. Each item says what it is, why it matters and what to do about it; set "answers" to the list item it covers. The D items are the insider detail inside the items. A short bullet list inside an item is fine where it genuinely helps. include_table is optional: set it true on at most one item, only if a comparison genuinely helps.',
      `4. section_type "closing": a short heading and 80-150 words that pull the list together, with a soft, unhurried invitation. ${CTA_LINK}`,
      `5. ${FAQ('3-5')}`,
    ].join('\n'),
    body_line: 'Write this list item directly: what it is, why it matters and what to do, with any first-hand detail below as proof. A short bullet list is fine if it genuinely helps.',
    writer_rules: [
      '2. This post is a LISTICLE. Every body section starts with "## " and its numbered heading from the outline, exactly as given ("## 1. ...", "## 2. ..."), in order. The closing and FAQ headings are not numbered.',
      '3. Each list item opens with its point straight away (a bold first sentence is optional), then explains why it matters and what to do. Keep items tight and scannable: short paragraphs, no long scene-setting.',
      '4. Short bullet lists inside a list item are allowed where they genuinely help scanning. Use a markdown table only if the outline marks an item with include_table.',
    ].join('\n'),
    editor_note: 'a LISTICLE: TL;DR, short opening, numbered list items ("## 1. ...", "## 2. ..."), a short closing and FAQs. Lists inside items are allowed.',
  },
  how_to: {
    label: 'How-to steps',
    heading_style: 'steps', bold_opener: false, table: 'optional', lists_allowed: true,
    spine: 'title_questions: the 4-10 steps the reader follows, in order, each a short imperative phrase (e.g. "Measure the roof and note any shading"). These are the spine of the post: one step section per item.',
    structure_text: [
      TLDR,
      `2. section_type "intro": section_name "Opening", 100-180 words. The first one or two sentences answer the H1 directly with the primary keyword (no scene or "Picture..." moment), then what the reader will be able to do by the end and what they need before starting. ${HOME_LINK}`,
      '3. section_type "body": one section per STEP (4-10 sections), 150-300 words each, in order. section_name is "Step 1: " followed by the step in sentence case (e.g. "Step 1: Measure the roof and note any shading"). At least one step heading contains the primary keyword or a supporting keyword naturally. Each step says exactly what to do, why, and the common mistake to avoid; set "answers" to the step it covers. The D items are the insider detail inside the steps. A short checklist inside a step is fine. include_table is optional: at most one step, only if it genuinely helps.',
      `4. section_type "closing": a short heading and 80-150 words on what to do next, with a soft, unhurried invitation. ${CTA_LINK}`,
      `5. ${FAQ('3-5')}`,
    ].join('\n'),
    body_line: 'Write this step as instructions: what to do, why, and the mistake to avoid, with any first-hand detail below as proof. A short checklist is fine if it genuinely helps.',
    writer_rules: [
      '2. This post is a HOW-TO. Every body section starts with "## " and its step heading from the outline, exactly as given ("## Step 1: ...", "## Step 2: ..."), in order. The closing and FAQ headings are not numbered.',
      '3. Each step opens with the action in plain words, then why it matters and the mistake to avoid. Keep it practical and easy to follow.',
      '4. Short bullet or numbered checklists inside a step are allowed where they genuinely help. Use a markdown table only if the outline marks a step with include_table.',
    ].join('\n'),
    editor_note: 'a HOW-TO: TL;DR, short opening, step sections ("## Step 1: ...", "## Step 2: ..."), a closing and FAQs. Checklists inside steps are allowed.',
  },
  comparison: {
    label: 'Comparison',
    heading_style: 'plain', bold_opener: false, table: 'required', lists_allowed: true,
    spine: 'title_questions: the 2-5 options being compared (e.g. "Monocrystalline panels", "Solar roof tiles"), followed by a final "Which should you choose?" question. These are the spine of the post: one section per option, then the verdict.',
    structure_text: [
      TLDR,
      `2. section_type "intro": section_name "Opening", 120-200 words. The first one or two sentences give the short answer with the primary keyword (no scene or "Picture..." moment), then what is being compared and for whom. ${HOME_LINK}`,
      '3. section_type "body": one section per OPTION (2-5 sections, 200-400 words each): section_name is the option and who it suits, in sentence case (e.g. "Solar roof tiles: best for new roofs and listed buildings"). Each covers strengths, limits, when to choose it and what drives its cost. Then ONE section "Side by side: how the options compare" with include_table true. Then ONE verdict section ("Which should you choose?" or similar) that gives clear, honest guidance by situation. Set "answers" to the option or question each section covers. The D items are the insider detail and proof.',
      `4. section_type "closing": a short heading and 80-150 words, the clear next step (what to prepare or send) with a soft, unhurried invitation. ${CTA_LINK}`,
      `5. ${FAQ('3-5')}`,
    ].join('\n'),
    body_line: 'Cover this option fairly: strengths, limits, when it is the right choice, with any first-hand detail below as proof.',
    writer_rules: [
      '2. This post is a COMPARISON. Every body and closing section starts with "## " and its heading from the outline, exactly as given.',
      '3. Treat every option fairly: strengths, limits and when it is the right choice. Be honest when the simpler or cheaper option wins.',
      '4. Short bullet lists (3-7 items, at most three in the body) only where they make information easier to scan. The section marked include_table gets one clear markdown comparison table of the options, each row showing a real difference, the use it suits and its limit.',
    ].join('\n'),
    editor_note: 'a COMPARISON: TL;DR, opening, one section per option, a side-by-side comparison table, a verdict, a closing and FAQs.',
  },
};
const profile = PROFILES[format];
// Headings follow the site's house style (QA also puts Title Case right in code)
if (site.heading_case === 'title') {
  profile.structure_text = profile.structure_text.replace(/sentence case/g, 'Title Case')
    + '\nHEADING CASE: on this website every section_name is in Title Case (e.g. "What Does Solar Panel Installation in Bristol Cost?").';
}
const case_study_rule = use_case_studies
  ? `${site.brand} case studies may be used as short supporting examples.`
  : `Do NOT use case studies in this post: no case-study examples, no client or event names from ${site.brand} jobs and no links to case-study pages. First-hand value comes from how ${site.brand} works (process, checks, contrarian advice and expert commentary) and the real details on its own pages instead.`;
return [{ json: { format, format_label: profile.label, use_case_studies, case_study_rule, profile } }];"""

BUILD_REQUEST_ROW = r"""// Log this request as a new row INSIDE the tracking Sheet's table. A plain append lands under a
// Google Sheets table instead of extending it, so the row is added with the Sheets API's
// appendCells on the table itself. Falls back to the sheet if it has no table.
const start = $('Start').first().json;
const settings = $('Post Settings').first().json;
const meta = $input.first().json || {};
const sheetUrl = String($('Config').first().json.sheet_url || '');
const spreadsheet_id = (sheetUrl.match(/\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/) || [])[1] || '';
const gid = Number((sheetUrl.match(/[#&?]gid=(\d+)/) || [])[1] || 0);
if (!spreadsheet_id) throw new Error('Config sheet_url is not a Google Sheets link.');

const site = $('Project').first().json;
const values = {
  'request id': Number($execution.id) || String($execution.id),
  'project': site.brand,
  'date': start.date,
  'seo name': start.seo_name,
  'title': start.title_idea,
  'main keyword': start.keyword,
  'note from seo': [site.brand, settings.format_label, settings.use_case_studies ? 'case studies: yes' : 'case studies: no',
    start.word_count ? `Approx. ${start.word_count} words` : '', start.reference_url ? `Reference: ${start.reference_url}` : '', start.notes]
    .filter(Boolean).join('. '),
  'status': 'Writing',
};
const DEFAULT_COLUMNS = ['Request ID', 'Date', 'Project', 'SEO name', 'Title', 'Main keyword', 'Note from SEO', 'Status', 'Blog file',
  'Word count', 'Meta title', 'Meta description', 'Slug', 'Notes', 'Info gain %'];
const norm = s => String(s || '').trim().toLowerCase();

// "27 Oct 2026" as a spreadsheet date serial, so a Date column treats it as a real date
const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
const serial = d => {
  const m = String(d || '').match(/^(\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4})$/);
  return m && m[2].toLowerCase() in MONTHS ? Date.UTC(Number(m[3]), MONTHS[m[2].toLowerCase()], Number(m[1])) / 86400000 + 25569 : null;
};
const cell = (v, type) => {
  if (v === undefined || v === null || v === '') return {};
  if (type === 'DATE' && serial(v) !== null) return { userEnteredValue: { numberValue: serial(v) } };
  if (typeof v === 'number') return { userEnteredValue: { numberValue: v } };
  return { userEnteredValue: { stringValue: String(v) } };
};

// The table that tracks requests is the one with a "Request ID" column
let table = null;
for (const s of meta.sheets || []) {
  for (const t of s.tables || []) {
    if (!table && (t.columnProperties || []).some(c => norm(c.columnName) === 'request id')) table = t;
  }
}

let request, target;
if (table) {
  const cols = [...table.columnProperties].sort((a, b) => (a.columnIndex || 0) - (b.columnIndex || 0));
  request = { appendCells: { tableId: table.tableId, rows: [{ values: cols.map(c => cell(values[norm(c.columnName)], c.columnType)) }], fields: 'userEnteredValue' } };
  target = `table "${table.name || table.tableId}"`;
} else {
  const sheet = (meta.sheets || []).find(s => s.properties?.sheetId === gid) || (meta.sheets || [])[0];
  const sheetId = sheet?.properties?.sheetId ?? gid;
  request = { appendCells: { sheetId, rows: [{ values: DEFAULT_COLUMNS.map(c => cell(values[norm(c)], c === 'Date' ? 'DATE' : '')) }], fields: 'userEnteredValue' } };
  target = `sheet ${sheetId} (no table found)`;
}
return [{ json: { spreadsheet_id, target, body: { requests: [request] } } }];"""

REFERENCE_PAGE = r"""// Optional reference page from the SEO: a competitor post to outrank (skyscraper). Read it once so
// the planner covers everything it covers and the writer beats it, without ever copying it
const url = String($('Start').first().json.reference_url || '').trim();
const none = { has_reference: false, reference_url: url, reference_title: '', reference_words: 0, reference_outline: [], reference_block: 'none', reference_note: '' };
if (!url) return [{ json: none }];
if (!/^https?:\/\/[^\s/$.?#][^\s]*$/i.test(url)) return [{ json: { ...none, reference_note: `CHECK: the reference link "${url}" is not a valid web address, so it was ignored.` } }];

let html = '';
if (typeof this?.helpers?.httpRequest === 'function') {
  try {
    const r = await this.helpers.httpRequest({
      method: 'GET', url, timeout: 30000, returnFullResponse: true, ignoreHttpStatusErrors: true, json: false,
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36', 'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'en-GB,en;q=0.9' },
    });
    if (r.statusCode >= 200 && r.statusCode < 400) html = String(r.body || '');
  } catch (e) { html = ''; }
}
if (html.length < 500) return [{ json: { ...none, reference_note: `CHECK: the reference page could not be read (${url}), so the post was planned from the search results only.` } }];

const decode = s => s
  .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
  .replace(/&quot;/gi, '"').replace(/&#0*39;|&#x27;|&rsquo;|&lsquo;|&apos;/gi, "'")
  .replace(/&ldquo;|&rdquo;/gi, '"').replace(/&ndash;|&mdash;/gi, '-').replace(/&hellip;/gi, '...')
  .replace(/&#(\d+);/g, (m, d) => String.fromCharCode(Number(d)));
const toText = h => decode(String(h).replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|h[1-6]|li|tr|div|section|td|th)>/gi, '\n').replace(/<[^>]+>/g, ' '))
  .replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
const count = t => (t.match(/\S+/g) || []).length;
const stripChrome = h => h.replace(/<(nav|header|footer|aside|form)\b[\s\S]*?<\/\1>/gi, ' ');

html = html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<(script|style|noscript|svg|iframe|template)\b[\s\S]*?<\/\1>/gi, ' ');
const title = toText(html.match(/<h1\b[^>]*>([\s\S]*?)<\/h1>/i)?.[1] || html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] || url);
let body = stripChrome((html.match(/<article\b[\s\S]*<\/article>/i) || html.match(/<main\b[\s\S]*<\/main>/i) || [html])[0]);
if (count(toText(body)) < 300) body = stripChrome(html);
const outline = [...body.matchAll(/<h([2-3])\b[^>]*>([\s\S]*?)<\/h\1>/gi)]
  .map(m => `${m[1] === '3' ? '  ' : ''}H${m[1]}: ${toText(m[2]).replace(/\s+/g, ' ')}`)
  .filter(h => h.length > 5).slice(0, 40);
const text = toText(body);
const reference_words = count(text);
const excerpt = text.split(/\s+/).slice(0, 2500).join(' ');
const reference_block = [
  `URL: ${url}`, `Title: ${title}`, `Length: about ${reference_words} words`,
  'Outline:', ...(outline.length ? outline.map(h => `- ${h}`) : ['- (no headings found)']),
  '', 'Main text (excerpt, for coverage only; never copy its wording):', excerpt,
].join('\n');
return [{ json: { has_reference: true, reference_url: url, reference_title: title, reference_words, reference_outline: outline, reference_block, reference_note: '' } }];"""

CLEAN_KB = r"""// Undo formatting added when the knowledge base is pasted into a rich-text editor:
// every line wrapped as "- **...**", escaped markdown (\#, \*\*) and &nbsp; blank lines
let text = String($input.first().json.kb || '').replace(/\r\n?/g, '\n').replace(/ /g, ' ');
const unentity = s => s.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
const WRAPPED = /^\s*(?:[-*+]\s+)?\*\*([\s\S]*)\*\*\s*$/;
const BLANK = /^\s*(?:[-*+]\s*)?(?:&nbsp;|\s)*$/;

const lines = text.split('\n').map(l => l.replace(/\s+$/, ''));
const content = lines.filter(l => !BLANK.test(l));
const wrapped = content.filter(l => WRAPPED.test(l)).length;
const escaped = (text.match(/\\[#*\-_.()\[\]!`>|~+]/g) || []).length;
const pasted = (content.length && wrapped / content.length > 0.5) || escaped > 20 || /&nbsp;/.test(text);

if (pasted) {
  text = lines.map(l => {
    if (BLANK.test(l)) return '';
    const m = l.match(WRAPPED);
    return m && wrapped / content.length > 0.5 ? m[1] : l;
  }).join('\n');
  // Markdown escapes: a backslash before any ASCII punctuation
  text = unentity(text).replace(/\\([!-\/:-@\[-`{-~])/g, '$1');
  // Editors turn bare emails and web addresses into links: [x](mailto:x) or [x](https://x) back to x
  text = text.replace(/\[([^\]]+)\]\((?:mailto:|https?:\/\/)?([^)\s]+)\)/g, (m, label, target) => label.replace(/\/$/, '') === target.replace(/\/$/, '') ? label : m);
  text = text.split('\n').map(l => l.replace(/\s+$/, '')).join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

// The writer's trimmed copy relies on numbered "## 1." section headings
const sections = (text.match(/^## \d+\./gm) || []).length;
return [{ json: { kb: text, kb_cleaned: Boolean(pasted), kb_sections: sections } }];"""

VALIDATE_OUTLINE = r"""// Clean up the outline: enforce the post structure, keyword and information-gain coverage,
// the link rules and the word count, then turn it into one outline text for the writer
const brief = $('Brief').first().json;
const map = brief.link_map;
const notes = [];

// www and non-www, http and https, and a trailing slash all count as the same page
const norm = u => String(u || '').trim().toLowerCase()
  .replace(/[?#].*$/, '')
  .replace(/^https?:\/\/(?:www\.)?/, 'https://')
  .replace(/\/+$/, '');
// n8n's Code sandbox has no URL class, so read the hostname with a regex
const domainOf = u => (String(u || '').trim().match(/^https?:\/\/(?:[^@\/?#]*@)?([^\/?#:]+)/i)?.[1] || '').replace(/^www\./i, '').toLowerCase();

const HOME = norm(map.homepage.url);
const allowed = new Map([[HOME, { url: map.homepage.url, anchor: map.homepage.anchors[0], topic: 'homepage', group: 'homepage' }]]);
for (const group of ['service_pages', 'case_studies', 'blog_posts', 'conversion']) {
  for (const p of map[group] || []) allowed.set(norm(p.url), { ...p, group });
}
// Any live page in the site's sitemap is a valid internal link too
for (const u of map.site_urls || []) {
  if (!allowed.has(norm(u))) allowed.set(norm(u), { url: u, anchor: u.split('/').filter(Boolean).pop().replace(/-/g, ' '), topic: '', group: 'site' });
}
const CONVERSION = (map.conversion || []).map(p => norm(p.url));

// 1. Structure: TL;DR, intro, body..., closing, FAQs
const raw = ($input.first().json.output?.sections || []).map(s => ({ ...s }));
if (!raw.length) throw new Error('Outline Planner returned no sections.');
const typeOf = s => String(s.section_type || '').toLowerCase().trim();
const firstOf = t => raw.find(s => typeOf(s) === t);

const tldr = firstOf('tldr') || { overview_idea: `Answer "${brief.final_title}" directly.` };
const intro = firstOf('intro') || { overview_idea: 'Answer the title directly, then say what the post covers.' };
const closing = firstOf('closing') || { section_name: 'What to do next', overview_idea: 'The clear next step: what to prepare or send, and a soft invitation to talk.' };
const faq = firstOf('faq') || { overview_idea: 'Answer the questions searchers ask most.' };
const body = raw.filter(s => !['tldr', 'intro', 'closing', 'faq'].includes(typeOf(s)));
if (!body.length) throw new Error('Outline Planner returned no body sections.');

Object.assign(tldr, { section_type: 'tldr', section_name: 'TL;DR' });
Object.assign(intro, { section_type: 'intro', section_name: 'Opening' });
Object.assign(closing, { section_type: 'closing', section_name: closing.section_name || 'What to do next' });
Object.assign(faq, { section_type: 'faq', section_name: 'FAQs' });
body.forEach(s => { s.section_type = 'body'; });
const settings = $('Post Settings').first().json;
const profile = settings.profile;
// Listicles and how-tos number their items; the number always matches the position
if (profile.heading_style === 'numbered' || profile.heading_style === 'steps') {
  body.forEach((s, i) => {
    const name = String(s.section_name || '').trim().replace(/^(?:step\s*)?\d+\s*[.:)\-]\s*/i, '');
    s.section_name = profile.heading_style === 'steps' ? `Step ${i + 1}: ${name}` : `${i + 1}. ${name}`;
  });
}
// GEO/AEO headings are the short search question alone: "Fragment: question?" and
// "Question? Fragment" both become "Question?"
body.forEach(s => {
  if (profile.heading_style !== 'question') return;
  let name = String(s.section_name || '').trim();
  const m = name.match(/^([^?:]+):\s*([^?]+\?)\s*$/);
  if (m) name = m[2][0].toUpperCase() + m[2].slice(1);
  name = name.replace(/^([^?]+\?)\s+.*$/, '$1');
  s.section_name = name;
  if (name.split(/\s+/).length > 12) s.long_heading = true;
});
if (!(faq.faq_questions || []).length) faq.faq_questions = brief.paa_questions.slice(0, 5);
faq.faq_questions = faq.faq_questions.slice(0, 6);

const sections = [tldr, intro, ...body, closing, faq];

// Supporting keywords: keep only the brief's list, and give any unassigned keyword to the
// body section whose heading and idea share the most words with it
const words = s => new Set(String(s || '').toLowerCase().match(/[a-z0-9]+/g) || []);
const supportingLc = new Map(brief.supporting_keywords.map(k => [k.toLowerCase(), k]));
body.forEach(s => {
  s.keywords = [...new Set((s.keywords || []).map(k => supportingLc.get(String(k).toLowerCase().trim())).filter(Boolean))];
});
const bestBody = text => {
  const w = words(text);
  let best = body[0], bestScore = -1;
  body.forEach(s => {
    const sw = words(`${s.section_name} ${s.overview_idea}`);
    const score = [...w].filter(x => sw.has(x)).length - s.keywords.length * 0.1;
    if (score > bestScore) { best = s; bestScore = score; }
  });
  return best;
};
for (const k of brief.supporting_keywords) {
  if (!body.some(s => s.keywords.includes(k))) bestBody(k).keywords.push(k);
}

// Information gain: every item lands in some body section
const gainLc = new Map(brief.information_gain.map(g => [g.toLowerCase(), g]));
body.forEach(s => {
  s.information_gain = (s.information_gain || []).map(g => String(g).trim()).filter(Boolean);
});
for (const g of brief.information_gain) {
  const lc = g.toLowerCase();
  if (!body.some(s => s.information_gain.some(x => x.toLowerCase() === lc))) bestBody(g).information_gain.push(g);
}
if (!gainLc.size) notes.push('Outline: no verified information-gain points were available for this topic.');
// No section is built on case studies: at most one case-study item per body section
// (extras move to a section that has none)
const isCase = g => /\(case_study_data\)/.test(g);
for (const s of body) {
  while (s.information_gain.filter(isCase).length > 1) {
    const free = body.find(b => b !== s && !b.information_gain.some(isCase));
    if (!free) break;
    const i = s.information_gain.map(isCase).lastIndexOf(true);
    free.information_gain.push(s.information_gain.splice(i, 1)[0]);
  }
}

// Every body section answers one of the reader's questions about the title
const titleQs = brief.title_questions || [];
const askedLc = new Set(body.map(s => String(s.answers || '').toLowerCase().trim()).filter(Boolean));
const spareQs = titleQs.filter(q => !askedLc.has(q.toLowerCase().trim()));
body.forEach(s => { s.answers = String(s.answers || '').trim() || spareQs.shift() || ''; });
if (spareQs.length) notes.push(`Outline: reader questions without their own section (cover them in the closest section): ${spareQs.join(' | ')}`);
const leftoverQs = spareQs;

// Tables follow the format: required (exactly one), optional (at most one) or none
let tableSet = false;
body.forEach(s => { s.include_table = profile.table !== 'none' && Boolean(s.include_table) && !tableSet; if (s.include_table) tableSet = true; });
if (!tableSet && profile.table === 'required') body[Math.min(1, body.length - 1)].include_table = true;

// Case studies switched off: case-study pages are not linkable
if (!settings.use_case_studies) {
  for (const [k, p] of [...allowed.entries()]) if (p.group === 'case_studies' || /\/case-studies\//.test(p.url)) allowed.delete(k);
}

// 2. Internal links: allowlisted URLs only, each used once, homepage in the intro, CTA in the closing
const used = new Set();
for (const s of sections) {
  const keep = [];
  if (s.section_type !== 'tldr') {
    for (const l of s.internal_links || []) {
      const key = norm(l?.url);
      if (!allowed.has(key)) { if (l?.url) notes.push(`Outline: dropped unknown internal URL ${l.url}`); continue; }
      if (used.has(key) || (key === HOME && s !== intro)) continue;
      used.add(key);
      keep.push({ url: allowed.get(key).url, anchor: String(l.anchor || allowed.get(key).anchor).trim() });
    }
  }
  s.internal_links = keep;
}
const addLink = (section, key, atStart) => {
  if (used.has(key)) return;
  used.add(key);
  const p = allowed.get(key);
  section.internal_links[atStart ? 'unshift' : 'push']({ url: p.url, anchor: p.anchor });
};
addLink(intro, HOME, true);
if (!closing.internal_links.some(l => CONVERSION.includes(norm(l.url)))) {
  const free = CONVERSION.find(k => !used.has(k));
  if (free) addLink(closing, free, false);
}

const totalInternal = () => sections.reduce((n, s) => n + s.internal_links.length, 0);
const MIN_INTERNAL = 5;
const MAX_INTERNAL = 8;

// Too few: top up with pages whose topic shares words with the keywords
if (totalInternal() < MIN_INTERNAL) {
  const kw = new Set(`${brief.primary_keyword} ${brief.keywords_csv}`.toLowerCase().match(/[a-z0-9]+/g) || []);
  const candidates = [...allowed.entries()]
    .filter(([k, p]) => !used.has(k) && ['service_pages', 'case_studies', 'blog_posts'].includes(p.group))
    .map(([k, p]) => ({ k, p, score: (p.topic.toLowerCase().match(/[a-z0-9]+/g) || []).filter(w => w.length > 2 && kw.has(w)).length }))
    .filter(c => c.score > 0)
    .sort((a, b) => b.score - a.score);
  let bi = 0;
  for (const c of candidates) {
    if (totalInternal() >= MIN_INTERNAL) break;
    used.add(c.k);
    body[bi++ % body.length].internal_links.push({ url: c.p.url, anchor: c.p.anchor });
  }
  if (totalInternal() < MIN_INTERNAL) notes.push(`Outline: only ${totalInternal()} internal links could be matched to this topic.`);
}
// Too many: trim from the last body sections (never the homepage or the closing CTA)
for (let i = body.length - 1; i >= 0 && totalInternal() > MAX_INTERNAL; i--) {
  while (body[i].internal_links.length && totalInternal() > MAX_INTERNAL) body[i].internal_links.pop();
}

// 3. External links: approved authoritative domains only, max 2, and the page must load
const APPROVED = map.approved_external_domains || [];
const isApproved = d => APPROVED.some(a => d === a || d.endsWith('.' + a));
const canFetch = typeof this?.helpers?.httpRequest === 'function';
let externalCount = 0;
for (const s of sections) {
  const keep = [];
  for (const l of s.external_links || []) {
    const d = domainOf(l?.url);
    if (!d) continue;
    if (s.section_type === 'tldr' || externalCount >= 2 || !isApproved(d)) {
      notes.push(`Outline: dropped external link ${l.url} (not an approved source or over the limit of 2)`);
      continue;
    }
    if (canFetch) {
      let ok = false;
      try {
        const r = await this.helpers.httpRequest({ method: 'GET', url: l.url, timeout: 10000, returnFullResponse: true, ignoreHttpStatusErrors: true });
        ok = r.statusCode >= 200 && r.statusCode < 400;
      } catch (e) { ok = false; }
      if (!ok) { notes.push(`Outline: dropped external link that did not load: ${l.url}`); continue; }
    } else {
      notes.push(`CHECK: external link not verified automatically: ${l.url}`);
    }
    keep.push({ url: l.url, source_name: l.source_name || d });
    externalCount++;
  }
  s.external_links = keep;
}

// 4. Word counts: TL;DR fixed at 50, everything else scaled so the total matches
const target = brief.target_word_count;
tldr.section_word_count = 50;
const flexible = sections.filter(s => s !== tldr);
flexible.forEach(s => { s.section_word_count = Math.max(80, Math.round(Number(s.section_word_count) || 300)); });
const factor = (target - 50) / flexible.reduce((n, s) => n + s.section_word_count, 0);
flexible.forEach(s => { s.section_word_count = Math.max(80, Math.round(s.section_word_count * factor)); });
const largest = body.reduce((a, b) => (b.section_word_count > a.section_word_count ? b : a));
largest.section_word_count += target - sections.reduce((n, s) => n + s.section_word_count, 0);

// 5. One outline text for the single writer call
const describe = (s, i) => {
  const lines = [`${i + 1}. [${s.section_type}] ${s.section_type === 'tldr' ? '## TL;DR' : s.section_type === 'intro' ? '(no heading)' : '## ' + String(s.section_name).trim()} (about ${s.section_word_count} words)`];
  if (s.overview_idea) lines.push(`   What to cover: ${s.overview_idea}`);
  if (s.section_type === 'tldr') lines.push(`   Use the primary keyword "${brief.primary_keyword}". No links.`);
  if (s.section_type === 'intro' || s.section_type === 'closing') lines.push(`   Use the primary keyword "${brief.primary_keyword}".`);
  if (s.section_type === 'intro') lines.push(`   Open with the direct answer to the title in one or two sentences, using the primary keyword "${brief.primary_keyword}" exactly${brief.opening_scene ? ` (the answer: ${brief.opening_scene})` : ''}. Never open with a scene or a "Picture..." moment.${brief.opening_detail ? ` Then, if it helps, one sentence of real supporting detail: ${brief.opening_detail}` : ''}`);
  if (s.section_type === 'body' && s.answers) lines.push(`   ${profile.heading_style === 'question' ? 'Reader question this section answers' : 'This section covers'}: ${s.answers}`);
  if (s.long_heading) lines.push('   Heading: shorten it to a question of at most 12 words, keeping its keyword.');
  if (s.section_type === 'body') lines.push(`   ${profile.body_line}`);
  if (s === body[body.length - 1] && leftoverQs.length) lines.push(`   Also answer briefly: ${leftoverQs.join(' | ')}`);
  if ((s.keywords || []).length) lines.push(`   Supporting keywords to use: ${s.keywords.join('; ')}`);
  if ((s.information_gain || []).length) lines.push(`   Information gain to weave in: ${s.information_gain.join(' | ')}`);
  if (s.include_table) lines.push('   Include ONE markdown comparison table in this section.');
  for (const l of s.internal_links || []) lines.push(`   Link: [${l.anchor}](${l.url})`);
  for (const l of s.external_links || []) lines.push(`   External source link (${l.source_name}): ${l.url}`);
  if (s.section_type === 'faq') lines.push(`   Questions: ${(s.faq_questions || []).join(' | ')}`);
  return lines.join('\n');
};
const outline_text = sections.map(describe).join('\n\n');

return [{
  json: {
    outline_text,
    sections: sections.map(s => ({
      section_type: s.section_type,
      section_name: String(s.section_name || '').trim(),
      section_word_count: s.section_word_count,
      answers: s.answers || '',
      keywords: s.keywords || [],
      information_gain: s.information_gain || [],
      include_table: Boolean(s.include_table),
      internal_links: s.internal_links,
      external_links: s.external_links,
      faq_questions: s.faq_questions || [],
    })),
    outline_notes: notes,
  },
}];"""

ASSEMBLE_BLOG = r"""// Put the H1 on top of the writer's markdown and strip anything that is not the post
const raw = String($input.first().json.text || '').trim()
  .replace(/^```(?:markdown|md)?\s*\n/i, '')
  .replace(/\n```\s*$/, '')
  .trim();
if (!raw) throw new Error('Blog Writer returned an empty post.');

// A cut-off draft (far too short, or no FAQs at the end) fails the run instead of letting the
// editor rebuild the post from scratch without the outline
const brief = $('Brief').first().json;
const words = (raw.match(/\S+/g) || []).length;
const target = Number(brief.target_word_count) || 1500;
const hasFaqs = /^## (FAQs|Frequently asked questions)\s*$/m.test(raw);
if (words < target * 0.5 || !hasFaqs) {
  throw new Error(`Blog Writer stopped early: ${words} words against a target of about ${target}${hasFaqs ? '' : ', and no FAQs section'}. `
    + 'The reply was cut short: either the writer model ran out of output tokens (its thinking counts towards the "Sonnet Writer" Maximum Number of Tokens, so raise that) or the OpenRouter key is close to its spending limit. Fix whichever applies, then submit the form again.');
}

// Drop any H1 the writer added; the brief's title is the H1
const body = raw.replace(/^# .*\n+/, '');
const title = brief.final_title;
return [{ json: { blog: `# ${title}\n\n${body}\n` } }];"""

QA = r"""// Deterministic link and style checks. Fixes what is safe to fix in code (unknown or
// duplicate internal links, unapproved or surplus external links) and lists the rest as issues
const brief = $('Brief').first().json;
const map = brief.link_map;
const settings = $('Post Settings').first().json;
const profile = settings.profile;
const site = $('Project').first().json;
let blog = String($input.first().json.blog || '').trim();

// www and non-www, http and https, and a trailing slash all count as the same page
const norm = u => String(u || '').trim().toLowerCase()
  .replace(/[?#].*$/, '')
  .replace(/^https?:\/\/(?:www\.)?/, 'https://')
  .replace(/\/+$/, '');
// n8n's Code sandbox has no URL class, so read the hostname with a regex
const domainOf = u => (String(u || '').trim().match(/^https?:\/\/(?:[^@\/?#]*@)?([^\/?#:]+)/i)?.[1] || '').replace(/^www\./i, '').toLowerCase();
const isOwn = d => d === site.domain || d.endsWith('.' + site.domain);

const HOME = norm(map.homepage.url);
const allowed = new Set([HOME]);
for (const group of ['service_pages', 'case_studies', 'blog_posts', 'conversion']) {
  for (const p of map[group] || []) allowed.add(norm(p.url));
}
for (const u of map.site_urls || []) allowed.add(norm(u));
// Case studies switched off: case-study pages are never linked
if (!settings.use_case_studies) for (const u of [...allowed]) if (/\/case-studies\//.test(u)) allowed.delete(u);
const protectedUrls = new Set([HOME, ...(map.conversion || []).map(p => norm(p.url))]);
const APPROVED = map.approved_external_domains || [];
const isApproved = d => APPROVED.some(a => d === a || d.endsWith('.' + a));

const fixes = [];
const issues = [];
const LINK = /\[([^\]]+)\]\(([^)\s]+)\)/g;

// 0. Never an em dash: em dashes and spaced dashes become commas (en dashes in number ranges stay)
const dashes = (blog.match(/—|(?<=\S)[^\S\n]+[–-][^\S\n]+(?=\S)/g) || []).length;
if (dashes) {
  blog = blog
    .replace(/(\d[\d,.]*k?)[^\S\n]*[—–-][^\S\n]+(\p{Sc}?\d)|(\d[\d,.]*k?)[^\S\n]+[—–-][^\S\n]*(\p{Sc}?\d)/gu, (m, a, b, c, d) => `${a || c} to ${b || d}`)
    .replace(/[^\S\n]*—[^\S\n]*/g, ', ')
    .replace(/(?<=\S)[^\S\n]+[–-][^\S\n]+(?=\S)/g, ', ')
    .replace(/,\s*([,.;:!?])/g, '$1');
  fixes.push(`Replaced ${dashes} em/spaced dash(es) with commas`);
}

// 0b. Body headings: "Question? Fragment" never ends the fragment with a full stop
let headingStops = 0;
blog = blog.replace(/^(## [^\n?]+\?[^\S\n]+[^\n]*?)\.+[^\S\n]*$/gm, (m, h) => { headingStops++; return h; });
if (headingStops) fixes.push(`Removed the full stop from ${headingStops} heading fragment(s)`);

// 0b2. House terminology is a straight swap, so it is fixed in code
let termSwaps = 0;
const esc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
for (const [avoid, use] of site.terminology || []) {
  blog = blog.replace(new RegExp(`\\b${esc(avoid)}\\b`, 'gi'), m => { termSwaps++; return m[0] === m[0].toUpperCase() ? use[0].toUpperCase() + use.slice(1) : use; });
}
if (termSwaps) fixes.push(`Changed ${termSwaps} term(s) to house style (${(site.terminology || []).map(([, u]) => `"${u}"`).join(', ')})`);

// 0c. Sites that use Title Case get it in code: every heading, or only the H1
const titleLevel = level => site.heading_case === 'title' || (site.heading_case === 'title_h1' && level === 1);
let recased = 0;
blog = blog.replace(/^(#{1,3}) (.+)$/gm, (m, hashes, h) => {
  if (!titleLevel(hashes.length) || h === 'TL;DR') return m;
  const t = titleCase(h);
  if (t !== h) recased++;
  return `${hashes} ${t}`;
});
if (recased) fixes.push(`Put ${recased} heading(s) in Title Case (${site.brand} house style)`);

// 1. Links: unlink anything that breaks the rules
const seen = new Set();
let externalCount = 0;
blog = blog.replace(LINK, (m, anchor, url) => {
  const full = url.startsWith('/') ? map.base_url + url : url;
  const d = domainOf(full);
  if (!d) return m;
  if (isOwn(d)) {
    const key = norm(full);
    if (!allowed.has(key)) { fixes.push(`Unlinked unknown internal URL ${url}`); return anchor; }
    if (seen.has(key)) { fixes.push(`Unlinked duplicate internal link ${url}`); return anchor; }
    seen.add(key);
    return `[${anchor}](${full})`;
  }
  if (!isApproved(d)) { fixes.push(`Unlinked external link to a non-approved site: ${url}`); return anchor; }
  if (externalCount >= 2) { fixes.push(`Unlinked external link over the limit of 2: ${url}`); return anchor; }
  externalCount++;
  return m;
});

// More than 8 internal links: unlink the last ones, keeping the homepage and CTA links
let internalUrls = [...blog.matchAll(LINK)].map(m => m[2]).filter(u => isOwn(domainOf(u)));
let surplus = internalUrls.length - 8;
if (surplus > 0) {
  const toDrop = new Set(internalUrls.filter(u => !protectedUrls.has(norm(u))).slice(-surplus).map(norm));
  blog = blog.replace(LINK, (m, anchor, url) => {
    if (toDrop.has(norm(url))) { toDrop.delete(norm(url)); fixes.push(`Unlinked surplus internal link ${url}`); return anchor; }
    return m;
  });
}

const links = [...blog.matchAll(LINK)].map(m => ({ anchor: m[1], url: m[2], domain: domainOf(m[2]) }));
const internal = links.filter(l => isOwn(l.domain));
const external = links.filter(l => l.domain && !isOwn(l.domain));
if (internal.length < 5) issues.push(`Only ${internal.length} internal links. Add links from the link menu so there are 5-8 in total, each worked naturally into an existing sentence.`);
if (!internal.some(l => norm(l.url) === HOME)) issues.push(`No homepage link. Add one link to ${map.homepage.url} with an anchor such as "${site.home_anchor}", ideally in the introduction.`);
const badAnchors = links.filter(l => /^(click here|here|this|read more|this page|link)$/i.test(l.anchor.trim()));
if (badAnchors.length) issues.push(`Vague link anchors (${badAnchors.map(l => `"${l.anchor}"`).join(', ')}). Rewrite them as descriptive, in-sentence anchors.`);

// 2. Style and claim rules (checked on text without URLs)
const text = blog.replace(/\]\([^)]*\)/g, ']');
const kwHasRent = /\brent/i.test(brief.primary_keyword);
const RULES = [
  // The project's acronyms in any other capitalisation (an all-lowercase match could be an ordinary word, so it is left alone)
  ...(site.acronyms || []).map(a => [new RegExp(`\\b${esc(a)}\\b`, 'gi'), `Write "${a}" exactly like that.`, m => m !== a && m !== m.toLowerCase()]),
  // All-lowercase acronyms of three letters or more (often from a link anchor copied from a URL)
  ...(site.acronyms || []).filter(a => a.length >= 3 && a !== a.toLowerCase()).map(a => [new RegExp(`\\b${esc(a.toLowerCase())}\\b`, 'g'), `Lowercase "${a.toLowerCase()}" (often from a link anchor copied from a URL). Write "${a}" and write anchors in natural words with proper capitals.`]),
  // Spelling follows the project's market (British or American)
  ...(site.market?.spelling === 'british' ? [
    [/\b(organiz|optimiz|recogniz|minimiz|maximiz|prioritiz|customiz|realiz|utiliz|specializ|visualiz)(e|es|ed|ing|ation|ations|er|ers)\b/gi, 'Use British -ise spelling.'],
    [/\b(color|colors|colored|favor|favorite|favorites|behavior|behaviors|center|centers|centered|catalog|traveling|traveled|canceled|aluminum|labeled)\b/gi, 'Use British spelling.'],
  ] : site.market?.spelling === 'american' ? [
    [/\b(organis|optimis|recognis|minimis|maximis|prioritis|customis|realis|utilis|specialis|visualis)(e|es|ed|ing|ation|ations|er|ers)\b/gi, 'Use American -ize spelling.'],
    [/\b(colour|colours|coloured|favour|favourite|favourites|behaviour|behaviours|centre|centres|centred|catalogue|travelling|travelled|cancelled|aluminium|labelled)\b/gi, 'Use American spelling.'],
  ] : []),
  [/\bonsite\b/gi, 'Write "on-site".'],
  [/\bwifi\b|\bWiFi\b|\bWifi\b/g, 'Write "Wi-Fi".'],
  // House terminology the code could not swap safely
  ...(site.terminology || []).map(([avoid, use]) => [new RegExp(`\\b${esc(avoid)}\\b`, 'gi'), `Use "${use}", not "${avoid}".`]),
  // This site's own claim rules (address, certifications, sister companies)
  ...(site.rules || []).map(([src, flags, msg]) => [new RegExp(src, flags), msg]),
  [/\b\d(\.\d)?[- ]?stars?\b|\bout of 5\b|\bTrustpilot\b|\bGoogle (rating|reviews)\b/gi, 'Do not quote ratings or reviews.'],
  [/\b(best in (?:the )?[A-Z][a-z]+|number one|no\. ?1|cheapest|lowest[- ]priced?|unbeatable)\b/g, 'Remove the unsupported superlative.'],
  [/\b(wow factor|breathtaking|game[- ]changer|unleash|elevate your|in today's fast-paced world|let's dive in|dive into|delve)\b/gi, 'Remove the hype or filler phrase.'],
  [/\bin your draft\b|\[insert|\bTBC\b|\bTODO\b|lorem ipsum/gi, 'Remove the drafting note.'],
  [/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, 'Remove emojis.'],
  [/\b(in today's|in this day and age|when it comes to|in conclusion|in summary|whether you're|it's important to note|it is important to note|in the world of|look no further|without further ado|navigating the|ever-evolving|at the end of the day|by definition|this guide (explains|covers|will))\b/gi, 'Rewrite these robotic or formulaic phrases in the warm, story-led voice.'],
  [/\b(sign up now|don't miss out|act now|book now|contact us today)\b/gi, 'Replace the hard CTA with a soft, unhurried invitation.'],
  [/\b(may|might)\b/g, 'Replace "may" and "might" with a direct statement of the verified fact (keep a real condition with "if" or "when"), or remove the claim.'],
  [/\bmak(?:e|es|ing) (?:more |much |no |little )?sense\b/gi, 'Replace "make sense" with the actual reason the option is suitable, useful or effective.'],
  [/\b(very|really|extremely|incredibly|amazing|incredible|game-changing|stunning)\b/gi, 'Remove the weak intensifier or empty adjective; use a precise word or a concrete detail.'],
  [/\b(things|stuff|solutions|this approach)\b/gi, 'Replace the vague placeholder with the specific equipment, process or result.'],
  [/\b(crucial|pivotal|seamless(?:ly)?|robust|leverag(?:e|es|ed|ing)|utilis(?:e|es|ed|ing)|landscape|realm|empower(?:s|ed|ing)?|unlock(?:s|ed|ing)?|foster(?:s|ed|ing)?|bolster(?:s|ed|ing)?|streamlin(?:e|es|ed|ing)|cutting-edge|state-of-the-art|tapestry|testament|furthermore|moreover|additionally|ultimately|plays? an? (?:vital|key|crucial|pivotal) role|a wide range of|it's worth noting|ensur(?:e|es|ed|ing))\b/gi, 'Replace these AI-sounding words with plain, everyday ones (e.g. "make sure" for "ensure", "use" for "leverage", "also" for "additionally").'],
];
for (const [re, msg, keep] of RULES) {
  const found = [...new Set(text.match(re) || [])].filter(m => !keep || keep(m));
  if (found.length) issues.push(`${msg} Found: "${found.slice(0, 5).join('", "')}"`);
}
// The brand in any other capitalisation. Skipped for a brand that is also a plain search phrase
// (a keyword such as "solar panel repairs" is not a misspelt "Solar Panel Repairs")
if (site.brand_check !== false) {
  const brandHits = [...new Set(text.match(new RegExp(`\\b${site.brand_re}\\b`, 'gi')) || [])].filter(s => s.replace(/\s+/g, ' ') !== site.brand);
  if (brandHits.length) issues.push(`Write the brand as "${site.brand}". Found: "${brandHits.slice(0, 5).join('", "')}"`);
}

// Pricing: a brand that gives prices only on request never publishes them, so a figure in its
// currency may only be a general market range
const SYMBOL = site.market?.currency_symbol || '£';
const PRICE = new RegExp(`${esc(SYMBOL)}\\s?\\d`);
const ownRe = new RegExp(`\\b(${site.brand_re}|we|we're|we'll|our|ours|us)\\b`, 'i');
const ownPriced = site.prices_on_request === false ? [] : text.split(/(?<=[.!?])\s+|\n+/)
  .filter(s => PRICE.test(s) && ownRe.test(s));
if (ownPriced.length) issues.push(`Never state or imply what ${site.brand} charges. Reword so any ${SYMBOL} figure is a general ${site.market?.country || ''} market range not tied to ${site.brand}, followed by the point that the real cost comes from a quote, or remove it. Found: "${ownPriced.slice(0, 3).map(s => s.trim().slice(0, 160)).join('", "')}"`);
const tldrText = (blog.match(/^## TL;DR\s*\n+([^\n]+)/m) || [])[1] || '';
const pricedHeadings = [...blog.matchAll(/^#{1,3}\s+(.+)$/gm)].map(m => m[1]).filter(h => PRICE.test(h));
if (PRICE.test(tldrText) || pricedHeadings.length) issues.push(`Remove ${SYMBOL} figures from the TL;DR and headings. Keep any general market range in the body only.`);

// 3. Headings: never ALL CAPS; sentence case wherever the site does not use Title Case
const KEEP_CAPS = new RegExp(`^(${['UK', 'US', 'USA', 'EU', 'ISO', 'CEO', 'FAQs?', 'TL;DR', 'Q&A', 'CTA', 'AI', 'SEO', 'Wi-Fi', ...(site.acronyms || []).map(esc)].join('|')})$`);
const brandWords = new Set(site.brand.split(' '));
for (const m of blog.matchAll(/^(#{1,3})\s+(.+)$/gm)) {
  const h = m[2].trim();
  const words = h.replace(/[^\p{L}\p{N}&;'’\- ]/gu, ' ').split(/\s+/).filter(Boolean);
  const letters = h.replace(new RegExp(`\\b(${['UK', 'US', 'TL;DR', 'FAQs?', ...(site.acronyms || []).map(esc)].join('|')})\\b`, 'g'), '').replace(/[^A-Za-z]/g, '');
  if (words.length >= 3 && letters.length >= 6 && letters === letters.toUpperCase()) {
    issues.push(`Heading in ALL CAPS, use ${titleLevel(m[1].length) ? 'Title Case' : 'sentence case'}: "${h}"`);
    continue;
  }
  if (titleLevel(m[1].length)) continue;
  const rest = words.slice(1).filter(w => w.length > 3 && !KEEP_CAPS.test(w) && !brandWords.has(w));
  const capped = rest.filter(w => /^[A-Z][a-z]/.test(w));
  if (rest.length >= 3 && capped.length / rest.length > 0.6) issues.push(`Heading looks like Title Case, use sentence case: "${h}"`);
}

// 4. Structure
if (!/^## TL;DR\s*$/m.test(blog)) issues.push('Missing the "## TL;DR" section directly under the H1.');
const faqStart = blog.search(/^## (FAQs|Frequently asked questions)/m);
if (faqStart < 0) issues.push('Missing the "## FAQs" section at the end.');
const faqCount = faqStart < 0 ? 0 : (blog.slice(faqStart).match(/^### /gm) || []).length;
if (faqStart >= 0 && (faqCount < 3 || faqCount > 8)) issues.push(`The FAQ section has ${faqCount} questions. Use 4-6 questions searchers actually ask, each answered first in 40-60 words.`);
if (profile.table === 'required' && !/^\|.*\|\s*\n\|?\s*:?-{3,}/m.test(blog)) issues.push('No comparison table. Add one markdown table where it genuinely helps the reader.');
const tldrPara = (blog.match(/^## TL;DR\s*\n+([^\n]+)/m) || [])[1] || '';
if (tldrPara && tldrPara.split(/\s+/).length > 75) issues.push('The TL;DR is over 75 words. Cut it to 40-60 words.');

// No bullet or numbered lists outside the FAQ (tables are fine)
const beforeFaq = faqStart < 0 ? blog : blog.slice(0, faqStart);
const listLines = beforeFaq.split('\n').filter(l => /^\s*(?:[-*+•]|\d+[.)])\s+\S/.test(l));
if (listLines.length && !profile.lists_allowed) issues.push(`Bullet or numbered lists found in the body. Rewrite them as flowing sentences. Found: "${listLines.slice(0, 3).map(l => l.trim().slice(0, 80)).join('", "')}"`);
const isListLine = l => /^\s*(?:[-*+•]|\d+[.)])\s+\S/.test(l || '');
const bodyLines = beforeFaq.split('\n');
const listCount = bodyLines.filter((l, i) => isListLine(l) && !isListLine(bodyLines[i - 1])).length;
if (profile.lists_allowed && listCount > 3) issues.push(`The body has ${listCount} lists. Keep at most three, where they make information easier to scan, and turn the rest into short paragraphs.`);

// Headings stay short and specific; no more than 300 words under one heading (Yoast); short paragraphs
const longHeadings = [...beforeFaq.matchAll(/^#{2,3} (.+)$/gm)].map(m => m[1].trim()).filter(h => h !== 'TL;DR' && h.split(/\s+/).length > 12);
if (longHeadings.length) issues.push(`Headings must be short and specific (at most 12 words): a direct question the section answers or a brief descriptive phrase. Shorten: "${longHeadings.slice(0, 4).join('", "')}"`);
const longBlocks = beforeFaq.split(/^#{2,3} .*$/m).slice(1)
  .map(b => ({ b, n: (b.replace(/^\|.*$/gm, '').replace(/\]\([^)]*\)/g, ']').match(/\S+/g) || []).length }))
  .filter(x => x.n > 300);
if (longBlocks.length) issues.push(`${longBlocks.length} section(s) run over 300 words without a subheading (Yoast limit). Split each with a "### " H3 on its sub-topic. Starts: "${longBlocks.slice(0, 3).map(x => x.b.trim().split(/\s+/).slice(0, 8).join(' ') + '...').join('", "')}"`);
const longParas = beforeFaq.split(/\n\s*\n/).filter(p => !/^\s*[#|]/.test(p) && (p.replace(/\]\([^)]*\)/g, ']').match(/\S+/g) || []).length > 120);
if (longParas.length) issues.push(`${longParas.length} paragraph(s) run over 120 words. Split them into paragraphs of one to four sentences: "${longParas.slice(0, 3).map(p => p.trim().split(/\s+/).slice(0, 8).join(' ') + '...').join('", "')}"`);

// Links sit on relevant words inside a useful sentence, never in a "read more" prompt
const linkPrompts = text.split(/(?<=[.!?])\s+|\n+/).filter(s => /\]/.test(s) && /^\W*(?:read (?:more|this|our|about|how)|you can (?:read|find|see|learn)|go through|see (?:our|how|the)|find out more|learn more|our (?:guide|article|post) (?:explains|covers|shows|on)|for more (?:on|about|detail)|check out)\b/i.test(s));
if (linkPrompts.length) issues.push(`Link prompts found. Put each link on relevant words inside a sentence that is useful without the link, and delete the prompt: "${linkPrompts.slice(0, 3).map(s => s.trim().slice(0, 100)).join('", "')}"`);

// Information blocks: every body section opens with a bold, declarative finding
// (the closing section, the TL;DR and the FAQs are exempt)
const sectionsH2 = [...blog.matchAll(/^## (.+)\n+([^\n]*)/gm)].map(m => ({ heading: m[1].trim(), first: m[2].trim() }));
const faqIdx = sectionsH2.findIndex(s => /^(FAQs|Frequently asked questions)/.test(s.heading));
const bodyH2 = sectionsH2.slice(0, faqIdx < 0 ? sectionsH2.length : faqIdx).filter(s => s.heading !== 'TL;DR').slice(0, -1);
const noBold = profile.bold_opener ? bodyH2.filter(s => !/^\*\*[^*]{10,}\*\*/.test(s.first)) : [];
if (noBold.length) issues.push(`Start each body section with one bold, declarative sentence stating its key finding (information block). Missing under: "${noBold.map(s => s.heading).slice(0, 5).join('", "')}"`);
// The story fragment after the question is a short phrase, not a sentence
const longFragments = profile.heading_style !== 'question_first' ? [] : bodyH2.map(s => s.heading.match(/\?\s+(.+)$/)?.[1] || '').filter(f => f.split(/\s+/).length > 7);

// Case studies switched off: flag client or place names from the project's case studies (capitalised, so
// they are names rather than ordinary words)
if (!settings.use_case_studies) {
  const tokens = new Set(brief.case_study_tokens || []);
  const names = [...new Set((text.match(/\b[A-Z][A-Za-z]{4,}\b/g) || []).filter(w => tokens.has(w.toLowerCase())))];
  if (names.length) issues.push(`This post must not use case studies, but it mentions case-study names: "${names.slice(0, 6).join('", "')}". Remove those examples or rewrite them as general, unnamed guidance.`);
}
if (longFragments.length) issues.push(`Heading story fragments must be short phrases of 2-7 words after the question (e.g. "The quote that didn't add up"), with no full stop. Shorten these, keeping each question as it is: "${longFragments.slice(0, 5).join('", "')}"`);

// Quotes: only real quotes from the knowledge base or the project's own published pages, never invented speech
const squash = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const kbText = squash(`${$('Knowledge Base').first().json.kb || ''} ${$('Own Evidence').first().json.evidence_text || ''}`);
const quotes = [...text.matchAll(/[“"‘]([^“”"‘’\n]{25,300})[”"’]/g)].map(m => m[1].trim());
const invented = quotes.filter(q => !kbText.includes(squash(q)));
if (invented.length) issues.push(`Quoted speech that is not in the knowledge base (invented quotes are not allowed). Rephrase it as narration. Found: "${invented.slice(0, 3).map(q => q.slice(0, 100)).join('", "')}"`);

// 5. Keywords: the primary keyword placed and in proportion, every supporting keyword used
// A keyword matches with small linking words in between ("solar installers in Bristol")
// Punctuation in the keyword is ignored ("How many solar panels do I need?"), and up to two
// linking words may sit between its words ("battery storage in the UK")
const kwRegex = k => new RegExp('\\b' + String(k).toLowerCase().replace(/[^\p{L}\p{N}\s'’&-]+/gu, ' ').trim().split(/\s+/).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\W+(?:(?:in|for|the|a|an|of|to|and|your|at|on)\\W+){0,2}') + '\\b', 'gu');
const countKw = (k, s) => (String(s).toLowerCase().match(kwRegex(k)) || []).length;
const word_count = (text.replace(/^#.*$/gm, ' ').match(/\S+/g) || []).length;
const primary = brief.primary_keyword;
const afterTldr = blog.replace(/^[\s\S]*?^## TL;DR\s*\n+[^\n]+\n+/m, '');
const opening = afterTldr.split(/\s+/).slice(0, 100).join(' ');
const h2s = [...blog.matchAll(/^## (.+)$/gm)].map(m => m[1]);
const missingSpots = [];
if (!countKw(primary, tldrPara)) missingSpots.push('the TL;DR');
if (!countKw(primary, opening)) missingSpots.push('the first 100 words of the opening');
if (!h2s.some(h => countKw(primary, h))) missingSpots.push('at least one H2');
if (missingSpots.length) issues.push(`The primary keyword "${primary}" is missing from ${missingSpots.join(', ')}. Work it in naturally.`);
// The opening answers the title; it never starts with a scene
if (/^\W*(?:picture|imagine|it's \d|it is \d|close your eyes)\b/i.test(opening)) issues.push(`The opening starts with a scene ("${opening.split(/\s+/).slice(0, 8).join(' ')}..."). Open with the direct answer to the title, using "${primary}", and keep any real detail as one supporting sentence after it.`);
// Frequency as uses per 1,000 words, so long keywords are not penalised (aim: about 3-8)
const primaryCount = countKw(primary, text);
const perThousand = word_count ? (primaryCount / word_count) * 1000 : 0;
if (perThousand < 2.5) issues.push(`The primary keyword "${primary}" appears only ${primaryCount} times in ${word_count} words. Use it naturally a few more times, aiming for about one use per 150-200 words.`);
if (perThousand > 10 && primaryCount > 4) issues.push(`The primary keyword "${primary}" appears ${primaryCount} times in ${word_count} words, which reads as stuffing. Replace some with natural variants, aiming for about one use per 150-200 words.`);
const missingSupporting = (brief.supporting_keywords || []).filter(k => !countKw(k, text));
if (missingSupporting.length) issues.push(`These supporting keywords never appear: "${missingSupporting.join('", "')}". Use each one at least once, naturally, in the section where it fits best.`);

// 6. Length against the target
const target = Number(brief.target_word_count) || 0;
if (target && word_count < target * 0.85) issues.push(`The post is ${word_count} words against a target of about ${target}. Add roughly ${target - word_count} words of story detail and practical substance (not filler) across the body sections.`);
if (target && word_count > target * 1.1) issues.push(`The post is ${word_count} words against a target of about ${target}. Trim roughly ${word_count - target} words: delete paragraphs that add no information first, then cut retold case-study narration and repeated points. Keep every fact, link, keyword and reader-question answer.`);

// The Doc shows the TL;DR as a separate box, so give the HTML step a body without it
const tldr = tldrPara.trim();
const blog_doc = blog.replace(/^## TL;DR\s*\n+[^\n]+\n*/m, 'TLDRBOXPLACEHOLDER\n\n');

// Body paragraphs (opening to closing, no headings, TL;DR or FAQs) for the gain auditor
const bodyMd = (faqStart < 0 ? afterTldr : afterTldr.slice(0, Math.max(0, afterTldr.search(/^## (FAQs|Frequently asked questions)/m)))) || afterTldr;
const paragraphs = bodyMd.split(/\n\s*\n/)
  .map(p => p.split('\n').filter(l => !/^#{1,6}\s/.test(l)).join(' ').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/\s+/g, ' ').trim())
  .filter(p => (p.match(/[a-z]/gi) || []).length > 20);

// 7. Readability: sentence rhythm and plain language across the body (tables left out).
// Flesch reading ease uses a simple syllable estimate; variety is the spread of sentence lengths.
const prose = paragraphs.filter(p => !p.startsWith('|'));
const sentences = prose.flatMap(p => p.replace(/\b(e\.g|i\.e|etc|approx|vs)\./gi, '$1').split(/(?<=[.!?])\s+(?=["“(]?[A-Z0-9\p{Sc}])/u))
  .map(s => s.trim()).filter(s => /[a-z]/i.test(s));
const wordsIn = s => (s.match(/[\p{L}\p{N}\p{Sc}'’-]+/gu) || []).length;
const lens = sentences.map(wordsIn).filter(n => n > 0);
const syllables = w => {
  w = w.toLowerCase().replace(/[^a-z]/g, '');
  if (w.length <= 3) return w ? 1 : 0;
  w = w.replace(/(?:[^laeiouy]es|[^laeiouy]ed|[^laeiouy]e)$/, '').replace(/^y/, '');
  return Math.max(1, (w.match(/[aeiouy]{1,2}/g) || []).length);
};
const proseWords = prose.join(' ').match(/[A-Za-z]+/g) || [];
const nSent = Math.max(1, lens.length);
const avgLen = lens.reduce((a, b) => a + b, 0) / nSent;
const flesch = Math.round(206.835 - 1.015 * avgLen - 84.6 * (proseWords.reduce((n, w) => n + syllables(w), 0) / Math.max(1, proseWords.length)));
const spread = Math.sqrt(lens.reduce((n, l) => n + (l - avgLen) ** 2, 0) / nSent);
const readability = {
  flesch,
  avg_sentence: Math.round(avgLen * 10) / 10,
  sentence_variety: Math.round(spread * 10) / 10,
  short_pct: Math.round((lens.filter(l => l <= 10).length / nSent) * 100),
  long_pct: Math.round((lens.filter(l => l > 30).length / nSent) * 100),
};
if (lens.length >= 15) {
  if (avgLen > 19) issues.push(`Readability: sentences average ${readability.avg_sentence} words (aim for 14-18). Split the longer sentences into two, keeping every fact, link and keyword.`);
  if (flesch < 55) issues.push(`Readability: the wording is heavy (Flesch reading ease ${flesch}; aim for 60+). Swap formal or abstract words for everyday ones and use contractions.`);
  if (readability.short_pct < 20) issues.push(`Readability: only ${readability.short_pct}% of sentences are short (10 words or fewer; aim for at least 25%). Add short, punchy sentences beside the longer ones so the rhythm varies like natural speech.`);
  if (spread < 6) issues.push(`Sentence rhythm is too even (lengths vary by only about ${readability.sentence_variety} words), which reads as machine-written. Mix short and long sentences and vary how they start.`);
  if (readability.long_pct > 10) issues.push(`${readability.long_pct}% of sentences run over 30 words. Break these up: "${sentences.filter(s => wordsIn(s) > 30).slice(0, 4).map(s => s.slice(0, 90) + '...').join('", "')}"`);
}

return [{
  json: {
    blog,
    blog_doc,
    tldr,
    paragraphs,
    readability,
    issues,
    fixes,
    has_issues: issues.length > 0,
    word_count,
    internal_links: internal.length,
    external_links: external.length,
  },
}];"""

CLEAN_EDITOR = r"""// Use the editor's version unless it came back broken or much shorter
const original = $('__QA_NODE__').first().json;
const edited = String($input.first().json.text || '').trim()
  .replace(/^```(?:markdown|md)?\s*\n/i, '')
  .replace(/\n```\s*$/, '')
  .trim();
const count = t => (t.replace(/\]\([^)]*\)/g, ']').match(/\S+/g) || []).length;
const ok = edited.startsWith('# ') && count(edited) >= count(original.blog) * 0.8;

return [{ json: { blog: ok ? edited : original.blog, editor_used: ok } }];"""

BUILD_DOC = r"""// Wrap the blog HTML with an SEO details table, then build a multipart request
// that Google Drive converts into a formatted Google Doc
const config = $('Config').first().json;
const site = $('Project').first().json;
const start = $('Start').first().json;
const brief = $('Brief').first().json;
const qa = $('Sign-off Result').first().json;
const meta = $('Meta Generator').first().json.output || {};
const gain = $('Verify Gain').first().json;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const slug = String(meta.slug || brief.final_title).toLowerCase()
  .replace(/^https?:\/\/[^/]+/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
// Meta description: tidy each of the model's options (no em dashes, no brand or quote prompt,
// capital first letter, closing full stop), then keep the best one: 140-155 characters,
// primary keyword in it, no brand name
const tidy = s => {
  let d = String(s || '').trim().replace(/\s*[—–]\s*/g, ', ').replace(/^["']|["']$/g, '');
  // A trailing sales sentence ("Request a quote from Northwind Solar.") is cut, not just flagged
  d = d.replace(/\s*(?:Request|Get|Ask for|Book)[^.!?]*(?:quote|callback|today)[^.!?]*[.!?]?\s*$/i, '').trim();
  if (d) d = d[0].toUpperCase() + d.slice(1);
  if (d && !/[.!?]$/.test(d)) d += '.';
  return d;
};
const brandRe = new RegExp(`\\b${site.brand_re}\\b`, 'i');
const kwPlain = String(brief.primary_keyword || '').toLowerCase().replace(/[^\p{L}\p{N}\s]+/gu, ' ').trim().split(/\s+/);
const hasKw = d => { const w = d.toLowerCase().replace(/[^\p{L}\p{N}\s]+/gu, ' '); return kwPlain.every(t => w.includes(t)); };
const descScore = d => (d.length >= 140 && d.length <= 155 ? 0 : 10 + Math.min(Math.abs(d.length - 148), 200))
  + (hasKw(d) ? 0 : 5) + (site.brand_check !== false && brandRe.test(d) ? 5 : 0);
const options = [...(meta.meta_descriptions || []), meta.meta_description].map(tidy).filter(Boolean);
let metaDescription = options.sort((a, b) => descScore(a) - descScore(b))[0] || '';
const descLen = metaDescription.length;
const descNotes = [
  ...(descLen < 140 || descLen > 155 ? [`CHECK: meta description is ${descLen} characters (aim for 140-155).`] : []),
  ...(metaDescription && !hasKw(metaDescription) ? [`CHECK: meta description does not use the primary keyword "${brief.primary_keyword}".`] : []),
];

const outlineNotes = $('Validate Outline').first().json.outline_notes || [];
// Nodes on a branch that did not run have no output, so read them carefully
const ran = (name, key) => { try { return $(name).first().json[key]; } catch (e) { return undefined; } };
const fixes = [...new Set(['QA Check', 'Recheck QA', 'Final QA', 'Sign-off QA'].flatMap(n => ran(n, 'fixes') || []))];
const surgical = ran('Clean Surgical Output', 'surgical_note');
const notes = [
  ...qa.issues.map(i => 'CHECK: ' + i),
  ...(surgical ? [surgical] : []),
  ...descNotes,
  ...outlineNotes,
  ...($('Reference Page').first().json.reference_note ? [$('Reference Page').first().json.reference_note] : []),
  ...(gain.gain_notes || []),
  ...fixes.map(f => 'Auto-fixed: ' + f),
];

// Information gain summary: the measured share and every first-hand point with its source
const used = new Set(qa.delta_used || []);
const deltaRows = (gain.delta_items || []).map(d => `${used.has(d.id) ? 'Used' : 'Not used'} | ${d.id} (${d.type}): ${d.finding} [${d.source_url}]`);

// JSON-LD for the CMS: Article plus FAQPage built from the post's FAQ section
const faqMd = (qa.blog.split(/^## (?:FAQs|Frequently asked questions)\s*$/m)[1] || '');
const faqs = [...faqMd.matchAll(/^### (.+)\n+([\s\S]*?)(?=\n### |\n## |$)/gm)]
  .map(m => ({ q: m[1].trim(), a: m[2].replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/[*_]/g, '').replace(/\s+/g, ' ').trim() }))
  .filter(f => f.q && f.a);
const jsonLd = [
  {
    '@context': 'https://schema.org', '@type': 'Article', headline: brief.final_title, description: metaDescription,
    inLanguage: 'en-GB', mainEntityOfPage: `${site.base}/${slug}`,
    author: site.author ? { '@type': 'Person', ...site.author } : { '@type': 'Organization', name: site.brand, url: site.home },
    publisher: { '@type': 'Organization', name: site.brand, url: site.home },
  },
  ...(faqs.length ? [{ '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: faqs.map(f => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })) }] : []),
];

const rows = [
  ['Project', `${site.brand} (${site.domain})`],
  ['Primary keyword', brief.primary_keyword],
  ['Supporting keywords', brief.keywords_csv],
  ['Slug', '/' + slug],
  ['Meta title', meta.meta_title],
  ['Meta description', `${metaDescription} (${descLen} characters)`],
  ['Category', meta.category],
  ['Word count', qa.word_count],
  ['Information gain', `${qa.gain_pct}% of the body is new, first-hand information (aim for 20-35%, with core search intent still covered)`],
  ['Format', $('Post Settings').first().json.format_label],
  ['Case studies', $('Post Settings').first().json.use_case_studies ? `Used (${site.brand} case studies as supporting examples)` : site.has_case_studies ? 'Not used (switched off by the SEO)' : 'Not used (this site has no case studies)'],
  ['Reference to outrank', (() => { const r = $('Reference Page').first().json; return !r.reference_url ? 'none' : r.has_reference ? `${r.reference_url} (read: about ${r.reference_words} words, ${r.reference_outline.length} headings)` : `${r.reference_url} (could not be read)`; })()],
  ['Readability', qa.readability ? `Flesch reading ease ${qa.readability.flesch} (aim 60+), average sentence ${qa.readability.avg_sentence} words, ${qa.readability.short_pct}% short sentences, ${qa.readability.long_pct}% over 30 words` : 'not measured'],
  ['Title focus', `${qa.focus_pct ?? 100}% of the body helps answer the title${(qa.unanswered_questions || []).length ? `; still weak on: ${qa.unanswered_questions.join('; ')}` : ''}`],
  ['Links', `${qa.internal_links} internal, ${qa.external_links} external`],
  ['Requested by', `${start.seo_name} on ${start.date}`],
  ['Approx. word count requested', start.word_count || 'not set (matched to what ranks)'],
  ['Special requirements', start.notes || 'none'],
];
const seoBlock = '<p><b>SEO details (delete before publishing)</b></p>'
  + `<table border="1" cellpadding="6">${rows.map(([k, v]) => `<tr><td><b>${esc(k)}</b></td><td>${esc(v)}</td></tr>`).join('')}</table>`
  + (deltaRows.length ? `<p><b>First-hand points (information gain) and their sources</b></p><ul>${deltaRows.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : '')
  + (notes.length ? `<p><b>Review notes</b></p><ul>${notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : '')
  + `<p><b>Structured data (paste into the page's JSON-LD / schema field)</b></p><p style="font-family:monospace;font-size:9pt">${esc(JSON.stringify(jsonLd))}</p>`
  + '<p>&nbsp;</p>';

// The TL;DR sits in its own shaded box under the H1, apart from the story
const tldrText = String(qa.tldr || '').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/[*_]/g, '');
const tldrBox = `<table border="1" cellpadding="14" width="100%" style="border-collapse:collapse;border:1px solid #c9d6e3"><tr><td style="background-color:#eef3f8">`
  + `<p><b>TL;DR</b></p><p>${esc(tldrText)}</p></td></tr></table><p>&nbsp;</p>`;
const bodyHtml = String($input.first().json.html || '')
  .replace(/<p>\s*TLDRBOXPLACEHOLDER\s*<\/p>/, tldrBox)
  .replace('TLDRBOXPLACEHOLDER', tldrBox);
const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body>${seoBlock}${bodyHtml}</body></html>`;

const boundary = 'blog_' + Date.now();
const metadata = { name: brief.final_title, mimeType: 'application/vnd.google-apps.document', parents: [config.docs_folder_id] };
const multipart_body = `--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(metadata)}\r\n`
  + `--${boundary}\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n${html}\r\n--${boundary}--`;

return [{
  json: {
    multipart_body,
    boundary,
    slug,
    meta_title: meta.meta_title || '',
    meta_description: metaDescription,
    word_count: qa.word_count,
    gain_pct: qa.gain_pct,
    notes: notes.join('\n'),
    status: qa.issues.length ? 'Done - check notes' : 'Done',
  },
}];"""

SURGICAL_CLEAN = r"""// Keep the surgical edit only if it really was surgical: most sentences of the audited post must
// come back word for word and the length must stay close; otherwise the audited post is kept
const original = String($('Final QA').first().json.blog || '');
const edited = String($input.first().json.text || '').trim()
  .replace(/^```(?:markdown|md)?\s*\n/i, '')
  .replace(/\n```\s*$/, '')
  .trim();
const sentencesOf = t => t.replace(/\]\([^)]*\)/g, ']').split(/(?<=[.!?])\s+|\n+/).map(s => s.trim()).filter(s => s.length > 20);
const count = t => (t.replace(/\]\([^)]*\)/g, ']').match(/\S+/g) || []).length;
const before = sentencesOf(original);
const after = new Set(sentencesOf(edited));
const kept = before.length ? before.filter(s => after.has(s)).length / before.length : 1;
const lengthRatio = count(edited) / Math.max(1, count(original));
const ok = edited.startsWith('# ') && kept >= 0.75 && lengthRatio >= 0.85 && lengthRatio <= 1.15;
const note = ok
  ? `Sign-off edit: surgical corrections made (${Math.round(kept * 100)}% of sentences unchanged)`
  : `Sign-off edit discarded: it changed too much (${Math.round(kept * 100)}% of sentences unchanged, length ${Math.round(lengthRatio * 100)}%), so the audited version was kept`;
return [{ json: { blog: ok ? edited : original, editor_used: ok, surgical_note: note } }];"""

SIGNOFF_RESULT = r"""// The post that is signed off: the sign-off audit when the surgical pass ran, otherwise the
// final audit (both carry the blog, its Doc version and the issues still open)
return $input.all();"""

# Brief (the H1) and QA (headings) share the Title Case helper
assert "const start = $('Start').first().json;\n" in BRIEF and "let blog = " in QA
BRIEF = BRIEF.replace("const start = $('Start').first().json;\n", "const start = $('Start').first().json;\n" + TITLE_CASE, 1)
QA = QA.replace("let blog = ", TITLE_CASE + "let blog = ", 1)
