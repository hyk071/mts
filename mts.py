import streamlit as st
import requests
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import numpy as np
import datetime
import random
import os
import matplotlib.font_manager as fm
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

API_URL = "http://api.data.go.kr/openapi/tn_pubr_public_unmanned_traffic_camera_api"
SERVICE_KEY = "2ReGLeF8d8+JQrzLO3u3VGwVQ58Fi6mZVAogLJ3OBSmCTAfvjKs2dObu+juc2BSS4jdNlo1Q/o0du+b8z9SuKQ=="

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
            일련번호 TEXT PRIMARY KEY,
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

# 데이터베이스에 데이터 저장 (중복 확인 추가)
def save_to_database(df):
    conn = sqlite3.connect('vehicle_violations.db')
    cursor = conn.cursor()
    for _, row in df.iterrows():
        cursor.execute('''
            INSERT OR IGNORE INTO violations (일련번호, 위반유형, 위반일시, 제한속도, 실제주행속도, 실제초과속도, 고지주행속도, 고지초과속도, 처리상태, 위반차로, 차종, 장소구분, 주민구분, 차명, 위반장소)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row['일련번호'], row['위반유형'], row['위반일시'], row['제한속도'], row['실제주행속도'], row['실제초과속도'],
            row['고지주행속도'], row['고지초과속도'], row['처리상태'], row['위반차로'], row['차종'], row['장소구분'],
            row['주민구분'], row['차명'], row['위반장소']
        ))
    conn.commit()
    conn.close()

# 시도명 자동 보정
def correct_region_name(input_name):
    region_mapping = {
        '서울': '서울특별시',
        '부산': '부산광역시',
        '울산': '울산광역시',
        '대전': '대전광역시',
        '대구': '대구광역시',
        '광주': '광주광역시',
        '인천': '인천광역시',
        '전라북도': '전북',
        '전라남도': '전남',
        '경상남도': '경남',
        '경상북도': '경북',
        '충청북도': '충북',
        '충청남도': '충남',
        '강원도': '강원',
        '경기도': '경기',
        # 필요에 따라 더 많은 지역 추가
    }
    return region_mapping.get(input_name, input_name)

# 카메라 데이터를 가져오는 함수
def get_camera_data(city=None, district=None, equipment_code=None):
    params = {
        'serviceKey': SERVICE_KEY,
        'numOfRows': 1000,
        'pageNo': 1,
        'type': 'json'
    }

    # 장비코드가 입력된 경우 해당 장비코드로 데이터 조회
    if equipment_code:
        params['mnlssRegltCameraManageNo'] = equipment_code
    else:
        # 시도명과 시군구명을 기준으로 데이터 조회
        if city:
            params['ctprvnNm'] = correct_region_name(city)
        if district:
            params['signguNm'] = district
    
    response = requests.get(API_URL, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if 'response' in data and 'body' in data['response'] and 'items' in data['response']['body']:
            return data['response']['body']['items']
        else:
            st.warning("해당 요청에 대한 데이터를 찾을 수 없습니다.")
            return []
    else:
        st.error("API 요청에 실패했습니다: " + response.text)
        return []

# 데이터베이스 초기화 버튼 추가
def reset_database():
    conn = sqlite3.connect('vehicle_violations.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM violations')
    conn.commit()
    conn.close()
    if 'equipment_code_input' in st.session_state:
        del st.session_state['equipment_code_input']
    st.warning("전체 데이터베이스가 초기화되었습니다. 분석할 파일을 새로 업로드하세요. 수동으로 새로고침 해주세요.")

# 이메일 알림 기능 추가
def send_email_alert(recipient_email, subject, body):
    sender_email = "your_email@example.com"
    sender_password = "your_password"
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.close()
        st.success("이메일 알림이 성공적으로 전송되었습니다.")
    except Exception as e:
        st.error(f"이메일 전송 실패: {e}")

# Streamlit 앱 시작
st.title("차량단속 데이터 분석 대시보드")

# 데이터베이스 생성
tab1, tab2, tab3 = st.tabs(["단속건수 분석", "단속장비 정보조회", "TCS와 TEMS 데이터 비교"])

# 단속건수 분석 탭
with tab1:
    st.header("단속건수 분석")
    uploaded_file = st.file_uploader("엑셀 파일 업로드", type=['xlsx'])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        save_to_database(df)
        st.success("데이터베이스에 저장되었습니다.")

    # 최근 분석 결과 표시
    conn = sqlite3.connect('vehicle_violations.db')
    df_db = pd.read_sql('SELECT * FROM violations', conn)
    conn.close()

    if not df_db.empty:
        # 장비코드 추가
        df_db['장비코드'] = df_db['일련번호'].str[:5]

        # 날짜 선택 위젯 추가
        st.sidebar.header("분석 결과 날짜 선택")
        df_db['위반일시'] = pd.to_datetime(df_db['위반일시'])
        available_dates = df_db['위반일시'].dt.date.unique()
        date_range = st.sidebar.date_input("기간 선택", value=(min(available_dates), max(available_dates)), min_value=min(available_dates), max_value=max(available_dates))
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date, end_date = min(available_dates), max(available_dates)
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
            st.warning("필터가 초기화되었습니다. 필요한 필터를 다시 선택하세요.")

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

            # 단속 건수 및 위반유형별 건수 통합 표로 표시
            st.subheader('단속 건수 요약')
            daily_counts = df_selected.groupby(df_selected['위반일시'].dt.date)['일련번호'].nunique().reset_index(name='단속 건수')
            daily_counts.columns = ['날짜', '단속 건수']

            violation_counts = df_selected.groupby([df_selected['위반일시'].dt.date, '위반유형'])['일련번호'].nunique().unstack(fill_value=0)
            violation_counts.index.name = '날짜'

            combined_df = pd.concat([daily_counts.set_index('날짜').T, violation_counts.T], sort=False)
            combined_df = combined_df.loc[:, (combined_df != 0).any(axis=0)]  # 모든 건수가 0인 열 제거
            total_violations = df_selected['일련번호'].nunique()
            st.write(f'총 단속건수: {total_violations} 건')
            st.write(combined_df)

            # 데이터 다운로드 버튼 추가
            csv = df_selected.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="데이터 다운로드 (CSV)",
                data=csv,
                file_name='traffic_violation_data.csv',
                mime='text/csv'
            )

            # 장비코드 검색 및 단속 건수 표시 (통합 표로 변경)
            st.header("장비코드 별 단속건수")
            equipment_code_input = st.text_input("장비코드를 입력하세요 (예: F1234, G5678 등)", value="", key='equipment_code_input')
            if equipment_code_input:
                specific_equipment_data = df_selected[df_selected['장비코드'] == equipment_code_input]
                if not specific_equipment_data.empty:
                    st.write(f"장비코드 {equipment_code_input}의 단속 장소: {specific_equipment_data['위반장소'].iloc[0]}")
                    daily_counts = specific_equipment_data.groupby(specific_equipment_data['위반일시'].dt.date)['일련번호'].nunique().reset_index(name='단속 건수')
                    daily_counts.columns = ['날짜', '단속 건수']

                    violation_counts = specific_equipment_data.groupby([specific_equipment_data['위반일시'].dt.date, '위반유형'])['일련번호'].nunique().unstack(fill_value=0)
                    violation_counts.index.name = '날짜'

                    combined_df_specific = pd.concat([daily_counts.set_index('날짜').T, violation_counts.T], sort=False)
                    combined_df_specific = combined_df_specific.loc[:, (combined_df_specific != 0).any(axis=0)]  # 모든 건수가 0인 열 제거
                    total_specific_violations = specific_equipment_data['일련번호'].nunique()
                    st.write(f'총 단속건수: {total_specific_violations} 건')
                    st.write(combined_df_specific)

                    # 이메일 알림 발송 옵션 추가
                    recipient_email = st.text_input("이메일 주소를 입력하세요 (알림 전송용)")
                    if st.button("이메일 알림 발송"):
                        if recipient_email:
                            subject = f"장비코드 {equipment_code_input}의 단속 건수 통계"
                            body = combined_df_specific.to_string()
                            send_email_alert(recipient_email, subject, body)
                        else:
                            st.error("이메일 주소를 입력해주세요.")
# 데이터베이스 초기화 버튼
if st.sidebar.button("전체 DB 삭제"):
    reset_database()
    st.warning("전체 데이터베이스가 초기화되었습니다. 수동으로 새로고침 해주세요.")

# 단속장비 정보조회 탭
with tab2:
    st.header("무인 교통 단속 카메라 정보조회")
    # 장비코드를 입력받아 해당 정보를 조회하는 폼 추가
    option = st.radio("조회 옵션을 선택하세요", ('장비코드로 조회', '시도명/시군구명으로 조회'))
    if option == '장비코드로 조회':
        equipment_code_input = st.text_input("장비코드를 입력하세요 (예: F1234, G5678 등)", key='equipment_code_lookup')
        if equipment_code_input:
            pattern = r'^[F-J][0-9]{4}$'
            if re.match(pattern, equipment_code_input):
                specific_camera_data = get_camera_data(equipment_code=equipment_code_input)
                if specific_camera_data:
                    st.write(f"장비코드 {equipment_code_input}의 카메라 데이터:")
                    st.dataframe(pd.DataFrame(specific_camera_data))
                else:
                    st.write(f"장비코드 {equipment_code_input}에 해당하는 카메라 정보가 없습니다.")
            else:
                st.error("올바른 장비코드를 입력해주세요 (알파벳 F-J, 숫자 0000-9999 형식)")
    elif option == '시도명/시군구명으로 조회':
        # 시도명과 시군구명 입력 필드 추가
        city = st.text_input("시도명을 입력하세요 (예: 서울, 경상남도 등)", "서울특별시")
        district = st.text_input("시군구명을 입력하세요 (예: 강남구, 창원시 등)")

        # 사용자가 버튼을 눌러 데이터를 가져옴
        if st.button("카메라 데이터 가져오기"):
            camera_data = get_camera_data(city=city, district=district)
            st.session_state['camera_data'] = camera_data

    # 세션 상태에 데이터가 있는 경우 표시
    if 'camera_data' in st.session_state and st.session_state['camera_data'] and option == '시도명/시군구명으로 조회':
        df = pd.DataFrame(st.session_state['camera_data'])
        st.write(f"{city} {district}의 카메라 데이터:")
        st.dataframe(df)

        # 지도 생성
        if not df.empty:
            center_lat = df['latitude'].astype(float).mean()
            center_lon = df['longitude'].astype(float).mean()

            # Folium 지도 객체 생성
            folium_map = folium.Map(location=[center_lat, center_lon], zoom_start=12)

            # 카메라 위치를 지도에 추가
            for idx, row in df.iterrows():
                folium.Marker([float(row['latitude']), float(row['longitude'])],
                              popup=f"단속구분: {row['regltSe']}<br>장소: {row['itlpc']}<br>제한속도: {row['lmttVe']}km/h").add_to(folium_map)

            # Streamlit에 Folium 지도 표시
            st_folium(folium_map)

# TCS와 TEMS 데이터 비교 탭
with tab3:
    st.title("TCS와 TEMS 데이터 비교 도구")
    st.write("두 개의 엑셀 파일을 업로드하여 데이터 일치 여부를 확인하세요.")

    # 파일 업로더
    col1, col2 = st.columns(2)

    with col1:
        uploaded_tcs = st.file_uploader("TCS 엑셀 파일 업로드", type=['xlsx'])
        if uploaded_tcs is not None:
            st.session_state.uploaded_tcs = uploaded_tcs  # 파일을 세션에 저장
    with col2:
        uploaded_tems = st.file_uploader("TEMS 엑셀 파일 업로드", type=['xlsx'])
        if uploaded_tems is not None:
            st.session_state.uploaded_tems = uploaded_tems  # 파일을 세션에 저장

    # 세션 상태에서 파일 읽기
    if 'uploaded_tcs' in st.session_state and 'uploaded_tems' in st.session_state:
        df_tcs = pd.read_excel(st.session_state.uploaded_tcs)
        df_tems = pd.read_excel(st.session_state.uploaded_tems)


        # 열 이름에서 줄바꿈 문자와 공백 제거
        df_tcs.columns = df_tcs.columns.str.replace(r'[\n\r]+', '', regex=True).str.strip()

        # 열 이름 매핑 (특정 열을 새로운 이름으로 매핑)
        tcs_column_mapping = {
            '장비번호': '장비코드',
            '운영상태': '장비운영상태',
            '장비종류': '단속형태',
            '설치장소': '설치지점',
            '설치 장소': '설치지점',
            '관할서': '관할경찰서',
            '제한속도(소형)': '제한속도',
            '단속속도(소형)': '단속속도',
            '최초정상운영시작일': '정상운영일',
            '제작회사': '설치업체'
        }

        tems_column_mapping = {
            '제어기 번호': '장비코드',
            '제어기모드': '장비운영상태',
            '제어기 유형': '단속형태',
            '설치주소': '설치지점',
            '경찰서 명칭': '관할경찰서',
            '소형제한속도': '제한속도',
            '소형단속속도': '단속속도',
            '설치일시': '정상운영일',
            '업체명': '설치업체'
        }

        # 열 이름 통일
        df_tcs.rename(columns=tcs_column_mapping, inplace=True)
        df_tems.rename(columns=tems_column_mapping, inplace=True)

        # TCS 데이터프레임의 정상운영일 열에서 '-'를 '.'로 변경 및 날짜 형식 통일
        df_tcs['정상운영일'] = df_tcs['정상운영일'].str.replace('.', '-')
        df_tcs['정상운영일'] = pd.to_datetime(df_tcs['정상운영일'], errors='coerce').dt.strftime('%Y년 %m월 %d일')

        # TEMS 데이터프레임의 정상운영일 열에서 시간 제거 및 날짜 형식 통일
        df_tems['정상운영일'] = pd.to_datetime(df_tems['정상운영일'], errors='coerce').dt.strftime('%Y년 %m월 %d일')

        
        # 값 매핑 딕셔너리 (비교 시 사용)
        value_mappings = {
            '설치업체': {
                '토페스': '토페스',
                '(주)토페스': '토페스',
                '건아정보': '건아정보기술(주)',
                '건아정보기술': '건아정보기술(주)',
                '건아정보(주)': '건아정보기술(주)',
                '건아기전': '건아정보기술(주)',
                '건아': '건아정보기술(주)',
                '건아정보기술(주)': '건아정보기술(주)',
                '진우산전': '진우ATS',
                '진우산전(주)': '진우ATS',
                '진우': '진우ATS',
                '진우에티에스': '진우ATS',
                '진우에이티에스': '진우ATS',
                '유니시큐': '유니시큐',
                '유니씨큐': '유니시큐',
                '아몽': '아몽솔루션(주)',
                '아몽솔루션': '아몽솔루션(주)',
                '아몽솔류션': '아몽솔루션(주)',
                '아프로시스': '아프로시스템즈',
                '아프로': '아프로시스템즈',
                '아프로시스템': '아프로시스템즈',
                '알티솔류션': '알티솔루션',
                '비츠로시스': '비츠로시스(주)',
                '비츠로시스(주)': '(주)비츠로시스',
                '하이테콤': '(주)하이테콤',
                '(주)렉스젠': '렉스젠'
            },
            '단속형태': {
                '과속': '과속제어기',
                '과속제어기': '과속제어기',
                '과속 및 신호': '다기능제어기',
                '다기능제어기': '다기능제어기',
                '구간단속': '구간제어기',
                '구간제어기': '구간제어기'
            },
            '장비운영상태': {
                '정상운영': '정상운영',
                '정상운영모드': '정상운영',
                '일시정지모드': '정상운영',
                '시범운영': '시범운영',
                '시범운영모드': '시범운영',
                '폐기': '폐기'
            },
            '관할경찰서': {
                '경남고성경찰서': '고성경찰서',
                '고성 경찰서': '고성경찰서',
                '고성경찰서': '고성경찰서',
                '6지구대': '６지구대',
            }
        }

        # 값 매핑 함수 정의
        def map_values(column, value):
            mapping = value_mappings.get(column, {})
            return mapping.get(value, value)

        # 비교를 위한 데이터프레임 복사 (원본 데이터 유지)
        df_tcs_compare = df_tcs.copy()
        df_tems_compare = df_tems.copy()

        # 비교할 열에 대해 값 매핑 적용
        for col in ['장비운영상태', '단속형태', '설치지점', '설치업체', '제한속도', '단속속도', '정상운영일', '관할경찰서']:
            if col in df_tcs_compare.columns:
                df_tcs_compare[col] = df_tcs_compare[col].apply(lambda x: map_values(col, x))
            if col in df_tems_compare.columns:
                df_tems_compare[col] = df_tems_compare[col].apply(lambda x: map_values(col, x))

            # '폐기' 상태 제거
            if '장비운영상태' in df_tcs_compare.columns:
                df_tcs_compare = df_tcs_compare[df_tcs_compare['장비운영상태'] != '폐기']
            if '장비운영상태' in df_tems_compare.columns:
                df_tems_compare = df_tems_compare[df_tems_compare['장비운영상태'] != '폐기']

        # 비교할 열 목록
        compare_columns = ['장비운영상태', '단속형태', '설치지점', '설치업체', '제한속도', '단속속도', '정상운영일', '관할경찰서']

        # 각 데이터프레임에서 실제로 존재하는 비교할 열 찾기
        tcs_columns_available = [col for col in compare_columns if col in df_tcs_compare.columns]
        tems_columns_available = [col for col in compare_columns if col in df_tems_compare.columns]

        # 두 데이터프레임에 공통으로 존재하는 열만 비교
        common_columns = list(set(tcs_columns_available).intersection(set(tems_columns_available)))

        # 비교할 열에 '장비코드' 추가
        common_columns_with_code = ['장비코드'] + common_columns

        # 필요한 열만 선택
        df_tcs_compare = df_tcs_compare[common_columns_with_code]
        df_tems_compare = df_tems_compare[common_columns_with_code]

        # 두 데이터프레임을 outer join으로 병합
        df_merged = pd.merge(df_tcs_compare, df_tems_compare, on='장비코드', how='outer', suffixes=('_TCS', '_TEMS'))
        
        # 데이터 비교를 위한 병합
        #df_merged = pd.merge(df_tcs_compare, df_tems_compare, on='장비코드', how='inner', suffixes=('_TCS', '_TEMS'))

        # TCS와 TEMS의 장비운영상태 및 단속형태에 따른 장비 대수 계산
        def get_equipment_summary(df, equipment_type_column='단속형태', operation_status_column='장비운영상태'):
            summary = {}
            unique_statuses = df[operation_status_column].unique()
            for status in unique_statuses:
                # 장비운영상태별로 필터링
                df_status = df[df[operation_status_column] == status]
                status_summary = {
                    '과속장비': df_status[df_status[equipment_type_column] == '과속제어기'].shape[0],
                    '다기능장비': df_status[df_status[equipment_type_column] == '다기능제어기'].shape[0],
                    '구간장비': df_status[df_status[equipment_type_column] == '구간제어기'].shape[0]
                }
                summary[status] = status_summary
            return summary

        # TCS 및 TEMS 데이터의 장비운영상태 및 단속형태별 요약 계산
        tcs_summary = get_equipment_summary(df_tcs_compare)
        tems_summary = get_equipment_summary(df_tems_compare)

        # Streamlit UI에 요약 표시
        #st.subheader("TCS 및 TEMS 장비 대수 요약")

        # 요약 내용을 표 형태로 표시
        #st.write("### TCS 장비 요약")
        #for status, counts in tcs_summary.items():
        #    st.write(f"**{status} 장비**")
        #    for equipment_type, count in counts.items():
        #        st.write(f"- {equipment_type}: {count}대")

        #st.write("### TEMS 장비 요약")
        #for status, counts in tems_summary.items():
        #    st.write(f"**{status} 장비**")
        #    for equipment_type, count in counts.items():
        #        st.write(f"- {equipment_type}: {count}대")

        # 장비운영상태별 및 단속형태별 요약을 표로 보기 좋게 정리
        summary_df = pd.DataFrame({
            '운영상태': [],
            'TCS - 과속장비': [],
            'TCS - 다기능장비': [],
            'TCS - 구간장비': [],
            'TEMS - 과속장비': [],
            'TEMS - 다기능장비': [],
            'TEMS - 구간장비': []
        })

        # 각 장비운영상태에 따른 장비 대수 추가
        all_statuses = set(tcs_summary.keys()).union(set(tems_summary.keys()))
        summary_rows = []
        for status in all_statuses:
            tcs_counts = tcs_summary.get(status, {'과속장비': 0, '다기능장비': 0, '구간장비': 0})
            tems_counts = tems_summary.get(status, {'과속장비': 0, '다기능장비': 0, '구간장비': 0})
            
            # 새 행을 딕셔너리로 생성
            row = {
                '운영상태': status,
                'TCS - 과속장비': tcs_counts['과속장비'],
                'TCS - 다기능장비': tcs_counts['다기능장비'],
                'TCS - 구간장비': tcs_counts['구간장비'],
                'TEMS - 과속장비': tems_counts['과속장비'],
                'TEMS - 다기능장비': tems_counts['다기능장비'],
                'TEMS - 구간장비': tems_counts['구간장비']
            }
            summary_rows.append(row)

        # pd.concat()을 사용해 데이터프레임 생성
        summary_df = pd.concat([summary_df, pd.DataFrame(summary_rows)], ignore_index=True)

        # 표 형태로 요약 결과 출력
        st.subheader("운영상태 및 단속형태별 TCS 및 TEMS 장비 대수 요약")
        st.dataframe(summary_df)

        # 차이가 나는 장비 추출
        differences = []

        for index, row in df_merged.iterrows():
            diff = {'장비코드': row['장비코드']}
            has_difference = False
            for col in compare_columns:
                if col in common_columns:
                    val_tcs = row[f"{col}_TCS"]
                    val_tems = row[f"{col}_TEMS"]
                    if pd.isnull(val_tcs) and pd.isnull(val_tems):
                        diff[col] = val_tcs
                    elif val_tcs != val_tems:
                        diff[col] = f"{val_tcs} | {val_tems}"
                        has_difference = True
                    else:
                        diff[col] = val_tcs
                else:
                    diff[col] = None  # 해당 열이 존재하지 않을 경우
            if has_difference:
                differences.append(diff)

        if differences:
            st.subheader("🔍 차이가 나는 장비 목록")
            differences_df = pd.DataFrame(differences)
            # 표시할 열 순서 지정
            display_columns = ['장비코드', '장비운영상태', '단속형태', '설치지점', '설치업체',
                               '제한속도', '단속속도', '정상운영일', '관할경찰서']
            # differences_df에 존재하는 열만 선택
            existing_columns = [col for col in display_columns if col in differences_df.columns]
            differences_df = differences_df[existing_columns]
            st.dataframe(differences_df)
        else:
            st.write("차이가 나는 장비가 없습니다.")

        # Streamlit의 선택 상자를 사용해 필터링 조건 선택 (기본 선택은 '장비운영상태')
        filter_option = st.selectbox(
            "비교할 항목을 선택하세요:",
            ['장비운영상태', '단속형태', '설치지점', '관할경찰서', '설치업체', '정상운영일', '제한속도', '단속속도'],
            index=0  # 기본 선택값으로 '장비운영상태' 설정
        )

        # 선택된 항목에 대해 서로 다른 데이터 필터링 및 출력
        if filter_option == '장비운영상태':
            different_operating_status = df_merged[df_merged['장비운영상태_TCS'] != df_merged['장비운영상태_TEMS']]
            st.write("장비운영상태가 서로 다른 항목들:")
            st.write(different_operating_status[['장비코드', '장비운영상태_TCS', '장비운영상태_TEMS']])
        elif filter_option == '단속형태':
            different_violation_type = df_merged[df_merged['단속형태_TCS'] != df_merged['단속형태_TEMS']]
            st.write("단속형태가 서로 다른 항목들:")
            st.write(different_violation_type[['장비코드', '단속형태_TCS', '단속형태_TEMS']])
        elif filter_option == '설치지점':
            different_install_location = df_merged[df_merged['설치지점_TCS'] != df_merged['설치지점_TEMS']]
            st.write("설치지점이 서로 다른 항목들:")
            st.write(different_install_location[['장비코드', '설치지점_TCS', '설치지점_TEMS']])
        elif filter_option == '관할경찰서':
            different_police_station = df_merged[df_merged['관할경찰서_TCS'] != df_merged['관할경찰서_TEMS']]
            st.write("관할경찰서가 서로 다른 항목들:")
            st.write(different_police_station[['장비코드', '관할경찰서_TCS', '관할경찰서_TEMS']])
        elif filter_option == '설치업체':
            different_installation_company = df_merged[df_merged['설치업체_TCS'] != df_merged['설치업체_TEMS']]
            st.write("설치업체가 서로 다른 항목들:")
            st.write(different_installation_company[['장비코드', '설치업체_TCS', '설치업체_TEMS']])
        elif filter_option == '정상운영일':
            different_normal_operating_date = df_merged[df_merged['정상운영일_TCS'] != df_merged['정상운영일_TEMS']]
            st.write("정상운영일이 서로 다른 항목들:")
            st.write(different_normal_operating_date[['장비코드', '정상운영일_TCS', '정상운영일_TEMS']])
        elif filter_option == '제한속도':
            different_speed_limit = df_merged[df_merged['제한속도_TCS'] != df_merged['제한속도_TEMS']]
            st.write("제한속도가 서로 다른 항목들:")
            st.write(different_speed_limit[['장비코드', '제한속도_TCS', '제한속도_TEMS']])
        elif filter_option == '단속속도':
            different_control_speed = df_merged[df_merged['단속속도_TCS'] != df_merged['단속속도_TEMS']]
            st.write("단속속도가 서로 다른 항목들:")
            st.write(different_control_speed[['장비코드', '단속속도_TCS', '단속속도_TEMS']])

    else:
        st.warning("두 개의 엑셀 파일을 모두 업로드해주세요.")

# Streamlit 화면에 매핑 후 데이터프레임 출력
#st.subheader("TCS 데이터 매핑 후 결과")
#st.write(df_tcs_compare)
#st.subheader("TEMS 데이터 매핑 후 결과")
#st.write(df_tems_compare)


# 열 이름 매핑 후 데이터프레임 확인
#st.write("TCS 열 이름 매핑 후 데이터프레임:")
#st.write(df_tcs.head())
#st.write("TEMS 열 이름 매핑 후 데이터프레임:")
#st.write(df_tems.head())

# 열 이름 매핑 후 열 목록 확인
#st.write("TCS 열 이름 매핑 후 열 목록:")
#st.write(df_tcs.columns)
#st.write("TEMS 열 이름 매핑 후 열 목록:")
#st.write(df_tems.columns)
