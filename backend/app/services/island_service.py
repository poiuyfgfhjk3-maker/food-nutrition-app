"""
Nutri-Island: 청소년/아동 맞춤 게이미피케이션 서비스 모듈
- 대상: 초등학생 ~ 중학생 (9~14세)
- 기능:
  1. 성장기 맞춤 영양 기준치(KDRIs) 적용
  2. 식단 영양소 기반 수호 크리처(Guardian) 배정
  3. 4대 핵심 자연 환경(하늘, 바위산, 꽃밭, 바다) 상태 판정
  4. 환경 터치 인터랙션: 원인 진단 & 식약처 DB 기반 다음 식단 추천
"""

from typing import Dict, List, Any, Optional
from app.services.db_service import search_foods, DAILY_RECOMMENDED

# 한국인 영양소 섭취기준 (KDRIs 9~14세 성장기 평균 기준)
YOUTH_RECOMMENDED = {
    "calories": 2000.0,       # 1일 권장 열량 (kcal)
    "carbohydrates": 270.0,   # 탄수화물 (g)
    "protein": 50.0,          # 단백질 (g)
    "fat": 50.0,              # 지방 (g)
    "sugar": 35.0,            # 총 당류 권장 상한 (g)
    "sodium": 1500.0,         # 나트륨 충분 섭취량 (mg)
    "calcium": 800.0,         # 칼슘 (mg)
    "iron": 12.0,             # 철분 (mg)
    "magnesium": 220.0,       # 마그네슘 (mg)
    "potassium": 2800.0,      # 칼륨 (mg)
    "zinc": 8.0,              # 아연 (mg)
    "fiber": 20.0,            # 식이섬유 (g)
    "vitamin_a": 600.0,       # 비타민 A (mcg RAE)
    "vitamin_c": 90.0,        # 비타민 C (mg)
    "vitamin_d": 10.0,        # 비타민 D (mcg)
    "folate": 350.0           # 엽산 (mcg DFE)
}

GUARDIANS = {
    "bear": {
        "id": "bear",
        "name": "가디언 베어",
        "role": "단백질 수호자",
        "emoji": "🐻",
        "color": "#e67e22",
        "title": "단단한 근육과 성장 파워",
        "description": "성장기 근육 형성과 신체 조직 강화에 필수적인 단백질을 공급받아 힘차게 활동합니다.",
        "quote": "단백질 파워 충전 완료! 튼튼한 바위산과 건강한 체력을 지켜줄게요."
    },
    "giraffe": {
        "id": "giraffe",
        "name": "가디언 지니",
        "role": "칼슘 & 골격 수호자",
        "emoji": "🦒",
        "color": "#f1c40f",
        "title": "쑥쑥 자라는 키와 단단한 뼈",
        "description": "키 성장과 단단한 치아, 골격 형성을 돕는 칼슘과 비타민D를 지켜줍니다.",
        "quote": "칼슘이 꽉 찼네요! 키가 쑥쑥 자라고 뼈가 더욱 튼튼해지는 신호예요."
    },
    "rabbit": {
        "id": "rabbit",
        "name": "가디언 토토",
        "role": "비타민 & 면역 수호자",
        "emoji": "🐰",
        "color": "#2ecc71",
        "title": "감기 예방과 건강한 피부",
        "description": "다양한 채소의 비타민A, C와 장 건강을 돕는 식이섬유를 바탕으로 섬의 숲을 피워냅니다.",
        "quote": "신선한 채소와 비타민의 힘! 면역 방패가 생겨 피로와 감기를 막아줘요."
    },
    "squirrel": {
        "id": "squirrel",
        "name": "가디언 도치",
        "role": "에너지 & 두뇌 수호자",
        "emoji": "🐿️",
        "color": "#e74c3c",
        "title": "하루를 신나게 달리는 활력",
        "description": "두뇌 회전과 활동에 필요한 깨끗한 탄수화물 복합 에너지를 공급받습니다.",
        "quote": "두뇌 활력 충전 완료! 공부할 때도, 뛰어놀 때도 지치지 않는 에너지예요."
    },
    "parrot": {
        "id": "parrot",
        "name": "가디언 피코",
        "role": "항산화 & 활력 수호자",
        "emoji": "🦜",
        "color": "#9b59b6",
        "title": "피로를 날리는 상큼한 비타민C",
        "description": "신선한 과일에서 얻는 비타민C로 활성산소를 줄이고 상쾌한 기분을 돕습니다.",
        "quote": "상큼한 과일 향기 가득! 지친 몸에 활력을 불어넣는 날갯짓이에요."
    },
    "hedgehog": {
        "id": "hedgehog",
        "name": "가디언 포키",
        "role": "영양 균형 감시자",
        "emoji": "🦔",
        "color": "#34495e",
        "title": "당류와 나트륨 주의 경보",
        "description": "당류나 나트륨이 일시적으로 높을 때 나타나, 수분 섭취와 신선식품 조화를 조언합니다.",
        "quote": "당분이나 염분이 조금 높았어요. 시원한 물 한 컵으로 몸의 밸런스를 맞춰주세요."
    }
}

def determine_guardian(nutrition: Dict[str, Any]) -> Dict[str, Any]:
    """식단 영양 분석 결과를 바탕으로 최적의 수호 크리처를 배정합니다."""
    protein = float(nutrition.get("protein", 0))
    calcium = float(nutrition.get("minerals", {}).get("calcium", 0))
    vit_c = float(nutrition.get("vitamins", {}).get("vitamin_c", 0))
    fiber = float(nutrition.get("vitamins", {}).get("fiber", 0))
    carbs = float(nutrition.get("carbohydrates", 0))
    sugar = float(nutrition.get("sugar", 0))
    sodium = float(nutrition.get("sodium", 0))

    # 1. 당류 과잉(20g 초과) 또는 나트륨 과잉(800mg 초과) 시 포키 등장
    if sugar > 20.0 or sodium > 800.0:
        guardian = GUARDIANS["hedgehog"].copy()
        if sugar > 20.0 and sodium > 800.0:
            guardian["custom_message"] = "당류와 나트륨이 다소 높게 측정되었어요. 물을 충분히 마셔 체내 균형을 찾아주세요."
        elif sugar > 20.0:
            guardian["custom_message"] = "단순 당류 비중이 높았습니다. 급격한 혈당 변화를 막기 위해 수분을 보충해 주세요."
        else:
            guardian["custom_message"] = "나트륨(염분)이 높았어요. 물을 마시고 다음 끼니에는 칼륨이 풍부한 채소를 추천해요."
        return guardian

    # 2. 비율 기반 점수 산정 (KDRIs 1회 평균 목표치 대비 달성도)
    scores = {
        "bear": protein / (YOUTH_RECOMMENDED["protein"] * 0.3),
        "giraffe": calcium / (YOUTH_RECOMMENDED["calcium"] * 0.3),
        "parrot": vit_c / (YOUTH_RECOMMENDED["vitamin_c"] * 0.3),
        "rabbit": fiber / (YOUTH_RECOMMENDED["fiber"] * 0.3),
        "squirrel": carbs / (YOUTH_RECOMMENDED["carbohydrates"] * 0.3)
    }

    best_key = max(scores, key=scores.get)
    best_guardian = GUARDIANS[best_key].copy()

    if best_key == "bear":
        best_guardian["custom_message"] = f"단백질 {protein:.1f}g 섭취! 성장기 뼈와 근육이 튼튼하게 자라나고 있습니다."
    elif best_key == "giraffe":
        best_guardian["custom_message"] = f"칼슘 {calcium:.1f}mg 충전! 키 성장과 단단한 치아 형성에 큰 힘이 됩니다."
    elif best_key == "parrot":
        best_guardian["custom_message"] = f"비타민 C {vit_c:.1f}mg 공급! 상큼한 활력으로 피로를 깨끗이 씻어내요."
    elif best_key == "rabbit":
        best_guardian["custom_message"] = f"식이섬유 {fiber:.1f}g 섭취! 소화가 원활해지고 장 건강이 강화됩니다."
    else:
        best_guardian["custom_message"] = f"활동 에너지 {carbs:.1f}g 충전! 오늘 하루 신체 활동과 학업에 집중할 수 있어요."

    return best_guardian

def calculate_island_environment(cumulative_nutrition: Dict[str, Any], meal_count: int = 1) -> Dict[str, Any]:
    """오늘 누적 영양 데이터를 바탕으로 4대 자연 환경의 상태를 판정합니다."""
    c = cumulative_nutrition
    target_ratio = min(1.0, max(0.25, meal_count * 0.28))

    cal_ratio = c.get("calories", 0) / (YOUTH_RECOMMENDED["calories"] * target_ratio)
    carb_ratio = c.get("carbohydrates", 0) / (YOUTH_RECOMMENDED["carbohydrates"] * target_ratio)
    protein_ratio = c.get("protein", 0) / (YOUTH_RECOMMENDED["protein"] * target_ratio)
    calcium_val = c.get("minerals", {}).get("calcium", 0)
    calcium_ratio = calcium_val / (YOUTH_RECOMMENDED["calcium"] * target_ratio)
    fiber_val = c.get("vitamins", {}).get("fiber", 0)
    vit_c_val = c.get("vitamins", {}).get("vitamin_c", 0)
    vitamin_ratio = (vit_c_val / (YOUTH_RECOMMENDED["vitamin_c"] * target_ratio) + fiber_val / (YOUTH_RECOMMENDED["fiber"] * target_ratio)) / 2
    sugar_val = c.get("sugar", 0)
    sodium_val = c.get("sodium", 0)

    # 1. 하늘 & 태양 (에너지)
    if meal_count == 0:
        sun_state = "sunny"
        sun_desc = "아직 식단이 기록되기 전의 평화롭고 따스한 기본 햇살이 섬을 비추고 있습니다."
    elif carb_ratio < 0.6:
        sun_state = "low"
        sun_desc = "활동 에너지(탄수화물)가 조금 부족하여 해님의 빛이 은은해요. 든든한 통곡물이나 밥을 보충해 보세요."
    elif carb_ratio > 1.5:
        sun_state = "heat"
        sun_desc = "열량과 탄수화물이 다소 높아 해님이 이글거려요! 신나게 운동하여 에너지를 발산해 보세요."
    else:
        sun_state = "sunny"
        sun_desc = "적정 에너지를 공급받아 황금빛 해님이 섬 전체를 따스하게 비추고 있습니다!"

    # 2. 하늘 날씨 & 구름 (당류)
    if meal_count == 0:
        cloud_state = "clear"
        cloud_desc = "하늘에 몽실몽실 하얀 뭉게구름이 평화롭게 떠다닙니다."
    elif sugar_val > (YOUTH_RECOMMENDED["sugar"] * 0.8):
        cloud_state = "storm"
        cloud_desc = "단순 당류 섭취가 높아 보랏빛 번개구름이 발생했어요! 물을 충분히 마시고 과자 대신 신선한 과일을 선택해 보세요."
    elif sugar_val < 18.0 and meal_count >= 1:
        cloud_state = "rainbow"
        cloud_desc = "당류 밸런스가 매우 우수합니다! 맑게 갠 하늘에 7색 무지개가 선명하게 떠올랐어요."
    else:
        cloud_state = "clear"
        cloud_desc = "하늘에 몽실몽실 하얀 뭉게구름이 평화롭게 떠다닙니다."

    # 3. 중앙 바위산 (단백질 & 칼슘)
    mountain_score = (protein_ratio + calcium_ratio) / 2
    if meal_count == 0:
        mountain_state = "normal"
        mountain_desc = "기본 형태의 든든한 바위산입니다. 고기, 생선, 달걀, 우유를 골고루 먹으면 더욱 높고 웅장해지며 황금 수정이 빛납니다!"
    elif mountain_score >= 0.7:
        mountain_state = "solid"
        mountain_desc = "단백질과 칼슘이 풍부하여 바위산이 높고 견고하게 솟았으며, 황금 수정이 단단하게 빛납니다!"
    else:
        mountain_state = "weak"
        mountain_desc = "단백질과 칼슘이 다소 부족하여 바위산이 낮고 흙언덕 상태입니다. 달걀, 두부, 생선, 우유를 보충해 주면 단단해집니다."

    # 4. 대지 & 꽃밭 (비타민 & 식이섬유)
    if meal_count == 0:
        meadow_state = "normal"
        meadow_desc = "싱그러운 초록 잔디가 깔린 기본 들판입니다. 신선한 채소와 과일을 먹으면 알록달록 무지개 꽃밭이 만개합니다!"
    elif vitamin_ratio >= 0.7:
        meadow_state = "blooming"
        meadow_desc = "비타민과 식이섬유가 듬뿍 공급되어 알록달록 꽃들이 활짝 피고 싱그러운 초록 숲이 우거졌습니다!"
    else:
        meadow_state = "wilted"
        meadow_desc = "채소와 비타민 섭취가 부족하여 꽃들이 아직 피어나지 못했어요. 신선한 나물이나 채소를 섭취해 보세요."

    # 5. 해변 바다 (나트륨)
    if meal_count == 0 or sodium_val <= (YOUTH_RECOMMENDED["sodium"] * 0.75):
        ocean_state = "calm"
        ocean_desc = "염분 농도가 안정적입니다! 잔잔하고 투명한 에메랄드빛 바다가 모래사장을 부드럽게 감싸고 있어요."
    else:
        ocean_state = "flooded"
        ocean_desc = "나트륨(염분) 섭취가 기준치보다 높아 바닷물이 차오르고 파도가 거세졌어요. 물을 마셔 수분을 조절해 주세요."

    return {
        "sun_state": sun_state,
        "cloud_state": cloud_state,
        "mountain_state": mountain_state,
        "meadow_state": meadow_state,
        "ocean_state": ocean_state,
        "details": {
            "sun": {
                "title": "하늘 & 태양 에너지",
                "status": "정상" if sun_state == "sunny" else ("주의" if sun_state == "heat" else "보충 필요"),
                "description": sun_desc,
                "nutrient": f"탄수화물 {c.get('carbohydrates', 0):.1f}g / {YOUTH_RECOMMENDED['carbohydrates']:.0f}g",
                "recommendations": get_db_recommendations("carbohydrate", sun_state)
            },
            "cloud": {
                "title": "기상 날씨 & 당류 지수",
                "status": "경보" if cloud_state == "storm" else ("최상" if cloud_state == "rainbow" else "안정"),
                "description": cloud_desc,
                "nutrient": f"당류 {sugar_val:.1f}g (상한 {YOUTH_RECOMMENDED['sugar']:.0f}g)",
                "recommendations": get_db_recommendations("sugar", cloud_state)
            },
            "mountain": {
                "title": "중앙 튼튼 바위산",
                "status": "견고함" if mountain_state == "solid" else "보강 필요",
                "description": mountain_desc,
                "nutrient": f"단백질 {c.get('protein', 0):.1f}g, 칼슘 {calcium_val:.1f}mg",
                "recommendations": get_db_recommendations("protein", mountain_state)
            },
            "meadow": {
                "title": "대지 & 만개한 정원",
                "status": "만개함" if meadow_state == "blooming" else "성장 필요",
                "description": meadow_desc,
                "nutrient": f"식이섬유 {fiber_val:.1f}g, 비타민C {vit_c_val:.1f}mg",
                "recommendations": get_db_recommendations("vitamin", meadow_state)
            },
            "ocean": {
                "title": "해변 & 에메랄드 바다",
                "status": "주의" if ocean_state == "flooded" else "청정",
                "description": ocean_desc,
                "nutrient": f"나트륨 {sodium_val:.1f}mg (권장 {YOUTH_RECOMMENDED['sodium']:.0f}mg)",
                "recommendations": get_db_recommendations("sodium", ocean_state)
            }
        }
    }

def get_db_recommendations(nutrient_type: str, state: str) -> List[Dict[str, str]]:
    """식약처 34.5만 건 DB 기반 맞춤 추천 음식 선별"""
    recommendations = []
    
    if nutrient_type == "protein":
        if state == "weak":
            items = search_foods("달걀말이", limit=1) + search_foods("두부조림", limit=1) + search_foods("닭가슴살", limit=1)
            for item in items:
                recommendations.append({
                    "food_name": item.get("name", "고단백 반찬"),
                    "tip": f"단백질 {item.get('protein', 0):.1f}g 함유! 바위산을 단단하게 세워줍니다."
                })
        else:
            recommendations.append({"food_name": "현재 견고한 상태!", "tip": "생선, 두부, 육류를 고르게 섭취해 유지하세요."})

    elif nutrient_type == "vitamin":
        if state == "wilted":
            items = search_foods("시금치나물", limit=1) + search_foods("방울토마토", limit=1) + search_foods("브로콜리", limit=1)
            for item in items:
                recommendations.append({
                    "food_name": item.get("name", "신선 채소"),
                    "tip": "비타민과 식이섬유가 풍부하여 숲과 꽃밭을 활짝 피워줍니다."
                })
        else:
            recommendations.append({"food_name": "정원이 만개했습니다!", "tip": "신선한 채소와 과일로 면역 장벽을 계속 유지해 보세요."})

    elif nutrient_type == "sugar":
        if state == "storm":
            recommendations = [
                {"food_name": "시원한 생수 1~2컵", "tip": "체내 당 농도를 희석하고 신진대사를 도와 번개구름을 걷어냅니다."},
                {"food_name": "플레인 그릭요거트", "tip": "가공 젤리나 탄산음료 대신 당이 낮은 요거트를 추천해요."}
            ]
        else:
            recommendations.append({"food_name": "맑은 하늘 유지 중!", "tip": "당류 섭취가 절제되어 집중력이 안정적으로 유지됩니다."})

    elif nutrient_type == "sodium":
        if state == "flooded":
            items = search_foods("바나나", limit=1) + search_foods("오이", limit=1)
            for item in items:
                recommendations.append({
                    "food_name": item.get("name", "칼륨 식품"),
                    "tip": "칼륨이 풍부하여 체내 과잉 염분(나트륨) 배출을 돕습니다."
                })
        else:
            recommendations.append({"food_name": "잔잔한 청정 바다!", "tip": "염분 밸런스가 좋아 몸이 붓지 않고 가볍습니다."})

    elif nutrient_type == "carbohydrate":
        if state == "low":
            items = search_foods("현미밥", limit=1) + search_foods("고구마", limit=1)
            for item in items:
                recommendations.append({
                    "food_name": item.get("name", "복합 탄수화물"),
                    "tip": "두뇌에 지속적인 에너지를 주어 집중력을 끌어올립니다."
                })
        else:
            recommendations.append({"food_name": "적정 활력 유지 중!", "tip": "충분한 에너지로 신나게 활동할 수 있습니다."})

    return recommendations[:3]

def get_next_meal_advice(meal_type: str, current_nutrition: Dict[str, Any]) -> str:
    """끼니 카테고리에 따른 다음 식단 맞춤 조언 생성"""
    prot = current_nutrition.get("protein", 0)
    fiber = current_nutrition.get("vitamins", {}).get("fiber", 0)
    sugar = current_nutrition.get("sugar", 0)

    if meal_type == "breakfast":
        next_meal = "점심"
    elif meal_type == "lunch":
        next_meal = "저녁"
    elif meal_type == "dinner":
        next_meal = "내일 아침"
    else:
        next_meal = "다음 식사"

    if fiber < 3.0:
        return f"{next_meal}에는 시금치나 샐러드 등 신선한 채소를 한 접시 곁들이면 정원이 더욱 푸르러질 거예요."
    elif prot < 10.0:
        return f"{next_meal}에는 달걀찜이나 생선구이, 두부 요리로 단백질을 보충해 주면 바위산이 더 견고해집니다."
    elif sugar > 15.0:
        return f"{next_meal} 전까지 물을 1~2컵 천천히 마셔주면 보랏빛 사탕 구름이 빠르게 정화됩니다."
    else:
        return f"현재 영양 밸런스가 매우 훌륭합니다! {next_meal}에도 균형 잡힌 식단을 이어가 보세요."
