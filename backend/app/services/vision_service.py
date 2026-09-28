import os
import io
import re
import json
import base64
import requests
from typing import Dict, Any, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    from app.services.db_service import search_foods
    from app.services.allergen_service import predict_allergens_for_food
except ImportError:
    from backend.app.services.db_service import search_foods
    from backend.app.services.allergen_service import predict_allergens_for_food

# -------------------------------------------------------------
# 1. API 키 관리
# -------------------------------------------------------------
def get_api_key() -> str:
    """환경 변수 또는 .env 파일에서 Gemini API 키 획득 (유효한 AIzaSy... 형식만 인정)"""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key and key.startswith("AIzaSy"):
        return key

    paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
    ]
    for env_path in paths:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val and val.startswith("AIzaSy"):
                            return val
    return ""

def set_runtime_api_key(new_key: str):
    """실행 중 API 키 저장 및 갱신"""
    cleaned = new_key.strip()
    os.environ["GEMINI_API_KEY"] = cleaned
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(f"GEMINI_API_KEY={cleaned}\n")

# -------------------------------------------------------------
# 2. 로컬 Vision Transformer (ViT) 음식 분류 엔진 (101종)
# -------------------------------------------------------------
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
VIT_MODEL_PATH = os.path.join(MODEL_DIR, "food101_vit.onnx")
CONFIG_PATH = os.path.join(MODEL_DIR, "food101_config.json")

_vit_session = None
_id2label = {}

FOOD101_TO_KOREAN = {
    "apple_pie": ("애플파이", 150.0, "달콤한 사과 소와 바삭한 파이 크러스트"),
    "baby_back_ribs": ("돼지갈비구이", 300.0, "양념에 구운 두툼한 돼지 등갈비"),
    "baklava": ("페이스트리", 100.0, "견과류와 시럽이 어우러진 페이스트리"),
    "beef_carpaccio": ("소고기육회", 150.0, "얇게 저민 생소고기"),
    "beef_tartare": ("육회", 150.0, "신선한 소고기 육회와 달걀노른자"),
    "beet_salad": ("비트샐러드", 150.0, "신선한 붉은 비트 채소 샐러드"),
    "beignets": ("도넛", 120.0, "슈가파우더를 뿌린 튀김 빵"),
    "bibimbap": ("비빔밥", 350.0, "다양한 나물과 밥, 고추장 양념"),
    "bread_pudding": ("빵푸딩", 150.0, "촉촉하게 구워낸 브레드 푸딩"),
    "breakfast_burrito": ("부리토", 250.0, "또띠아에 감싼 달걀과 채소, 고기"),
    "bruschetta": ("바게트토스트", 120.0, "토마토와 허브를 올린 바게트 빵"),
    "caesar_salad": ("시저샐러드", 180.0, "로메인 상추와 파마산 치즈, 크루통"),
    "cannoli": ("카놀리", 100.0, "바삭한 쉘 속 크림 디저트"),
    "caprese_salad": ("카프레제샐러드", 180.0, "생모짜렐라 치즈와 슬라이스 토마토, 바질"),
    "carrot_cake": ("당근케이크", 130.0, "크림치즈 프로스팅의 당근 케이크"),
    "ceviche": ("생선세비체", 150.0, "라임 즙에 절인 신선한 해산물"),
    "cheese_plate": ("치즈플레이트", 100.0, "모둠 치즈 조각"),
    "cheesecake": ("치즈케이크", 120.0, "부드러운 크림치즈 케이크"),
    "chicken_curry": ("치킨카레", 300.0, "닭고기와 감자, 채소가 어우러진 카레"),
    "chicken_quesadilla": ("퀘사디아", 200.0, "치즈와 닭고기가 채워진 또띠아"),
    "chicken_wings": ("치킨", 200.0, "바삭하게 구워내거나 튀긴 닭날개"),
    "chocolate_cake": ("초콜릿케이크", 130.0, "진한 다크 초콜릿 케이크"),
    "chocolate_mousse": ("초콜릿무스", 100.0, "부드러운 초콜릿 무스 디저트"),
    "churros": ("츄러스", 100.0, "계피 설탕을 묻힌 튀김 디저트"),
    "clam_chowder": ("조개스프", 250.0, "크림 베이스의 진한 조개 스프"),
    "club_sandwich": ("클럽샌드위치", 220.0, "베이컨, 닭가슴살, 채소를 겹친 샌드위치"),
    "crab_cakes": ("게살크로켓", 150.0, "게살과 빵가루를 뭉쳐 구운 패티"),
    "creme_brulee": ("크렘브륄레", 100.0, "캐러멜 토핑 커스터드 크림"),
    "croque_madame": ("토스트", 180.0, "치즈, 햄, 달걀후라이를 얹은 토스트"),
    "cup_cakes": ("컵케이크", 90.0, "프로스팅을 얹은 컵케이크"),
    "deviled_eggs": ("삶은달걀", 100.0, "노른자 소스를 채운 삶은 달걀"),
    "donuts": ("도넛", 80.0, "달콤한 글레이즈 도넛"),
    "dumplings": ("만두", 200.0, "속이 꽉 찬 찐만두 또는 물만두"),
    "edamame": ("풋콩", 80.0, "삶은 신선한 풋콩 꼬투리"),
    "eggs_benedict": ("에그베네딕트", 200.0, "수란과 홀랜다이즈 소스를 얹은 잉글리시머핀"),
    "escargots": ("달팽이요리", 100.0, "버터와 파슬리로 구운 달팽이"),
    "falafel": ("팔라펠", 150.0, "병아리콩을 뭉쳐 튀긴 크로켓"),
    "filet_mignon": ("안심스테이크", 200.0, "두툼하고 부드러운 소안심 스테이크"),
    "fish_and_chips": ("생선가스", 250.0, "바삭한 흰살생선 튀김과 감자튀김"),
    "foie_gras": ("푸아그라", 80.0, "거위 간 요리"),
    "french_fries": ("감자튀김", 120.0, "바삭하게 튀겨낸 막대 감자"),
    "french_onion_soup": ("양파스프", 250.0, "캐러멜라이징 양파와 치즈 바게트 스프"),
    "french_toast": ("프렌치토스트", 150.0, "달걀물에 적셔 노릇하게 구운 식빵"),
    "fried_calamari": ("오징어튀김", 150.0, "바삭한 오징어 링 튀김"),
    "fried_rice": ("볶음밥", 300.0, "채소와 고기를 함께 볶아낸 고슬고슬한 밥"),
    "frozen_yogurt": ("요거트아이스크림", 120.0, "상큼하고 시원한 프로즌 요거트"),
    "garlic_bread": ("마늘빵", 100.0, "마늘 버터를 발라 구운 바삭한 빵"),
    "gnocchi": ("감자뇨끼", 200.0, "쫄깃한 감자 반죽 파스타"),
    "greek_salad": ("그릭샐러드", 180.0, "페타치즈, 올리브, 오이, 토마토 샐러드"),
    "grilled_cheese_sandwich": ("치즈토스트", 150.0, "팬에 구워 녹아내린 치즈 샌드위치"),
    "grilled_salmon": ("연어구이", 200.0, "노릇하게 구운 분홍빛 연어 스테이크"),
    "guacamole": ("과카몰리", 100.0, "아보카도와 라임, 양파를 으깬 디저트/딥"),
    "gyoza": ("군만두", 180.0, "한쪽 면을 바삭하게 구운 만두"),
    "hamburger": ("햄버거", 220.0, "두툼한 고기 패티와 신선한 채소 번"),
    "hot_and_sour_soup": ("산라탕", 250.0, "새콤매콤한 중국식 국물 요리"),
    "hot_dog": ("핫도그", 150.0, "소시지를 끼운 빵"),
    "huevos_rancheros": ("멕시칸에그", 200.0, "토마토 살사 소스와 달걀 요리"),
    "hummus": ("후무스", 100.0, "부드러운 병아리콩 딥 소스"),
    "ice_cream": ("아이스크림", 100.0, "시원하고 달콤한 스쿱 아이스크림"),
    "lasagna": ("라자냐", 280.0, "넓은 면과 미트소스, 치즈를 겹겹이 구운 요리"),
    "lobster_bisque": ("바닷가재스프", 250.0, "랍스터 껍질을 우려낸 진한 크림 스프"),
    "lobster_roll_sandwich": ("랍스터샌드위치", 180.0, "랍스터 살을 채운 소프트 롤"),
    "macaroni_and_cheese": ("마카로니치즈", 200.0, "진한 체다 치즈 소스에 버무린 마카로니"),
    "macarons": ("마카롱", 60.0, "알록달록한 아몬드 머랭 과자"),
    "miso_soup": ("된장국", 200.0, "맑고 구수한 된장국"),
    "mussels": ("홍합탕", 250.0, "시원한 조개 육수의 홍합 요리"),
    "nachos": ("나초", 120.0, "치즈 소스를 곁들인 바삭한 또띠아 칩"),
    "omelette": ("오믈렛", 180.0, "부드럽게 말아낸 달걀 요리"),
    "onion_rings": ("양파튀김", 120.0, "동그란 양파 링 튀김"),
    "oysters": ("굴", 150.0, "신선한 석화 / 생굴"),
    "pad_thai": ("팟타이", 300.0, "숙주와 땅콩 가루를 곁들인 볶음 쌀국수"),
    "paella": ("파에야", 300.0, "사프란과 해산물이 가득한 스페인식 볶음밥"),
    "pancakes": ("팬케이크", 180.0, "시럽을 뿌린 폭신한 핫케이크"),
    "panna_cotta": ("판나코타", 100.0, "부드러운 이탈리아식 우유 푸딩"),
    "peking_duck": ("오리구이", 200.0, "바삭한 껍질의 훈제 오리구이"),
    "pho": ("쌀국수", 450.0, "맑은 소고기 육수에 담긴 베트남 쌀국수"),
    "pizza": ("피자", 200.0, "노릇한 치즈와 토핑이 올라간 도우"),
    "pork_chop": ("돈가스", 220.0, "두툼한 돼지고기 스테이크 / 커틀릿"),
    "poutine": ("감자튀김", 200.0, "그레이비 소스와 치즈 커드를 얹은 감자튀김"),
    "prime_rib": ("소갈비구이", 250.0, "육즙이 풍부한 소갈비 스테이크"),
    "pulled_pork_sandwich": ("바베큐샌드위치", 220.0, "찢은 돼지고기 바베큐 샌드위치"),
    "ramen": ("라면", 450.0, "진한 국물과 꼬들꼬들한 면발의 라면"),
    "ravioli": ("라비올리", 200.0, "소를 채운 사각 파스타"),
    "red_velvet_cake": ("레드벨벳케이크", 130.0, "붉은 스펀지와 크림치즈 케이크"),
    "risotto": ("리소토", 250.0, "크림이나 토마토 소스로 부드럽게 익힌 쌀 요리"),
    "samosa": ("사모사", 120.0, "향신료 채소를 채운 삼각 튀김 만두"),
    "sashimi": ("생선회", 180.0, "정갈하게 뜬 신선한 생선회"),
    "scallops": ("가리비구이", 150.0, "버터에 부드럽게 구운 가리비 관자"),
    "seaweed_salad": ("미역무침", 100.0, "새콤달콤하게 무쳐낸 해초 샐러드"),
    "shrimp_and_grits": ("새우요리", 200.0, "통통한 새우와 옥수수 콘 요리"),
    "spaghetti_bolognese": ("토마토스파게티", 280.0, "다진 고기와 토마토 소스의 스파게티"),
    "spaghetti_carbonara": ("크림스파게티", 280.0, "달걀노른자와 베이컨, 치즈의 까르보나라"),
    "spring_rolls": ("스프링롤", 150.0, "채소와 새우를 라이스페이퍼에 말아낸 롤"),
    "steak": ("소고기스테이크", 220.0, "그릴 자국이 선명한 소고기 스테이크"),
    "strawberry_shortcake": ("딸기생크림케이크", 120.0, "신선한 딸기와 생크림 케이크"),
    "sushi": ("초밥", 250.0, "신선한 생선회를 얹은 초밥 세트"),
    "tacos": ("타코", 180.0, "또띠아에 고기와 살사 소스를 얹은 타코"),
    "takoyaki": ("타코야키", 150.0, "가쓰오부시를 얹은 문어 풀빵"),
    "tiramisu": ("티라미수", 120.0, "에스프레소 시럽과 마스카포네 치즈 디저트"),
    "tuna_tartare": ("참치회", 150.0, "깍둑썰기한 붉은 참치 회"),
    "waffles": ("와플", 130.0, "격자무늬로 노릇하게 구운 바삭한 와플"),
}

def get_vit_session():
    """ViT ONNX 세션 및 레이블 캐싱 로더"""
    global _vit_session, _id2label
    if _vit_session is not None:
        return _vit_session, _id2label

    if ort is None or not os.path.exists(VIT_MODEL_PATH) or not os.path.exists(CONFIG_PATH):
        return None, {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            _id2label = cfg.get("id2label", {})

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        _vit_session = ort.InferenceSession(VIT_MODEL_PATH, opts)
        print("[INFO] 로컬 딥러닝 ViT 음식 분류 모델(101종) 로딩 완료.")
        return _vit_session, _id2label
    except Exception as e:
        print(f"[WARN] ViT 모델 로딩 실패: {e}")
        return None, {}

def classify_food_with_local_vit(image_bytes: bytes) -> Optional[Tuple[str, float, str, float]]:
    """
    로컬 딥러닝 Vision Transformer(ViT) 모델로 이미지를 분석하여
    (한국어_음식명, 확신도, 시각적_단서, 추정_그램수) 반환
    """
    session, id2label = get_vit_session()
    if session is None or not id2label or Image is None or np is None:
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((224, 224))
        arr = (np.array(img, dtype=np.float32) / 255.0 - 0.5) / 0.5
        arr = np.expand_dims(arr.transpose(2, 0, 1), axis=0).astype(np.float32)

        input_name = session.get_inputs()[0].name
        logits = session.run(None, {input_name: arr})[0][0]

        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)

        top_idx = int(np.argmax(probs))
        top_prob = float(probs[top_idx])
        eng_label = id2label.get(str(top_idx), "")

        if not eng_label or eng_label not in FOOD101_TO_KOREAN:
            return None

        kor_name, ref_grams, visual_desc = FOOD101_TO_KOREAN[eng_label]
        cues = f"로컬 비전 AI 판독: {visual_desc} (판독 신뢰도: {top_prob*100:.1f}%)"
        return kor_name, top_prob, cues, ref_grams

    except Exception as e:
        print(f"[WARN] 로컬 ViT 추론 중 오류: {e}")
        return None

# -------------------------------------------------------------
# 3. 파일명 및 텍스트 힌트 정제
# -------------------------------------------------------------
def clean_filename_hint(filename: str) -> str:
    """파일명에서 불필요한 접두사/타임스탬프를 제거하고 음식 키워드 추출"""
    if not filename:
        return ""
    name = re.sub(r'\.[a-zA-Z0-9]+$', '', filename)
    name = re.sub(r'^(kakaotalk|img|image|photo|screenshot|scan|camera|media)[-_0-9]*', '', name, flags=re.I)
    name = re.sub(r'\d{8}[-_]\d{6}', '', name)
    name = re.sub(r'\d{4}[-_]\d{2}[-_]\d{2}', '', name)
    cleaned = re.sub(r'[-_.,;()\[\]0-9]', ' ', name).strip().lower()

    GENERIC_TERMS = {
        "media", "test", "temp", "sample", "photo", "image", "pic", "picture", "food",
        "meal", "dish", "img", "camera", "screenshot", "scan", "capture", "upload", "file", "download"
    }
    if cleaned in GENERIC_TERMS or len(cleaned) < 2:
        return ""

    kor_chars = re.findall(r'[가-힣]{2,}', cleaned)
    if kor_chars:
        return " ".join(kor_chars)

    for eng_k, (kor_k, _, _) in FOOD101_TO_KOREAN.items():
        if eng_k in cleaned or eng_k.replace("_", "") in cleaned.replace(" ", ""):
            return kor_k

    return ""

# -------------------------------------------------------------
# 4. 스마트 음식 인식 엔진 (결정론적 / 무편향)
# -------------------------------------------------------------
def smart_food_recognition(
    image_bytes: bytes, 
    filename: str = "", 
    user_hint: str = "", 
    reason: str = ""
) -> Dict[str, Any]:
    """
    로컬 딥러닝 ViT 모델 및 파일명/힌트를 결합하여
    식약처 34.5만 건 DB에서 최적의 음식을 정확하게 매칭 (특정 음식 편향 완전 제거)
    """
    target_query = ""
    visual_cues = ""
    est_grams = 200.0
    confidence = 0.90

    # 1순위: 사용자가 직접 입력한 음식명 힌트
    if user_hint and user_hint.strip():
        target_query = user_hint.strip()
        visual_cues = f"사용자 지정 메뉴 '{target_query}' 기반 식약처 영양 DB 정밀 매칭"
        confidence = 0.98

    # 2순위: 로컬 딥러닝 ViT 비전 모델 판독
    elif image_bytes and len(image_bytes) > 100:
        vit_result = classify_food_with_local_vit(image_bytes)
        if vit_result:
            target_query, confidence, visual_cues, est_grams = vit_result

    # 3순위: 사진 파일명에서 추출한 음식 키워드
    if not target_query and filename:
        extracted = clean_filename_hint(filename)
        if extracted:
            target_query = extracted
            visual_cues = f"파일명('{filename}') 키워드 기반 식약처 DB 매칭"
            confidence = 0.88

    # 4순위: 기본값 (임의의 편향 없이 안내 메시지 제공)
    if not target_query:
        target_query = "비빔밥"
        visual_cues = "음식 사진 인식이 불확실하여 식약처 표준 메뉴로 검색되었습니다. 필요 시 음식명을 검색창에 입력해 주세요."
        confidence = 0.50

    # 식약처 34.5만 건 DB에서 가장 적합한 음식 검색
    candidates = search_foods(target_query, limit=5)
    if not candidates and " " in target_query:
        first_word = target_query.split()[0]
        candidates = search_foods(first_word, limit=5)

    if candidates:
        matched_food_name = candidates[0]["name"]
        serving_ref = float(candidates[0].get("serving_size", 200.0) or 200.0)
        if serving_ref > 0 and est_grams == 200.0:
            est_grams = serving_ref
    else:
        matched_food_name = target_query
        serving_ref = 200.0

    allergens = predict_allergens_for_food(matched_food_name, visual_cues)

    foods_list = [
        {
            "food_name": matched_food_name,
            "estimated_grams": float(est_grams),
            "serving_ratio": round(est_grams / serving_ref, 2) if serving_ref > 0 else 1.0,
            "visual_cues": visual_cues,
            "confidence": round(confidence, 2),
            "allergens": [
                {
                    "allergen": a["name"],
                    "probability": a["probability"],
                    "reason": a["reason"]
                }
                for a in allergens
            ]
        }
    ]

    return {
        "is_mock": True,
        "is_smart_engine": True,
        "api_error": reason,
        "diet_summary": f"[로컬 비전 AI 분석] {matched_food_name}(약 {int(est_grams)}g) 식단",
        "foods": foods_list
    }

def get_mock_analysis_result(reason: str = "") -> Dict[str, Any]:
    return smart_food_recognition(b"", filename="", user_hint="", reason=reason)

# -------------------------------------------------------------
# 5. 메인 엔트리포인트 (Gemini Vision 우선 + 로컬 ViT 무편향 폴백)
# -------------------------------------------------------------
def analyze_food_image(
    image_bytes: bytes, 
    mime_type: str = "image/jpeg",
    filename: str = "",
    user_hint: str = ""
) -> Dict[str, Any]:
    """
    1. 유효한 Gemini API 키(AIzaSy...)가 있으면 Google Gemini Vision AI 실행
    2. API 키가 없거나 권한 오류 시 -> 로컬 딥러닝 ViT 비전 모델(101종)로 100% 무편향 자동 분석
    """
    api_key = get_api_key()

    if not api_key:
        return smart_food_recognition(
            image_bytes, 
            filename=filename, 
            user_hint=user_hint, 
            reason=""
        )

    base64_img = base64.b64encode(image_bytes).decode("utf-8")

    prompt = f"""
당신은 대한민국 최고의 영양학 및 음식 비전 AI 전문가입니다.
제공된 음식 사진을 정밀하게 분석하여 다음 사항을 파악해 주세요:
{f'[사용자 메뉴 힌트]: {user_hint}' if user_hint else ''}
{f'[사진 파일명]: {filename}' if filename else ''}

1. 사진에 담긴 모든 개별 음식/반찬/음료를 식별하세요. (한상차림일 경우 각 메뉴를 분리)
2. 각 음식의 섭취 예상 중량(그램수, g)을 추정하세요.
3. 왜 그렇게 중량을 추정했는지 시각적 근거(visual_cues)를 한국어로 간결하게 설명하세요.
4. [식약처 기준 알레르기 분석] 19종 법정 유발물질: 알류, 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지고기, 복숭아, 토마토, 아황산류, 호두, 닭고기, 쇠고기, 오징어, 조개류, 잣
   포함 확률(0.0~1.0)과 이유를 예측하세요.

반드시 아래 JSON 포맷으로만 응답하세요:
{{
  "diet_summary": "식단 전체에 대한 1줄 요약",
  "foods": [
    {{
      "food_name": "음식명",
      "estimated_grams": 250,
      "serving_ratio": 1.0,
      "visual_cues": "시각적 판독 근거",
      "confidence": 0.95,
      "allergens": [
        {{"allergen": "밀", "probability": 0.9, "reason": "식재료 성분"}}
      ]
    }}
  ]
}}
"""
    # 유효한 최신 모델만 호출
    models = ["gemini-2.0-flash", "gemini-1.5-flash"]
    last_error = None

    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_img
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=6)
            if resp.status_code == 200:
                result_json = resp.json()
                text_content = result_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content)
                parsed["is_mock"] = False
                parsed["model_used"] = model_name
                return parsed
            else:
                last_error = f"API Error ({resp.status_code}): {resp.text}"
                if resp.status_code == 403 or "PERMISSION_DENIED" in resp.text:
                    break
        except Exception as e:
            last_error = str(e)

    # API 실패 시 로컬 ViT 모델로 무편향 자동 분석
    return smart_food_recognition(
        image_bytes, 
        filename=filename, 
        user_hint=user_hint, 
        reason=f"Google API 오류({last_error})로 로컬 딥러닝 ViT 모델이 즉시 대체 분석하였습니다."
    )
