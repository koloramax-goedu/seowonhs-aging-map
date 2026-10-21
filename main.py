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

# 2. 데이터 URL
POPULATION_URL = "https://raw.githubusercontent.com/koloramax-goedu/seowonhs-data/main/population_ts_yearly_gender.zip"
GEOJSON_URL = "https://raw.githubusercontent.com/koloramax-goedu/seowonhs-data/main/sigungu_kr.geojson"

# 3. 데이터 로딩 및 전처리 캐싱
@st.cache_data
def load_all_data():
    # GeoJSON 시군구 경계 데이터 수신 (requests 이용)
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
    
    # 나이별 열 분류 (전체, 고령, 유소년)
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

# 앱 헤더
st.title("🗺️ 전국 인구구조 단계구분도 (2015 ~ 2026)")
st.caption("연도별 읍·면·동 인구 데이터를 기반으로 시군구별 고령화율(65세 이상) 및 유소년 비율(0~14세) 변화를 확인하는 지도입니다.")

# 데이터 로드
with st.spinner("데이터를 불러오는 중입니다..."):
    geojson_data, geo_df, grouped_pop = load_all_data()

# 컨트롤 패널 (상단 컨트롤 필터)
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

# 지표별 구간 및 고정 색상 범주 설정
if selected_metric == "고령화율 (65세 이상)":
    merged['비율'] = (merged['고령인구'] / merged['총인구'] * 100).round(2)
    metric_label = "고령화율"
    bins = [-float('inf'), 19, 23, 28, 38, float('inf')]
    bin_labels = ['19% 미만', '19% ~ 23% 미만', '23% ~ 28% 미만', '28% ~ 38% 미만', '38% 이상']
    color_map = {
        '19% 미만': '#fef0d9',
        '19% ~ 23% 미만': '#fdcc8a',
        '23% ~ 28% 미만': '#fc8d59',
        '28% ~ 38% 미만': '#e34a33',
        '38% 이상': '#b30000',
        '데이터 없음': '#d3d3d3'
    }
else:
    merged['비율'] = (merged['유소년인구'] / merged['총인구'] * 100).round(2)
    metric_label = "유소년 비율"
    bins = [-float('inf'), 8, 10, 12, 14, float('inf')]
    bin_labels = ['8% 미만', '8% ~ 10% 미만', '10% ~ 12% 미만', '12% ~ 14% 미만', '14% 이상']
    color_map = {
        '8% 미만': '#f0f9e8',
        '8% ~ 10% 미만': '#bae4bc',
        '10% ~ 12% 미만': '#7bccc4',
        '12% ~ 14% 미만': '#43a2ca',
        '14% 이상': '#0868ac',
        '데이터 없음': '#d3d3d3'
    }

# 총인구가 0이거나 데이터가 없는 지역 처리
merged.loc[merged['총인구'] == 0, '비율'] = None

# 색 구간 범주화 (pd.cut)
merged['구간'] = pd.cut(merged['비율'], bins=bins, labels=bin_labels)
merged['구간'] = merged['구간'].astype(str).fillna('데이터 없음')
merged.loc[merged['구간'] == 'nan', '구간'] = '데이터 없음'

# 시·도 선택 드롭다운
with ctrl_col3:
    sido_options = ["전국"] + sorted([s for s in merged['시도'].dropna().unique() if s])
    selected_sido = st.selectbox("🔍 시·도 선택 (지도 확대)", sido_options)

# 시·도 필터링
if selected_sido != "전국":
    display_df = merged[merged['시도'] == selected_sido].copy()
else:
    display_df = merged.copy()

# 상단 지표 카드 세 장 (평균 비율, 가장 높은 시군구, 가장 낮은 시군구)
valid_df = display_df[display_df['비율'].notna() & (display_df['총인구'] > 0)]

st.divider()

if not valid_df.empty:
    total_pop_sum = valid_df['총인구'].sum()
    if selected_metric == "고령화율 (65세 이상)":
        overall_rate = (valid_df['고령인구'].sum() / total_pop_sum * 100) if total_pop_sum > 0 else 0
    else:
        overall_rate = (valid_df['유소년인구'].sum() / total_pop_sum * 100) if total_pop_sum > 0 else 0

    max_row = valid_df.loc[valid_df['비율'].idxmax()]
    min_row = valid_df.loc[valid_df['비율'].idxmin()]

    c1, c2, c3 = st.columns(3)
    sido_prefix = f"{selected_sido} " if selected_sido != "전국" else "전국 "
    
    c1.metric(
        label=f"📌 {sido_prefix}평균 {metric_label}",
        value=f"{overall_rate:.2f}%"
    )
    c2.metric(
        label=f"🔺 가장 높은 시군구",
        value=f"{max_row['비율']:.2f}%",
        delta=f"{max_row['시도']} {max_row['시군구']}",
        delta_color="off"
    )
    c3.metric(
        label=f"🔻 가장 낮은 시군구",
        value=f"{min_row['비율']:.2f}%",
        delta=f"{min_row['시도']} {min_row['시군구']}",
        delta_color="off"
    )

# 툴팁용 문자열 컬럼 생성
display_df['비율_표시'] = display_df['비율'].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "데이터 없음")

# Plotly 단계구분도 생성
fig = px.choropleth(
    display_df,
    geojson=geojson_data,
    locations='코드',
    featureidkey='properties.코드',
    color='구간',
    color_discrete_map=color_map,
    category_orders={'구간': bin_labels + ['데이터 없음']},
    custom_data=['시도', '시군구', '비율_표시', '총인구'],
    labels={'구간': f'{metric_label} 구간'}
)

fig.update_geos(
    fitbounds="locations",
    visible=False
)

fig.update_traces(
    marker_line_width=0.6,
    marker_line_color="#444444",
    hovertemplate=(
        "<b>%{customdata[0]} %{customdata[1]}</b><br>"
        f"{metric_label}: <b>%{{customdata[2]}}</b><br>"
        "총인구: %{customdata[3]:,} 명<extra></extra>"
    )
)

fig.update_layout(
    height=680,
    margin={"r": 0, "t": 10, "l": 0, "b": 10},
    legend=dict(
        title=dict(text=f"<b>{metric_label} 구간</b>"),
        orientation="v",
        yanchor="top",
        y=0.98,
        xanchor="left",
        x=0.01,
        bgcolor="rgba(255, 255, 255, 0.85)",
        bordercolor="#cccccc",
        borderwidth=1
    )
)

st.plotly_chart(fig, use_container_width=True)

# 행정구역 미매칭 / 회색 처리 안내 문구
unmatched_in_display = display_df[display_df['구간'] == '데이터 없음']
if not unmatched_in_display.empty:
    unmatched_names = sorted(unmatched_in_display['시군구'].dropna().unique())
    unmatched_names_str = ", ".join(unmatched_names)
    st.info(
        f"ℹ️ **행정구역 경계 미매칭 지역 ({len(unmatched_names)}곳, 지도상 회색 표시):** "
        f"{unmatched_names_str}\n\n"
        f"*선택한 {selected_year}년 기준 인구 데이터가 없거나, 행정구역 개편 시점에 따라 경계 파일(GeoJSON)과 코드가 일치하지 않는 지역입니다.*"
    )

# 상세 데이터 보기
with st.expander("📊 상세 데이터 보기"):
    st.dataframe(
        display_df[['코드', '시도', '시군구', '총인구', '고령인구', '유소년인구', '비율', '구간']]
        .rename(columns={'비율': f'{metric_label}(%)'})
        .sort_values(by=f'{metric_label}(%)', ascending=False)
        .reset_index(drop=True),
        use_container_width=True
    )
