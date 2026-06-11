// Client-safe company-size classification by employer name.
// Buckets are approximate global headcount; Educational is a kind, not a size.
// See docs/superpowers/specs/2026-06-10-company-size-filter-design.md.

export const SIZE_BUCKETS = [
  "Mega", // ~100k+ employees
  "Big", // ~10k–100k
  "Medium", // ~1k–10k
  "Small", // ~200–1k
  "Startup", // under ~200
  "Educational", // universities, colleges, schools, research institutes
  "Unknown",
] as const;

export type SizeBucket = (typeof SIZE_BUCKETS)[number];

// Legal/suffix tokens stripped from the end of a name, repeatedly.
const SUFFIXES = new Set([
  "inc", "incorporated", "llc", "llp", "lp", "corp", "corporation", "ltd",
  "limited", "plc", "gmbh", "co", "company", "holdings", "group",
  "technologies", "technology", "usa", "us", "america", "intl",
  "international",
]);

function normalize(name: string): string {
  let words = name
    .toLowerCase()
    .replace(/[.,'’"()]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ");
  if (words[0] === "the") words = words.slice(1);
  while (
    words.length > 1 &&
    (SUFFIXES.has(words[words.length - 1]) ||
      words[words.length - 1] === "&" ||
      words[words.length - 1] === "and")
  ) {
    words = words.slice(0, -1);
  }
  return words.join(" ");
}

const EDU_RE =
  /\buniversit|\b(college|school|academy|institute|polytechnic|cuny|suny)s?\b|\.edu\b/i;

// Curated map, keyed by normalized name. Weighted toward employers that
// show up in a US software job hunt. Headcounts are approximate; when a
// company sits on a boundary it gets the bucket it is best known as.
const KNOWN: Record<string, SizeBucket> = {
  // ── Mega (~100k+) ──────────────────────────────────────────────
  amazon: "Mega", "amazon com": "Mega", "amazon web services": "Mega",
  aws: "Mega", google: "Mega", alphabet: "Mega", microsoft: "Mega",
  apple: "Mega", meta: "Mega", facebook: "Mega", walmart: "Mega",
  "jpmorgan chase": "Mega", jpmorgan: "Mega", "jp morgan": "Mega",
  "jpmorganchase": "Mega", accenture: "Mega", ibm: "Mega", oracle: "Mega",
  intel: "Mega", samsung: "Mega", "samsung electronics": "Mega",
  "tata consultancy services": "Mega", tcs: "Mega", infosys: "Mega",
  wipro: "Mega", cognizant: "Mega", capgemini: "Mega", deloitte: "Mega",
  "ernst & young": "Mega", ey: "Mega", pwc: "Mega", kpmg: "Mega",
  "bank of america": "Mega", "wells fargo": "Mega", citi: "Mega",
  citigroup: "Mega", citibank: "Mega", hcltech: "Mega", hcl: "Mega",
  dell: "Mega", "hewlett packard enterprise": "Mega", comcast: "Mega",
  verizon: "Mega", "at&t": "Mega", att: "Mega", "t-mobile": "Mega",
  target: "Mega", costco: "Mega", "home depot": "Mega", boeing: "Mega",
  "lockheed martin": "Mega", rtx: "Mega", raytheon: "Mega",
  "general motors": "Mega", gm: "Mega", ford: "Mega",
  "ford motor": "Mega", tesla: "Mega", disney: "Mega",
  "walt disney": "Mega", sony: "Mega", siemens: "Mega",
  "johnson & johnson": "Mega",
  unitedhealth: "Mega", "unitedhealth group": "Mega", optum: "Mega",
  "cvs health": "Mega", cvs: "Mega", fedex: "Mega", ups: "Mega",
  "united parcel service": "Mega", bosch: "Mega", foxconn: "Mega",
  volkswagen: "Mega", toyota: "Mega", htc: "Mega", lg: "Mega",
  "berkshire hathaway": "Mega", anthem: "Mega", elevance: "Mega",
  "elevance health": "Mega", humana: "Mega", cigna: "Mega",
  aetna: "Mega", kaiser: "Mega", "kaiser permanente": "Mega",
  "charles schwab": "Mega",

  // ── Big (~10k–100k) ────────────────────────────────────────────
  nvidia: "Big", qualcomm: "Big", broadcom: "Big", amd: "Big",
  "advanced micro devices": "Big", micron: "Big",
  "texas instruments": "Big", "applied materials": "Big", asml: "Big",
  tsmc: "Big", "analog devices": "Big", arm: "Medium",
  cisco: "Big", "cisco systems": "Big", sap: "Big", salesforce: "Big",
  adobe: "Big", vmware: "Big", "palo alto networks": "Big",
  fortinet: "Big", akamai: "Big", netapp: "Big", "juniper networks": "Big",
  hp: "Big", lenovo: "Big", motorola: "Big", "motorola solutions": "Big",
  nokia: "Big", ericsson: "Big", netflix: "Big", uber: "Big",
  linkedin: "Big", paypal: "Big", ebay: "Big", intuit: "Big",
  servicenow: "Big", workday: "Big", atlassian: "Big", block: "Big",
  square: "Big", doordash: "Big", expedia: "Big", "expedia group": "Big",
  booking: "Big", "booking com": "Big", "booking holdings": "Big",
  "goldman sachs": "Big", "morgan stanley": "Big", barclays: "Big",
  ubs: "Big", "deutsche bank": "Big", hsbc: "Mega", "bny mellon": "Big",
  bny: "Big", "state street": "Big", visa: "Big", mastercard: "Big",
  "american express": "Big", amex: "Big", "capital one": "Big",
  discover: "Big", fidelity: "Big", "fidelity investments": "Big",
  vanguard: "Big", blackrock: "Big", bloomberg: "Big",
  "bloomberg lp": "Big", fis: "Big", fiserv: "Big", adp: "Big",
  paychex: "Big", "epic systems": "Big", epic: "Big", cerner: "Big",
  "electronic arts": "Big", ea: "Big", "activision blizzard": "Big",
  "take-two interactive": "Big", "take two interactive": "Big",
  ubisoft: "Big", nintendo: "Big", spacex: "Big", "northrop grumman": "Big",
  "general dynamics": "Big", "booz allen hamilton": "Big",
  "booz allen": "Big", leidos: "Big", caci: "Big", mitre: "Big",
  honeywell: "Big", ge: "Big", "ge aerospace": "Big", abb: "Big",
  philips: "Big", pfizer: "Big", merck: "Big", novartis: "Big",
  roche: "Big", astrazeneca: "Big", amgen: "Big", medtronic: "Big",
  "thermo fisher": "Big", "thermo fisher scientific": "Big",
  mckinsey: "Big", "mckinsey & company": "Big", bcg: "Big",
  "boston consulting": "Big", "boston consulting group": "Big",
  bain: "Big", "bain & company": "Big", gartner: "Big", nielsen: "Big",
  experian: "Big", equifax: "Big", transunion: "Big", moodys: "Big",
  "s&p global": "Big", "sp global": "Big", nasdaq: "Big", ice: "Big",
  "intercontinental exchange": "Big", cme: "Big", "cme group": "Big",
  zoom: "Big", "zoom video communications": "Big", autodesk: "Big",
  synopsys: "Big", cadence: "Big", "cadence design systems": "Big",
  ansys: "Big", mathworks: "Big", sas: "Big", "sas institute": "Big",
  teradata: "Big", informatica: "Big", "dell emc": "Big", nutanix: "Big",
  "check point": "Big", citrix: "Big", "verisk analytics": "Big",
  verisk: "Big", "walmart global tech": "Mega",
  "general electric": "Big",
  wayfair: "Big", chewy: "Big", "best buy": "Mega", lowes: "Mega",
  "lowe s": "Mega", macys: "Big", nordstrom: "Big", gap: "Big",
  nike: "Big", adidas: "Big", starbucks: "Mega", "mcdonald s": "Mega",
  mcdonalds: "Mega", pepsico: "Mega", "coca-cola": "Big",
  "coca cola": "Big", "procter & gamble": "Mega", "procter gamble": "Mega",
  unilever: "Big", nestle: "Mega", airbus: "Big", caterpillar: "Mega",
  "john deere": "Big", deere: "Big", "3m": "Big", dow: "Big",
  dupont: "Big", exxonmobil: "Big", chevron: "Big", shell: "Big",
  bp: "Big", schlumberger: "Mega", halliburton: "Big",
  "delta air lines": "Mega", delta: "Mega", "united airlines": "Mega",
  "american airlines": "Mega", southwest: "Big",
  "southwest airlines": "Big", marriott: "Mega", hilton: "Big",

  // ── Medium (~1k–10k) ───────────────────────────────────────────
  airbnb: "Medium", lyft: "Medium", snowflake: "Medium",
  databricks: "Medium", stripe: "Medium", shopify: "Medium",
  spotify: "Medium", twilio: "Medium", datadog: "Medium",
  mongodb: "Medium", cloudflare: "Medium", palantir: "Medium",
  snap: "Medium", "snap inc": "Medium", snapchat: "Medium",
  pinterest: "Medium", reddit: "Medium", dropbox: "Medium",
  coinbase: "Medium", robinhood: "Medium", instacart: "Medium",
  grubhub: "Medium", zillow: "Medium", "zillow group": "Medium",
  redfin: "Medium", yelp: "Medium", tripadvisor: "Medium",
  okta: "Medium", crowdstrike: "Medium", zscaler: "Medium",
  splunk: "Medium", elastic: "Medium", confluent: "Medium",
  hashicorp: "Medium", gitlab: "Medium", github: "Medium",
  unity: "Medium", roblox: "Medium", "epic games": "Medium",
  "riot games": "Medium", discord: "Medium", twitch: "Medium",
  duolingo: "Medium", coursera: "Medium", udemy: "Medium",
  chegg: "Medium", "2u": "Medium", squarespace: "Medium",
  wix: "Medium", godaddy: "Medium", hubspot: "Medium",
  zendesk: "Medium", asana: "Medium", monday: "Medium",
  "monday com": "Medium", smartsheet: "Medium", docusign: "Medium",
  box: "Medium", slack: "Medium", figma: "Medium", canva: "Medium",
  miro: "Medium", airtable: "Medium", affirm: "Medium",
  klarna: "Medium", chime: "Medium", plaid: "Medium", brex: "Medium",
  ramp: "Medium", marqeta: "Medium", "sofi": "Medium",
  betterment: "Medium", wealthfront: "Small", "carta": "Medium",
  gusto: "Medium", rippling: "Medium", deel: "Medium",
  "openai": "Medium", anthropic: "Medium", "x ai": "Medium",
  xai: "Medium", "scale ai": "Medium", scale: "Medium",
  "jane street": "Medium", "two sigma": "Medium", citadel: "Medium",
  "citadel securities": "Medium", "d e shaw": "Medium",
  "de shaw": "Medium", "the d e shaw group": "Medium",
  "hudson river trading": "Medium", "jump trading": "Medium",
  optiver: "Medium", imc: "Medium", "imc trading": "Medium",
  drw: "Medium", "akuna capital": "Medium", "virtu financial": "Medium",
  virtu: "Medium", "point72": "Medium", "millennium management": "Medium",
  millennium: "Medium", "tower research": "Medium",
  "tower research capital": "Medium", sig: "Medium",
  "susquehanna international group": "Medium", susquehanna: "Medium",
  "flow traders": "Medium", arista: "Medium", "arista networks": "Medium",
  "pure storage": "Medium", "cockroach labs": "Small", neo4j: "Small",
  redis: "Medium", grafana: "Medium", "grafana labs": "Medium",
  sentry: "Small", newrelic: "Medium", "new relic": "Medium",
  pagerduty: "Medium", fastly: "Medium", digitalocean: "Medium",
  heroku: "Medium", samsara: "Medium", verkada: "Medium",
  anduril: "Medium", "anduril industries": "Medium", flexport: "Medium",
  faire: "Medium", whatnot: "Medium", "etsy": "Medium",
  upwork: "Medium", fiverr: "Medium", toast: "Medium",
  "toast inc": "Medium", clover: "Medium", "olo": "Small",
  oscar: "Medium", "oscar health": "Medium", "ro": "Small",
  tempus: "Medium", "tempus ai": "Medium", "flatiron health": "Medium",
  komodo: "Small", "komodo health": "Small", benchling: "Small",
  "guardant health": "Medium", grammarly: "Medium", quora: "Small",
  glassdoor: "Medium", indeed: "Big", "zip recruiter": "Medium",
  ziprecruiter: "Medium", greenhouse: "Medium", lever: "Small",
  ashby: "Startup", workato: "Medium", zapier: "Small",
  webflow: "Small", framer: "Startup", contentful: "Small",
  algolia: "Small", "elastic path": "Small", bigcommerce: "Medium",
  klaviyo: "Medium", braze: "Medium", iterable: "Small",
  amplitude: "Medium", mixpanel: "Small", segment: "Small",
  heap: "Small", fullstory: "Small", "six flags": "Big",

  // ── Small (~200–1k) ────────────────────────────────────────────
  vercel: "Small", notion: "Small", "weights & biases": "Small",
  "weights biases": "Small", wandb: "Small", "hugging face": "Small",
  huggingface: "Small", retool: "Small", airbyte: "Small",
  dbt: "Small", "dbt labs": "Small", fivetran: "Small",
  astronomer: "Small", prefect: "Startup", dagster: "Startup",
  "dagster labs": "Startup", temporal: "Small",
  "temporal technologies": "Small", clickhouse: "Small",
  timescale: "Startup", planetscale: "Startup", neon: "Startup",
  turso: "Startup", "fly io": "Startup", render: "Startup",
  railway: "Startup", replit: "Small", cursor: "Startup",
  anysphere: "Startup", codeium: "Startup", windsurf: "Startup",
  sourcegraph: "Small", warp: "Startup", "browserbase": "Startup",
  posthog: "Startup", "plausible": "Startup", launchdarkly: "Small",
  statsig: "Startup", "linear b": "Startup", honeycomb: "Startup",
  "honeycomb io": "Startup", chronosphere: "Small", cribl: "Small",
  vanta: "Small", drata: "Small", snyk: "Medium", "1password": "Small",
  tailscale: "Startup", "ngrok": "Startup", kong: "Small",
  "kong inc": "Small", apollo: "Small", "apollo graphql": "Small",
  prisma: "Startup", clerk: "Startup", auth0: "Small",
  workos: "Startup", stytch: "Startup", "plain": "Startup",

  // ── Startup (<~200) ────────────────────────────────────────────
  "mistral ai": "Startup", mistral: "Startup", cohere: "Small",
  perplexity: "Small", "perplexity ai": "Small", "together ai": "Startup",
  together: "Startup", modal: "Startup", "modal labs": "Startup",
  replicate: "Startup", anyscale: "Startup", langchain: "Startup",
  llamaindex: "Startup", pinecone: "Startup", weaviate: "Startup",
  chroma: "Startup", zilliz: "Startup", "eleven labs": "Startup",
  elevenlabs: "Startup", runway: "Small", "runway ml": "Small",
  luma: "Startup", "luma ai": "Startup", pika: "Startup",
  suno: "Startup", "stability ai": "Startup", groq: "Startup",
  cerebras: "Small", sambanova: "Small", "sambanova systems": "Small",
  tenstorrent: "Small", etched: "Startup", "baseten": "Startup",
  fireworks: "Startup", "fireworks ai": "Startup", lambda: "Small",
  "lambda labs": "Small", coreweave: "Medium", "crusoe": "Small",
  "crusoe energy": "Small", supabase: "Startup", linear: "Startup",
  "linear app": "Startup", superhuman: "Startup", cron: "Startup",
  raycast: "Startup", "arc": "Startup", "browser company": "Startup",
  "the browser company": "Startup", granola: "Startup",
  "rewind ai": "Startup", limitless: "Startup", mem: "Startup",
  "glean": "Small", "harvey": "Startup", "harvey ai": "Startup",
  hebbia: "Startup", "sierra": "Startup", "sierra ai": "Startup",
  decagon: "Startup", "11x": "Startup", "cognition": "Startup",
  "cognition ai": "Startup", "cognition labs": "Startup",
  devin: "Startup", magic: "Startup", "magic ai": "Startup",
  poolside: "Startup", augment: "Startup", "augment code": "Startup",
  tabnine: "Startup", "sweep": "Startup", factory: "Startup",
  "factory ai": "Startup", reflection: "Startup",
  "reflection ai": "Startup", "world labs": "Startup",
  "physical intelligence": "Startup", skild: "Startup",
  "skild ai": "Startup", "figure": "Startup", "figure ai": "Startup",
  "1x": "Startup", "1x technologies": "Startup", apptronik: "Startup",

  // ── Educational / research (named entries; generic names are
  //    caught by the heuristic regex) ─────────────────────────────
  nyu: "Educational", "new york university": "Educational",
  mit: "Educational", caltech: "Educational", stanford: "Educational",
  harvard: "Educational", princeton: "Educational", yale: "Educational",
  columbia: "Educational", cornell: "Educational", "uc berkeley": "Educational",
  berkeley: "Educational", ucla: "Educational", usc: "Educational",
  "carnegie mellon": "Educational", cmu: "Educational",
  "georgia tech": "Educational", "virginia tech": "Educational",
  "texas a&m": "Educational", "texas a m": "Educational",
  oxford: "Educational", cambridge: "Educational",
  "eth zurich": "Educational", "allen institute": "Educational",
  "allen institute for ai": "Educational", ai2: "Educational",
  "broad institute": "Educational", "max planck": "Educational",
  "lawrence berkeley national laboratory": "Educational",
  "lawrence livermore national laboratory": "Educational",
  "oak ridge national laboratory": "Educational",
  "argonne national laboratory": "Educational",
  "los alamos national laboratory": "Educational",
  "jet propulsion laboratory": "Educational", jpl: "Educational",
  nasa: "Big", "national institutes of health": "Big", nih: "Big",
};

/** Classify a raw company name into a size bucket. Never throws. */
export function companySize(name: string): SizeBucket {
  if (!name || !name.trim()) return "Unknown";
  const key = normalize(name);
  const known = KNOWN[key];
  if (known) return known;
  if (EDU_RE.test(name)) return "Educational";
  return "Unknown";
}
