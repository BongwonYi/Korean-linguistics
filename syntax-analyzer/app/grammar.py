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

import json
import os
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from .features import load_endings, predicate_features
from .voice import voice_info
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
# 바른이 보조사(JX)로 태깅하지만 체언에 붙어 부사어를 만드는 것('예정대로', '꽃처럼')
ADV_JX = {"대로", "처럼", "만큼", "같이", "보다"}
# 동격 관형절을 주로 받는 체언(빈자리 없이 꾸밈을 받음: '비가 오는 소리', '그가 왔다는 사실')
CONTENT_HEADS = {"사실", "소문", "생각", "소식", "소리", "냄새", "느낌", "기억", "가운데", "중", "도중",
                 "때", "동안", "뒤", "후", "전", "다음", "줄", "수", "리", "척", "체", "듯", "바람", "탓",
                 "덕분", "까닭", "이유", "경우", "모습", "장면"}

CASE_ROLE = {
    "JKS": "주어", "JKC": "보어", "JKO": "목적어", "JKG": "관형어",
    "JKB": "부사어", "JKV": "독립어", "JKQ": "부사어",
}
SINGLE_SLOTS = {"주어", "보어", "목적어"}
ARG_ROLES = ("주어", "목적어", "보어", "부사어")
ADV_DERIV_LEMMA = {"없이": "없다", "같이": "같다", "달리": "다르다"}
# 간접 인용의 어미(바른은 '-ㄴ다고'를 연결 어미 하나로 분석함)
QUOTE_EC = {"다고", "ㄴ다고", "는다고", "라고", "으라고", "자고", "냐고", "느냐고", "으냐고", "니냐고"}

# ---------------------------------------------------------------------------
# 격틀 사전
#  기본: frames_krdict.json — 국립국어원 한국어기초사전 문형에서 자동 생성(CC BY-SA 2.0 KR)
#        + frames_override.json — 표제어 단위로 기본 격틀을 바꿔 끼우는 교사 판정
#  frames_v0.json — 손으로 만든 초기 사전(평가 비교용)
# ---------------------------------------------------------------------------

_FRAMES: tuple[dict, dict] | None = None
APP = Path(__file__).parent


def _read_frames(p: Path) -> tuple[dict, dict]:
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    idx: dict[str, list[dict]] = {}
    for ent in data.get("entries", []):
        idx.setdefault(ent["lemma"], []).append(ent)
    return idx, data.get("slot_cases", {})


def load_frames() -> tuple[dict, dict]:
    """(lemma → 격틀 항목 목록, 성분별 기본 조사)"""
    global _FRAMES
    if _FRAMES is None:
        custom = os.environ.get("SYNTAX_FRAMES")
        if custom:
            # 평가용: 지정한 격틀 파일만 쓴다(덮어쓰기 없음)
            _FRAMES = _read_frames(Path(custom))
        else:
            idx, cases = _read_frames(APP / "frames_krdict.json")
            over, _ = _read_frames(APP / "frames_override.json")
            idx.update(over)  # 덮어쓰기 파일에 있는 표제어는 기본 격틀 전체를 바꾼다
            _FRAMES = (idx, cases)
    return _FRAMES


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
    frame_arg: str = ""           # 격틀에 따라 논항으로 다시 본 '체언+이라고' 등의 형태


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


def lemma_of(e: Eojeol) -> str | None:
    """서술어 어절의 기본형(격틀 사전 표제어)."""
    s = e.pred_stem
    if s is None:
        return None
    if e.ending == "ADV_DERIV":
        return ADV_DERIV_LEMMA.get(s.form)
    if s.tag == "VCP":
        return "이다"
    if s.tag == "VCN":
        return "아니다"
    if s.tag in ("XSV", "XSA"):
        core = _core(e.morphs)
        k = next(i for i in range(len(core) - 1, -1, -1) if core[i] is s)
        base = ""
        for m in reversed(core[:k]):
            if m.tag in ("NNG", "NNP", "NNB", "XR", "MAG"):
                base = m.form + base
            else:
                break
        return base + s.form + "다"
    return s.form + "다"


def _arg_form(e: Eojeol) -> str | None:
    """논항 어절의 격 표지 형태(조사, 또는 '-게' 같은 어미). 보조사만 있거나 조사가 없으면 None."""
    if e.frame_arg:
        return e.frame_arg
    if e.kind == "pred" and e.ending == "EC":
        if e.quoted:
            return "-고"   # 기초사전 문형의 인용 자리 표기('3-고 생각하다')
        return "-" + e.ending_form
    ct = _case_tag(e)
    if ct:
        return _particle_str(e, ct)
    return None


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

    frames, slot_cases = load_frames()

    # 2-1) '체언+이라고' 다음 서술어의 격틀에 '라고' 부사어 자리가 있으면 절이 아니라 필수적 부사어로 본다
    #      (교재 10장 문형 (5) '나는 그를 학생이라고 생각한다')
    for e in E:
        if (e.kind == "pred" and e.ending == "EC" and e.pred_stem and e.pred_stem.tag == "VCP"
                and e.ending_form in ("라고", "고") and e.idx + 1 < n and E[e.idx + 1].kind == "pred"):
            lem = lemma_of(E[e.idx + 1])
            if any(s["role"] == "부사어" and e.ending_form in s.get("case", [])
                   for ent in frames.get(lem, []) for s in ent["frame"]):
                e.kind, e.pk, e.frame_arg = "nominal", "", e.ending_form
                e.particles = []
    # 2-2) 간접 인용절: '-다고/-라고/-자고/-냐고'로 끝난 절(교재 12장 '형은 철수가 학교에 간다고 말했다')
    for e in E:
        if (e.kind == "pred" and e.ending == "EC" and e.ending_form in QUOTE_EC and not e.aux_main
                and any(x.kind == "pred" for x in E[e.idx + 1:])):
            e.quoted, e.pk = True, "emb"

    # 2-3) '체언+에 의해(서)': 서술어 '의하다'의 절이 아니라 피동문의 행위주를 나타내는 부사어 한 덩어리로 본다
    for e in E:
        if (e.kind == "pred" and e.pred_stem is not None and e.pred_stem.form == "의하" and e.ending == "EC"
                and e.idx > 0 and E[e.idx - 1].kind == "nominal" and _particle_str(E[e.idx - 1], "JKB") == "에"):
            prev = E[e.idx - 1]
            e.kind, e.pk, e.frame_arg = "agent", "", "에 의해"
            prev.head, prev.role, prev.dep_label = e.idx, "부사어", "꾸밈"
            prev.role_note = "'에 의해'와 함께 부사어"
            prev.reason = (f"'{prev.text} {e.text}'는 '체언+에 의해(서)'의 짜임으로, 둘이 함께 행위의 주체(행위주)를 "
                           f"나타내는 부사어 구실을 합니다(주로 피동문에 쓰임).")
    cands = [e.idx for e in E if e.kind == "pred" and not e.aux_main]

    def main_of(j: int) -> int:
        """보조 용언 서술어 j의 본용언(없으면 j)."""
        k = j
        while k - 1 >= 0 and E[k - 1].aux_main and E[k - 1].head == k:
            k -= 1
        return k

    def frame_entries(j: int) -> list[dict]:
        m = main_of(j)
        if E[m].pred_stem is not None and E[m].pred_stem.tag == "VX":
            return []
        return frames.get(lemma_of(E[m]) or "", [])

    def frame_case(j: int, form: str) -> bool:
        """서술어 j의 격틀에 '부사어 + form(조사)' 자리가 있는가."""
        return any(sl["role"] == "부사어" and form in sl.get("case", [])
                   for ent in frame_entries(j) for sl in ent["frame"])

    def frame_allows(j: int, slot: str) -> bool:
        ents = frame_entries(j)
        return not ents or any(s["role"] == slot for ent in ents for s in ent["frame"])

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

    def emb_takes_adverbial(i: int, j: int, k: int) -> bool:
        """부사어 i를 뒤의 서술어 k 대신 안긴 절의 서술어 j에 연결할지('발에 땀이 나도록', '학교에 간 사실').

        j의 격틀에 그 조사의 부사어 자리가 있고, k의 격틀에는 없거나 i와 j 사이에 이미 j의 논항이 있을 때."""
        ct = _case_tag(E[i])
        if ct != "JKB":
            return False
        form = _particle_str(E[i], "JKB")
        if not frame_case(j, form):
            return False
        if not frame_case(k, form) or any(E[x].head == j for x in range(i + 1, j)):
            return True
        # 뒤 서술어의 주어가 이미 정해졌고(주제어 등), i 앞에 주격 조사 주어가 있으면 i는 안긴 절 안에 있다
        if "주어" in filled.get(k, set()):
            for x in range(i - 1, -1, -1):
                if E[x].kind == "pred":
                    break
                if E[x].kind == "nominal" and _case_tag(E[x]) == "JKS":
                    return True
        return False

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
            if not multi and not frame_allows(j, slot):
                continue  # 격틀에 이 자리가 없는 서술어는 건너뛴다
            if E[j].pk == "emb":
                later = [k for k in after[pos + 1:] if E[k].pk != "emb"]
                if multi:
                    if later and not emb_takes_adverbial(i, j, later[0]):
                        continue
                else:
                    if later and slot not in filled[later[0]] and frame_allows(later[0], slot):
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
        elif e.kind == "agent":
            j = next_pred(i)
            e.head, e.role, e.dep_label = (j if j is not None else root), "부사어", "꾸밈"
            e.role_note = "'에 의해'와 함께 부사어"
            e.reason = (f"'{E[i - 1].text} {e.text}'가 함께 행위의 주체를 나타내는 부사어입니다. '의하다'를 서술어로 하는 "
                        f"절로 보지 않고, 조사처럼 굳어진 표현으로 보았습니다.")
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
        if e.frame_arg:
            return "부사어", False
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
            if jx.form in ADV_JX:
                return "부사어", False
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
        if e.frame_arg:
            e.reason = (f"'{e.text}'는 체언에 '이다'와 '-{e.frame_arg}'가 붙은 형태입니다. 뒤의 서술어 "
                        f"'{lemma_of(E[j])}'의 격틀에 '-{e.frame_arg}' 자리가 있어 절이 아니라 부사어로 보았습니다"
                        f"(교재 10장 문형 (5)). 인용절로 보는 견해도 있습니다.")
            e.role_note = "인용절로 보기도 함"
        elif e.kind == "pred" and e.ending == "ETN":
            e.reason = (f"용언 {_stem_desc(e)}에 명사형 전성 어미 '-{e.ending_form}'(ETN)가 붙어 명사절이 되고, "
                        + (f"격 조사 '{''.join(m.form for m in e.particles)}'가 붙어 명사절 전체가 {slot} 구실을 합니다."
                           if e.particles else f"명사절 전체가 {slot} 구실을 합니다."))
        elif e.kind == "pred" and e.quoted and e.ending == "EC":
            e.role = "부사어"
            e.dep_label = "인용절 → 용언"
            e.role_note = "간접 인용절"
            e.reason = (f"용언 {_stem_desc(e)}에 간접 인용의 '-{e.ending_form}'가 붙어 남의 말이나 생각을 옮기는 "
                        f"인용절이 됩니다(바른은 '-{e.ending_form}'를 연결 어미로 분석). 인용절은 안긴문장이며 "
                        f"학교문법에서는 인용절 전체를 부사어로 봅니다.")
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
        elif jx is not None and jx.form in ADV_JX:
            e.reason = (f"보조사 '{jx.form}'(JX)가 붙어 '~과 같이, ~에 따라' 같은 뜻으로 서술어를 꾸미므로 "
                        f"부사어입니다.")
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

    # 6) 격틀로 자리 채우기 — 서술어별 자릿수, 필수/수의 성분, 생략 논항
    argst = [_fill_frame(E, j, main_of(j), frame_entries(j), slot_cases) for j in cands]

    # 6-1) 서술어별 문법 요소(종결 표현, 높임, 시제·동작상, 부정)
    sf = [x.form for e in E for x in e.morphs if x.tag == "SF"]
    punct = sf[-1] if sf else ""
    for a in argst:
        j = a["predicate"]
        a["features"] = predicate_features(E, j, a["main"], a["lemma"], E[j].pk == "main", punct)
        # 6-2) 사동·피동과 논항 변화
        v = a["voice"] = voice_info(E, a, frames)
        if v:
            back = f"{v['counterpart_label']}: {v['counterpart']}"
            a["features"].append({"cat": "사동·피동", "value": v["type"], "markers": [v["form"]],
                                  "note": back + (f" ({v['note']})" if v["note"] else ""),
                                  "estimated": v["estimated"], "warn": False})

    # 7) 문장 구조(절) 판정
    clauses, structure = _clauses(E, root, cands, notes)
    out = _pack(sent, E, clauses, structure, cands, notes)
    out["argument_structure"] = argst
    fin = next((a for a in argst if E[a["predicate"]].pk == "main" and E[a["predicate"]].idx == root), None)         or next((a for a in argst if E[a["predicate"]].pk == "main"), None)
    out["sentence_features"] = [f for f in (fin["features"] if fin else [])
                                if f["cat"] in ("문장 종결", "상대 높임")]
    return out


def _compatible(slot: dict, role: str, form: str | None, slot_cases: dict, cross: bool) -> bool:
    cases = slot.get("case")
    if not cross:
        if slot["role"] != role:
            return False
        if form is None:
            # 형태 표지가 없는 확정 성분(부사 등)은 조사가 명시된 자리를 채우지 않는다
            return cases is None
        return form in (cases if cases is not None else slot_cases.get(role, []))
    # 다른 성분 자리: 격틀에 그 형태가 명시된 경우만('학교를 가다'의 '를' → 부사어 자리)
    return form is not None and cases is not None and form in cases


def _match(ent: dict, args: list[Eojeol], slot_cases: dict, gap: bool = False):
    """격틀 항목 하나에 논항을 배정한다. (배정표, 남은 논항, 점수). gap: 관형절 서술어인지"""
    slots = ent["frame"]
    assign: dict[int, Eojeol] = {}
    fixed = [a for a in args if not a.estimated]
    guessed = [a for a in args if a.estimated]
    rest: list[Eojeol] = []
    # 같은 성분 자리부터: 주어·목적어·보어는 앞에서부터, 부사어는 서술어에 가까운 것부터
    # ('오후에 사무실에 배달되었다' → '사무실에'가 자리를 채움)
    order = ([a for a in fixed if a.role != "부사어"]
             + [a for a in reversed(fixed) if a.role == "부사어"])
    left: list[Eojeol] = []
    for a in order:
        form = _arg_form(a)
        k = next((i for i, s in enumerate(slots) if i not in assign
                  and _compatible(s, a.role, form, slot_cases, False)), None)
        if k is None:
            left.append(a)
        else:
            assign[k] = a
    # 그다음 다른 성분 자리: 격틀에 그 형태가 명시된 경우('의준이를 주다'의 '를' → 부사어 자리)
    for a in sorted(left, key=lambda x: x.idx):
        form = _arg_form(a)
        k = next((i for i, s in enumerate(slots) if i not in assign
                  and _compatible(s, a.role, form, slot_cases, True)), None)
        if k is None:
            rest.append(a)
        else:
            assign[k] = a
    # 보조사·조사 생략 논항: 남은 자리에 어순을 지키며 배정한다(보어는 형태가 있어야 하므로 제외).
    # 지금 추정한 성분과 같은 자리, 주제 보조사(은/는)는 주어 자리, 조사 생략은 주어 아닌 자리를 우선한다.
    # 보조사는 주격·목적격 조사 자리에만 대신 쓰이고 부사격 조사는 남기므로('학교에는'),
    # 보조사만 붙은 논항('예정대로', '사과는')은 부사어 자리를 채우지 않는다.
    open_slots = [i for i, s in enumerate(slots) if i not in assign and s["role"] != "보어"]
    best_pairs: list[tuple[int, Eojeol]] = []
    best_sc = None
    for k in range(min(len(open_slots), len(guessed)), -1, -1):
        for gs in combinations(guessed, k):
            for ss in combinations(open_slots, k):
                sc = 0
                for a, i in zip(gs, ss):
                    role = slots[i]["role"]
                    jx = _jx(a)
                    if jx is not None and role == "부사어":
                        sc = None
                        break
                    sc += 2 if a.role == role else 0
                    if jx is not None and jx.form in TOPIC_JX:
                        sc += 1 if role == "주어" else 0
                    elif jx is None:
                        sc += 1 if role != "주어" else 0
                if sc is not None and (best_sc is None or sc > best_sc):
                    best_sc, best_pairs = sc, list(zip(ss, gs))
        if best_sc is not None:
            break
    for i, a in best_pairs:
        assign[i] = a
    used = {id(a) for _, a in best_pairs}
    rest += [a for a in guessed if id(a) not in used]
    # 점수: 채운 필수 자리(2) + 채운 수의 자리(1)
    #  + 조사·어미로 형태가 확인된 논항이 채운 자리(2): 형태 근거가 있는 격틀을 고르도록
    #    ('이런 식으로 나오다' → '1이 2로 나오다', 조사 없는 '만일'로 '에' 자리를 채운 격틀보다 앞섬)
    #  - 자리를 못 찾은 확정 주어·목적어·보어(2), 자리를 못 찾은 추정 논항(1), 비어 있는 필수 자리(1)
    req = sum(1 for i, s in enumerate(slots) if s.get("required") and i in assign)
    opt = sum(1 for i, s in enumerate(slots) if not s.get("required") and i in assign)
    marked = sum(1 for a in assign.values() if not a.estimated)
    core_left = sum(1 for a in rest if a.role in SINGLE_SLOTS and not a.estimated)
    guess_left = sum(1 for a in rest if a.role in SINGLE_SLOTS and a.estimated)
    missing = sum(1 for i, s in enumerate(slots) if s.get("required") and i not in assign)
    # 관형절: 꾸밈을 받는 체언이 빈 필수 자리 하나를 채운다('내가 좋아하는 것' → 목적어 자리).
    # gap에 성분 집합을 주면 그 성분 자리가 비어 있을 때만 인정한다(의존명사 '것' 앞은 주어·목적어만).
    if gap and missing:
        roles = gap if isinstance(gap, (set, frozenset)) else None
        if roles is None or any(s.get("required") and i not in assign and s["role"] in roles
                                for i, s in enumerate(slots)):
            missing -= 1
            req += 1
    # + 형태 근거에 따른 추정 논항의 적합도: 주제 보조사(은/는) → 주어 자리, 조사 생략 → 주어 아닌 자리 (+1)
    #   ('민수야, 밥 먹어라' → '1이 2를 먹다'가 한 자리 '1이 먹다(귀가 먹다)'와 같은 점수가 되어 빈도순으로 앞섬)
    #   앞 단계에서 임시로 추정한 성분은 근거가 약하므로 격틀 점수에는 넣지 않는다.
    fit = 0
    for i, a in best_pairs:
        jx = _jx(a)
        role = slots[i]["role"]
        if (jx is not None and jx.form in TOPIC_JX and role == "주어") or (jx is None and role != "주어"):
            fit += 1
    return assign, rest, 2 * req + opt + 3 * marked - 2 * core_left - guess_left - missing + fit


def _fill_frame(E: list[Eojeol], j: int, m: int, ents: list[dict], slot_cases: dict) -> dict:
    lemma = lemma_of(E[m])
    args = [e for e in E if e.head in (j, m) and e.idx != m and e.role in ARG_ROLES]
    info = {"predicate": j, "main": m, "lemma": lemma, "frame_found": bool(ents),
            "sense": None, "places": None, "slots": [], "omitted": [], "adjuncts": [],
            "unmatched": [], "relative": None}
    if not ents:
        info["adjuncts"] = [a.idx for a in args if a.role == "부사어"]
        return info
    gap = E[m].ending == "ETM" or E[j].ending == "ETM"
    if gap:
        h = E[j].head
        noun = "".join(x.form for x in _core(E[h].morphs) if x.tag in NOMINAL) if h is not None and h >= 0 else ""
        if noun in CONTENT_HEADS:
            gap = False  # 동격 관형절을 주로 받는 체언이면 빈자리를 가정하지 않는다
        elif h is not None and h >= 0 and any(x.tag == "NNB" for x in _core(E[h].morphs)):
            gap = {"주어", "목적어"}  # 의존명사('것' 등)는 부사어 자리의 빈자리를 받는 일이 드묾
    best = max((_match(ent, args, slot_cases, gap) + (ent,) for ent in ents), key=lambda x: x[2])
    assign, rest, _, ent = best
    info["sense"] = ent.get("sense")
    info["places"] = ent["places"]
    info["pattern"] = ent.get("example", "")      # 사전 문형 또는 격틀 예문(화면 표시용)
    info["frame_source"] = ent.get("source", "")
    for i, s in enumerate(ent["frame"]):
        a = assign.get(i)
        info["slots"].append({"role": s["role"], "required": bool(s.get("required")),
                              "case": s.get("case"), "filled_by": a.idx if a else None})
        if a is None:
            if s.get("required"):
                info["omitted"].append(s["role"])
            continue
        if a.estimated and a.role != s["role"]:
            a.role = a.dep_label = s["role"]
            a.role_note = "격틀로 추정"
            jx = _jx(a)
            mark = f"보조사 '{jx.form}'(JX)만 붙어" if jx else "조사가 생략되어"
            a.reason = (f"'{a.text}'에는 {mark} 격을 형태로 알 수 없습니다. 서술어 '{lemma}'의 격틀에서 "
                        f"{s['role']} 자리가 비어 있어 {s['role']}로 추정했습니다.")
        elif a.role != s["role"]:
            a.role_note = f"형식상 {a.role}(격틀의 {s['role']} 자리)"
            a.reason += (f" 다만 '{lemma}'의 격틀에서는 {s['role']} 자리를 채웁니다"
                         f"(기능상 {s['role']}로 보는 견해가 있음).")
        if s["role"] == "부사어" and s.get("required") and a.role == "부사어":
            if not a.role_note:
                a.role_note = "필수적 부사어"
            a.reason += f" 서술어 '{lemma}'가 꼭 필요로 하는 자리이므로 필수적 부사어입니다."
    for a in rest:
        (info["adjuncts"] if a.role == "부사어" else info["unmatched"]).append(a.idx)
    # 관형절: 채워지지 않은 필수 자리 중 하나를 꾸밈을 받는 체언이 채운다
    if E[m].ending == "ETM" or E[j].ending == "ETM":
        h = E[j].head
        gaps = info["omitted"]
        info["relative"] = {"head_noun": h, "type": "관계" if gaps else "동격",
                            "gap_candidates": list(gaps)}
    return info


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
    nxt_np = nxt is not None and nxt.kind == "nominal" and _core(nxt.morphs)[0].tag == "NP"
    if nxt is not None and (nxt.kind in ("nominal",) or nxt.kind == "modifier") and not nxt_np:
        # 체언이 조사 없이 대명사를 꾸미는 경우는 드물어('너 어디'), 대명사 앞에서는 관형어로 보지 않는다
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

    # 서술절: 한 서술어에 주어가 둘 연결된 경우('코끼리는 코가 길다', '이 책이 글씨가 작다')
    for p in [*cands, root] if root not in cands else cands:
        subj = [k for k in ch.get(p, []) if E[k].role == "주어"]
        if len(subj) < 2:
            continue
        inner = [k for k in subj if _case_tag(E[k]) == "JKS"]
        outer = [k for k in subj if k not in inner]
        if not outer and len(inner) >= 2:
            outer, inner = inner[:1], inner[1:]   # 주격 조사 주어가 둘이면 앞의 것이 문장 전체의 주어
        if not (inner and outer):
            continue
        k = inner[-1]
        span = sorted(set(_subtree(ch, k)) | {p} |
                      {x for c in ch[p] if c > k and c not in outer and c not in subj for x in _subtree(ch, c)})
        span = [x for x in span if x >= k]
        cid += 1
        clauses.append({"id": cid, "group": "안긴문장", "type": "서술절", "predicate": p,
                        "span": span, "text": words(span),
                        "note": f"서술절을 안은 절의 주어: {E[outer[0]].text} / 서술절의 주어: {E[k].text}"})
        E[k].role_note = "서술절의 주어"
        E[outer[0]].role_note = "서술절을 안은 문장(절)의 주어"

    # 연결 어미의 의미 관계(이어진문장·부사절)
    ec = load_endings().get("EC", {})
    for c in clauses:
        e = E[c["predicate"]]
        if c["type"] in ("대등", "종속", "부사절") and e.ending == "EC" and e.ending_form in ec:
            c["meaning"] = ec[e.ending_form]

    # 절의 포함 관계(나무 구조): 범위를 포함하는 가장 작은 절이 부모
    for c in clauses:
        sc = set(c["span"])
        outer_c = [d for d in clauses if d is not c and sc < set(d["span"])]
        par = min(outer_c, key=lambda d: len(d["span"]), default=None)
        c["parent"] = par["id"] if par else None
    for c in clauses:
        depth, q = 0, c
        while q["parent"] is not None and depth < 10:
            q = next(d for d in clauses if d["id"] == q["parent"])
            depth += 1
        c["depth"] = depth

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
