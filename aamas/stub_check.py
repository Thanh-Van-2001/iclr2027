"""List macros main.tex uses that numbers.tex does not define; write a stub
file defining them as '??' so a draft can be compiled before every run record
exists. The real build never includes the stub."""
import io
import re
import sys

d = sys.argv[1] if len(sys.argv) > 1 else "paper/aamas"
main = io.open(f"{d}/main.tex", encoding="utf-8").read()
nums = io.open(f"{d}/numbers.tex", encoding="utf-8").read()
used = set(re.findall(r"\\n([A-Z][A-Za-z]+)\{\}", main))
defined = set(re.findall(r"\\newcommand\{\\n([A-Za-z]+)\}", nums))
missing = sorted(used - defined)
print(len(used), "used;", len(missing), "missing:", missing)
io.open(f"{d}/numbers_stub.tex", "w", encoding="utf-8").write(
    "".join("\\newcommand{\\n%s}{??}\n" % m for m in missing))
t = main.replace("\\input{numbers}", "\\input{numbers}\n\\input{numbers_stub}", 1)
io.open(f"{d}/main_test.tex", "w", encoding="utf-8").write(t)
