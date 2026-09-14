"""Derive the AAMAS gold-set reader workflow from the reference-set D script:
same protocol, different directory and item counts."""
import io
import sys

WF = "C:/Users/Admin/.claude/projects/d--holy-grail/a1a1b1ca-754a-4ce1-a848-2c094c364924/workflows/scripts/"
s = io.open(WF + "gold-d-vlm-read-wf_c4db79ae-fa2.js", encoding="utf-8").read()
reps = [
    ("name: 'gold-d-vlm-read'", "name: 'aamas-gold-read'"),
    ("description: 'Read the 180 rendered reference-set D items blind, five per agent, under the Appendix D protocol'",
     "description: 'Read the rendered AAMAS reference-set items blind, five per agent, under the released protocol'"),
    ("phases: [{ title: 'Read', detail: '36 agents, five items each' }],",
     "phases: [{ title: 'Read', detail: 'five items per agent' }],"),
    ("""const items = []
for (let i = 1; i <= 180; i++) {
  const id = String(i).padStart(3, '0')
  items.push({ id, stratum: i <= 100 ? 'testable' : i <= 140 ? 'no_bar' : 'no_n' })
}""", """const N_T = args && args.testable ? args.testable : 100
const N_B = args && args.no_bar ? args.no_bar : 40
const N_N = args && args.no_n ? args.no_n : 0
const items = []
for (let i = 1; i <= N_T + N_B + N_N; i++) {
  const id = String(i).padStart(3, '0')
  items.push({ id, stratum: i <= N_T ? 'testable' : i <= N_T + N_B ? 'no_bar' : 'no_n' })
}"""),
    ("audits/gold_d/items.json", "audits/aamas_gold/items.json"),
    ("log(`${rows.length} rows read of 180`)", "log(`${rows.length} rows read of ${items.length}`)"),
]
for a, b in reps:
    assert a in s, a[:50]
    s = s.replace(a, b)
s = s.replace("gold_d", "aamas_gold")
assert "gold_d" not in s
io.open(WF + "aamas-gold-read.js", "w", encoding="utf-8").write(s)
print("ok", s.count("aamas_gold"))
