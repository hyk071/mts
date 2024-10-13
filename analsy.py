import streamlit as st
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import folium
from streamlit_folium import folium_static
import numpy as np
import datetime
import random
import matplotlib.font_manager as fm
import os

# 한글 폰트 설정
font_path = os.path.join(os.getcwd(), 'static/fonts/NanumGothic.ttf')
font_prop = fm.FontProperties(fname=font_path)
plt.rcParams['font.family'] = font_prop.get_name()
plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지

# 데이터베이스 연결 및 테이블 생성
def create_database():
    conn = sqlite3.connect('vehicle_violations.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS violations (
            일련번호 TEXT,
            위반유형 TEXT,
            위반일시 DATETIME,
            제한속도 INTEGER,
            실제주행속도 INTEGER,
            실제초과속도 INTEGER,
            고지주행속도 INTEGER,
            고지초과속도 INTEGER,
            처리상태 TEXT,
            위반차로 INTEGER,
            차종 TEXT,
            장소구분 TEXT,
            주민구분 TEXT,
            차명 TEXT,
            위반장소 TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 데이터베이스에 데이터 저장
def save_to_database(df):
    conn = sqlite3.connect('vehicle_violations.db')
    df.to_sql('violations', conn, if_exists='append', index=False)
    conn.close()

# Streamlit 앱
st.title('차량단속 데이터 분석 대시보드')

# 데이터베이스 생성
create_database()

# 데이터 업로드
uploaded_file = st.file_uploader("엑셀 파일을 업로드하세요", type=["xlsx"], label_visibility="collapsed")
if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)
    analysis_columns = [
        "일련번호", "위반유형", "위반일시", "제한속도", "실제주행속도", "실제초과속도",
        "고지주행속도", "고지초과속도", "처리상태", "위반차로", "차종", "장소구분",
        "주민구분", "차명", "위반장소"
    ]
    df_analysis = df[analysis_columns]

    # 개인정보 제거 후 데이터베이스에 저장
    save_to_database(df_analysis)
    st.success("파일이 데이터베이스에 저장되었습니다.")

# 최근 분석 결과 표시
conn = sqlite3.connect('vehicle_violations.db')
df_db = pd.read_sql('SELECT * FROM violations', conn)
conn.close()

if not df_db.empty:
    # 날짜 선택 위젯 추가
    st.sidebar.header("분석 결과 날짜 선택")
    df_db['위반일시'] = pd.to_datetime(df_db['위반일시'])
    available_dates = df_db['위반일시'].dt.date.unique()
    date_range = st.sidebar.date_input("기간 선택", value=(min(available_dates), max(available_dates)), min_value=min(available_dates), max_value=max(available_dates))
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        st.sidebar.error("종료일을 선택하세요.")
        st.stop()
    df_selected = df_db[(df_db['위반일시'].dt.date >= start_date) & (df_db['위반일시'].dt.date <= end_date)]

    # 필터 추가
    st.sidebar.header("필터 설정")
    violation_type_filter = st.sidebar.selectbox("위반유형 선택", options=['전체'] + list(df_selected['위반유형'].unique()), index=0, key='violation_type_filter')
    status_filter = st.sidebar.selectbox("처리상태 선택", options=['전체'] + list(df_selected['처리상태'].unique()), index=0, key='status_filter')
    location_type_filter = st.sidebar.selectbox("장소구분 선택", options=['전체'] + list(df_selected['장소구분'].unique()), index=0, key='location_type_filter')

    # 필터 리셋 버튼 추가
    if st.sidebar.button("필터 리셋"):
        for key in ['violation_type_filter', 'status_filter', 'location_type_filter']:
            if key in st.session_state:
                del st.session_state[key]
        st.experimental_rerun()

    # 필터 적용
    if violation_type_filter != '전체':
        df_selected = df_selected[df_selected['위반유형'] == violation_type_filter]
    if status_filter != '전체':
        df_selected = df_selected[df_selected['처리상태'] == status_filter]
    if location_type_filter != '전체':
        df_selected = df_selected[df_selected['장소구분'] == location_type_filter]

    if not df_selected.empty:
        # 분석 결과 제목 표시
        start_date = df_selected['위반일시'].min().date()
        end_date = df_selected['위반일시'].max().date()
        st.subheader(f"분석 기간: {start_date} ~ {end_date}")

        # 단속 건수 표로 표시
        st.subheader('단속 건수 요약')
        total_count = df_selected['일련번호'].nunique()
        st.write(f'단속 건수 총합계: {total_count}건')
        summary = df_selected.groupby(['위반유형', '장소구분', '처리상태']).size().reset_index(name='건수')
        st.write(summary)
        st.write("카테고리 별 단속 건수 부분 합계:")
        part_sum = df_selected.groupby(['위반유형'])['일련번호'].nunique().reset_index(name='건수')
        st.write(part_sum)

        # 단속 건수가 급증한 장비 경고 알림
        df_db['장비코드'] = df_db['일련번호'].str[:5]
        equipment_counts = df_db.groupby('장비코드').size()
        df_selected['장비코드'] = df_selected['일련번호'].str[:5]
        recent_counts = df_selected.groupby('장비코드').size().reindex(equipment_counts.index, fill_value=0)
        increase_threshold = 1.5  # 1.5배 이상 증가한 경우 경고
        alerts = recent_counts[recent_counts > (equipment_counts * increase_threshold)]

        if not alerts.empty:
            st.warning("경고: 단속 건수가 급증한 장비가 발견되었습니다.")
            st.write(alerts)

        # 위반 유형별 발생 빈도 시각화
        st.subheader('위반 유형별 발생 빈도')
        violation_counts = df_selected['위반유형'].value_counts()
        fig, ax = plt.subplots()
        ax.bar(violation_counts.index, violation_counts.values, color='skyblue')
        ax.set_xlabel('위반유형', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('위반 유형별 건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
        st.pyplot(fig)

        # 시간대별 위반 건수 시각화
        df_selected['시간대'] = df_selected['위반일시'].dt.hour
        time_counts = df_selected['시간대'].value_counts().sort_index()
        st.subheader('시간대별 위반 건수')
        fig, ax = plt.subplots()
        ax.plot(time_counts.index, time_counts.values, marker='o', color='skyblue')
        ax.set_xlabel('시간대', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('시간대별 위반 건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
        st.pyplot(fig)

        # 차종별 위반 건수 시각화
        st.subheader('차종별 위반 건수')
        car_type_counts = df_selected['차종'].value_counts()
        fig, ax = plt.subplots()
        ax.bar(car_type_counts.index, car_type_counts.values, color='skyblue')
        ax.set_xlabel('차종', fontproperties=font_prop)
        ax.set_ylabel('건수', fontproperties=font_prop)
        ax.set_title('차종별 건수', fontproperties=font_prop)
        plt.xticks(fontproperties=font_prop)
        plt.yticks(fontproperties=font_prop)
        st.pyplot(fig)
