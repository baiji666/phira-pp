/**
 * Verify the standalone build by running its own JS (API + PP math) headlessly
 * in Node and printing the same numbers the page would show.  The result is then
 * compared against the Python CLI (`scripts/pp.py best <id> -n 100`).
 *
 *   node scripts/verify_standalone.mjs 459003
 */
import fs from "node:fs";
import vm from "node:vm";

const uid = Number(process.argv[2] || 459003);
const html = fs.readFileSync("PhiraPP.html", "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  + "\nglobalThis.__t = { DIFF, performancePP, getCharts, playerChart, pool, "
  + "resolveDifficulty, osuTotal, pickBest, bestRow, P };\n";

const fakeEl = () => ({ value: "", innerHTML: "", disabled: false, addEventListener() {} });
const ctx = {
  console, URL, fetch, Math, Number, Array, Object, JSON, Promise, String,
  RegExp, Error, isNaN, parseInt, parseFloat, setTimeout, clearTimeout,
  document: { querySelector: fakeEl },
  localStorage: { getItem: () => null, setItem() {} },
};
vm.createContext(ctx);
vm.runInContext(script, ctx);
const T = ctx.__t;

const kvCount = Object.keys(T.DIFF).length;
console.log("community 定数 embedded charts:", kvCount);

const t0 = Date.now();
const ids = Object.keys(T.DIFF).map(Number);
const metaMap = await T.getCharts(ids);
console.log("charts meta:", metaMap.size);

let player = null;
try { player = await (await fetch("https://phira.5wyxi.com/user/" + uid)).json(); } catch (e) {}

const recs = await T.pool(ids, 12, (cid) => T.playerChart(uid, cid));

const items = [];
let failed = 0;
recs.forEach((rows, idx) => {
  if (rows && rows.__error) { failed++; return; }
  if (!rows || !rows.length) return;
  const cid = ids[idx];
  const [diff, src] = T.resolveDifficulty(cid, metaMap.get(cid) || null);
  const r = T.bestRow(rows, diff);
  if (!r) return;
  const b = diff ? T.performancePP(diff, r) : null;
  items.push({ cid, rec: r, diff, src, pp: b ? b.pp : 0 });
});
items.sort((a, b) => b.pp - a.pp);
const top = items.slice(0, 100);
const total = T.osuTotal(top.map((x) => x.pp));

console.log(`player: ${player && player.name} (id=${uid})`);
console.log(`scanned=${ids.length} played=${items.length} failed=${failed}`);
console.log(`elapsed=${((Date.now() - t0) / 1000).toFixed(1)}s`);
console.log(`TOTAL_PP(top100) = ${total.toFixed(1)}`);
console.log("top 8:");
top.slice(0, 8).forEach((x, i) => {
  const m = metaMap.get(x.cid) || {};
  console.log(`  ${String(i + 1).padStart(2)} ${x.pp.toFixed(1).padStart(7)} ` +
    `${String(x.diff).padStart(5)} ${(Number(x.rec.accuracy) * 100).toFixed(2).padStart(7)}% ` +
    `#${x.cid} ${m.name || ""}`);
});
