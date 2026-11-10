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
