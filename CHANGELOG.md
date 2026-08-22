# Changelog

## v1.1 — Unreleased

- `ID,target = 10⁻⁷ × (W/L) A` constant-current 기준과 `log10(ID)`–`VGS`
  선형 보간을 사용하는 Vth 추출을 추가했습니다.
- 낮은 VDS와 높은 VDS의 Vth로
  `1000 × (Vth,low − Vth,high) / (VDS,high − VDS,low)`를 계산해 DIBL을
  `mV/V` 단위로 기록하도록 했습니다.
- 공통 1.0 V 비교와 모델 명목 VDD 비교를 구분했습니다. HP는 명목 VDD가
  공통 VDD와 같아 중복 행을 제거하고, LP는 공통 1.0 V와 명목 1.1 V를 모두
  남겨 `results/vth_dibl_metrics.csv`에 총 3행을 기록합니다.
- Vth 기준전류에 `[0.1, 0.3, 1.0, 3.0, 10.0]` 배수를 적용하는 민감도 분석과
  15행 `results/vth_dibl_sensitivity.csv`를 추가했습니다.
- `vth_comparison.png`, `dibl_comparison.png`,
  `vth_dibl_sensitivity.png`을 추가해 기준 조건과 민감도 결과를
  시각화했습니다.
- Vth 교차점, DIBL 부호·단위, 비교 행 구성과 기준 수치를 확인하는 단위·
  통합·회귀 테스트를 보강했습니다.
- Vth 입력의 NaN/Inf, 비양수 ID, 중복·비증가 VGS와 무교차·복수교차를
  명시적 오류로 처리하도록 입력 검증을 강화했습니다.
- 설정의 W/L·온도와 처리 CSV 메타데이터가 다르면 재처리를 요구하도록 해
  오래된 데이터에 새 설정을 잘못 적용하는 경우를 차단했습니다.
- 릴리스 검증기가 기존 Ion/Ioff/SS뿐 아니라 3행 Vth/DIBL과 15행 민감도
  CSV도 원본 처리 데이터에서 다시 계산해 비교하도록 확장했습니다.
- README에 Vth/DIBL 공식, 기준전류 민감도, 재현 명령, 출력 파일과 해석
  한계를 문서화했습니다.
- 이 항목은 아직 태그·릴리스되지 않은 v1.1 작업 내역입니다.

## v1.0-public — 2026-08-19

- GitHub 첫 화면에서 핵심 결과·문제 해결·검증 범위를 빠르게 확인하도록
  README 도입부와 대표 그림을 정리했습니다.
- push와 pull request에서 20개 테스트, SS 표 재생성, 릴리스 매니페스트와
  수치 의미 검증을 수행하는 GitHub Actions workflow를 추가했습니다.
- 원본 코드·문서의 MIT License와 PTM 모델 카드 등 제3자 자료의 범위를
  설명하는 `THIRD_PARTY_NOTICES.md`를 추가했습니다.
- 모델 카드, raw 출력, 생성 netlist와 로그를 공개 저장소에서 제외하도록
  `.gitignore`를 보강했습니다.
- 로컬 Matplotlib 글꼴 캐시를 공개 패키지에서 제거했습니다.
- 모델 카드 SHA-256을 실행 전에 강제 검증하고 생성 netlist의 모델 경로를
  저장소 상대경로로 제한했습니다.
- 728개 창·72개 설정·10개 current-ceiling 결과를 재생성하는
  `ss_sensitivity.py`와 세 원본 CSV를 추가했습니다.
- 12자리 유효숫자 직렬화와 의미상 수치 검증으로 플랫폼의 마지막 비트
  차이와 파일 무결성 검사를 분리했습니다.

## v1.0 — 2026-08-15

- VGS sweep 시작점을 0 V에서 −0.2 V로 확장했습니다.
- `vgs_start_v`를 설정값과 `SweepSpec`에 추가했습니다.
- netlist, 예상 행 수, 첫점 검사, manifest와 조건 문서가 시작 전압을 사용하도록 수정했습니다.
- Ioff 정의를 `VGS = 0 V`로 명시하고 `Ioff_definition_VGS_V` 열을 추가했습니다.
- 최신 5곡선·1,245행 결과와 4행 metrics를 포함했습니다.
- 민감도 분석의 평가 가능 60조건에서 선택 SS 창의 −0.2 V 하한 접촉이
  0건임을 확인했습니다.
- Python–Excel 교차 구현 검산 16/16 PASS 파일과 SS 민감도 분석 파일을 포함했습니다.
- 확장 sweep, 행 수, bundled CSV와 필수 결과 파일을 확인하는 회귀 테스트를 추가했습니다.
- 최신 데이터로 결과 요약과 그림 3개를 다시 생성했습니다.

## Starter baseline — 2026-08-03

- 0 V 시작 sweep, 5곡선·1,045행 파이프라인
- 모델 검증, netlist 생성, ngspice 실행, CSV 처리, 지표 추출과 기본 단위 테스트
