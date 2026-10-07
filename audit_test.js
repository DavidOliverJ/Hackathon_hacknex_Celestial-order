const fs = require("fs");
const path = require("path");
const vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "audit.html"), "utf8");
const blocks = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)]
  .map(m => m[1]);
console.log("script blocks:", blocks.length);
if (blocks.length !== 2) { console.error("expected 2 inline script blocks"); process.exit(1); }

// syntax check both
blocks.forEach((b, i) => {
  try { new vm.Script(b, { filename: `block${i}.js` }); console.log(`block ${i}: syntax OK`); }
  catch (e) { console.error(`block ${i}: SYNTAX ERROR`, e.message); process.exit(1); }
});

// run engine (block 0) in a sandbox
const sandbox = { console, globalThis: {} };
vm.createContext(sandbox);
sandbox.globalThis = sandbox;
vm.runInContext(blocks[0], sandbox, { filename: "engine.js" });
const AQ = sandbox.AQ;
if (!AQ) { console.error("engine did not export AQ"); process.exit(1); }

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log("  ok  " + name); }
  else { fail++; console.log("  FAIL " + name + (extra !== undefined ? "  => " + JSON.stringify(extra) : "")); }
}

// ---- unit: parseNumber ----
check("int", AQ.parseNumber("42").v === 42);
check("neg", AQ.parseNumber("-45").v === -45);
check("comma group", AQ.parseNumber("1,234.50").v === 1234.5 && AQ.parseNumber("1,234.50").comma);
check("dollar", AQ.parseNumber("$980").v === 980 && AQ.parseNumber("$980").currency);
check("euro", AQ.parseNumber("€980").currency);
check("rupee", AQ.parseNumber("₹1,000").v === 1000);
check("bad text null", AQ.parseNumber("not-a-number") === null);
check("percent null", AQ.parseNumber("12%") === null);

// ---- unit: parseDateVal ----
check("iso", AQ.parseDateVal("2024-01-05").fmt === "iso");
check("slash dmy unambig", AQ.parseDateVal("25/03/2024").fmt === "dmy");
check("slash mdy unambig", AQ.parseDateVal("03/25/2024").fmt === "mdy");
check("slash ambiguous", AQ.parseDateVal("03/04/2024").fmt === "ambiguous");
check("text date", AQ.parseDateVal("Jan 5, 2024").fmt === "text");
check("not date", AQ.parseDateVal("hello") === null);

// ---- dataset: sales_transactions.csv ----
const sales = fs.readFileSync(path.join(__dirname, "data", "raw", "sales_transactions.csv"), "utf8");
const ps = AQ.parseDelimited(sales);
console.log("\nsales_transactions.csv:", ps.rows.length, "rows,", ps.headers.length, "cols, delim=" + JSON.stringify(ps.delimiter));
check("row count 5120", ps.rows.length === 5120, ps.rows.length);
check("8 columns", ps.headers.length === 8, ps.headers);

const rs = AQ.analyze(ps, "sales_transactions.csv");
console.log("score:", rs.score, "grade:", rs.grade, "counts:", JSON.stringify(rs.counts));
console.log("issues:");
rs.issues.forEach(i => console.log(`  [${i.sev}] (${i.cat}) ${i.title}  count=${i.count}`));
console.log("columns:");
rs.columns.forEach(c => console.log(`  ${c.name}: type=${c.type} missing=${c.missingPct}% unique=${c.unique} sample=${JSON.stringify(c.sample)}`));

const find = (pred) => rs.issues.find(pred);
const dup = find(i => i.cat === "duplicate" && i.sev === "critical");
check("duplicate rows detected ~120", dup && Math.abs(dup.count - 120) <= 1, dup && dup.count);
const missingAmt = find(i => i.column && /amount/i.test(i.column) && i.cat === "missing");
check("missing amounts ~74", missingAmt && Math.abs(missingAmt.count - 74) <= 1, missingAmt && missingAmt.count);
const missingReg = find(i => i.column && /region/i.test(i.column) && i.cat === "missing");
check("missing regions ~15", missingReg && Math.abs(missingReg.count - 15) <= 1, missingReg && missingReg.count);
const dateCol = rs.columns.find(c => c.type === "date");
check("a date column classified", !!dateCol, rs.columns.map(c => c.name + ":" + c.type));
const mixedFmt = find(i => i.cat === "format" && /date/i.test(i.title));
check("mixed date formats flagged", !!mixedFmt, mixedFmt && mixedFmt.title);
check("minority-only count on mixed dates", mixedFmt && mixedFmt.count < 5120, mixedFmt && mixedFmt.count);
const nonnum = find(i => i.cat === "wrong" && /non-numeric/i.test(i.title));
check("no false non-numeric (sales amounts are clean)", !nonnum, nonnum && nonnum.title);
const fkDup = find(i => i.column === "product_id" && i.cat === "duplicate");
check("FK columns not flagged as duplicate ids", !fkDup, fkDup && fkDup.title);
const pkDup = find(i => i.column === "order_id" && i.cat === "duplicate");
check("order_id duplicates still flagged", !!pkDup && pkDup.count === 120, pkDup && pkDup.count);
const neg = find(i => i.cat === "wrong" && /negative/i.test(i.title));
check("negative values flagged", !!neg, neg && neg.title);
check("digest builds", AQ.buildDigest(rs, 9000).length <= 9100);

// ---- dataset: products.csv ----
const prod = fs.readFileSync(path.join(__dirname, "data", "raw", "products.csv"), "utf8");
const pp = AQ.parseDelimited(prod);
const rp = AQ.analyze(pp, "products.csv");
console.log("\nproducts.csv:", pp.rows.length, "rows; score:", rp.score);
rp.issues.forEach(i => console.log(`  [${i.sev}] (${i.cat}) ${i.title}  count=${i.count}`));
const casing = rp.issues.find(i => i.cat === "inconsistent" && /spelled/i.test(i.title));
check("category casing flagged", !!casing, casing && casing.title);
const pmiss = rp.issues.filter(i => i.cat === "missing");
check("missing categories flagged", pmiss.length > 0, pmiss.length);

// ---- inline sample CSV (mimics the UI Load-example path) ----
const SAMPLE = `order_id,region,amount,currency,age,notes,signup_date
1,EMEA,"1,234.50",USD,34,ok,2024-01-05
2,emea,\u20ac980,USD,41, ok ,03/04/2024
3,EMEA,1200,USD,,missing,2024-02-11
3,EMEA,1200,USD,,missing,2024-02-11
4,APAC,-45,USD,250,n/a,2024-03-02
5,EMEA  ,800,EUR,37,"unknown",13/09/2024
6,North,not-a-number,USD,29,ok,2024-04-18
7,North,640,GBP,44,ok,2024-05-21
8,South,1500,USD,31,ok,2024-06-02
9,EMEA,1200,USD,38,,
10,APAC,2200,USD,36,ok,2024-07-14`;
const pi = AQ.parseDelimited(SAMPLE);
const ri = AQ.analyze(pi, "example.csv");
console.log("\nexample sample: score", ri.score, "issues", ri.issues.length);
ri.issues.forEach(i => console.log(`  [${i.sev}] (${i.cat}) ${i.title}  count=${i.count}`));
check("sample rows parsed", ri.rows === 11, ri.rows);
check("sample dup flagged", ri.issues.some(i => i.cat === "duplicate" && i.sev === "critical"));
check("sample missing age flagged", ri.issues.some(i => i.column === "age" && i.cat === "missing"));
check("sample bad email/neg age", ri.issues.some(i => i.column === "age" && i.cat === "wrong"));
check("sample mixed currency flagged", ri.issues.some(i => /currencies/i.test(i.title)));
check("sample whitespace flagged", ri.issues.some(i => /spaces/i.test(i.title) || /stray/i.test(i.title)));
check("sample casing flagged", ri.issues.some(i => i.cat === "inconsistent" && /spelled/i.test(i.title)));
check("sample ambiguous date flagged", ri.issues.some(i => /ambiguous/i.test(i.title)));
check("sample currency symbol flagged", ri.issues.some(i => /currency symbol/i.test(i.title)));

// thousands separators on a currency-free numeric column
const mini = `qty,label\n"1,234",a\n99,b\n2,500,c\n`;
const rm = AQ.analyze(AQ.parseDelimited(mini), "mini.csv");
check("thousands separators flagged", rm.issues.some(i => /thousands/i.test(i.title)),
  rm.issues.map(i => i.title));

// invalid emails
const em = AQ.parseDelimited(`email\nok@x.co\nnot-an-email\nfoo@bar\n`);
const re = AQ.analyze(em, "em.csv");
check("invalid emails flagged", re.issues.some(i => /invalid email/i.test(i.title)),
  re.issues.map(i => i.title));

// sequential index + mixed phone formats (customers-1000 style)
const cust = `Index,Customer Id,Phone\n1,UU001,"(309)296-7074x287"\n2,UU002,273.797.0373x2908\n3,UU003,605-809-2422\n4,UU004,693.610.6424x88410\n5,UU005,18004567890\n6,UU006,"+1 555 123 4567"\n7,UU007,555 1234\n8,UU008,"(555) 123-4567 x99"\n9,UU009,5552345678\n10,UU010,5553456789\n`;
const rc = AQ.analyze(AQ.parseDelimited(cust), "cust.csv");
check("sequential index flagged", rc.issues.some(i => /sequential row counter/i.test(i.title)),
  rc.issues.map(i => i.title));
check("mixed phone formats flagged", rc.issues.some(i =>
  /mixed phone formats/i.test(i.title) && i.column === "Phone"),
  rc.issues.map(i => i.title));
check("index stays an info, not critical", rc.issues.some(i =>
  /sequential row counter/i.test(i.title) && i.sev === "info"));

// numeric-looking column stored as text
const t = `name,age\nA,thirty\nB,twenty\nC,forty\nD,fifty\n`;
const rt = AQ.analyze(AQ.parseDelimited(t), "t.csv");
check("numeric-name column stored as text flagged",
  rt.issues.some(i => /looks numeric but is stored as text/i.test(i.title) && i.column === "age"),
  rt.issues.map(i => i.title));

// no regression: customers-style file must not false-flag firstname etc.
check("no numeric-name false positive on 'name'", !rt.issues.some(i => i.column === "name"));

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
