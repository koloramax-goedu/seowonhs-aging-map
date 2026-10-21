import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# 1. 페이지 설정
st.set_page_config(
    page_title="전국 고령화 & 유소년 비율 단계구분도",
    page_icon="🗺️",
    layout="wide"
)

# 2. 데이터 URL (koloramax-goedu/seowonhs-data 리포지토리로 변경)
POPULATION_URL = "https://raw.githubusercontent.com/koloramax-goedu/seowonhs-data/main/population_ts_yearly_gender.zip"
GEOJSON_URL = "https://raw.githubusercontent.com/koloramax-goedu/seowonhs-data/main/sigungu_kr.geojson"

# 3. 데이터 로딩 및 전처리 캐싱
@st.cache_data
def load_all_data():
    # GeoJSON 시군구 경계 데이터 수신
    res = requests.get(GEOJSON_URL)
    geojson_data = res.json()
    
    # GeoJSON 속성 추출 (코드, 시군구, 시도)
    geo_list = []
    for f in geojson_data['features']:
        props = f['properties']
        geo_list.append({
            '코드': str(props.get('코드', '')).strip(),
            '시도_geo': str(props.get('시도', '')).strip(),
            '시군구_geo': str(props.get('시군구', '')).strip()
        })
    geo_df = pd.DataFrame(geo_list)
    
    # 인구 데이터 (ZIP 압축 CSV) 읽기 - 코드는 문자열 로드
    df = pd.read_csv(POPULATION_URL, dtype={'코드': str})
    
    # 행정구역 개편에 따른 옛 코드 보정 함수
    # - 군위군: 47720 -> 27720 (대구광역시 군위군)
    # - 강원도: 42 -> 51 (강원특별자치도)
    # - 전라북도: 45 -> 52 (전북특별자치도)
    def remap_code(c):
        c = str(c).strip()
        if c.startswith('47720'):
            return '27720' + c[5:]
        if c.startswith('42'):
            return '51' + c[2:]
        if c.startswith('45'):
            return '52' + c[2:]
        return c

    df['코드_remapped'] = df['코드'].apply(remap_code)
    df['sigungu_code'] = df['코드_remapped'].str[:5]
    
    # 연도 정제 (숫자 4자리 추출: 예 2015 ~ 2026)
    df['연도_int'] = df['연도'].astype(str).str.extract(r'(\d{4})')[0].astype(int)
    
    # 나이별 열 분류
    total_cols = [c for c in df.columns if c.startswith('계_')]
    
    def parse_age(col_name):
        clean = col_name.replace('계_', '').replace('세', '').replace('이상', '').strip()
        try:
            return int(clean)
        except ValueError:
            return -1

    elderly_cols = [c for c in total_cols if parse_age(c) >= 65]
    youth_cols = [c for c in total_cols if 0 <= parse_age(c) <= 14]
    
    # 행별 합계 계산
    df['총인구'] = df[total_cols].sum(axis=1)
    df['고령인구'] = df[elderly_cols].sum(axis=1)
    df['유소년인구'] = df[youth_cols].sum(axis=1)
    
    # 연도별, 시군구별 집계
    grouped = df.groupby(['연도_int', 'sigungu_code']).agg({
        '시도': 'first',
        '시군구': 'first',
        '총인구': 'sum',
        '고령인구': 'sum',
        '유소년인구': 'sum'
    }).reset_index()
    
    return geojson_data, geo_df, grouped

# 타이틀
st.title("🗺️ 전국 인구구조 단계구분도 (2015 ~ 2026)")
st.caption("연도별 읍·면·동 인구 데이터를 기반으로 시군구별 고령화율(65세 이상) 및 유소년 비율(0~14세) 변화를 확인하는 지도입니다.")

# 데이터 로드
with st.spinner("데이터를 불러오는 중입니다..."):
    geojson_data, geo_df, grouped_pop = load_all_data()

# 컨트롤 패널 (상단 필터)
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 3, 3])

available_years = sorted(grouped_pop['연도_int'].unique())

with ctrl_col1:
    selected_year = st.slider(
        "📅 연도 선택",
        min_value=int(min(available_years)),
        max_value=int(max(available_years)),
        value=int(max(available_years)),
        step=1
    )

with ctrl_col2:
    selected_metric = st.selectbox(
        "📊 지표 선택",
        ["고령화율 (65세 이상)", "유소년 비율 (0~14세)"]
    )

# 선택한 연도의 인구 데이터 필터링 및 GeoJSON 매칭
year_pop = grouped_pop[grouped_pop['연도_int'] == selected_year]

merged = pd.merge(
    geo_df,
    year_pop,
    left_on='코드',
    right_on='sigungu_code',
    how='left'
)

# 지역명 보완
merged['시도'] = merged['시도'].fillna(merged['시도_geo'])
merged['시군구'] = merged['시군구'].fillna(merged['시군구_geo'])

# 수치 정제
merged['총인구'] = merged['총인구'].fillna(0).astype(int)
merged['고령인구'] = merged['고령인구'].fillna(0).astype(int)
merged['유소년인구'] = merged['유소년인구'].fillna(0).astype(int)

# 지표별 구간 및 색상 설정
if selected_metric == "고령화율 (65세 이상)":
    merged['비율'] = (merged['고령인구'] / merged['총인구'] * 100).round(2)
    metric_label = "고령화율"
