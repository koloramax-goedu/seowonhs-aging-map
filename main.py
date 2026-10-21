import streamlit as st
import pandas as pd
import requests
import plotly.express as px

# 1. 페이지 설정
st.set_page_config(
    page_title="2026년 전국 고령화 단계구분도",
    page_icon="🗺️",
    layout="wide"
)

# 2. 데이터 URL 설정
POPULATION_URL = "https://raw.githubusercontent.com/first2022-cyber/contents//main/population_ts_yearly_gender.zip"
GEOJSON_URL = "https://raw.githubusercontent.com/first2022-cyber/contents//main/sigungu_kr.geojson"

# 3. 데이터 로딩 및 전처리 캐싱
@st.cache_data
def load_and_process_data():
    # GeoJSON 시군구 경계 데이터 수신 (requests 이용)
    res = requests.get(GEOJSON_URL)
    geojson_data = res.json()
    
    # GeoJSON 속성 추출 (코드, 시군구, 시도) - 코드는 문자열 처리
    geo_list = []
    for f in geojson_data['features']:
        props = f['properties']
        geo_list.append({
            '코드': str(props.get('코드', '')).strip(),
            '시도_geo': props.get('시도', ''),
            '시군구_geo': props.get('시군구', '')
        })
    geo_df = pd.DataFrame(geo_list)
    
    # 인구 데이터 (ZIP 압축 CSV) 읽기 - 코드는 문자열로 로드
    df = pd.read_csv(POPULATION_URL, dtype={'코드': str})
    
    # '2026년' 데이터만 필터링
    df_2026 = df[df['연도'].astype(str).str.contains('2026')].copy()
    
    # 각 동 '코드'의 앞 5자리로 시군구 코드 추출
    df_2026['sigungu_code'] = df_2026['코드'].astype(str).str.strip().str[:5]
    
    # 전체 인구 열: '계_'로 시작하는 모든 열 (남_, 여_ 제외)
    total_cols = [c for c in df_2026.columns if c.startswith('계_')]
    
    # 65세 이상 인구 열 파싱 ('계_65세' ~ '계_100세 이상')
    def parse_age(col_name):
        clean = col_name.replace('계_', '').replace('세', '').replace('이상', '').strip()
        try:
            return int(clean)
        except ValueError:
            return -1

    elderly_cols = [c for c in total_cols if parse_age(c) >= 65]
    
    # 행별 총인구 및 고령인구 계산
    df_2026['총인구'] = df_2026[total_cols].sum(axis=1)
    df_2026['고령인구'] = df_2026[elderly_cols].sum(axis=1)
    
    # 시군구 코드(앞 5자리) 기준 집계
    grouped = df_2026.groupby('sigungu_code').agg({
        '시도': 'first',
        '시군구': 'first',
        '총인구': 'sum',
        '고령인구': 'sum'
    }).reset_index()
    
    # GeoJSON 지역 코드 기준 병합 (문자열 코드 매칭)
    merged = pd.merge(
        geo_df,
        grouped,
        left_on='코드',
        right_on='sigungu_code',
        how='left'
    )
    
    # 지역명 결측치 보완
    merged['시도'] = merged['시도'].fillna(merged['시도_geo'])
    merged['시군구'] = merged['시군구'].fillna(merged['시군구_geo'])
    merged['지역명'] = merged['시도'] + ' ' + merged['시군구']
    
    # 결측치 및 65세 이상 비율(%) 계산
    merged['총인구'] = merged['총인구'].fillna(0).astype(int)
    merged['고령인구'] = merged['고령인구'].fillna(0).astype(int)
    merged['고령화율'] = (merged['고령인구'] / merged['총인구'] * 100).round(2)
    merged['고령화율'] = merged['고령화율'].fillna(0)
    
    return geojson_data, merged

# UI 구성
st.title("🗺️ 2026년 전국 시군구 고령화 단계구분도")
st.caption("2026년 6월 기준 전국 읍·면·동 인구 데이터를 바탕으로 집계한 시군구별 65세 이상 고령화율 단계구분도입니다.")

with st.spinner("데이터 및 GeoJSON 지도를 불러오는 중입니다..."):
    geojson_data, df = load_and_process_data()

# 사이드바 필터
st.sidebar.header("🔍 검색 및 필터")
sido_list = ["전체"] + sorted([s for s in df['시도'].dropna().unique() if s])
selected_sido = st.sidebar.selectbox("시·도 선택", sido_list)

if selected_sido != "전체":
    filtered_df = df[df['시도'] == selected_sido].copy()
else:
    filtered_df = df.copy()

# 요약 지표 (KPI Cards)
total_pop = filtered_df['총인구'].sum()
elderly_pop = filtered_df['고령인구'].sum()
avg_rate = (elderly_pop / total_pop * 100) if total_pop > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("총 인구", f"{total_pop:,} 명")
col2.metric("65세 이상 인구", f"{elderly_pop:,} 명")
col3.metric("평균 고령화율", f"{avg_rate:.2f} %")

if not filtered_df.empty and filtered_df['총인구'].sum() > 0:
    max_row = filtered_df.loc[filtered_df['고령화율'].idxmax()]
    col4.metric("최고 고령화 지역", f"{max_row['시군구']}", f"{max_row['고령화율']:.1f}%")

st.divider()

# Plotly 단계구분도 생성 (배경지도 없이 경계선만 표시)
fig = px.choropleth(
    filtered_df,
    geojson=geojson_data,
    locations='코드',
    featureidkey='properties.코드',
    color='고령화율',
    color_continuous_scale='Reds',
    custom_data=['시도', '시군구', '고령화율', '총인구', '고령인구'],
    labels={'고령화율': '고령화율 (%)'}
)

# 타일 지도 삭제 및 경계만 표시 설정
fig.update_geos(
    fitbounds="locations",
    visible=False
)

# 마우스 오버(Hover) 시 시군구 이름과 고령화율(%) 표시
fig.update_traces(
    marker_line_width=0.6,
    marker_line_color="#555555",
    hovertemplate="<b>%{customdata[0]} %{customdata[1]}</b><br>고령화율: %{customdata[2]:.2f}%<extra></extra>"
)

fig.update_layout(
    height=680,
    margin={"r": 0, "t": 10, "l": 0, "b": 10},
    coloraxis_colorbar=dict(
        title="고령화율 (%)",
        ticksuffix="%",
        thickness=16,
        len=0.75
    )
)

st.plotly_chart(fig, use_container_width=True)

# 상세 데이터 테이블
with st.expander("📊 시군구별 상세 데이터 보기"):
    st.dataframe(
        filtered_df[['코드', '시도', '시군구', '총인구', '고령인구', '고령화율']]
        .sort_values(by='고령화율', ascending=False)
        .reset_index(drop=True),
        use_container_width=True
    )
