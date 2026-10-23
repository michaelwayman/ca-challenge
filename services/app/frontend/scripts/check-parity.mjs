// Two checks on the SCSS tree:
//  1. Parity: every rule in reference/theme.css (the compiled WP theme) has a
//     counterpart in the compiled SCSS that sets the same properties (values may
//     differ because spacing and type snap to the token scale).
//  2. Markup: every class used in the Django templates and in the React components
//     (src/**/*.tsx) is defined in the stylesheet.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

import postcss from 'postcss';
import * as sass from 'sass-embedded';

const { map, skip } = JSON.parse(readFileSync('scripts/parity-map.json', 'utf8'));
const compiledCss = sass.compile('scss/main.scss').css;

// Longhands count as their shorthand family: margin-top is covered by margin.
const FAMILIES = ['margin', 'padding', 'border', 'background', 'font'];
const family = (prop) => FAMILIES.find((f) => prop === f || prop.startsWith(`${f}-`)) ?? prop;

function collect(css) {
  const rules = new Map();
  postcss.parse(css).walkRules((rule) => {
    const context =
      rule.parent.type === 'atrule' ? `@${rule.parent.name} ${rule.parent.params} ` : '';
    const props = rule.nodes.filter((n) => n.type === 'decl').map((n) => n.prop);
    for (const selector of rule.selectors) {
      const key = context + selector.replace(/\s+/g, ' ').trim();
      rules.set(key, new Set([...(rules.get(key) ?? []), ...props]));
    }
  });
  return rules;
}

const reference = collect(readFileSync('reference/theme.css', 'utf8'));
const compiled = collect(compiledCss);
const problems = [];
let mapped = 0;

for (const [selector, props] of reference) {
  if (selector in skip) continue;
  const entry = map[selector];
  if (!entry) {
    problems.push(`unmapped reference rule: ${selector}`);
    continue;
  }
  const { to, alias = {} } = Array.isArray(entry) ? { to: entry } : entry;
  const available = new Set();
  for (const target of to) {
    const found = compiled.get(target);
    if (!found) problems.push(`${selector}: no compiled rule for ${target}`);
    for (const prop of found ?? []) available.add(family(prop));
  }
  for (const prop of props) {
    if (!available.has(family(alias[prop] ?? prop))) {
      problems.push(`${selector}: ${prop} is not set by ${to.join(' + ')}`);
    }
  }
  mapped += 1;
}

const definedClasses = new Set([...compiledCss.matchAll(/\.([a-z][\w-]*)/g)].map((m) => m[1]));
// The app's Django templates. Listed explicitly, not "the whole app directory": this
// folder lives inside it, and walking it would crawl node_modules.
const TEMPLATE_DIRS = ['../catalog/templates', '../templates'];
const templates = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (name.endsWith('.html')) templates.push(path);
  }
}

TEMPLATE_DIRS.forEach(walk);
// A wrong path must fail loudly: checking zero templates would pass vacuously.
if (templates.length === 0) problems.push(`no templates found under ${TEMPLATE_DIRS.join(', ')}`);
for (const path of templates) {
  for (const [, value] of readFileSync(path, 'utf8').matchAll(/class="([^"]*)"/g)) {
    for (const name of value
      .replace(/\{[{%].*?[}%]\}/g, ' ')
      .split(/\s+/)
      .filter(Boolean)) {
      if (!definedClasses.has(name)) problems.push(`${path}: class "${name}" has no CSS`);
    }
  }
}

// The React components: class names in className attributes, plus the state classes that
// components append as quoted fragments with a leading space (`trigger${active ? ' active' : ''}`).
const APPENDED = /^ [a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const sources = [];

function walkSources(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walkSources(path);
    else if (name.endsWith('.tsx') && !name.endsWith('.test.tsx')) sources.push(path);
  }
}

walkSources('src');
if (sources.length === 0) problems.push('no components found under src');
for (const path of sources) {
  const text = readFileSync(path, 'utf8');
  const names = new Set();
  const split = (value) =>
    value
      .replace(/\$\{[^}]*\}/g, ' ')
      .split(/\s+/)
      .filter(Boolean);
  for (const [, quoted, template] of text.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)) {
    split(quoted ?? template).forEach((name) => names.add(name));
  }
  for (const quote of ["'", '"']) {
    for (const [, value] of text.matchAll(new RegExp(`${quote}([^${quote}\\n]*)${quote}`, 'g'))) {
      if (APPENDED.test(value)) names.add(value.trim());
    }
  }
  for (const name of names) {
    // A trailing dash is a class built at runtime (star-${kind}).
    if (name.endsWith('-')) continue;
    if (!definedClasses.has(name)) problems.push(`${path}: class "${name}" has no CSS`);
  }
}

console.log(
  `${mapped} reference rules mapped, ${Object.keys(skip).length} intentionally skipped, ` +
    `${templates.length} templates and ${sources.length} components checked`,
);
if (problems.length) {
  console.error(problems.map((p) => `  ${p}`).join('\n'));
  process.exit(1);
}
console.log('parity and markup checks passed');
