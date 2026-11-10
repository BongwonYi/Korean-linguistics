"""픽스처 문장의 분석 결과를 사람이 읽기 쉽게 출력한다: python -m tools.show"""
import glob
import json
import sys

from app.grammar import analyze_response

files = sys.argv[1:] or sorted(glob.glob("tests/fixtures/s*.json"))
for f in files:
    r = analyze_response(json.load(open(f, encoding="utf-8")))
    for s in r["sentences"]:
        E = s["eojeols"]
        print("■", s["text"], "→", s["sentence_kind"], s["structure"])
        parts = []
        for e in E:
            if not e["role"]:
                continue
            h = e["head"]
            ht = "ROOT" if h is None or h < 0 else E[h]["text"]
            star = "*" if e["estimated"] else ""
            note = f"({e['role_note']})" if e["role_note"] else ""
            parts.append(f"{e['text']}:{e['role']}{star}{note}→{ht}")
        print("    " + " | ".join(parts))
        for c in s["clauses"]:
            print("    [", c["group"], c["type"], "]", c["text"], "/", c["note"])
