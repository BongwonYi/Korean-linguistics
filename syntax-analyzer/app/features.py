"""서술어별 문법 요소(문장 종결, 높임, 시제·동작상, 부정)를 형태소로 판정한다.

판정 표는 endings.json(기본)과 endings_override.json(교사 판정, 있으면)에서 읽는다.
결과 항목: {"cat": 범주, "value": 값, "markers": [근거 형태], "note": 설명, "estimated": bool, "warn": bool}
"""
from __future__ import annotations

import json
from pathlib import Path

APP = Path(__file__).parent
_TABLE: dict | None = None

PAST_EP = {"었", "았", "였", "ㅆ"}
ADJ_STEMS = {"VA", "VCP", "VCN"}


def load_endings() -> dict:
    global _TABLE
    if _TABLE is None:
        t = json.loads((APP / "endings.json").read_text(encoding="utf-8"))
        over = APP / "endings_override.json"
        if over.exists():
            for k, v in json.loads(over.read_text(encoding="utf-8")).items():
                if isinstance(v, dict) and isinstance(t.get(k), dict):
                    t[k].update(v)
                else:
                    t[k] = v
        _TABLE = t
    return _TABLE


def _item(cat, value, markers=(), note="", estimated=False, warn=False):
    return {"cat": cat, "value": value, "markers": list(markers), "note": note,
            "estimated": estimated, "warn": warn}


def _eun(word: str) -> str:
    """받침에 맞는 보조사 '은/는'."""
    c = word[-1] if word else ""
    return "은" if "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else "는"


def _clean(text: str) -> str:
    return text.strip('.,!?"\'')


def predicate_features(E: list, j: int, m: int, lemma: str | None, final: bool, punct: str) -> list[dict]:
    """서술어(본용언 E[m] … 끝 어절 E[j])의 문법 요소.

    final: 문장을 끝맺는 서술어(종결 어미)인지. punct: 그 문장의 끝 문장 부호('?' 등).
    """
    T = load_endings()
    chain = range(m, j + 1)
    morphs = [x for k in chain for x in E[k].morphs]
    last = E[j]
    feats: list[dict] = []
    stem_tags = {x.tag for x in E[m].morphs}
    adj_like = bool(stem_tags & ADJ_STEMS) and "VV" not in stem_tags
    ef = next((x for x in reversed(last.morphs) if x.tag == "EF"), None)

    # 1) 문장 종결 표현과 상대 높임(종결 어미가 있는 서술어)
    if ef is not None:
        row = T["EF"].get(ef.form)
        if row:
            types = row["type"]
            est = len(types) > 1
            if "의문" in types and punct == "?":
                typ, est = "의문", False
            elif ef.form == "라" and "VCP" in stem_tags:
                typ, est = "평서", False
            else:
                typ = types[0]
            note = row.get("note", "")
            if est:
                note = (note + "; " if note else "") + f"'-{ef.form}'{_eun(ef.form)} {'·'.join(types)}에 두루 쓰여 억양과 문맥으로 정함"
            if not final:
                note = (note + "; " if note else "") + "인용된 문장의 종결 표현"
            feats.append(_item("문장 종결", f"{typ}문", [f"-{ef.form}"], note, est))
            lv = row.get("level")
            if lv:
                feats.append(_item("상대 높임", lv, [f"-{ef.form}"], T["levels"].get(lv, "")))
        else:
            feats.append(_item("문장 종결", "?", [f"-{ef.form}"], "어미 표에 없는 종결 어미", True))

    # 2) 시제(명령문·청유문은 시제를 나타내지 않음)
    if feats and feats[0]["value"] in ("명령문", "청유문") and not feats[0]["estimated"]:
        return feats + _rest(E, j, m, lemma, T, chain, morphs)
    eps = [x.form for x in last.morphs if x.tag == "EP"]
    etm = next((x for x in reversed(last.morphs) if x.tag == "ETM"), None)
    past = [f for f in eps if f in PAST_EP]
    rel = "" if ef is not None else "상대 시제: 안은 문장(또는 뒤 절) 서술어의 시점을 기준으로 함"
    if etm is not None and etm.form in T["ETM"]:
        row = T["ETM"][etm.form]
        tense = row["tense"]
        mk = [f"-{etm.form}"]
        if past:
            tense, mk = "과거", [f"-{past[0]}-"] + mk
        elif adj_like and "tense_adj" in row:
            tense = row["tense_adj"]
        note = "; ".join(x for x in (row.get("note", ""), "관형사형 어미로 나타냄", rel) if x)
        feats.append(_item("시제", tense, mk, note))
    elif past or "겠" in eps or "더" in eps or (ef is not None and ef.form.startswith("더")):
        if len(past) >= 2:
            tense, mk, note = "과거", [f"-{past[0]}{past[1]}-"], "대과거(과거보다 앞선 일이나 단절된 과거)"
        elif past:
            tense, mk, note = "과거", [f"-{past[0]}-"], ""
        elif "더" in eps or (ef is not None and ef.form.startswith("더")):
            tense, mk, note = "과거", ["-더-"], T["EP"]["더"]["note"]
        else:
            tense, mk, note = "미래", ["-겠-"], T["EP"]["겠"]["note"]
        if "겠" in eps and past:
            mk.append("-겠-")
            note = "과거의 일을 추측함"
        note = "; ".join(x for x in (note, rel) if x)
        feats.append(_item("시제", tense, mk, note))
    elif ef is not None:
        mk = [f"-{ef.form}"] if ef.form in ("ㄴ다", "는다") else []
        feats.append(_item("시제", "현재", mk, "과거·미래를 나타내는 선어말 어미가 없음"))

    return feats + _rest(E, j, m, lemma, T, chain, morphs)


def _rest(E, j, m, lemma, T, chain, morphs) -> list[dict]:
    """동작상, 주체·객체 높임, 부정."""
    feats: list[dict] = []
    # 3) 동작상(본용언 + 보조 용언)
    for k in range(m, j):
        a, b = E[k], E[k + 1]
        aux = next((x for x in b.morphs if x.tag == "VX"), None)
        if a.ending == "EC" and aux is not None:
            key = f"{a.ending_form}+{aux.form}"
            if key in T["aspect"]:
                feats.append(_item("동작상", T["aspect"][key], [f"-{a.ending_form} {aux.form}다"]))

    # 4) 주체 높임: 서술어의 '-시-'와 주어의 '께서'·'-님'
    subj = [e for e in E if e.role == "주어" and e.head in chain]
    shi = [x for x in morphs if x.tag == "EP" and x.form in ("시", "으시")]
    lex = lemma in T["subject_honor_verbs"]
    s_mk = []
    for e in subj:
        for x in e.morphs:
            if x.tag == "JKS" and x.form == "께서":
                s_mk.append("께서")
            elif x.tag == "XSN" and x.form == "님":
                s_mk.append("-님")
    if shi or lex:
        mk = (["-시-"] if shi else []) + ([f"{lemma}(높임 어휘)"] if lex else []) + s_mk
        warn = [e for e in subj if any(x.tag == "NP" and x.form in T["humble_pronouns"] for x in e.morphs)]
        note = "서술어의 주체(주어)를 높임"
        if warn:
            note = f"주어 '{_clean(warn[0].text)}'는 말하는 이 자신이라 주체 높임과 어울리지 않음(높임 표현 확인)"
        feats.append(_item("주체 높임", "높임", mk, note, warn=bool(warn)))
    elif "께서" in s_mk:
        feats.append(_item("주체 높임", "확인 필요", s_mk,
                           "주어에 '께서'가 쓰였지만 서술어에 '-시-'가 없음(높임 표현 확인)", warn=True))

    # 5) 객체 높임: 부사어 '께', 높임 어휘(드리다·여쭙다·뵙다·모시다)
    args = [e for e in E if e.head in chain and e.idx not in chain]
    kke = [f"{_clean(e.text)}(께)" for e in args if any(x.tag == "JKB" and x.form == "께" for x in e.morphs)]
    olex = lemma in T["object_honor_verbs"]
    if kke or olex:
        mk = kke + ([f"{lemma}(높임 어휘)"] if olex else [])
        feats.append(_item("객체 높임", "높임", mk, "서술어의 객체(목적어나 부사어가 가리키는 대상)를 높임"))

    # 6) 부정
    N = T["negation"]
    for e in E:
        if e.kind == "adverb" and e.head in chain and _clean(e.text) in N["adverbs"]:
            w = _clean(e.text)
            feats.append(_item("부정", f"짧은 부정({w})", [w], N["adverbs"][w]))
    for k in range(m + 1, j + 1):
        aux = next((x for x in E[k].morphs if x.tag == "VX"), None)
        prev = E[k - 1]
        if aux is not None and aux.form in N["aux"] and prev.ending_form == "지":
            feats.append(_item("부정", f"긴 부정(-지 {aux.form}다)", [f"-지 {aux.form}다"], N["aux"][aux.form]))
    if lemma in N["lexical"] and E[m].ending != "ADV_DERIV":
        feats.append(_item("부정", "어휘적 부정", [lemma], N["lexical"][lemma], estimated=True))
    return feats
