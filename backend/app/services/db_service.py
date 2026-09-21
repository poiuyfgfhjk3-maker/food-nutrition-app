import sqlite3
import os
import re
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "nutrition.db")

# 한국인 영양소 섭취기준 (1일 권장섭취량 / 성인 남녀 평균 기준)
DAILY_RECOMMENDED = {
    "calories": 2000.0,       # kcal
    "carbohydrates": 130.0,   # g
    "protein": 55.0,          # g
    "fat": 50.0,              # g
    "sugar": 50.0,            # g (총당류 상한 10~20%)
    "sodium": 2000.0,         # mg (WHO/식약처 목표량)
    "fiber": 25.0,            # g (식이섬유)
    "calcium": 700.0,         # mg (칼슘)
    "iron": 12.0,             # mg (철)
    "magnesium": 315.0,       # mg (마그네슘)
    "potassium": 3500.0,      # mg (칼륨)
    "zinc": 8.5,              # mg (아연)
    "vitamin_a": 700.0,       # μg RAE (비타민 A)
    "vitamin_c": 100.0,       # mg (비타민 C)
    "vitamin_d": 10.0,        # μg (비타민 D)
    "folate": 400.0           # μg DFE (엽산)
}

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """SQLite 테이블 및 FTS5 전문 검색 가상 테이블 초기화 및 컬럼 마이그레이션"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_code TEXT,
            name TEXT NOT NULL,
            category TEXT,
            serving_size REAL NOT NULL DEFAULT 100.0,
            serving_unit TEXT DEFAULT 'g',
            calories REAL NOT NULL DEFAULT 0.0,
            carbohydrates REAL NOT NULL DEFAULT 0.0,
            protein REAL NOT NULL DEFAULT 0.0,
            fat REAL NOT NULL DEFAULT 0.0,
            sugar REAL NOT NULL DEFAULT 0.0,
            sodium REAL NOT NULL DEFAULT 0.0,
            cholesterol REAL NOT NULL DEFAULT 0.0,
            saturated_fat REAL NOT NULL DEFAULT 0.0,
            trans_fat REAL NOT NULL DEFAULT 0.0,
            fiber REAL NOT NULL DEFAULT 0.0,
            calcium REAL NOT NULL DEFAULT 0.0,
            iron REAL NOT NULL DEFAULT 0.0,
            magnesium REAL NOT NULL DEFAULT 0.0,
            potassium REAL NOT NULL DEFAULT 0.0,
            zinc REAL NOT NULL DEFAULT 0.0,
            vitamin_a REAL NOT NULL DEFAULT 0.0,
            vitamin_c REAL NOT NULL DEFAULT 0.0,
            vitamin_d REAL NOT NULL DEFAULT 0.0,
            folate REAL NOT NULL DEFAULT 0.0,
            source TEXT DEFAULT '식약처'
        );
    """)

    # 기존 테이블이 이미 있을 경우 무기질/비타민 컬럼 자동 마이그레이션
    cursor.execute("PRAGMA table_info(foods)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    new_cols = [
        ("fiber", "REAL NOT NULL DEFAULT 0.0"),
        ("calcium", "REAL NOT NULL DEFAULT 0.0"),
        ("iron", "REAL NOT NULL DEFAULT 0.0"),
        ("magnesium", "REAL NOT NULL DEFAULT 0.0"),
        ("potassium", "REAL NOT NULL DEFAULT 0.0"),
        ("zinc", "REAL NOT NULL DEFAULT 0.0"),
        ("vitamin_a", "REAL NOT NULL DEFAULT 0.0"),
        ("vitamin_c", "REAL NOT NULL DEFAULT 0.0"),
        ("vitamin_d", "REAL NOT NULL DEFAULT 0.0"),
        ("folate", "REAL NOT NULL DEFAULT 0.0"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE foods ADD COLUMN {col_name} {col_type}")

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS foods_fts USING fts5(
            name,
            category,
            content='foods',
            content_rowid='id'
        );
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS foods_ai AFTER INSERT ON foods BEGIN
            INSERT INTO foods_fts(rowid, name, category) VALUES (new.id, new.name, new.category);
        END;
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS foods_ad AFTER DELETE ON foods BEGIN
            INSERT INTO foods_fts(foods_fts, rowid, name, category) VALUES('delete', old.id, old.name, old.category);
        END;
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS foods_au AFTER UPDATE ON foods BEGIN
            INSERT INTO foods_fts(foods_fts, rowid, name, category) VALUES('delete', old.id, old.name, old.category);
            INSERT INTO foods_fts(rowid, name, category) VALUES (new.id, new.name, new.category);
        END;
    """)

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM foods")
    count = cursor.fetchone()[0]
    if count == 0:
        seed_korean_foods(conn)

    conn.close()

def seed_korean_foods(conn: sqlite3.Connection):
    cursor = conn.cursor()
    sample_foods = [
        # 밥류
        ("쌀밥", "밥류", 210.0, 304.5, 68.2, 5.7, 0.6, 0.0, 3.2, 0.0, 0.1, 0.0, 1.3, 6.3, 0.4, 31.5, 73.5, 1.1, 0.0, 0.0, 0.0, 6.3),
        ("현미밥", "밥류", 210.0, 321.0, 68.0, 6.5, 2.5, 0.0, 2.5, 0.0, 0.5, 0.0, 3.2, 18.9, 1.5, 75.6, 180.0, 1.8, 0.0, 0.0, 0.0, 16.8),
        ("김치찌개", "찌개류", 300.0, 180.0, 12.0, 14.0, 8.5, 4.0, 1250.0, 25.0, 2.5, 0.0, 3.8, 65.0, 2.1, 38.0, 480.0, 1.2, 85.0, 18.5, 0.2, 45.0),
        ("된장찌개", "찌개류", 300.0, 145.0, 14.0, 11.0, 5.0, 3.5, 1150.0, 10.0, 1.2, 0.0, 4.2, 95.0, 1.8, 42.0, 520.0, 1.5, 42.0, 8.0, 0.1, 38.0),
        ("계란말이", "달걀류", 100.0, 160.0, 3.2, 11.0, 11.5, 1.5, 340.0, 260.0, 3.5, 0.1, 0.2, 58.0, 1.9, 14.0, 160.0, 1.3, 140.0, 0.0, 1.8, 35.0),
        ("시금치나물", "나물류", 70.0, 45.0, 4.0, 2.8, 2.1, 0.5, 210.0, 0.0, 0.3, 0.0, 2.5, 98.0, 2.4, 35.0, 360.0, 0.8, 380.0, 28.0, 0.0, 110.0),
        ("삼겹살구이", "구이류", 200.0, 660.0, 0.0, 34.0, 58.0, 0.0, 160.0, 110.0, 20.0, 0.6, 0.0, 12.0, 1.6, 32.0, 380.0, 3.8, 6.0, 0.0, 0.5, 8.0),
        ("닭가슴살구이", "구이류", 100.0, 120.0, 0.0, 26.0, 1.5, 0.0, 85.0, 65.0, 0.4, 0.0, 0.0, 15.0, 0.8, 28.0, 260.0, 1.0, 4.0, 0.0, 0.1, 5.0),
        ("배추김치", "김치류", 50.0, 15.0, 2.5, 1.0, 0.3, 1.2, 340.0, 0.0, 0.05, 0.0, 1.2, 32.0, 0.6, 12.0, 140.0, 0.3, 45.0, 8.5, 0.0, 22.0),
        ("사과", "과일", 250.0, 130.0, 34.0, 0.6, 0.4, 26.0, 2.0, 0.0, 0.1, 0.0, 4.5, 12.0, 0.3, 15.0, 270.0, 0.1, 8.0, 12.0, 0.0, 7.5),
        ("우유", "유제품", 200.0, 130.0, 9.5, 6.4, 7.2, 9.0, 100.0, 20.0, 4.5, 0.2, 0.0, 210.0, 0.1, 24.0, 320.0, 0.8, 75.0, 2.0, 1.2, 10.0),
    ]

    cursor.executemany("""
        INSERT INTO foods (
            name, category, serving_size, calories, carbohydrates, protein, fat, sugar, sodium,
            cholesterol, saturated_fat, trans_fat,
            fiber, calcium, iron, magnesium, potassium, zinc, vitamin_a, vitamin_c, vitamin_d, folate
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sample_foods)
    conn.commit()

def search_foods(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    # 음식 DB 및 국가표준식품성분표(비타민/무기질 풍부) 최우선 정렬
    order_clause = """
        ORDER BY 
            CASE 
                WHEN source LIKE '%음식DB%' THEN 1
                WHEN source LIKE '%식품성분표%' THEN 2
                WHEN source LIKE '%가공식품%' THEN 3
                ELSE 4 
            END,
            LENGTH(name) ASC
    """

    # 1. 완전 일치 우선
    cursor.execute(f"""
        SELECT * FROM foods WHERE name = ? {order_clause} LIMIT ?
    """, (cleaned_query, limit))
    exact_matches = [dict(row) for row in cursor.fetchall()]

    # 2. 부분 일치 검색
    cursor.execute(f"""
        SELECT * FROM foods WHERE name LIKE ? {order_clause} LIMIT ?
    """, (f"%{cleaned_query}%", limit))
    like_matches = [dict(row) for row in cursor.fetchall()]

    # 3. FTS5 검색 시도
    fts_term = re.sub(r'[^\w\s]', '', cleaned_query).strip()
    fts_matches = []
    if fts_term:
        try:
            cursor.execute(f"""
                SELECT f.* FROM foods f
                JOIN foods_fts fts ON f.id = fts.rowid
                WHERE foods_fts MATCH ?
                {order_clause.replace('source', 'f.source').replace('name', 'f.name')}
                LIMIT ?
            """, (f"{fts_term}*", limit))
            fts_matches = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            pass

    # 중복 제거 및 우선순위 정렬 (exact -> like -> fts)
    seen_ids = set()
    results = []
    for item in exact_matches + like_matches + fts_matches:
        if item["id"] not in seen_ids:
            seen_ids.add(item["id"])
            results.append(item)
            if len(results) >= limit:
                break

    conn.close()
    return results

def get_food_by_id(food_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM foods WHERE id = ?", (food_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def calculate_nutrition(food_data: Dict[str, Any], grams: float) -> Dict[str, Any]:
    """
    기준 중량(1회 제공량 g) 대비 실제 섭취 중량(g)에 비례하여
    칼로리, 탄단지, 무기질, 비타민을 정밀 계산하고,
    할루시네이션이 아님을 수학적으로 증명하는 단계별 계산 근거(Proof Breakdown)를 함께 생성
    """
    serving_size = food_data.get("serving_size", 100.0)
    if serving_size <= 0:
        serving_size = 100.0

    ratio = grams / serving_size

    # 기본 매크로 영양소
    calories = round(food_data.get("calories", 0.0) * ratio, 1)
    carbs = round(food_data.get("carbohydrates", 0.0) * ratio, 1)
    protein = round(food_data.get("protein", 0.0) * ratio, 1)
    fat = round(food_data.get("fat", 0.0) * ratio, 1)
    sugar = round(food_data.get("sugar", 0.0) * ratio, 1)
    sodium = round(food_data.get("sodium", 0.0) * ratio, 1)
    cholesterol = round(food_data.get("cholesterol", 0.0) * ratio, 1)
    sat_fat = round(food_data.get("saturated_fat", 0.0) * ratio, 1)
    trans_fat = round(food_data.get("trans_fat", 0.0) * ratio, 1)

    # 주요 무기질
    calcium = round(food_data.get("calcium", 0.0) * ratio, 1)
    iron = round(food_data.get("iron", 0.0) * ratio, 2)
    magnesium = round(food_data.get("magnesium", 0.0) * ratio, 1)
    potassium = round(food_data.get("potassium", 0.0) * ratio, 1)
    zinc = round(food_data.get("zinc", 0.0) * ratio, 2)

    # 주요 비타민 및 식이섬유
    fiber = round(food_data.get("fiber", 0.0) * ratio, 1)
    vitamin_a = round(food_data.get("vitamin_a", 0.0) * ratio, 1)
    vitamin_c = round(food_data.get("vitamin_c", 0.0) * ratio, 1)
    vitamin_d = round(food_data.get("vitamin_d", 0.0) * ratio, 2)
    folate = round(food_data.get("folate", 0.0) * ratio, 1)

    # 한국인 1일 영양소 기준치 대비 %
    dv_percentages = {
        "calories": round((calories / DAILY_RECOMMENDED["calories"]) * 100, 1),
        "carbohydrates": round((carbs / DAILY_RECOMMENDED["carbohydrates"]) * 100, 1),
        "protein": round((protein / DAILY_RECOMMENDED["protein"]) * 100, 1),
        "fat": round((fat / DAILY_RECOMMENDED["fat"]) * 100, 1),
        "sugar": round((sugar / DAILY_RECOMMENDED["sugar"]) * 100, 1),
        "sodium": round((sodium / DAILY_RECOMMENDED["sodium"]) * 100, 1),
        "fiber": round((fiber / DAILY_RECOMMENDED["fiber"]) * 100, 1),
        "calcium": round((calcium / DAILY_RECOMMENDED["calcium"]) * 100, 1),
        "iron": round((iron / DAILY_RECOMMENDED["iron"]) * 100, 1),
        "magnesium": round((magnesium / DAILY_RECOMMENDED["magnesium"]) * 100, 1),
        "potassium": round((potassium / DAILY_RECOMMENDED["potassium"]) * 100, 1),
        "zinc": round((zinc / DAILY_RECOMMENDED["zinc"]) * 100, 1),
        "vitamin_a": round((vitamin_a / DAILY_RECOMMENDED["vitamin_a"]) * 100, 1),
        "vitamin_c": round((vitamin_c / DAILY_RECOMMENDED["vitamin_c"]) * 100, 1),
        "vitamin_d": round((vitamin_d / DAILY_RECOMMENDED["vitamin_d"]) * 100, 1),
        "folate": round((folate / DAILY_RECOMMENDED["folate"]) * 100, 1)
    }

    # 할루시네이션 방지 및 투명성 검증용 단계별 수식 분해 (Proof Breakdown)
    def make_proof(name_kr, raw_val, unit, calc_val):
        raw = round(float(raw_val or 0.0), 2)
        return {
            "name": name_kr,
            "raw_db_val": raw,
            "unit": unit,
            "calculated_val": calc_val,
            "equation": f"{raw}{unit} × ({grams}g ÷ {serving_size}g) = {raw}{unit} × {round(ratio, 3)}배 = {calc_val}{unit}"
        }

    proofs = [
        make_proof("열량", food_data.get("calories"), "kcal", calories),
        make_proof("탄수화물", food_data.get("carbohydrates"), "g", carbs),
        make_proof("단백질", food_data.get("protein"), "g", protein),
        make_proof("지방", food_data.get("fat"), "g", fat),
        make_proof("당류", food_data.get("sugar"), "g", sugar),
        make_proof("나트륨", food_data.get("sodium"), "mg", sodium),
        make_proof("식이섬유", food_data.get("fiber"), "g", fiber),
        make_proof("칼슘", food_data.get("calcium"), "mg", calcium),
        make_proof("철분", food_data.get("iron"), "mg", iron),
        make_proof("마그네슘", food_data.get("magnesium"), "mg", magnesium),
        make_proof("칼륨", food_data.get("potassium"), "mg", potassium),
        make_proof("아연", food_data.get("zinc"), "mg", zinc),
        make_proof("비타민 A", food_data.get("vitamin_a"), "μg", vitamin_a),
        make_proof("비타민 C", food_data.get("vitamin_c"), "mg", vitamin_c),
        make_proof("비타민 D", food_data.get("vitamin_d"), "μg", vitamin_d),
        make_proof("엽산", food_data.get("folate"), "μg", folate),
    ]

    return {
        "food_id": food_data.get("id"),
        "name": food_data.get("name"),
        "food_code": food_data.get("food_code") or f"DB-{food_data.get('id')}",
        "category": food_data.get("category", "기타"),
        "source": food_data.get("source", "식품의약품안전처"),
        "serving_size_ref": round(serving_size, 1),
        "consumed_grams": round(grams, 1),
        "serving_ratio": round(ratio, 3),
        "calories": calories,
        "carbohydrates": carbs,
        "protein": protein,
        "fat": fat,
        "sugar": sugar,
        "sodium": sodium,
        "cholesterol": cholesterol,
        "saturated_fat": sat_fat,
        "trans_fat": trans_fat,
        "minerals": {
            "calcium": calcium,
            "iron": iron,
            "magnesium": magnesium,
            "potassium": potassium,
            "zinc": zinc
        },
        "vitamins": {
            "fiber": fiber,
            "vitamin_a": vitamin_a,
            "vitamin_c": vitamin_c,
            "vitamin_d": vitamin_d,
            "folate": folate
        },
        "dv_percentages": dv_percentages,
        "proof_breakdown": {
            "formula": "최종 영양성분 = 식약처 DB 원본 수치 × (섭취 중량 ÷ 1회 기준량)",
            "serving_size_ref": serving_size,
            "consumed_grams": grams,
            "ratio_multiplier": round(ratio, 3),
            "source_document": food_data.get("source", "식품의약품안전처 영양성분DB"),
            "items": proofs
        }
    }

def get_database_stats() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM foods")
    total_count = cursor.fetchone()[0]
    cursor.execute("SELECT category, COUNT(*) as cnt FROM foods GROUP BY category ORDER BY cnt DESC LIMIT 5")
    top_categories = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {
        "total_foods": total_count,
        "top_categories": top_categories
    }
