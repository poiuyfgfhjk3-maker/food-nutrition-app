"""
식품의약품안전처 및 농촌진흥청 영양성분 DB 엑셀(.xlsx) 고속 자동 임포터 (v3.0)
- 탄/단/지/당/나트륨뿐만 아니라,
  주요 무기질(칼슘, 철, 마그네슘, 칼륨, 아연) 및 주요 비타민(비타민 A, C, D, 엽산, 식이섬유)을 완벽 지원합니다.
"""

import os
import sys
import glob
import re
import sqlite3
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "nutrition.db")
RAW_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "raw")

COLUMN_MAPPINGS = {
    "name": [
        "식품명", "식품이름", "음식명", "식품명_한글", "FOOD_NM_KR", "SAMPLE_NAME", 
        "식품상세명칭", "메뉴명", "품목명"
    ],
    "category": [
        "식품군", "식품대분류", "식품중분류", "대분류", "카테고리", "DB_GRP_NM", 
        "FOOD_CAT_NM", "식품분류", "식품대분류명"
    ],
    "food_code": [
        "식품코드", "FOOD_CD", "표준식품코드", "ITEM_CODE", "DB10.4 번호", "DB10.4\n번호"
    ],
    "serving_size": [
        "1회제공량", "1회 제공량", "1회 섭취참고량", "총내용량", "SERVING_SIZE", 
        "1회제공량(g)", "1회 섭취참고량(g)", "기준중량(g)", "영양성분함량기준량",
        "1회분량중량/용량", "1회분량중량", "내용량"
    ],
    "serving_unit": [
        "단위", "내용량단위", "SERVING_UNIT"
    ],
    "calories": [
        "에너지(kcal)", "열량(kcal)", "에너지", "열량", "AMT_NUM1", "CALORIES", "에너지 (kcal)"
    ],
    "carbohydrates": [
        "탄수화물(g)", "탄수화물", "AMT_NUM7", "CARBOHYDRATE", "탄수화물 (g)"
    ],
    "protein": [
        "단백질(g)", "단백질", "AMT_NUM3", "PROTEIN", "단백질 (g)"
    ],
    "fat": [
        "지방(g)", "지방", "AMT_NUM4", "FAT", "지방 (g)"
    ],
    "sugar": [
        "당류(g)", "총당류(g)", "당류", "AMT_NUM8", "SUGARS", "당류 (g)"
    ],
    "sodium": [
        "나트륨(mg)", "나트륨", "AMT_NUM14", "SODIUM", "나트륨 (mg)"
    ],
    "cholesterol": [
        "콜레스테롤(mg)", "콜레스테롤", "AMT_NUM24", "CHOLESTEROL", "콜레스테롤 (mg)"
    ],
    "saturated_fat": [
        "포화지방산(g)", "포화지방(g)", "포화지방산", "포화지방", "AMT_NUM25", "SATURATED_FAT"
    ],
    "trans_fat": [
        "트랜스지방산(g)", "트랜스지방(g)", "트랜스지방산", "트랜스지방", "AMT_NUM26", "TRANS_FAT"
    ],
    # --- 주요 무기질 및 비타민 추가 ---
    "fiber": [
        "식이섬유(g)", "총 식이섬유", "총\n식이섬유", "식이섬유", "총식이섬유", "FIBER", "AMT_NUM9"
    ],
    "calcium": [
        "칼슘(mg)", "칼슘", "CALCIUM", "AMT_NUM10", "칼슘 (mg)"
    ],
    "iron": [
        "철(mg)", "철분(mg)", "철", "철분", "IRON", "AMT_NUM11", "철 (mg)"
    ],
    "magnesium": [
        "마그네슘(mg)", "마그네슘", "MAGNESIUM", "AMT_NUM13", "마그네슘 (mg)"
    ],
    "potassium": [
        "칼륨(mg)", "칼륨", "POTASSIUM", "AMT_NUM12", "칼륨 (mg)"
    ],
    "zinc": [
        "아연(mg)", "아연", "ZINC", "AMT_NUM16", "아연 (mg)"
    ],
    "vitamin_a": [
        "비타민A(μg RAE)", "비타민 A(μg RAE)", "비타민A(ug RAE)", "비타민 A(ug RAE)", 
        "비타민 A", "비타민A", "VITAMIN_A", "AMT_NUM18"
    ],
    "vitamin_c": [
        "비타민 C(mg)", "비타민C(mg)", "비타민 C", "비타민C", "VITAMIN_C", "AMT_NUM21", "비타민 C (mg)"
    ],
    "vitamin_d": [
        "비타민 D(μg)", "비타민D(μg)", "비타민 D(ug)", "비타민D(ug)", "비타민 D", "비타민D", 
        "VITAMIN_D", "AMT_NUM22"
    ],
    "folate": [
        "엽산(μg DFE)", "엽산(ug DFE)", "엽산(μg)", "엽산(ug)", "엽산", "FOLATE", "AMT_NUM23"
    ]
}

def clean_float_with_unit(val, default=0.0) -> float:
    """단위(mg, g, ml 등)를 감안한 수치 파싱 (예: '350mg' -> 0.35g)"""
    if pd.isna(val):
        return default
    if isinstance(val, (int, float)):
        return float(val)

    val_str = str(val).strip().lower()
    is_mg = "mg" in val_str and "g" not in val_str.replace("mg", "")
    val_clean = re.sub(r'[^\d.]', '', val_str)
    if not val_clean:
        return default

    try:
        num = float(val_clean)
        return num / 1000.0 if is_mg else num
    except ValueError:
        return default

def clean_float(val, default=0.0) -> float:
    """일반 수치 정제"""
    if pd.isna(val):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    val_str = re.sub(r'[^\d.]', '', str(val).strip())
    try:
        return float(val_str) if val_str else default
    except ValueError:
        return default

def match_columns(df_columns: List[str]) -> Dict[str, str]:
    """컬럼명을 표준 키로 유연하게 매핑"""
    matched = {}
    normalized_cols = {str(col).strip().replace(" ", "").replace("\n", "").lower(): col for col in df_columns}

    for standard_key, candidates in COLUMN_MAPPINGS.items():
        found = None
        for candidate in candidates:
            cand_norm = candidate.strip().replace(" ", "").replace("\n", "").lower()
            # 1. 완전 일치
            for norm_key, original_col in normalized_cols.items():
                if norm_key == cand_norm:
                    found = original_col
                    break
            if found:
                break
            # 2. 포함 검사
            for norm_key, original_col in normalized_cols.items():
                if cand_norm in norm_key:
                    found = original_col
                    break
            if found:
                break
        if found:
            matched[standard_key] = found

    return matched

def find_best_sheet_and_header(excel_path: str) -> Tuple[str, int]:
    xl = pd.ExcelFile(excel_path)
    sheet_names = xl.sheet_names

    preferred_sheets = []
    for s in sheet_names:
        if "Database 10.4" in s:
            preferred_sheets.insert(0, s)
        elif any(k in s for k in ["Database", "가공식품", "음식", "식품", "DB"]):
            preferred_sheets.append(s)

    if not preferred_sheets:
        preferred_sheets = sheet_names

    best_sheet = preferred_sheets[0]
    best_header_row = 0
    max_match_score = -1

    for sheet in preferred_sheets[:4]:
        try:
            preview_df = xl.parse(sheet, header=None, nrows=6)
            if preview_df.empty:
                continue

            for row_idx, row in preview_df.iterrows():
                row_str = " ".join([str(v) for v in row.values if pd.notna(v)])
                score = 0
                if "식품명" in row_str or "음식명" in row_str or "SAMPLE_NAME" in row_str:
                    score += 10
                if "에너지" in row_str or "열량" in row_str:
                    score += 5
                if "단백질" in row_str:
                    score += 3
                if "칼슘" in row_str:
                    score += 3
                if "비타민" in row_str:
                    score += 3

                if score > max_match_score:
                    max_match_score = score
                    best_sheet = sheet
                    best_header_row = row_idx
        except Exception:
            continue

    return best_sheet, best_header_row

def import_excel_to_sqlite(excel_path: str, source_name: Optional[str] = None) -> int:
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {excel_path}")

    source = source_name or os.path.basename(excel_path)
    print(f"\n[INFO] 엑셀 파일 분석 시작: {source}")

    best_sheet, header_row = find_best_sheet_and_header(excel_path)
    print(f"[INFO] 선택된 시트: '{best_sheet}', 헤더 위치: 행 {header_row}")

    df = pd.read_excel(excel_path, sheet_name=best_sheet, header=header_row)
    print(f"[INFO] 로드 완료: 총 {len(df):,}행, {len(df.columns)}개 컬럼")

    if len(df) > 0 and df.iloc[0].astype(str).str.contains(r'kcal|g|mg|단위', case=False).any():
        df = df.iloc[1:]

    col_map = match_columns(list(df.columns))
    print("[INFO] 매핑된 주요 영양/무기질/비타민 컬럼:")
    for std_k, mapped_c in col_map.items():
        print(f"  - {std_k}: '{mapped_c}'")

    if "name" not in col_map:
        raise ValueError(f"식품명 컬럼을 자동으로 인식하지 못했습니다. (선택 시트: {best_sheet})")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")

    cursor.execute("DELETE FROM foods WHERE source = ?", (source,))

    records = []
    for _, row in df.iterrows():
        name_val = row.get(col_map.get("name"))
        if pd.isna(name_val) or not str(name_val).strip():
            continue

        name = str(name_val).strip()
        category = str(row.get(col_map.get("category", ""), "기타")).strip()
        if category == "nan" or not category:
            category = "기타"

        food_code = str(row.get(col_map.get("food_code", ""), ""))
        if food_code == "nan":
            food_code = ""

        if "serving_size" in col_map:
            serving_size = clean_float_with_unit(row.get(col_map["serving_size"]), default=100.0)
        else:
            serving_size = 100.0
        if serving_size <= 0:
            serving_size = 100.0

        calories = clean_float(row.get(col_map.get("calories", "")))
        carbohydrates = clean_float(row.get(col_map.get("carbohydrates", "")))
        protein = clean_float(row.get(col_map.get("protein", "")))
        fat = clean_float(row.get(col_map.get("fat", "")))
        sugar = clean_float(row.get(col_map.get("sugar", "")))
        sodium = clean_float(row.get(col_map.get("sodium", "")))
        cholesterol = clean_float(row.get(col_map.get("cholesterol", "")))
        saturated_fat = clean_float(row.get(col_map.get("saturated_fat", "")))
        trans_fat = clean_float(row.get(col_map.get("trans_fat", "")))

        # 무기질 및 비타민 수치
        fiber = clean_float(row.get(col_map.get("fiber", "")))
        calcium = clean_float(row.get(col_map.get("calcium", "")))
        iron = clean_float(row.get(col_map.get("iron", "")))
        magnesium = clean_float(row.get(col_map.get("magnesium", "")))
        potassium = clean_float(row.get(col_map.get("potassium", "")))
        zinc = clean_float(row.get(col_map.get("zinc", "")))
        vitamin_a = clean_float(row.get(col_map.get("vitamin_a", "")))
        vitamin_c = clean_float(row.get(col_map.get("vitamin_c", "")))
        vitamin_d = clean_float(row.get(col_map.get("vitamin_d", "")))
        folate = clean_float(row.get(col_map.get("folate", "")))

        records.append((
            food_code, name, category, serving_size, 'g',
            calories, carbohydrates, protein, fat, sugar, sodium,
            cholesterol, saturated_fat, trans_fat,
            fiber, calcium, iron, magnesium, potassium, zinc,
            vitamin_a, vitamin_c, vitamin_d, folate, source
        ))

    print(f"[INFO] 유효 데이터 {len(records):,}건 변환 완료. DB 일괄 저장 중...")

    chunk_size = 10000
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        cursor.executemany("""
            INSERT INTO foods (
                food_code, name, category, serving_size, serving_unit,
                calories, carbohydrates, protein, fat, sugar, sodium,
                cholesterol, saturated_fat, trans_fat,
                fiber, calcium, iron, magnesium, potassium, zinc,
                vitamin_a, vitamin_c, vitamin_d, folate, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, chunk)
        conn.commit()

    conn.close()
    print(f"[SUCCESS] {source} -> {len(records):,}건 적재 성공!\n")
    return len(records)

def sync_all_raw_files() -> Dict[str, Any]:
    xlsx_files = glob.glob(os.path.join(RAW_DATA_DIR, "*.xlsx"))
    results = {}
    total_added = 0
    for f in xlsx_files:
        fname = os.path.basename(f)
        try:
            cnt = import_excel_to_sqlite(f, source_name=fname)
            results[fname] = {"status": "success", "count": cnt}
            total_added += cnt
        except Exception as e:
            results[fname] = {"status": "error", "error": str(e)}

    return {
        "total_files": len(xlsx_files),
        "total_records": total_added,
        "details": results
    }

if __name__ == "__main__":
    from app.services.db_service import init_database
    init_database()

    if len(sys.argv) > 1:
        import_excel_to_sqlite(sys.argv[1])
    else:
        res = sync_all_raw_files()
        print("[SUMMARY]", res)
