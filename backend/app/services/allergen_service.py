"""
식품의약품안전처 「식품등의 표시기준」 19종 알레르기 유발물질 정의 및 AI 예측 엔진
- 법적 기준: 알류(가금류), 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지고기, 복숭아, 토마토, 
             아황산류(이산화황 10mg/kg 이상), 호두, 닭고기, 쇠고기, 오징어, 조개류(굴, 전복, 홍합 포함), 잣
- 기능:
  1. 19종 표준 메타데이터 제공
  2. 음식명, 시각적 단서, 조리법 기반 알레르기 유발물질 포함 확률(0~100%) 및 위험 등급 추정
  3. AI 비전 예측과 규칙 기반 지식베이스의 앙상블 결합
"""

import re
from typing import List, Dict, Any, Optional

# 식품의약품안전처 고시 19종 법정 알레르기 유발물질
MFDS_ALLERGENS = [
    {
        "id": "egg",
        "name": "알류(가금류)",
        "short_name": "알류",
        "emoji": "🥚",
        "description": "달걀, 오리알, 메추리알 등 가금류의 알 및 그 가공품",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 알류(가금류에 한함) 및 그 가공품",
        "common_ingredients": ["계란", "달걀", "메추리알", "난백", "난황", "마요네즈", "지단", "오믈렛", "스크램블"],
        "cross_reactivity": "오리알, 메추리알, 거위알 등 가금류 알 전반",
        "clinical_notes": "난백 단백질(오보뮤코이드, 오발부민)은 열에 비교적 안정하여 완숙 조리 시에도 알레르기를 유발할 수 있습니다.",
        "action_guide": "전, 튀김, 볶음밥, 빵류 조리 시 달걀물/지단 제외 요청 필요"
    },
    {
        "id": "milk",
        "name": "우유",
        "short_name": "우유",
        "emoji": "🥛",
        "description": "우유, 분유, 치즈, 버터, 연유, 유청 등 유제품",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 우유 및 유가공품",
        "common_ingredients": ["우유", "치즈", "버터", "생크림", "크림", "요거트", "연유", "라떼", "유청단백"],
        "cross_reactivity": "산양유, 양유 및 카제인 함유 유제품",
        "clinical_notes": "카제인 및 유청단백질(베타-락토글로불린) 알레르기로 유당불내증과 구별되며 급성 반응을 유발할 수 있습니다.",
        "action_guide": "버터, 치즈, 크림, 분유, 마가린 및 유청단백 함유 식품 섭취 주의"
    },
    {
        "id": "buckwheat",
        "name": "메밀",
        "short_name": "메밀",
        "emoji": "🌾",
        "description": "메밀, 메밀면, 메밀묵, 메밀전병 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 메밀 및 그 가공품",
        "common_ingredients": ["메밀", "모밀", "메밀국수", "평양냉면", "막국수"],
        "cross_reactivity": "대황 등 마디풀과 식물",
        "clinical_notes": "극미량(ppm 단위)으로도 급성 아나필락시스를 유발할 수 있는 고위험 알레르겐입니다.",
        "action_guide": "냉면, 막국수, 소바, 메밀전병 및 동일 제면기 사용 업소 주의"
    },
    {
        "id": "peanut",
        "name": "땅콩",
        "short_name": "땅콩",
        "emoji": "🥜",
        "description": "땅콩, 땅콩버터, 피넛소스 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 땅콩 및 그 가공품",
        "common_ingredients": ["땅콩", "피넛", "땅콩가루", "땅콩버터", "견과가루"],
        "cross_reactivity": "루핀, 대두, 완두 등 콩과 식물 및 일부 견과류",
        "clinical_notes": "가열 조리 시 항원성이 강화되는 특성이 있으며, 소량으로도 호흡기 증상 및 전신 반응 위험이 높습니다.",
        "action_guide": "땅콩분태, 땅콩버터, 피넛소스, 동남아/중식 볶음요리 섭취 시 사전 확인 필수"
    },
    {
        "id": "soybean",
        "name": "대두",
        "short_name": "대두",
        "emoji": "🫘",
        "description": "콩, 두부, 된장, 간장, 콩기름, 두유 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 대두 및 그 가공품",
        "common_ingredients": ["대두", "콩", "된장", "간장", "두부", "유부", "고추장", "청국장", "콩나물", "두유", "쌈장"],
        "cross_reactivity": "기타 콩류, 완두콩, 렌틸콩, 땅콩",
        "clinical_notes": "한국 전통 발효 장류(된장, 간장, 고추장)의 핵심 원료로 한식 전반에 광범위하게 잠재되어 있습니다.",
        "action_guide": "된장찌개, 간장 양념, 두부, 유부, 콩나물, 대두유 및 유화제(대두레시틴) 확인"
    },
    {
        "id": "wheat",
        "name": "밀",
        "short_name": "밀",
        "emoji": "🌾",
        "description": "밀가루, 빵, 국수, 라면, 파스타, 튀김옷, 부침개 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 밀 및 그 가공품",
        "common_ingredients": ["밀", "밀가루", "소맥분", "빵", "면", "라면", "국수", "스파게티", "튀김", "만두피", "케이크", "도넛"],
        "cross_reactivity": "보리, 호밀, 귀리 등 글루텐 함유 곡물",
        "clinical_notes": "글루텐(글리아딘, 글루테닌) 매개 소화기 및 피부 반응, 운동유발성 아나필락시스 주의",
        "action_guide": "면류, 빵, 튀김옷, 만두피, 어묵, 간장 제조용 소맥분 함유 여부 확인"
    },
    {
        "id": "mackerel",
        "name": "고등어",
        "short_name": "고등어",
        "emoji": "🐟",
        "description": "고등어구이, 고등어조림 등 고등어 및 가공식품",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 고등어 및 그 가공품",
        "common_ingredients": ["고등어", "고등어자반", "고등어조림", "고등어구이"],
        "cross_reactivity": "참치, 꽁치, 삼치 등 등푸른생선 및 기타 어류 파발부민",
        "clinical_notes": "생선 근육 단백질 파발부민(Parvalbumin) 및 신선도 저하 시 발생하는 히스타민 중독 유사 증상에 유의해야 합니다.",
        "action_guide": "고등어구이, 조림, 어묵, 생선 육수 농축물 함유 여부 확인"
    },
    {
        "id": "crab",
        "name": "게",
        "short_name": "게",
        "emoji": "🦀",
        "description": "꽃게, 대게, 홍게, 게장, 게맛살 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 게 및 그 가공품",
        "common_ingredients": ["꽃게", "대게", "홍게", "게살", "게장", "간장게장", "양념게장", "게맛살", "크랩", "킹크랩"],
        "cross_reactivity": "새우, 가재, 랍스터, 집게 등 갑각류 전반",
        "clinical_notes": "주요 항원인 트로포미오신(Tropomyosin)은 열에 안정적이므로 고온 가열 조리 후에도 항원성이 유지됩니다.",
        "action_guide": "꽃게탕, 게장, 게살볶음밥, 게맛살(게 엑기스), 짬뽕 해물 육수 주의"
    },
    {
        "id": "shrimp",
        "name": "새우",
        "short_name": "새우",
        "emoji": "🦐",
        "description": "생새우, 건새우, 새우젓, 새우튀김 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 새우 및 그 가공품",
        "common_ingredients": ["새우", "새우젓", "대하", "건새우", "칵테일새우", "새우튀김", "감바스", "쉬림프"],
        "cross_reactivity": "게, 가재, 랍스터, 연체동물 및 집먼지진드기",
        "clinical_notes": "김치 발효 시 사용되는 새우젓 및 육수용 건새우 가루 등 육안으로 식별하기 어려운 형태가 많습니다.",
        "action_guide": "배추김치, 찌개 육수, 튀김, 젓갈류 섭취 전 새우젓 사용 여부 필수 문의"
    },
    {
        "id": "pork",
        "name": "돼지고기",
        "short_name": "돼지고기",
        "emoji": "🥓",
        "description": "삼겹살, 제육, 돈가스, 햄, 소시지, 돈육 육수 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 돼지고기 및 그 가공품",
        "common_ingredients": ["돼지고기", "삼겹살", "목살", "제육", "돈육", "돈가스", "햄", "소시지", "베이컨", "보쌈", "족발", "탕수육"],
        "cross_reactivity": "고양이 털 알레르기 환자의 포크-캣(Pork-Cat) 증후군 교차반응",
        "clinical_notes": "가공육(햄, 소시지) 및 돈골 농축 육수(라멘, 순대국) 등에 혼합 분말 형태로 널리 사용됩니다.",
        "action_guide": "제육볶음, 돈가스, 햄/소시지, 만두소, 찌개 고명 및 돈골 육수 확인"
    },
    {
        "id": "peach",
        "name": "복숭아",
        "short_name": "복숭아",
        "emoji": "🍑",
        "description": "백도, 황도, 천도복숭아 및 통조림, 주스 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 복숭아 및 그 가공품",
        "common_ingredients": ["복숭아", "백도", "황도", "천도복숭아", "복숭아잼", "복숭아아이스티"],
        "cross_reactivity": "자두, 살구, 사과, 체리 등 장미과 과일 및 자작나무 꽃가루",
        "clinical_notes": "과피(껍질)의 지질전이단백(Pru p 3)은 열과 소화효소에 강해 중증 전신 반응을 유발할 수 있습니다.",
        "action_guide": "생과일, 과일주스, 과채가공품, 샐러드 드레싱, 빙수 토핑 확인"
    },
    {
        "id": "tomato",
        "name": "토마토",
        "short_name": "토마토",
        "emoji": "🍅",
        "description": "토마토, 방울토마토, 케첩, 토마토소스, 퓌레 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 토마토 및 그 가공품",
        "common_ingredients": ["토마토", "방울토마토", "케첩", "토마토소스", "마리나라", "토마토페이스트"],
        "cross_reactivity": "감자, 가지, 피망 등 가지과 식물 및 라텍스-과일 증후군",
        "clinical_notes": "생토마토뿐만 아니라 조리된 소스, 케첩, 페이스트 형태에서도 알레르기 항원성이 잔존합니다.",
        "action_guide": "케첩, 파스타 소스, 피자 소스, 햄버거 패티 소스, 샐러드 확인"
    },
    {
        "id": "sulfite",
        "name": "아황산류(이산화황 10mg/kg 이상)",
        "short_name": "아황산류",
        "emoji": "🧪",
        "description": "건조 과일, 절임류, 와인, 과채 가공품 등의 보존료/산화방지제",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 아황산류를 첨가하여 최종제품에 SO2로서 10mg/kg 이상 함유한 경우",
        "common_ingredients": ["건포도", "건망고", "건과일", "와인", "백포도주", "곶감", "절임류", "물엿가공품"],
        "cross_reactivity": "식품첨가물 산화방지제 및 표백제 과민증",
        "clinical_notes": "기관지 천식 환자에게 급성 천명음, 호흡곤란, 아나필락시스 유사 발작을 유발할 수 있습니다.",
        "action_guide": "건포도, 건망고 등 건조과일, 와인, 절임류, 물엿, 과채주스 성분표 확인"
    },
    {
        "id": "walnut",
        "name": "호두",
        "short_name": "호두",
        "emoji": "🧠",
        "description": "호두, 호두과자, 호두파이, 견과 가공품 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 호두 및 그 가공품",
        "common_ingredients": ["호두", "월넛", "호두분태", "호두과자", "호두파이"],
        "cross_reactivity": "피칸(Pecan), 헤이즐넛, 캐슈넛 등 견과류 전반",
        "clinical_notes": "소량으로도 기도 부종 및 아나필락시스를 유발하는 대표적인 고위험 나무 견과류입니다.",
        "action_guide": "호두과자, 베이커리 빵/파이, 시리얼, 견과류 토핑 샐러드 섭취 주의"
    },
    {
        "id": "chicken",
        "name": "닭고기",
        "short_name": "닭고기",
        "emoji": "🍗",
        "description": "치킨, 닭가슴살, 삼계탕, 닭볶음탕, 치킨스톡 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 닭고기 및 그 가공품",
        "common_ingredients": ["닭고기", "치킨", "닭", "닭가슴살", "삼계탕", "백숙", "닭볶음탕", "닭갈비", "치킨스톡"],
        "cross_reactivity": "칠면조, 오리고기 및 조류 알레르겐",
        "clinical_notes": "닭고기 살코기뿐 아니라 치킨스톡, 육수 농축액, 가공 소시지 혼합육에 함유됩니다.",
        "action_guide": "치킨, 삼계탕, 닭볶음탕, 닭가슴살 샐러드, 치킨스톡 베이스 육수 확인"
    },
    {
        "id": "beef",
        "name": "쇠고기",
        "short_name": "쇠고기",
        "emoji": "🥩",
        "description": "소고기, 불고기, 갈비, 소고기 육수, 쇠고기 분말스프 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 쇠고기 및 그 가공품",
        "common_ingredients": ["소고기", "쇠고기", "한우", "불고기", "갈비", "차돌박이", "사골", "우족", "육수", "비프", "소고기스프"],
        "cross_reactivity": "우유 단백질 알레르기 및 진드기 매개 알파갈(Alpha-gal) 증후군",
        "clinical_notes": "소고기 육수, 쇠고기 다시다, 사골 분말스프 등 국물 조미료 성분으로 광범위 사용됩니다.",
        "action_guide": "불고기, 스테이크, 사골곰탕, 미역국, 라면 분말스프 비프 성분 확인"
    },
    {
        "id": "squid",
        "name": "오징어",
        "short_name": "오징어",
        "emoji": "🦑",
        "description": "오징어, 오징어볶음, 마른오징어, 오징어채, 먹물 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 오징어 및 그 가공품",
        "common_ingredients": ["오징어", "진미채", "오징어채", "한치", "물오징어", "오징어순대", "오징어젓"],
        "cross_reactivity": "문어, 낙지, 꼴뚜기, 주꾸미 등 두족류 및 연체동물",
        "clinical_notes": "연체동물 트로포미오신 단백질 알레르기로 건조 가공품에서도 강한 알레르기를 유발합니다.",
        "action_guide": "오징어볶음, 짬뽕, 진미채, 건어물, 해물파전, 젓갈류 섭취 확인"
    },
    {
        "id": "shellfish",
        "name": "조개류(굴, 전복, 홍합 포함)",
        "short_name": "조개류",
        "emoji": "🦪",
        "description": "굴, 전복, 홍합, 바지락, 꼬막, 가리비, 조개 육수 및 굴소스 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 조개류(굴, 전복, 홍합 포함) 및 그 가공품",
        "common_ingredients": ["조개", "굴", "전복", "홍합", "바지락", "가리비", "꼬막", "모시조개", "굴소스", "조개스톡", "재첩"],
        "cross_reactivity": "바지락, 꼬막, 가리비, 재첩 등 패류 전반 및 연체류",
        "clinical_notes": "중식의 굴소스, 해물 칼국수 육수, 조개젓 등 국물 요리에 빈번히 용출됩니다.",
        "action_guide": "굴소스 조리 요리, 해물 뚝배기, 바지락 칼국수, 패류 육수 확인"
    },
    {
        "id": "pine_nut",
        "name": "잣",
        "short_name": "잣",
        "emoji": "🌲",
        "description": "잣, 잣죽, 백자인, 잣고명 등",
        "legal_definition": "식품의약품안전처 「식품등의 표시기준」 제6조 별표 2: 잣 및 그 가공품",
        "common_ingredients": ["잣", "잣가루", "잣죽", "잣고명"],
        "cross_reactivity": "기타 견과류 및 솔과 식물",
        "clinical_notes": "한국 전통 궁중음식, 한과, 죽, 샐러드에 고명으로 자주 사용되며 아나필락시스 반응에 주의해야 합니다.",
        "action_guide": "잣죽, 수정과, 한과, 신선로, 떡 및 고급 소스류 고명 확인"
    }
]

# 한국 대표 요리 및 조리 형태에 따른 휴리스틱 지식베이스
# 각 규칙은 (allergen_id, probability, risk_level, reason) 형태를 제공
DISH_ALLERGEN_RULES = {
    # 밥류
    "비빔밥": [
        ("egg", 0.95, "매우 높음", "달걀후라이 또는 지단 고명 기본 포함"),
        ("beef", 0.85, "높음", "소고기 볶음 고명 또는 소고기 육수 양념 사용"),
        ("soybean", 0.95, "매우 높음", "양념장(고추장/간장) 및 콩나물 고명"),
        ("wheat", 0.80, "높음", "전통 발효 고추장의 소맥분(밀) 발효 성분")
    ],
    "볶음밥": [
        ("egg", 0.90, "매우 높음", "스크램블 에그 또는 계란 코팅 조리"),
        ("soybean", 0.85, "높음", "간장 및 식용유 양념 베이스"),
        ("pork", 0.70, "높음", "햄, 베이컨 또는 다진 돼지고기 첨가 가능성"),
        ("wheat", 0.65, "보통", "간장 및 굴소스(소맥분) 양념")
    ],
    "김밥": [
        ("egg", 0.95, "매우 높음", "계란 지단 필수 속재료"),
        ("pork", 0.85, "높음", "햄 또는 소시지 속재료"),
        ("soybean", 0.90, "매우 높음", "우엉/어묵 간장 조림 양념"),
        ("wheat", 0.75, "높음", "어묵 및 간장 소맥분 함유"),
        ("crab", 0.60, "보통", "게맛살 속재료(게 엑기스 또는 연육)")
    ],
    "카레": [
        ("wheat", 0.95, "매우 높음", "카레 루(Roux)의 밀가루 베이스"),
        ("milk", 0.60, "보통", "버터 및 유크림 부드러움 증진 첨가"),
        ("beef", 0.50, "보통", "쇠고기 육수 또는 깍둑썰기 고기"),
        ("pork", 0.50, "보통", "돼지고기 등심 또는 안심 주재료"),
        ("soybean", 0.70, "높음", "대두유 및 가공유지")
    ],
    # 찌개 및 국류
    "김치찌개": [
        ("pork", 0.85, "높음", "돼지고기(목살/삼겹살) 육수 및 건더기"),
        ("soybean", 0.80, "높음", "두부 속재료 및 국간장 양념"),
        ("shrimp", 0.75, "높음", "배추김치 양념의 새우젓 발효 성분"),
        ("wheat", 0.40, "보통", "양조간장 및 조미스프의 미량 밀 성분")
    ],
    "된장찌개": [
        ("soybean", 0.98, "매우 높음", "된장(대두 발효) 및 두부 주재료"),
        ("wheat", 0.60, "보통", "시판 재래된장의 소맥분 혼합 성분"),
        ("shellfish", 0.65, "높음", "바지락, 조개 육수 또는 멸치다시마 베이스"),
        ("beef", 0.35, "낮음", "차돌박이 또는 쇠고기 육수 가능성")
    ],
    "미역국": [
        ("beef", 0.80, "높음", "소고기 양지머리 참기름 볶음 베이스"),
        ("soybean", 0.85, "높음", "조선간장(국간장) 간 맞춤"),
        ("shellfish", 0.40, "보통", "홍합 또는 바지락 미역국 변형 가능성")
    ],
    "순두부찌개": [
        ("soybean", 0.98, "매우 높음", "순두부(대두 가공품) 주재료"),
        ("egg", 0.90, "매우 높음", "날달걀 투하 토핑"),
        ("shellfish", 0.75, "높음", "바지락 조개 육수 및 해물 베이스"),
        ("shrimp", 0.60, "보통", "새우젓 간 및 칵테일 새우"),
        ("pork", 0.40, "보통", "다진 돼지고기 고추기름 볶음")
    ],
    "부대찌개": [
        ("pork", 0.98, "매우 높음", "스팸, 소시지, 다진 돼지고기"),
        ("wheat", 0.95, "매우 높음", "라면 사리 및 햄류 소맥 전분"),
        ("soybean", 0.90, "매우 높음", "베이크드 빈스(대두) 및 두부"),
        ("beef", 0.70, "높음", "사골 육수 또는 쇠고기 분말스프"),
        ("milk", 0.50, "보통", "슬라이스 치즈 토핑")
    ],
    # 반찬 및 고기류
    "계란말이": [
        ("egg", 1.00, "매우 높음", "달걀 전란 주재료"),
        ("soybean", 0.50, "보통", "조리 식용유 및 간장/소금간"),
        ("wheat", 0.30, "낮음", "맛술 또는 조미 양념")
    ],
    "삼겹살": [
        ("pork", 1.00, "매우 높음", "돼지고기 삼겹 부위 원육"),
        ("soybean", 0.80, "높음", "곁들임 쌈장 및 기름장 간장")
    ],
    "제육볶음": [
        ("pork", 1.00, "매우 높음", "돼지고기 앞다리/목살 주재료"),
        ("soybean", 0.90, "매우 높음", "고추장, 간장 양념 베이스"),
        ("wheat", 0.75, "높음", "고추장 소맥분 발효 성분")
    ],
    "불고기": [
        ("beef", 1.00, "매우 높음", "소고기 우둔/등심 주재료"),
        ("soybean", 0.95, "매우 높음", "진간장 양념 베이스"),
        ("wheat", 0.75, "높음", "양조간장 소맥분 성분")
    ],
    "닭갈비": [
        ("chicken", 1.00, "매우 높음", "닭다리살 원육 주재료"),
        ("soybean", 0.90, "매우 높음", "고추장 및 진간장 양념"),
        ("wheat", 0.75, "높음", "고추장 소맥분 및 떡사리 밀가루")
    ],
    "치킨": [
        ("chicken", 1.00, "매우 높음", "닭고기 원육"),
        ("wheat", 0.98, "매우 높음", "바삭한 튀김옷(밀가루/치킨파우더)"),
        ("soybean", 0.90, "매우 높음", "튀김 전용 대두유"),
        ("milk", 0.60, "보통", "우유 염지제(잡내 제거) 또는 치즈 시즈닝")
    ],
    "돈가스": [
        ("pork", 1.00, "매우 높음", "돼지 등심/안심 원육"),
        ("wheat", 0.98, "매우 높음", "밀가루 반죽 및 빵가루"),
        ("egg", 0.95, "매우 높음", "튀김 옷 고정 달걀물"),
        ("milk", 0.50, "보통", "우유 연육 및 돈가스 브라운 소스 버터"),
        ("tomato", 0.70, "높음", "돈가스 소스 내 케첩 성분")
    ],
    # 면류 및 빵/디저트
    "라면": [
        ("wheat", 0.99, "매우 높음", "유탕 유탕면(소맥분 90% 이상)"),
        ("soybean", 0.85, "높음", "분말스프의 간장분말 및 탈지대두"),
        ("beef", 0.70, "높음", "쇠고기 맛 엑기스 및 비프스톡 분말"),
        ("pork", 0.60, "보통", "돈골 추출 농축분말"),
        ("egg", 0.50, "보통", "계란 블록 또는 계란 투하 조리"),
        ("shellfish", 0.40, "보통", "해물 농축 엑기스 분말")
    ],
    "짜장면": [
        ("wheat", 0.99, "매우 높음", "중화면(밀가루) 주재료"),
        ("soybean", 0.95, "매우 높음", "춘장(검은 콩/대두 발효) 소스"),
        ("pork", 0.85, "높음", "다진 돼지고기 짜장 볶음"),
        ("shellfish", 0.50, "보통", "굴소스 양념 첨가")
    ],
    "짬뽕": [
        ("wheat", 0.99, "매우 높음", "중화면(밀가루)"),
        ("squid", 0.90, "매우 높음", "오징어 건더기 필수 포함"),
        ("shellfish", 0.85, "높음", "홍합, 바지락 조개 육수 및 해물"),
        ("pork", 0.60, "보통", "돼지고기 채 볶음 육수"),
        ("soybean", 0.70, "높음", "고추기름 및 간장 양념")
    ],
    "피자": [
        ("wheat", 0.99, "매우 높음", "피자 도우(밀가루 강력분)"),
        ("milk", 0.99, "매우 높음", "모짜렐라 치즈 토핑"),
        ("tomato", 0.95, "매우 높음", "토마토 피자 소스"),
        ("pork", 0.80, "높음", "페퍼로니, 베이컨, 햄 토핑"),
        ("beef", 0.50, "보통", "불고기 피자 또는 쇠고기 토핑")
    ],
    "샌드위치": [
        ("wheat", 0.99, "매우 높음", "식빵(밀가루)"),
        ("egg", 0.85, "높음", "삶은 달걀 토핑 또는 마요네즈"),
        ("milk", 0.75, "높음", "슬라이스 치즈 또는 식빵 버터"),
        ("pork", 0.70, "높음", "샌드위치 햄 또는 베이컨"),
        ("tomato", 0.65, "높음", "슬라이스 생토마토")
    ],
    "토스트": [
        ("wheat", 0.99, "매우 높음", "식빵(소맥분) 주재료"),
        ("milk", 0.85, "높음", "버터 구이 및 치즈"),
        ("egg", 0.70, "높음", "계란 지단 및 프라이 반죽"),
        ("peanut", 0.40, "보통", "땅콩버터 스프레드 첨가 가능성"),
        ("soybean", 0.60, "높음", "대두 레시틴 및 식물성 마가린")
    ],
    "땅콩버터": [
        ("peanut", 1.00, "매우 높음", "땅콩(Peanut) 100% 원재료 스프레드"),
        ("soybean", 0.70, "높음", "식물성 유지 가공 및 대두 레시틴 유화제")
    ],
    "피넛버터": [
        ("peanut", 1.00, "매우 높음", "땅콩(Peanut) 원재료 스프레드"),
        ("soybean", 0.70, "높음", "식물성 유지 가공 및 대두 레시틴 유화제")
    ],
    "식빵": [
        ("wheat", 0.99, "매우 높음", "식빵 강력분(소맥분) 주재료"),
        ("milk", 0.80, "높음", "버터 및 탈지분유 배합"),
        ("soybean", 0.50, "보통", "대두 레시틴 유화제")
    ],
    "딸기잼": [
        ("sulfite", 0.40, "보통", "과채가공품 및 보존 성분의 아황산류")
    ],
    "잼": [
        ("sulfite", 0.40, "보통", "과채가공품 및 펙틴의 아황산류")
    ],
    "우유": [
        ("milk", 1.00, "매우 높음", "원유 100%")
    ],
    "도넛": [
        ("wheat", 0.99, "매우 높음", "밀가루 반죽"),
        ("milk", 0.85, "높음", "우유 및 버터"),
        ("egg", 0.80, "높음", "반죽 달걀 첨가"),
        ("soybean", 0.50, "보통", "식용유 튀김")
    ],
    "배추김치": [
        ("shrimp", 0.85, "높음", "새우젓 발효 양념"),
        ("shellfish", 0.40, "보통", "굴 또는 조개젓 첨가 가능성"),
        ("wheat", 0.30, "낮음", "풀국(밀가루풀/찹쌀풀)")
    ]
}

def get_risk_level_text(prob: float) -> str:
    """확률 값에 따른 식약처 안전 권고 등급 부여"""
    if prob >= 0.85:
        return "매우 높음 (위험)"
    elif prob >= 0.60:
        return "높음 (주의)"
    elif prob >= 0.30:
        return "보통 (확인 필요)"
    else:
        return "낮음 (잠재적 미량)"

def get_allergen_meta(allergen_id: str) -> Optional[Dict[str, Any]]:
    """알레르기 ID로 공식 메타데이터 조회"""
    for item in MFDS_ALLERGENS:
        if item["id"] == allergen_id or item["name"] == allergen_id or item["short_name"] == allergen_id:
            return item
    return None

def predict_allergens_for_food(food_name: str, visual_cues: str = "") -> List[Dict[str, Any]]:
    """
    단일 음식명과 비전 AI의 visual_cues를 분석하여
    식약처 19종 중 포함될 가능성이 있는 알레르기 유발물질을 확률과 함께 반환
    """
    results: Dict[str, Dict[str, Any]] = {}
    clean_name = food_name.strip()

    # 1. 완벽 또는 부분 일치 규칙 테이블 탐색
    matched_rule_key = None
    for rule_key in DISH_ALLERGEN_RULES:
        if rule_key in clean_name or clean_name in rule_key:
            matched_rule_key = rule_key
            break

    if matched_rule_key:
        for a_id, prob, risk, reason in DISH_ALLERGEN_RULES[matched_rule_key]:
            meta = get_allergen_meta(a_id)
            if meta:
                results[a_id] = {
                    "id": a_id,
                    "name": meta["name"],
                    "short_name": meta["short_name"],
                    "emoji": meta["emoji"],
                    "probability": round(prob, 2),
                    "percentage": int(round(prob * 100)),
                    "risk_level": get_risk_level_text(prob),
                    "reason": reason,
                    "proof": {
                        "legal_basis": meta.get("legal_definition", "식약처 「식품등의 표시기준」 법정 19종 의무 표시 대상"),
                        "detected_reason": reason,
                        "common_ingredients": meta.get("common_ingredients", []),
                        "cross_reactivity": meta.get("cross_reactivity", "동일 계통 식재료와의 교차반응 가능성을 주의하세요."),
                        "clinical_notes": meta.get("clinical_notes", "알레르기 반응 유발 시 즉각 섭취를 중단하고 전문의와 상담하세요."),
                        "action_guide": meta.get("action_guide", "해당 성분에 민감한 경우 주문 시 해당 식재료 제외를 요청하세요.")
                    }
                }

    # 2. visual_cues 및 음식명 키워드 정규식 기반 추가/보정 탐색
    text_to_scan = f"{clean_name} {visual_cues}".lower()

    for item in MFDS_ALLERGENS:
        a_id = item["id"]
        # 이미 90% 이상으로 판정된 경우 패스
        if a_id in results and results[a_id]["probability"] >= 0.9:
            continue

        for kw in item["common_ingredients"]:
            kw_clean = kw.lower()
            if len(kw_clean) == 1:
                is_match = bool(re.search(rf'(?<![가-힣a-zA-Z]){re.escape(kw_clean)}(?![가-힣a-zA-Z])', text_to_scan))
            else:
                is_match = kw_clean in text_to_scan

            if is_match:
                prob = 0.85
                reason = f"명칭 및 시각 단서에서 '{kw}' 성분 직접 감지"
                
                # 원재료 자체일 경우 확률 100%
                if clean_name.lower() == kw.lower():
                    prob = 1.0
                    reason = f"{item['short_name']} 원재료 식품"

                if a_id not in results or results[a_id]["probability"] < prob:
                    results[a_id] = {
                        "id": a_id,
                        "name": item["name"],
                        "short_name": item["short_name"],
                        "emoji": item["emoji"],
                        "probability": round(prob, 2),
                        "percentage": int(round(prob * 100)),
                        "risk_level": get_risk_level_text(prob),
                        "reason": reason,
                        "proof": {
                            "legal_basis": item.get("legal_definition", "식약처 「식품등의 표시기준」 법정 19종 의무 표시 대상"),
                            "detected_reason": reason,
                            "common_ingredients": item.get("common_ingredients", []),
                            "cross_reactivity": item.get("cross_reactivity", "동일 계통 식재료와의 교차반응 가능성을 주의하세요."),
                            "clinical_notes": item.get("clinical_notes", "알레르기 반응 유발 시 즉각 섭취를 중단하고 전문의와 상담하세요."),
                            "action_guide": item.get("action_guide", "해당 성분에 민감한 경우 주문 시 해당 식재료 제외를 요청하세요.")
                        }
                    }
                break

    # 확률 내림차순 정렬
    sorted_results = sorted(results.values(), key=lambda x: x["probability"], reverse=True)
    return sorted_results

def merge_ai_and_rule_allergens(ai_allergens: List[Dict[str, Any]], rule_allergens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    AI 비전이 직접 식별한 알레르기 정보와 규칙 기반 지식베이스 정보를 상호 보완 병합
    """
    merged: Dict[str, Dict[str, Any]] = {}

    # 규칙 기반 먼저 적재
    for r in rule_allergens:
        merged[r["id"]] = r

    # AI 비전 결과로 갱신 또는 보강
    for ai_item in ai_allergens:
        name_or_id = ai_item.get("allergen", "") or ai_item.get("id", "")
        meta = get_allergen_meta(name_or_id)
        if not meta:
            continue
        
        a_id = meta["id"]
        prob = float(ai_item.get("probability", 0.8))
        prob = max(0.0, min(1.0, prob))
        reason = ai_item.get("reason", "") or "AI 비전 시각 인식"

        if a_id in merged:
            # 더 높은 신뢰도 채택
            max_prob = max(merged[a_id]["probability"], prob)
            merged[a_id]["probability"] = round(max_prob, 2)
            merged[a_id]["percentage"] = int(round(max_prob * 100))
            merged[a_id]["risk_level"] = get_risk_level_text(max_prob)
            if reason:
                merged[a_id]["reason"] = f"{merged[a_id]['reason']} (AI 검증: {reason})"
                if "proof" in merged[a_id]:
                    merged[a_id]["proof"]["detected_reason"] = merged[a_id]["reason"]
        else:
            merged[a_id] = {
                "id": a_id,
                "name": meta["name"],
                "short_name": meta["short_name"],
                "emoji": meta["emoji"],
                "probability": round(prob, 2),
                "percentage": int(round(prob * 100)),
                "risk_level": get_risk_level_text(prob),
                "reason": reason,
                "proof": {
                    "legal_basis": meta.get("legal_definition", "식약처 「식품등의 표시기준」 법정 19종 의무 표시 대상"),
                    "detected_reason": reason,
                    "common_ingredients": meta.get("common_ingredients", []),
                    "cross_reactivity": meta.get("cross_reactivity", "동일 계통 식재료와의 교차반응 가능성을 주의하세요."),
                    "clinical_notes": meta.get("clinical_notes", "알레르기 반응 유발 시 즉각 섭취를 중단하고 전문의와 상담하세요."),
                    "action_guide": meta.get("action_guide", "해당 성분에 민감한 경우 주문 시 해당 식재료 제외를 요청하세요.")
                }
            }

    return sorted(merged.values(), key=lambda x: x["probability"], reverse=True)

def aggregate_meal_allergens(foods_with_allergens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    식단 내 모든 개별 음식에서 검출된 알레르기 유발물질을 종합 집계 (최대 확률 기준)
    """
    aggregated: Dict[str, Dict[str, Any]] = {}

    for f in foods_with_allergens:
        food_name = f.get("name") or f.get("detected_name", "음식")
        for a in f.get("allergens", []):
            a_id = a["id"]
            meta = get_allergen_meta(a_id) or {}
            if a_id not in aggregated:
                aggregated[a_id] = {
                    "id": a["id"],
                    "name": a["name"],
                    "short_name": a["short_name"],
                    "emoji": a["emoji"],
                    "max_probability": a["probability"],
                    "max_percentage": a["percentage"],
                    "risk_level": a["risk_level"],
                    "detected_in_foods": [food_name],
                    "reasons": [f"[{food_name}] {a['reason']}"],
                    "proof": {
                        "legal_basis": meta.get("legal_definition", "식약처 「식품등의 표시기준」 법정 19종 의무 표시 대상"),
                        "detected_in_foods": [food_name],
                        "reasons": [f"[{food_name}] {a['reason']}"],
                        "common_ingredients": meta.get("common_ingredients", []),
                        "cross_reactivity": meta.get("cross_reactivity", ""),
                        "clinical_notes": meta.get("clinical_notes", ""),
                        "action_guide": meta.get("action_guide", "")
                    }
                }
            else:
                if food_name not in aggregated[a_id]["detected_in_foods"]:
                    aggregated[a_id]["detected_in_foods"].append(food_name)
                    aggregated[a_id]["reasons"].append(f"[{food_name}] {a['reason']}")
                    aggregated[a_id]["proof"]["detected_in_foods"].append(food_name)
                    aggregated[a_id]["proof"]["reasons"].append(f"[{food_name}] {a['reason']}")
                if a["probability"] > aggregated[a_id]["max_probability"]:
                    aggregated[a_id]["max_probability"] = a["probability"]
                    aggregated[a_id]["max_percentage"] = a["percentage"]
                    aggregated[a_id]["risk_level"] = a["risk_level"]

    return sorted(aggregated.values(), key=lambda x: x["max_probability"], reverse=True)
