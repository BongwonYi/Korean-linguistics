"""저장된 바른 분석 결과(tests/fixtures)로 문장 성분 판정 규칙을 검사한다.

실행: python -m pytest tests  (바른 API를 호출하지 않음)
"""
import json
from pathlib import Path

import pytest

from app.grammar import analyze_response

FIX = Path(__file__).parent / "fixtures"


def load(n):
    return analyze_response(json.loads((FIX / f"s{n:02d}.json").read_text(encoding="utf-8")))["sentences"][0]


def roles(s):
    return {e["text"].strip('.,!"'): e["role"] for e in s["eojeols"] if e["role"]}


def head_of(s, word):
    E = s["eojeols"]
    e = next(x for x in E if x["text"].strip('.,!"') == word)
    return "ROOT" if e["head"] < 0 else E[e["head"]]["text"].strip('.,!"')


def clause_types(s):
    return sorted(c["type"] for c in s["clauses"])


CASES = [
    # (번호, 기대 성분, 홑/겹, 절 종류)
    (1, {"철수가": "주어", "영희에게": "부사어", "예쁜": "관형어", "꽃을": "목적어", "주었다": "서술어"}, "겹문장", ["관형절"]),
    (2, {"물이": "주어", "얼음이": "보어", "되었다": "서술어"}, "홑문장", []),
    (3, {"그는": "주어", "학생이": "보어", "아니다": "서술어"}, "홑문장", []),
    (4, {"나는": "주어", "학생이다": "서술어"}, "홑문장", []),
    (5, {"하늘이": "주어", "매우": "부사어", "푸르다": "서술어"}, "홑문장", []),
    (6, {"와": "독립어", "눈이": "주어", "온다": "서술어"}, "홑문장", []),
    (7, {"민수야": "독립어", "밥": "목적어", "먹어라": "서술어"}, "홑문장", []),
    (8, {"동생은": "주어", "책을": "목적어", "읽고": "서술어", "나는": "주어"}, "겹문장", ["대등"]),
    (9, {"비가": "주어", "와서": "서술어", "길이": "주어"}, "겹문장", ["종속"]),
    (10, {"나는": "주어", "그가": "주어", "범인임을": "목적어", "알았다": "서술어"}, "겹문장", ["명사절"]),
    (11, {"내가": "주어", "어제": "부사어", "산": "관형어", "책이": "주어"}, "겹문장", ["관형절"]),
    (12, {"그는": "주어", "없이": "부사어"}, "겹문장", ["부사절"]),
    (13, {"코끼리는": "주어", "코가": "주어", "길다": "서술어"}, "겹문장", ["서술절"]),
    (14, {"선생님께서": "주어", "학교에": "부사어", "가셨다": "서술어"}, "홑문장", []),
    (15, {"철수의": "관형어", "동생이": "주어"}, "홑문장", []),
    (16, {"그는": "주어", "말했다": "서술어"}, "겹문장", ["인용절"]),
    (17, {"새": "관형어", "옷을": "목적어", "샀다": "서술어"}, "홑문장", []),
    (18, {"그러나": "독립어/부사어", "우리는": "주어", "포기하지": "서술어", "않았다": "서술어"}, "홑문장", []),
    (19, {"꽃이": "주어", "예쁘게": "부사어", "피었다": "서술어"}, "겹문장", ["부사절"]),
    (20, {"책이": "주어", "책상": "관형어", "위에": "부사어", "있다": "서술어"}, "홑문장", []),
    (21, {"나는": "주어", "두": "관형어", "개를": "목적어"}, "홑문장", []),
    (22, {"그는": "주어", "집에": "부사어", "가": "서술어", "버렸다": "서술어"}, "홑문장", []),
    (23, {"나는": "주어", "밥을": "목적어", "먹고": "서술어", "학교에": "부사어"}, "겹문장", ["대등"]),
    (24, {"비가": "주어", "오면": "서술어", "소풍을": "목적어"}, "겹문장", ["종속"]),
    (25, {"우리는": "주어", "그가": "주어", "돌아오기를": "목적어"}, "겹문장", ["명사절"]),
]


@pytest.mark.parametrize("n,expected,kind,clauses", CASES)
def test_roles_and_structure(n, expected, kind, clauses):
    s = load(n)
    got = roles(s)
    for w, r in expected.items():
        assert got[w] == r, f"{s['text']}: '{w}' 기대 {r}, 결과 {got[w]}"
    assert s["sentence_kind"] == kind
    assert clause_types(s) == clauses


def test_embedded_subject_attaches_to_embedded_predicate():
    assert head_of(load(11), "내가") == "산"
    assert head_of(load(10), "그가") == "범인임을"
    assert head_of(load(10), "나는") == "알았다"
    assert head_of(load(1), "철수가") == "주었다"


def test_topic_in_coordinate_clause():
    s = load(8)
    assert head_of(s, "동생은") == "읽고"
    assert head_of(s, "나는") == "들었다"


def test_every_eojeol_has_reason():
    for n, *_ in CASES:
        for e in load(n)["eojeols"]:
            if e["role"]:
                assert e["reason"], (n, e["text"])


def test_frame_choice_prefers_case_marked_arguments():
    """격틀 점수가 같으면 조사로 형태가 확인된 논항이 채우는 격틀을 고른다('이런 식으로 나오다')."""
    from app.grammar import Eojeol, Morph, _match, classify

    def eo(i, text, morphs, role, est):
        e = Eojeol(i, text, [Morph(f, t) for f, t in morphs])
        classify(e)
        e.role, e.estimated = role, est
        return e

    subj = eo(0, "네가", [("네", "NP"), ("가", "JKS")], "주어", False)
    bare = eo(1, "만일", [("만일", "NNG")], "목적어", True)          # 조사 없는 체언(추정)
    adv = eo(2, "식으로", [("식", "NNB"), ("으로", "JKB")], "부사어", False)
    cases = {"주어": ["이", "가"], "목적어": ["을", "를"]}
    at_e = {"frame": [{"role": "주어", "required": True}, {"role": "부사어", "case": ["에"], "required": True}]}
    by_ro = {"frame": [{"role": "주어", "required": True}, {"role": "부사어", "case": ["으로", "로"], "required": True}]}
    s_e = _match(at_e, [subj, bare, adv], cases)[2]
    s_ro = _match(by_ro, [subj, bare, adv], cases)[2]
    assert s_ro > s_e


# ---------------------------------------------------------------------------
# 문법 요소(문장 종결, 높임, 시제·동작상, 부정)
# ---------------------------------------------------------------------------

def feats(s, word):
    E = s["eojeols"]
    a = next(a for a in s["argument_structure"] if E[a["predicate"]]["text"].strip('.,!?"').split('.')[0] == word)
    return {f["cat"]: f for f in a["features"]}


def fake(*tokens):
    """[(어절, [(형태, 태그), …]), …] → 바른 응답 모양."""
    toks = [{"text": {"content": w}, "morphemes": [{"text": {"content": f}, "tag": t} for f, t in ms]}
            for w, ms in tokens]
    return analyze_response({"sentences": [{"text": {"content": " ".join(w for w, _ in tokens)},
                                            "tokens": toks}]})["sentences"][0]


@pytest.mark.parametrize("n, word, expect", [
    (1, "주었다", {"문장 종결": "평서문", "상대 높임": "해라체", "시제": "과거"}),
    (7, "먹어라", {"문장 종결": "명령문", "상대 높임": "해라체"}),
    (11, "산", {"시제": "과거"}),            # 동사 + 관형사형 -ㄴ
    (1, "예쁜", {"시제": "현재"}),           # 형용사 + 관형사형 -ㄴ
    (14, "가셨다", {"주체 높임": "높임", "시제": "과거"}),
    (18, "않았다", {"부정": "긴 부정(-지 않다)"}),
    (22, "버렸다", {"동작상": "완료상"}),
    (16, "갈게", {"상대 높임": "해체"}),
])
def test_grammar_features(n, word, expect):
    f = feats(load(n), word)
    for cat, val in expect.items():
        assert f[cat]["value"] == val, (cat, f.get(cat))


def test_imperative_has_no_tense():
    assert "시제" not in feats(load(7), "먹어라")


def test_sentence_features_from_final_predicate():
    sf = {f["cat"]: f["value"] for f in load(14)["sentence_features"]}
    assert sf == {"문장 종결": "평서문", "상대 높임": "해라체"}


def test_subject_honor_mismatch_is_flagged():
    s = fake(("할머니께서", [("할머니", "NNG"), ("께서", "JKS")]),
             ("왔다.", [("오", "VV"), ("았", "EP"), ("다", "EF"), (".", "SF")]))
    f = feats(s, "왔다")["주체 높임"]
    assert f["warn"] and f["value"] == "확인 필요"


def test_question_mark_decides_ambiguous_ending():
    s = fake(("밥", [("밥", "NNG")]), ("먹어?", [("먹", "VV"), ("어", "EF"), ("?", "SF")]))
    f = feats(s, "먹어")["문장 종결"]
    assert f["value"] == "의문문" and not f["estimated"]


def test_short_negation_and_object_honor():
    s = fake(("나는", [("나", "NP"), ("는", "JX")]),
             ("선생님께", [("선생", "NNG"), ("님", "XSN"), ("께", "JKB")]),
             ("선물을", [("선물", "NNG"), ("을", "JKO")]),
             ("못", [("못", "MAG")]),
             ("드렸다.", [("드리", "VV"), ("었", "EP"), ("다", "EF"), (".", "SF")]))
    f = feats(s, "드렸다")
    assert f["부정"]["value"] == "짧은 부정(못)"
    assert f["객체 높임"]["value"] == "높임"


# ---------------------------------------------------------------------------
# 절 구조(간접 인용절, '에 의해', 서술절, 안긴 절의 부사어, 절 나무)
# ---------------------------------------------------------------------------

def test_indirect_quote_clause():
    s = load(29)   # 그는 내일 비가 온다고 말했다.
    assert roles(s)["온다고"] == "부사어"
    assert clause_types(s) == ["인용절"]
    assert head_of(s, "비가") == "온다고"


def test_agent_phrase_is_not_a_clause():
    s = load(30)   # 그 사건이 경찰에 의해 해결되었다.
    assert s["sentence_kind"] == "홑문장"
    assert roles(s)["의해"] == "부사어" and head_of(s, "사건이") == "해결되었다"


def test_predicate_clause_in_each_conjunct_and_tree():
    s = load(31)   # 영수는 키가 크고 민수는 키가 작다.
    assert clause_types(s) == ["대등", "서술절", "서술절"]
    inner = next(c for c in s["clauses"] if c["type"] == "서술절" and c["text"].startswith("키가 크고"))
    outer = next(c for c in s["clauses"] if c["type"] == "대등")
    assert inner["parent"] == outer["id"] and inner["depth"] == 1
    assert outer.get("meaning", "").startswith("나열")


def test_adverbial_attaches_inside_embedded_clause():
    s = fake(("철수가", [("철수", "NNP"), ("가", "JKS")]),
             ("학교에", [("학교", "NNG"), ("에", "JKB")]),
             ("간", [("가", "VV"), ("ㄴ", "ETM")]),
             ("사실을", [("사실", "NNG"), ("을", "JKO")]),
             ("몰랐다.", [("모르", "VV"), ("았", "EP"), ("다", "EF"), (".", "SF")]))
    assert head_of(s, "학교에") == "간"


# ---------------------------------------------------------------------------
# 사동·피동과 논항 변화
# ---------------------------------------------------------------------------

def voice(s, word):
    E = s["eojeols"]
    a = next(a for a in s["argument_structure"] if E[a["predicate"]]["text"].strip('.,!?"') == word)
    return a["voice"]


@pytest.mark.parametrize("n, word, kind, back", [
    (26, "먹였다", "사동", "아이가 밥을 먹다."),
    (27, "잡혔다", "피동", "고양이가 쥐를 잡다."),
    (28, "했다", "사동", "아이가 밥을 먹다."),
    (30, "해결되었다", "피동", "경찰이 사건을 해결하다."),
])
def test_voice_and_counterpart(n, word, kind, back):
    v = voice(load(n), word)
    assert v["type"] == kind and v["counterpart"] == back


def test_plain_verb_has_no_voice():
    assert voice(load(1), "주었다") is None
