"""바른 형태소 분석 결과를 바탕으로 학교문법의 문장 성분과 문장 구조를 판정하는 규칙 엔진.

설계 원칙
- 같은 입력에는 항상 같은 결과가 나온다(규칙 기반).
- 모든 판정에 근거(reason)를 붙여 학생이 '왜 그렇게 판정했는지' 볼 수 있게 한다.
- 형태 정보만으로 확정할 수 없는 경우(조사 생략, 보조사 결합 등)는 '추정'으로 표시한다.
- 의존 관계(head)는 학교문법 분석을 돕기 위한 참고 정보다.

입력: 바른 AnalyzeSyntax 응답(JSON, dict)
출력: analyze_response() 가 돌려주는 dict (README의 '출력 형식' 참고)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tags import ENDINGS, MODIFIERS, NOMINAL, PRED_STEM, PUNCT, SCHOOL_POS, TAG_NAMES

# ---------------------------------------------------------------------------
# 어미·조사 목록
# ---------------------------------------------------------------------------

# 대등적 연결 어미
COORD_EC = {"고", "며", "으며", "지만", "나", "으나", "거나", "든지", "든가", "고도"}
# 부사절을 만드는 어미(학교문법에서 부사형 전성 어미로 다루는 것)
ADV_EC = {"게", "도록", "듯이", "듯", "게끔"}
# '없이, 같이, 달리'처럼 부사절의 서술어로 보는 파생 부사
ADV_DERIV = {"없이", "같이", "달리"}
# 조사 없이 부사어로 쓰이는 시간 명사
TIME_NOUNS = {"오늘", "내일", "모레", "글피", "지금", "요즘", "아까", "이제", "올해",
              "작년", "내년", "올봄", "올여름", "올가을", "올겨울", "방금", "어젯밤", "오늘밤"}
TOPIC_JX = {"은", "는", "ㄴ"}

CASE_ROLE = {
    "JKS": "주어", "JKC": "보어", "JKO": "목적어", "JKG": "관형어",
    "JKB": "부사어", "JKV": "독립어", "JKQ": "부사어",
}
SINGLE_SLOTS = {"주어", "보어", "목적어"}


@dataclass
class Morph:
    form: str
    tag: str


@dataclass
class Eojeol:
    idx: int
    text: str
    morphs: list[Morph]
    kind: str = "other"           # pred / nominal / adverb / conj_adverb / modifier / interj / punct
    ending: str | None = None     # pred: EF / EC / ETM / ETN / ADV_DERIV / NONE
    ending_form: str = ""         # pred: 마지막 어미의 형태
    quoted: bool = False          # 인용격 조사(JKQ)가 붙은 서술어
    particles: list[Morph] = field(default_factory=list)  # 끝에 붙은 조사들
    pred_stem: Morph | None = None

    # 분석 결과
    head: int | None = None
    role: str = ""
    role_note: str = ""
    dep_label: str = ""
    reason: str = ""
    estimated: bool = False
    aux_main: bool = False        # 보조 용언 앞의 본용언
    pk: str = ""                  # 서술어 종류: main / conn / emb


def _core(morphs: list[Morph]) -> list[Morph]:
    return [m for m in morphs if m.tag not in PUNCT]


def classify(e: Eojeol) -> None:
    """어절 하나를 형태 정보로 분류한다."""
    core = _core(e.morphs)
    if not core:
        e.kind = "punct"
        return
    tags = [m.tag for m in core]

    # 서술어(용언 어간 또는 '이다')가 있는가
    stem_positions = [i for i, t in enumerate(tags) if t in PRED_STEM]
    if stem_positions:
        last = stem_positions[-1]
        e.kind = "pred"
        e.pred_stem = core[last]
        after = core[last + 1:]
        ends = [m for m in after if m.tag in ENDINGS]
        e.particles = [m for m in after if m.tag.startswith("J")]
        etags = [m.tag for m in ends]
        if "ETN" in etags:
            e.ending = "ETN"
            e.ending_form = next(m.form for m in ends if m.tag == "ETN")
        elif "ETM" in etags:
            e.ending = "ETM"
            e.ending_form = next(m.form for m in ends if m.tag == "ETM")
        elif "EF" in etags:
            e.ending = "EF"
            e.ending_form = [m.form for m in ends if m.tag == "EF"][-1]
        elif "EC" in etags:
            e.ending = "EC"
            e.ending_form = [m.form for m in ends if m.tag == "EC"][-1]
        else:
            e.ending = "NONE"
        e.quoted = any(m.tag == "JKQ" for m in e.particles)
        return

    first = core[0]
    if first.tag == "IC":
        e.kind = "interj"
    elif first.tag == "MAJ":
        e.kind = "conj_adverb"
    elif first.tag == "MAG":
        if first.form in ADV_DERIV:
            e.kind = "pred"
            e.ending = "ADV_DERIV"
            e.ending_form = first.form
            e.pred_stem = first
        else:
            e.kind = "adverb"
    elif first.tag in MODIFIERS and len(core) == 1:
        e.kind = "modifier"
    elif any(t in NOMINAL for t in tags):
        e.kind = "nominal"
        # 끝에서부터 연속된 조사
        parts: list[Morph] = []
        for m in reversed(core):
            if m.tag.startswith("J"):
                parts.insert(0, m)
            else:
                break
        e.particles = parts
    else:
        e.kind = "other"


def _case_tag(e: Eojeol) -> str | None:
    for m in e.particles:
        if m.tag.startswith("JK"):
            return m.tag
    return None


def _jx(e: Eojeol) -> Morph | None:
    for m in e.particles:
        if m.tag == "JX":
            return m
    return None


def _jc(e: Eojeol) -> bool:
    return bool(e.particles) and all(m.tag in ("JC",) for m in e.particles)


def _particle_str(e: Eojeol, tag: str) -> str:
    return "".join(m.form for m in e.particles if m.tag == tag)


def _stem_desc(e: Eojeol) -> str:
    s = e.pred_stem
    return f"'{s.form}'({TAG_NAMES.get(s.tag, s.tag)})" if s else ""


# ---------------------------------------------------------------------------
# 문장 분석
# ---------------------------------------------------------------------------

def analyze_sentence(sent: dict) -> dict:
    tokens = sent.get("tokens", [])
    E: list[Eojeol] = []
    for i, tok in enumerate(tokens):
        morphs = [Morph(m["text"]["content"], m["tag"]) for m in tok.get("morphemes", [])]
        e = Eojeol(i, tok["text"]["content"], morphs)
        classify(e)
        E.append(e)

    n = len(E)
    notes: list[str] = []
    real = [e for e in E if e.kind != "punct"]
    if not real:
        return _pack(sent, E, [], "분석할 어절이 없습니다", [], notes)

    # 1) 본용언 + 보조 용언 묶기 ('가 버렸다', '포기하지 않았다')
    for e in E:
        if e.kind == "pred" and e.ending == "EC" and e.idx + 1 < n:
            nxt = E[e.idx + 1]
            nc = _core(nxt.morphs)
            if nxt.kind == "pred" and nc and nc[0].tag == "VX":
                e.aux_main = True
                e.head = nxt.idx
                e.role = "서술어"
                e.role_note = "본용언"
                e.dep_label = "보조 용언에 연결"
                e.reason = (f"연결 어미 '-{e.ending_form}' 뒤에 보조 용언 '{nc[0].form}-'이 이어지므로 "
                            f"'{e.text} {nxt.text}' 전체가 하나의 서술어(본용언 + 보조 용언)입니다.")

    # 2) 서술어 종류
    for e in E:
        if e.kind != "pred" or e.aux_main:
            continue
        if e.ending == "EF":
            e.pk = "emb" if e.quoted else "main"
        elif e.ending in ("ETM", "ETN", "ADV_DERIV"):
            e.pk = "emb"
        elif e.ending == "EC" and e.ending_form in ADV_EC:
            e.pk = "emb"
        else:
            e.pk = "conn"
    cands = [e.idx for e in E if e.kind == "pred" and not e.aux_main]

    mains = [j for j in cands if E[j].pk == "main"]
    if mains:
        root = mains[-1]
    elif cands:
        root = cands[-1]
    else:
        root = real[-1].idx
    R = E[root]
    R.head = -1
    R.dep_label = "뿌리(문장 전체의 서술어)"
    if R.kind == "pred":
        R.role = "서술어"
        if R.pred_stem and R.pred_stem.tag == "VCP":
            R.reason = (f"체언에 서술격 조사 '이다'(바른 태그 VCP)가 붙고 종결 어미 '-{R.ending_form}'로 "
                        f"문장이 끝나므로 문장 전체의 서술어입니다.")
        elif R.ending == "EF":
            R.reason = f"용언 {_stem_desc(R)}에 종결 어미 '-{R.ending_form}'가 붙어 문장을 끝맺으므로 문장 전체의 서술어입니다."
        else:
            R.reason = "문장 끝에 오는 용언이므로 문장 전체의 서술어로 보았습니다."
    for j in mains[:-1]:
        E[j].pk = "conn"  # 한 문장에 종결형이 둘 이상이면 앞의 것을 이어진 절처럼 처리

    filled: dict[int, set[str]] = {j: set() for j in cands}

    def next_nominal(i: int) -> int | None:
        for k in range(i + 1, n):
            if E[k].kind == "nominal":
                return k
            if E[k].kind == "pred" and E[k].ending in ("ETN",):
                return k
        return None

    def next_pred(i: int, skip_emb: bool = False) -> int | None:
        for j in cands:
            if j > i and not (skip_emb and E[j].pk == "emb"):
                return j
        return None

    def choose_head(i: int, slot: str, topic: bool = False) -> tuple[int, bool]:
        """논항 i가 연결될 서술어를 고른다. (head, 정상 여부)"""
        after = [j for j in cands if j > i]
        if not after:
            return root, False
        if topic and root in after and slot not in filled[root]:
            return root, True
        for pos, j in enumerate(after):
            multi = slot not in SINGLE_SLOTS
            if not multi and slot in filled[j]:
                continue
            if E[j].pk == "emb":
                later = [k for k in after[pos + 1:] if E[k].pk != "emb"]
                if multi:
                    if later:
                        continue
                else:
                    if later and slot not in filled[later[0]]:
                        continue
            return j, True
        return after[0], False

    # 3) 논항이 아닌 요소의 연결
    for e in E:
        if e.head is not None or e.kind == "punct":
            continue
        i = e.idx
        if e.kind == "interj":
            e.head, e.role, e.dep_label = root, "독립어", "독립"
            e.reason = f"감탄사 '{_core(e.morphs)[0].form}'는 다른 성분과 직접 관계를 맺지 않는 독립어입니다."
        elif e.kind == "conj_adverb":
            e.head, e.role, e.dep_label = root, "독립어/부사어", "문장 접속"
            e.role_note = "교재에 따라 다름"
            e.reason = (f"접속 부사 '{_core(e.morphs)[0].form}'(MAJ)는 앞 문장과 이 문장을 이어 줍니다. "
                        f"학교문법 교재에 따라 독립어 또는 부사어로 처리합니다.")
        elif e.kind == "modifier":
            k = next_nominal(i)
            e.head, e.role, e.dep_label = (k if k is not None else root), "관형어", "꾸밈"
            m = _core(e.morphs)[0]
            e.reason = f"관형사 '{m.form}'({TAG_NAMES[m.tag]})가 뒤의 체언을 꾸미므로 관형어입니다."
        elif e.kind == "adverb":
            j = next_pred(i)
            e.head, e.role, e.dep_label = (j if j is not None else root), "부사어", "꾸밈"
            m = _core(e.morphs)[0]
            e.reason = f"부사 '{m.form}'({TAG_NAMES[m.tag]})가 뒤의 용언을 꾸미므로 부사어입니다."
        elif e.kind == "pred" and e.ending == "ETM":
            k = next_nominal(i)
            e.head, e.role, e.dep_label = (k if k is not None else root), "관형어", "관형절 → 체언"
            e.reason = (f"용언 {_stem_desc(e)}에 관형사형 전성 어미 '-{e.ending_form}'(ETM)가 붙어 "
                        f"뒤의 체언을 꾸밉니다. 관형절의 서술어이며, 관형절 전체가 관형어 구실을 합니다.")
        elif e.kind == "pred" and (e.ending == "ADV_DERIV" or (e.ending == "EC" and e.ending_form in ADV_EC)):
            j = next_pred(i)
            e.head, e.role, e.dep_label = (j if j is not None else root), "부사어", "부사절 → 용언"
            if e.ending == "ADV_DERIV":
                e.reason = (f"'{e.ending_form}'는 용언에서 파생된 부사로, 학교문법에서는 '{e.ending_form}'를 "
                            f"서술어로 하는 부사절(안긴문장)로 봅니다. 부사절 전체가 부사어 구실을 합니다.")
            else:
                e.reason = (f"용언 {_stem_desc(e)}에 어미 '-{e.ending_form}'가 붙어 뒤의 용언을 꾸밉니다. "
                            f"부사절의 서술어이며, 부사절 전체가 부사어 구실을 합니다.")
                e.role_note = (f"'-{e.ending_form}'는 교재에 따라 부사형 전성 어미 또는 연결 어미로 봄"
                               f"(바른 태그: EC)")
        elif e.kind == "pred" and e.pk == "conn":
            j = next_pred(i, skip_emb=True)
            if j is None:
                j = root
            coord = e.ending_form in COORD_EC
            e.head, e.role = j, "서술어"
            e.dep_label = "대등하게 이어짐" if coord else "종속적으로 이어짐"
            kind = "대등적" if coord else "종속적"
            e.reason = (f"용언 {_stem_desc(e)}에 {kind} 연결 어미 '-{e.ending_form}'가 붙어 앞 절을 끝맺고 "
                        f"뒤 절로 이어 줍니다. 앞 절의 서술어입니다.")
            if e.ending_form == "고":
                e.role_note = "'-고'는 나열이면 대등, 시간 순서(계기)이면 종속으로 보기도 함"
            elif not coord:
                e.role_note = "종속절은 부사절로 보기도 함(교재에 따라 다름)"

    # 4) 논항(주어·목적어·보어·부사어)의 연결 — 오른쪽에서 왼쪽으로
    def arg_slot(e: Eojeol) -> tuple[str, bool] | None:
        """(slot, topic) — 논항이 아니면 None"""
        if e.kind == "pred" and e.ending == "ETN":
            ct = _case_tag(e)
            if ct in ("JKS", "JKO", "JKC", "JKB"):
                return CASE_ROLE[ct], False
            jx = _jx(e)
            if jx is not None:
                return "주어", jx.form in TOPIC_JX
            return "주어", False
        if e.kind == "pred" and e.quoted:
            return "부사어", False
        if e.kind != "nominal":
            return None
        ct = _case_tag(e)
        if ct in ("JKS", "JKC", "JKO", "JKB", "JKQ"):
            return CASE_ROLE[ct], False
        if ct in ("JKG", "JKV") or _jc(e):
            return None
        jx = _jx(e)
        if jx is not None:
            return "주어", jx.form in TOPIC_JX
        return None

    pending = [e for e in E if e.head is None and e.kind != "punct"]
    args = [(e, arg_slot(e)) for e in pending]
    args = [(e, s) for e, s in args if s is not None]
    order = [a for a in reversed(args) if a[1][1]] + [a for a in reversed(args) if not a[1][1]]
    for e, (slot, topic) in order:
        j, ok = choose_head(e.idx, slot, topic)
        e.head = j
        jx = _jx(e)
        ct = _case_tag(e)
        if slot in SINGLE_SLOTS and j in filled:
            if slot in filled[j] and slot == "주어":
                e.role_note = "서술절을 안은 문장의 주어"
            filled[j].add(slot)
        e.role = slot
        e.dep_label = slot
        if e.kind == "pred" and e.ending == "ETN":
            e.reason = (f"용언 {_stem_desc(e)}에 명사형 전성 어미 '-{e.ending_form}'(ETN)가 붙어 명사절이 되고, "
                        + (f"격 조사 '{''.join(m.form for m in e.particles)}'가 붙어 명사절 전체가 {slot} 구실을 합니다."
                           if e.particles else f"명사절 전체가 {slot} 구실을 합니다."))
        elif e.kind == "pred" and e.quoted:
            e.role = "부사어"
            e.dep_label = "인용절 → 용언"
            e.reason = (f"인용격 조사 '{_particle_str(e, 'JKQ')}'(JKQ)가 붙어 따옴표 안의 말이 인용절이 됩니다. "
                        f"인용절은 안긴문장이며, 학교문법에서는 인용절 전체를 부사어로 봅니다.")
        elif ct in CASE_ROLE:
            pform = "".join(m.form for m in e.particles)
            e.reason = f"{TAG_NAMES[ct]} '{_particle_str(e, ct)}'({ct})가 붙어 {slot}입니다."
            if ct == "JKC":
                e.reason = (f"보격 조사 '{_particle_str(e, ct)}'(JKC)가 붙고 서술어 '되다/아니다' 앞에 오므로 보어입니다.")
            if ct == "JKQ":
                e.dep_label = "인용"
            if jx is not None:
                e.reason += f" (보조사 '{jx.form}'가 함께 붙음: '{pform}')"
        elif jx is not None:
            e.estimated = True
            e.reason = (f"보조사 '{jx.form}'(JX)는 격을 나타내지 않습니다. 서술어와의 관계로 보아 주어로 "
                        f"추정했습니다(문맥에 따라 목적어 등일 수 있음).")
        if not ok and slot == "주어" and e.role_note == "":
            e.role_note = "연결할 서술어를 확정하기 어려움"

    # 5) 나머지: 관형격·접속 조사, 조사 없는 체언
    for e in E:
        if e.head is not None or e.kind == "punct":
            continue
        i = e.idx
        ct = _case_tag(e)
        if ct == "JKG":
            k = next_nominal(i)
            e.head, e.role, e.dep_label = (k if k is not None else root), "관형어", "꾸밈"
            e.reason = f"관형격 조사 '{_particle_str(e, 'JKG')}'(JKG)가 붙어 뒤의 체언을 꾸미므로 관형어입니다."
        elif ct == "JKV":
            e.head, e.role, e.dep_label = root, "독립어", "부름"
            e.reason = f"호격 조사 '{_particle_str(e, 'JKV')}'(JKV)가 붙어 부르는 말이 되므로 독립어입니다."
        elif e.kind == "nominal" and _jc(e):
            k = next_nominal(i)
            e.head, e.dep_label = (k if k is not None else root), "접속"
            e.role = E[k].role if k is not None and E[k].role else "?"
            e.reason = (f"접속 조사 '{_particle_str(e, 'JC')}'(JC)로 뒤의 체언과 이어져 함께 하나의 성분"
                        f"({e.role})을 이룹니다.")
        elif e.kind == "nominal":
            _bare_noun(e, E, cands, root, filled, next_nominal, next_pred)
        else:
            e.head = root
            e.role = "?"
            e.reason = "형태 정보만으로 성분을 판정하지 못했습니다."
            e.estimated = True

    # 6) 문장 구조(절) 판정
    clauses, structure = _clauses(E, root, cands, notes)
    return _pack(sent, E, clauses, structure, cands, notes)


def _bare_noun(e, E, cands, root, filled, next_nominal, next_pred) -> None:
    """조사 없이 쓰인 체언."""
    i = e.idx
    n = len(E)
    nxt = next((E[k] for k in range(i + 1, n) if E[k].kind != "punct"), None)
    word = "".join(m.form for m in _core(e.morphs))
    e.estimated = True
    if word in TIME_NOUNS:
        j = next_pred(i)
        e.head, e.role, e.dep_label = (j if j is not None else root), "부사어", "꾸밈"
        e.reason = f"시간을 나타내는 명사 '{word}'가 조사 없이 용언을 꾸미므로 부사어로 보았습니다."
        e.estimated = False
        return
    if nxt is not None and nxt.kind == "modifier" and _core(nxt.morphs)[0].tag == "MMN":
        k = next_nominal(nxt.idx)
        e.head = k if k is not None else root
        e.role = E[k].role if k is not None and E[k].role else "?"
        e.dep_label = "수량 표현과 함께"
        e.reason = (f"'{word}' 뒤에 수량 표현(수 관형사 + 단위 명사)이 이어집니다. 조사가 생략되어 수량 표현과 "
                    f"함께 하나의 성분({e.role})을 이루는 것으로 보았습니다.")
        return
    if nxt is not None and (nxt.kind in ("nominal",) or nxt.kind == "modifier"):
        k = next_nominal(i)
        e.head, e.role, e.dep_label = (k if k is not None else root), "관형어", "꾸밈"
        e.reason = f"체언 '{word}'가 조사 없이 바로 뒤의 체언을 꾸미므로 관형어(체언 단독)로 보았습니다."
        e.estimated = False
        return
    j = next_pred(i)
    if j is None:
        j = root
    e.head = j
    stem = E[j].pred_stem
    if stem is not None and stem.tag in ("VV", "XSV") and "목적어" not in filled.get(j, set()):
        e.role = "목적어"
        filled.setdefault(j, set()).add("목적어")
        e.reason = (f"체언 '{word}' 뒤에 조사가 생략되었습니다. 뒤의 서술어가 동사이고 목적어가 따로 없어 "
                    f"목적어로 추정했습니다(주어일 수도 있음).")
    else:
        e.role = "주어"
        filled.setdefault(j, set()).add("주어")
        e.reason = f"체언 '{word}' 뒤에 조사가 생략되었습니다. 서술어와의 관계로 보아 주어로 추정했습니다."
    e.role_note = "조사 생략"
    e.dep_label = e.role


def _children(E: list[Eojeol]) -> dict[int, list[int]]:
    ch: dict[int, list[int]] = {e.idx: [] for e in E}
    for e in E:
        if e.head is not None and e.head >= 0:
            ch[e.head].append(e.idx)
    return ch


def _subtree(ch: dict[int, list[int]], j: int, exclude: set[int] = frozenset()) -> list[int]:
    out, stack = [], [j]
    while stack:
        k = stack.pop()
        if k in exclude:
            continue
        out.append(k)
        stack.extend(ch.get(k, []))
    return sorted(out)


def _clauses(E, root, cands, notes):
    ch = _children(E)
    # 본용언은 보조 용언과 한 서술어이므로 절 범위에 함께 넣는다
    clauses = []
    structure: list[str] = []
    cid = 0

    def words(span):
        return " ".join(E[k].text for k in span if E[k].kind != "punct")

    for j in cands:
        e = E[j]
        span = _subtree(ch, j)
        if j == root:
            continue
        ctype = None
        if e.ending == "ETM":
            ctype = ("안긴문장", "관형절")
        elif e.ending == "ETN":
            ctype = ("안긴문장", "명사절")
        elif e.ending == "ADV_DERIV" or (e.ending == "EC" and e.ending_form in ADV_EC):
            ctype = ("안긴문장", "부사절")
        elif e.quoted:
            ctype = ("안긴문장", "인용절")
        elif e.pk == "conn":
            ctype = ("이어진문장의 앞 절", "대등" if e.ending_form in COORD_EC else "종속")
        if ctype is None:
            continue
        cid += 1
        clauses.append({"id": cid, "group": ctype[0], "type": ctype[1], "predicate": j,
                        "span": span, "text": words(span), "note": e.role_note})

    # 서술절: 뿌리 서술어에 주어가 둘 연결된 경우(보조사 주어 + 주격 조사 주어)
    subj = [k for k in ch.get(root, []) if E[k].role == "주어"]
    if len(subj) >= 2:
        inner = [k for k in subj if _case_tag(E[k]) == "JKS"]
        outer = [k for k in subj if k not in inner]
        if inner and outer:
            k = inner[-1]
            span = sorted(set(_subtree(ch, k)) | {root} |
                          {x for c in ch[root] if c > k and c not in outer for x in _subtree(ch, c)})
            # 본용언+보조 용언
            span = sorted(set(span))
            cid += 1
            clauses.append({"id": cid, "group": "안긴문장", "type": "서술절", "predicate": root,
                            "span": span, "text": words(span),
                            "note": f"문장 전체의 주어: {E[outer[0]].text} / 서술절의 주어: {E[k].text}"})
            E[k].role_note = "서술절의 주어"
            E[outer[0]].role_note = "문장 전체의 주어(서술절을 안은 문장)"

    groups = {c["type"] for c in clauses}
    coord = [c for c in clauses if c["group"].startswith("이어진")]
    emb = [c for c in clauses if c["group"] == "안긴문장"]
    if not clauses:
        structure = ["홑문장"]
    else:
        if coord:
            kinds = sorted({c["type"] for c in coord})
            structure.append("이어진문장(" + "·".join(f"{k}적으로 이어진 문장" for k in kinds) + ")")
        if emb:
            kinds = []
            for c in emb:
                if c["type"] not in kinds:
                    kinds.append(c["type"])
            structure.append("안은문장(" + "·".join(f"{k}을 안은 문장" for k in kinds) + ")")
    if "인용절" in groups:
        notes.append("인용절은 학교문법에서 부사어 구실을 하는 안긴문장으로 다룹니다.")
    return clauses, structure


def _pack(sent, E, clauses, structure, cands, notes):
    preds = [j for j in cands] if cands else []
    eojeols = []
    for e in E:
        eojeols.append({
            "idx": e.idx,
            "text": e.text,
            "morphemes": [{"form": m.form, "tag": m.tag, "tag_name": TAG_NAMES.get(m.tag, m.tag),
                           "school_pos": SCHOOL_POS.get(m.tag, "")} for m in e.morphs],
            "tagged": "+".join(f"{m.form}/{m.tag}" for m in e.morphs),
            "role": e.role if e.kind != "punct" else "",
            "role_note": e.role_note,
            "estimated": e.estimated,
            "head": e.head,
            "dep_label": e.dep_label,
            "reason": e.reason,
            "is_predicate": e.idx in preds or e.aux_main,
        })
    if isinstance(structure, str):
        structure = [structure]
    kind = "홑문장" if structure == ["홑문장"] else "겹문장"
    return {
        "text": sent.get("text", {}).get("content", ""),
        "refined": sent.get("refined", ""),
        "eojeols": eojeols,
        "clauses": clauses,
        "sentence_kind": kind,
        "structure": structure,
        "notes": notes,
    }


def analyze_response(resp: dict) -> dict:
    """바른 AnalyzeSyntax 응답 전체를 분석한다."""
    return {"sentences": [analyze_sentence(s) for s in resp.get("sentences", [])]}
