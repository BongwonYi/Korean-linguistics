"""사동·피동 판정과 논항 변화(주동문·능동문 되돌리기).

- 통사적: '-게 하다'(사동), '-어지다'·'-게 되다'(피동)
- 파생적: '-시키다'(사동), '-되다'·'-당하다'(피동), 접미사 -이-/-히-/-리-/-기-/-우-/-구-/-추-
  (derivations.json: 기초사전 '파생어' 관계. 사동인지 피동인지는 문장에서 고른 격틀과 기본형 격틀을 비교해 정함)

결과: {"type": 사동/피동, "form", "base_lemma", "base_pattern", "counterpart_label": 주동문/능동문,
       "counterpart": 되돌린 문장, "changes": [논항 변화 설명], "estimated", "note"}
"""
from __future__ import annotations

import json
from pathlib import Path

APP = Path(__file__).parent
_DERIV: dict | None = None
_ADJ: set | None = None
CAUSEE_CASES = ("에게", "한테", "께", "에")
AGENT_CASES = ("에게", "한테", "에게서", "에 의해", "에")
PUNCT_TAGS = ("SF", "SP", "SS", "SE", "SO", "SW")
TIME_WORDS = {"오늘", "어제", "내일", "모레", "아침", "점심", "저녁", "밤", "낮", "새벽", "오전", "오후", "주말",
              "때", "동안", "날", "해", "달", "봄", "여름", "가을", "겨울", "요즘", "지금", "올해", "작년", "내년"}


def load_derivations() -> dict:
    global _DERIV, _ADJ
    if _DERIV is None:
        p = APP / "derivations.json"
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        _DERIV, _ADJ = d.get("pairs", {}), set(d.get("adjectives", []))
    return _DERIV


def is_adjective(lemma: str) -> bool:
    load_derivations()
    return lemma in _ADJ


def _batchim(w: str) -> bool:
    c = w[-1] if w else ""
    return "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 != 0


def _ga(w: str) -> str:
    return w + ("이" if _batchim(w) else "가")


def _reul(w: str) -> str:
    return w + ("을" if _batchim(w) else "를")


def _clean(t: str) -> str:
    return t.strip('.,!?"\'')


def _np(e) -> str:
    """조사를 뗀 체언 부분('선생님께서' → '선생님')."""
    core = [x for x in e.morphs if x.tag not in PUNCT_TAGS]
    while core and core[-1].tag.startswith("J"):
        core.pop()
    return "".join(x.form for x in core)


def _req_roles(ent: dict) -> list[str]:
    return [s["role"] for s in ent["frame"] if s.get("required")]


def _case(e) -> str:
    if e.frame_arg:
        return e.frame_arg
    return "".join(x.form for x in e.particles if x.tag == "JKB")


def _lexical_bases(lemma: str, frames: dict) -> tuple[list[str], bool]:
    """파생 사동사·피동사의 기본형 후보와, 사전 대응표에서 왔는지 여부."""
    pairs = load_derivations()
    if lemma in pairs:
        return [b for b in pairs[lemma] if b in frames], True
    stem = lemma[:-1]
    if len(stem) >= 2 and stem[-1] in "히기":   # 사전에 없는 대응은 오분석이 적은 -히-/-기-만 추정
        base = stem[:-1] + "다"
        if base in frames:
            return [base], False
    return [], False


def _classify(E, a, frames):
    """(종류, 형식, 기본형, 추정 여부, 설명) 또는 None."""
    j, m, lemma = a["predicate"], a["main"], a.get("lemma") or ""
    main, last, stem = E[m], E[j], E[m].pred_stem
    if stem is None:
        return None
    # 통사적 사동·피동(본용언 + 보조 용언)
    if m != j and main.ending == "EC":
        aux = next((x for x in last.morphs if x.tag == "VX"), None)
        if aux is not None:
            if main.ending_form == "게" and aux.form == "하":
                return "사동", "통사적 사동(-게 하다)", lemma, False, ""
            if main.ending_form in ("어", "아", "여") and aux.form == "지" and stem.tag in ("VV", "XSV"):
                return "피동", "통사적 피동(-어지다)", lemma, False, ""
            if main.ending_form == "게" and aux.form == "되":
                return "피동", "통사적 피동(-게 되다)", lemma, False, "'-게 되다'를 피동으로 보지 않는 교재도 있음"
    # 접미사 '-시키다', '-되다', '-당하다'
    if lemma.endswith("시키다") and len(lemma) > 3:
        return "사동", "파생적 사동(-시키다)", lemma[:-3] + "하다", False, \
            "'-시키다'가 붙은 말을 사동사로 보지 않는 교재도 있음"
    for suf in ("당하다", "되다"):
        b = lemma[:-len(suf)] + "하다"
        if lemma.endswith(suf) and len(lemma) > len(suf) and b in frames and "목적어" in _req_roles(frames[b][0]):
            note = "'-되다'가 붙은 말을 피동사로 보지 않는 교재도 있음" if suf == "되다" else ""
            return "피동", f"파생적 피동(-{suf})", lemma[:-len(suf)] + "하다", False, note
    # 한 단어로 굳은 '-어지다'(찢어지다)
    if (lemma.endswith("지다") and len(lemma) >= 4 and lemma[-3] in "어아여" and (lemma[:-3] + "다") in frames
            and not is_adjective(lemma[:-3] + "다")):
        return "피동", "통사적 피동(-어지다)", lemma[:-3] + "다", False, "바른이 한 단어로 분석함"
    # 접미사 -이-/-히-/-리-/-기-/-우-/-구-/-추-
    if stem.tag != "VV" or not a.get("frame_found"):
        return None
    if m > 0 and E[m - 1].kind == "pred" and E[m - 1].head == m and E[m - 1].ending == "EC"             and E[m - 1].ending_form in ("어", "아", "여", "게"):
        return None   # '깨끗해 보이다'처럼 앞의 용언에 기대어 쓰인 경우
    bases, from_dict = _lexical_bases(lemma, frames)
    if not bases:
        return None
    droles = [s["role"] for s in a["slots"] if s.get("required")]
    # 기본형의 대표 격틀(가장 많이 쓰인 뜻, 격틀 사전의 첫 항목)과 비교한다
    bents = [(b, frames[b][0]) for b in bases]
    note = "기초사전 '파생어' 관계와 격틀 비교로 판정" if from_dict else "형태로 추정한 대응(사전에 파생어 관계가 없음)"
    if "목적어" not in droles:
        base = next((b for b, e in bents if "목적어" in _req_roles(e)), None)
        if base:
            return "피동", f"파생적 피동(-{lemma[-2]}-)", base, not from_dict, note
    else:
        base = next((b for b, e in bents if len(_req_roles(e)) < a["places"]), None)
        if base:
            # 같은 표제어에 목적어 없는 격틀(피동 뜻)도 있으면 '소매를 잡히다' 같은 목적어 있는 피동문일 수 있음
            both = any("목적어" not in _req_roles(e) for e in frames.get(lemma, []))
            if both:
                note += "; 목적어가 있는 피동문('경찰에게 소매를 잡혔다')일 수도 있음"
            return "사동", f"파생적 사동(-{lemma[-2]}-)", base, (not from_dict) or both, note
    return None


def voice_info(E: list, a: dict, frames: dict) -> dict | None:
    c = _classify(E, a, frames)
    if c is None:
        return None
    kind, form, base, estimated, note = c
    j, m = a["predicate"], a["main"]
    chain = range(m, j + 1)
    deps = [e for e in E if e.head in chain and e.idx not in chain]
    subj = next((e for e in deps if e.role == "주어"), None)
    objs = [e for e in deps if e.role == "목적어"]
    advs = [e for e in deps if e.role == "부사어"]
    changes: list[str] = []
    if kind == "사동":
        bfr = frames.get(base, [])
        base_has_obj = bool(bfr) and "목적어" in _req_roles(bfr[0])
        causee = next((e for e in advs if _case(e) in CAUSEE_CASES), None)
        if causee is None and objs and (not base_has_obj or len(objs) > 1):
            causee, objs = objs[0], objs[1:]       # '형이 동생을 울렸다': 목적어가 주동문의 주어
        if subj is not None:
            changes.append(f"주어 '{_np(subj)}': 새로 생긴 자리(시키는 이, 사동주)")
        if causee is not None:
            changes.append(f"주동문의 주어 '{_np(causee)}' → 사동문의 {causee.role} '{_clean(causee.text)}'")
        changes += [f"목적어 '{_np(o)}'{'은' if _batchim(_np(o)) else '는'} 그대로 목적어" for o in objs]
        parts = [_ga(_np(causee)) if causee is not None else "(누군가가)"] + [_reul(_np(o)) for o in objs]
        label = "주동문"
    else:
        agent = None
        for cs in AGENT_CASES:
            agent = next((e for e in advs if _case(e) == cs), None)
            if agent is not None:
                break
        if agent is not None and _case(agent) == "에" and (_np(agent) in TIME_WORDS or "되다" in form or "당하다" in form):
            agent = None   # '오후에', '사무실에'는 행위주가 아님
        if subj is not None:
            changes.append(f"능동문의 목적어 '{_np(subj)}' → 피동문의 주어 '{_clean(subj.text)}'")
        if agent is not None:
            noun_e = E[agent.idx - 1] if agent.frame_arg == "에 의해" else agent
            shown = (f"{_clean(noun_e.text)} {_clean(agent.text)}" if noun_e is not agent else _clean(agent.text))
            changes.append(f"능동문의 주어 '{_np(noun_e)}' → 피동문의 부사어 '{shown}'")
            who = _ga(_np(noun_e))
        else:
            changes.append("능동문의 주어(행위주)는 문장에 드러나지 않음")
            who = "(누군가가)"
        parts = [who] + ([_reul(_np(subj))] if subj is not None else [])
        label = "능동문"
    pattern = next((e.get("example", "") for e in frames.get(base, [])), "")
    return {"type": kind, "form": form, "base_lemma": base, "base_pattern": pattern,
            "counterpart_label": label, "counterpart": " ".join(parts + [base]) + ".",
            "changes": changes, "estimated": estimated, "note": note}
