# PTM 45 nm NMOS Reproducible Analysis

**Reproducible ngspice–Python analysis of PTM 45 nm HP/LP NMOS**

**최신 공개 릴리스:** v1.1<br>
**릴리스 날짜:** 2026-08-22<br>
**v1.1 수치·자동화 검증일:** 2026-08-22<br>
**데이터·수치 검증일:** 2026-08-15<br>
**공개 패키지 검증일:** 2026-08-22<br>
**테스트 환경:** Python 3.12<br>
**데이터 유형:** PTM 모델 기반 ngspice 시뮬레이션 — 실제 웨이퍼 측정값 아님

PTM 45 nm Bulk CMOS의 high-performance(HP)·low-power(LP) NMOS 모델을
ngspice로 DC sweep하고, Python으로 `Ion`, `Ioff`, `Ion/Ioff`, minimum local
subthreshold swing(SS), constant-current 문턱전압(`Vth`)과 DIBL을 추출하는
파이프라인입니다. 동일한 가공 시뮬레이션 CSV를 입력으로 Excel 수식을 별도
구현해 기존 지표의 계산 일치성을 확인했고, SS 설정과 Vth 기준전류를 바꿔
추출 알고리즘 민감도를 점검했습니다.

이 저장소는 **비교 조건 통제 → 경계 문제 탐지 → sweep 확장 → 지표 추출 →
교차 구현 검산 → 민감도·회귀 테스트**의 추적 가능한 흐름을 보여주는
포트폴리오입니다. 결과는 명목 PTM 모델의 DC 시뮬레이션이며, 측정 웨이퍼,
실제 공정 변동, 수율, 회로 속도 또는 전체 전력 측정 결과가 아닙니다.

![공통 1.0 V에서의 HP·LP 핵심 지표 비교](results/figures/hp_lp_common_vdd_metrics.png)

## 한눈에 보기

| 구분 | 내용 |
|---|---|
| 문제 | 서로 다른 명목 VDD와 SS 회귀창의 sweep 하한 접촉이 비교를 왜곡할 수 있음 |
| 구현 | ngspice DC sweep, tidy CSV, Ion/Ioff/SS/Vth/DIBL 자동 추출, 그림·요약 생성 |
| 핵심 판단 | HP·LP 비교 바이어스를 통제하고 Vth는 `10⁻⁷ × W/L A`에서 정의 |
| 검산 | 자동 단위·통합·회귀·무결성 테스트, Excel 교차 구현, SS·Vth 기준 민감도 |
| 한계 | 단일 W/L·25 °C·명목 PTM DC 결과이며 실제 실리콘·PVT·공정 분포를 검증하지 않음 |

빠르게 보려면 [공통 1.0 V 결과](#공통-10-v-핵심-결과),
[Vth·DIBL 기준 결과](#v11-vthdibl-기준-결과),
[대표 문제 해결](#2-대표-문제-해결), [재현 방법](#3-재현-방법),
[검증 범위와 한계](#9-검증-범위와-한계)를 순서대로 확인하세요.

## 1. 릴리스 상태

| 항목 | v1.0-public | v1.1 |
|---|---:|---:|
| 시뮬레이션 곡선 | 5개 | 5개 |
| 가공 데이터 | 1,245행 | 1,245행 |
| Python Ion/Ioff/SS 지표 | 4행, 21열 | 4행, 21열 |
| Vth/DIBL 지표 | 미포함 | 기준 3행 + 민감도 15행 |
| 자동화 테스트(단위·통합·회귀·무결성) | 20/20 PASS | 38/38 PASS |
| Python–Excel 교차 구현 검산 | 16/16 PASS | 16/16 PASS |
| SS 추출 민감도 조건 | 60개 평가 가능 / 72개 전체 | 60개 평가 가능 / 72개 전체 |
| 정의상 평가 불가 | 12개 — 11점 창·span 조합 | 12개 — 11점 창·span 조합 |
| 평가 가능 조건의 VGS 하한 접촉 | 0건 | 0건 |

### v1.1 Vth·DIBL 기준 결과

Vth는 `ID,target = 10⁻⁷ × (W/L) A`인 constant-current 기준과
`log10(ID)`–`VGS` 선형 보간으로 추출했습니다. 현재 `W = 1 µm`,
`L = 0.045 µm`이므로 기준전류는 `2.22222222222e-6 A`입니다.

| 모델 | 비교 기준 | VDS low→high (V) | Vth low (V) | Vth high (V) | DIBL (mV/V) |
|---|---|---:|---:|---:|---:|
| HP | 공통 1.0 V | 0.05→1.0 | 0.323646394 | 0.184795847 | 146.158470 |
| LP | 공통 1.0 V | 0.05→1.0 | 0.530393011 | 0.457564062 | 76.662052 |
| LP | 모델 명목 1.1 V | 0.05→1.1 | 0.530393011 | 0.450641602 | 75.953722 |

HP의 명목 VDD와 공통 비교 VDD는 모두 1.0 V이므로 동일한 비교를 중복하지
않습니다. 따라서 결과는 HP 공통 1행, LP 공통·명목 2행으로 총 3행입니다.
이는 누락이 아니라 비교 조건 중복 제거에 따른 의도된 비대칭입니다.

### 공통 1.0 V 핵심 결과

두 모델 모두 `VGS = VDS = 1.0 V`, `W = 1 µm`, `L = 45 nm`, `25 °C`로
맞춘 결과가 HP–LP 비교의 주 결과입니다.

| 모델 | Ion (µA/µm) | Ioff (A/µm) | Ion/Ioff | Minimum local SS* (mV/dec) |
|---|---:|---:|---:|---:|
| HP | 1339.206 | 2.004500e-08 | 6.681000e+04 | 87.50593 |
| LP | 401.985 | 2.115037e-11 | 1.900603e+07 | 86.64802 |

\* 프로젝트에서 정의한 21점 이동창 중 조건을 만족하는 최소값입니다.
전체 subthreshold 영역의 전역 기울기나 고유한 소자 상수를 뜻하지 않습니다.

- 동일한 DC 바이어스에서 HP의 `Ion`은 LP보다 **3.331배** 컸습니다.
  이는 구동전류 비교이며 capacitance나 회로 지연을 계산한 속도 결과는 아닙니다.
- HP의 `Ioff`는 LP보다 **947.74배** 컸으므로 이 조건에서는 LP의 정적
  누설전류가 더 작았습니다.
- LP의 `Ion/Ioff`는 HP보다 **284.48배** 컸습니다. 이 DC 비율은 동적
  전력을 포함한 전체 저전력 성능의 측정값이 아닙니다.
- 기준 minimum local SS 차이는 **0.858 mV/dec**였습니다. 프로젝트가 정한
  기술적 기준인 “모든 평가 가능 설정에서 대칭 상대차 ≤ 5%”를 적용하면 두
  값은 유사했고, 실제 최대 차이는 **1.44%**였습니다. 이는 통계적 동등성
  검정이나 산업 표준이 아니라 추출 설정에 대한 기술 통계입니다.

공통 1.0 V 비교는 외부 바이어스와 형상을 맞춘 기술적 비교입니다. 두 모델
카드는 여러 파라미터가 함께 다르므로 특정 한 파라미터의 인과효과를 분리한
실험은 아닙니다.

## 2. 대표 문제 해결

초기 0 V 시작 sweep에서는 HP의 최소 SS 회귀 구간이 sweep 하한에 닿아
더 낮은 VGS 영역이 잘린 결과일 가능성이 있었습니다.

1. 하한 접촉을 결과의 불확실성으로 식별했습니다.
2. VGS 시작점을 `−0.2 V`로 확장했습니다.
3. `Ion`과 `Ioff` 정의는 각각 지정 endpoint와 `VGS = 0 V`로 유지했습니다.
4. 동일한 가공 시뮬레이션 CSV를 Excel 수식으로 별도 구현해 Python 결과와
   교차 검산했습니다.
5. 회귀창 길이·최소 R²·최소 전류 span·전류 상한을 바꿔 추출 알고리즘의
   민감도를 확인했습니다.

확장 후 HP 기준 구간은 `−0.035~0.065 V`, R²는 `0.9999986`, 사용점은
21개였습니다. 민감도 분석의 평가 가능 60조건 중 선택 구간이 `−0.2 V`
하한에 닿은 경우는 0건이므로 최초의 경계 문제는 평가한 범위에서
제거됐습니다. R²는 선택 구간의 직선성을 뜻하며 PTM의 물리 정확성을
검증하지 않습니다.

## 3. 재현 방법

### A. 공개 패키지 그대로 검증

모델 카드나 ngspice 없이 실행할 수 있습니다. 매니페스트 검증은 결과 파일을
덮어쓰기 전에 수행합니다.

```powershell
py -3.12 -m venv ..\ptm45-v11-venv
..\ptm45-v11-venv\Scripts\Activate.ps1
py -m pip install --requirement requirements-lock.txt
py -B -m unittest discover -s tests -v
py -B ss_sensitivity.py
py -B verify_release.py
```

가상환경은 공개 번들 무결성 검사 대상에 포함되지 않도록 저장소 바깥에
생성합니다.

기대 결과는 모든 테스트의 `OK`, SS 민감도 표의 정상 재생성, 매니페스트·
공개 번들·수치 검증의 `PASS`입니다. `-B`는 검증 중 `__pycache__`와 `.pyc`
파일이 생겨 공개 번들 검사를 방해하지 않도록 합니다.

### B. 포함된 CSV에서 지표·그림 다시 생성

```powershell
py -B ptm_pipeline.py analyze
```

기존 4행 `metrics.csv`와 그림에 더해 다음 v1.1 산출물을 생성합니다.

```text
results/vth_dibl_metrics.csv              # 기준 조건 3행
results/vth_dibl_sensitivity.csv          # 5배수 × 3비교 = 15행
results/figures/vth_comparison.png
results/figures/dibl_comparison.png
results/figures/vth_dibl_sensitivity.png
```

CSV는 12자리 유효숫자로 직렬화해 수치 라이브러리의 마지막 비트 차이를
억제합니다. 다른 운영체제의 글꼴 렌더링은 PNG 파일 해시를 바꿀 수 있으므로
의미상 재계산 일치는 자동 테스트가 허용오차로 확인합니다.

### C. ngspice부터 새로 실행

공식 PTM 모델 파일을 `models/`에 준비한 뒤 실행합니다.

```powershell
py ptm_pipeline.py all --ngspice "C:\Spice64\bin\ngspice_con.exe"
```

기대 결과:

```text
Completed: 5 curves, 1245 data rows, 4 metric rows.
```

Windows 자동 실행에는 GUI 실행 파일이 아니라 콘솔용 `ngspice_con.exe`를
사용합니다.

### 재현 가능 범위

| 목적 | 필요한 입력 | 상태 |
|---|---|---|
| 공개 ZIP 무결성·핵심 수치 확인 | 저장소 파일만 | 가능 |
| 포함된 CSV에서 지표·그림·SS 민감도 재생성 | 저장소 파일만 | 가능 |
| PTM 모델부터 새로운 전체 실행 | 공식 모델 카드·ngspice | 가능 |
| 2026-08-15 원 실행의 bit-for-bit 감사 | 당시 raw·netlist·log | 불가 — 원본 미포함 |

## 4. 모델 파일 준비

라이선스와 원본 동일성 관리를 위해 모델 카드는 배포본에 포함하지 않습니다.

| 구분 | 저장 위치 | 명목 VDD | 강제 검증 SHA-256 |
|---|---|---:|---|
| HP | `models/45nm_HP.pm` | 1.0 V | `c9ed2e513523c57a76912a35b2860cb85e4aaa3402b69757d84efa9cc2fb8410` |
| LP | `models/45nm_LP.pm` | 1.1 V | `397141eb8a813045075ac2be3098d3b136ebaf4d597c08fca627922a75e443b7` |

- PTM 공식 페이지: <https://mec.umn.edu/ptm>
- HP 모델: <https://drive.google.com/file/d/1H5eUrlxDpi2Sdmf5W9rCsjBRjttYPFZs/view?usp=drive_link>
- LP 모델: <https://drive.google.com/file/d/1l_4DKHzqwFFLugqTWzVWdWruB7eJL4mK/view?usp=drive_link>

`doctor`, `generate-netlists`, `simulate`, `process`, `all` 명령은 모델명·명목
VDD뿐 아니라 `project_config.json`의 SHA-256과 실제 파일 해시가 정확히
일치해야 진행됩니다. 생성 netlist에는 저장소 상대경로만 기록됩니다.

## 5. 시뮬레이션 조건

| 모델 | VDS | VGS 범위 | 점 수 | 용도 |
|---|---:|---:|---:|---|
| HP | 0.05 V | −0.2~1.0 V | 241 | 낮은 드레인 바이어스 |
| HP | 1.0 V | −0.2~1.0 V | 241 | HP 명목 및 공통 1.0 V |
| LP | 0.05 V | −0.2~1.1 V | 261 | 낮은 드레인 바이어스 |
| LP | 1.1 V | −0.2~1.1 V | 261 | LP 명목 조건 |
| LP | 1.0 V | −0.2~1.0 V | 241 | 공통 1.0 V 비교 |

- VGS 간격: 5 mV
- 온도: 25 °C
- W/L: 1 µm / 45 nm
- Body와 source: 0 V

HP의 명목 1.0 V 곡선은 공통 1.0 V 비교에도 재사용하므로 별도 중복
곡선을 만들지 않습니다.

## 6. 지표 정의

```text
Ion  = ID(VGS = 비교 조건의 endpoint, VDS = 해당 조건)
Ioff = ID(VGS = 0 V, VDS = 해당 조건)
```

VGS sweep은 −0.2 V에서 시작하지만 `Ioff`는 첫 데이터점이 아니라 항상
`VGS = 0 V`에서 추출합니다.

Minimum local SS는 양의 전류의 `log10(ID)`–`VGS` 관계를 다음 기준으로
분석합니다.

- 21점 연속 이동창
- 전류 상한 `max(ID) ≤ 1% × Ion`
- 전류 span ≥ 0.75 decade
- R² ≥ 0.995
- 조건을 만족하는 창 중 기울기가 가장 큰 창 선택

선택한 SS와 함께 VGS·ID 범위, 점 개수, R²와 알고리즘 이름을
`results/metrics.csv`에 기록합니다.

### Constant-current Vth

Vth 기준전류는 다음과 같이 정의합니다.

```text
ID,target = 1e-7 A × (W / L)
          = 1e-7 A × (1.0 µm / 0.045 µm)
          = 2.22222222222e-6 A
```

기준전류를 사이에 둔 두 점 `(VGS1, ID1)`, `(VGS2, ID2)`에서
`log10(ID)`를 선형 보간합니다.

```text
Vth = VGS1
    + [log10(ID,target) - log10(ID1)]
      / [log10(ID2) - log10(ID1)] × (VGS2 - VGS1)
```

VGS·ID의 NaN/Inf, 비양수 ID, 중복·비증가 VGS를 명시적으로 거부하며,
기준전류와의 교차점이 정확히 하나일 때만 값을 반환합니다. 사용한 기준전류·
추출법·보간법은 `results/vth_dibl_metrics.csv`에 함께 기록합니다.

### DIBL

낮은 VDS와 높은 VDS에서 동일한 기준전류로 추출한 Vth를 사용합니다.

```text
DIBL [mV/V]
  = 1000 × (Vth,lowVDS - Vth,highVDS)
         / (VDS,high - VDS,low)
```

높은 VDS에서 Vth가 낮아지는 일반적인 경우 양의 DIBL이 됩니다. `1000`은
분자의 V 단위를 mV로 바꾸며, 최종 단위는 `mV/V`입니다.

### Vth 기준전류 민감도

기준값에 `[0.1, 0.3, 1.0, 3.0, 10.0]`을 곱해 Vth와 DIBL이 추출 규칙에
얼마나 민감한지 확인합니다.

```text
ID,target(m) = m × 1e-7 A × (W/L)
m ∈ {0.1, 0.3, 1.0, 3.0, 10.0}
```

현재 세 비교 조건에 각 5개 배수를 적용하므로
`results/vth_dibl_sensitivity.csv`는 15행입니다. 이 결과는 기준전류 선택의
알고리즘 민감도이며, 공정·온도·소자 간 변동성 분석을 뜻하지 않습니다.

## 7. 출력과 검증 파일

```text
ptm45-nmos-reproducible-analysis/
├── .github/workflows/ci.yml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── RELEASE_MANIFEST.sha256
├── project_config.json
├── ptm_pipeline.py
├── ss_sensitivity.py
├── verify_release.py
├── requirements-lock.txt
├── models/                         # 공식 모델을 사용자가 배치
├── netlists/generated/             # 전체 실행 시 생성; Git 제외
├── data/
│   ├── raw/                        # 전체 실행 시 생성; Git 제외
│   ├── processed/                  # 5곡선·1,245행 포함
│   ├── metadata/
│   └── synthetic/
├── results/
│   ├── metrics.csv
│   ├── vth_dibl_metrics.csv
│   ├── vth_dibl_sensitivity.csv
│   ├── comparison_summary.md
│   ├── figures/
│   │   ├── id_vg_linear.png
│   │   ├── id_vg_semilog.png
│   │   ├── hp_lp_common_vdd_metrics.png
│   │   ├── vth_comparison.png
│   │   ├── dibl_comparison.png
│   │   └── vth_dibl_sensitivity.png
│   └── validation/
│       ├── PTM45_Excel_Cross_Implementation_Check.xlsx
│       ├── PTM45_SS_Sensitivity_Analysis.xlsx
│       ├── all_window_statistics.csv
│       ├── sensitivity_results.csv
│       ├── cutoff_sensitivity.csv
│       └── VALIDATION_SUMMARY.md
├── evidence/
└── tests/
```

`id_vg_linear.png`과 `id_vg_semilog.png`는 모델별 명목 조건 시각화입니다
(HP 1.0 V, LP 1.1 V). 정량 HP–LP 비교 근거는 공통 1.0 V 그림과 표입니다.
`vth_comparison.png`은 낮은·높은 VDS의 Vth, `dibl_comparison.png`은 비교
조건별 DIBL, `vth_dibl_sensitivity.png`은 기준전류 배수에 따른 결과 변화를
보여줍니다.

## 8. 배포본에 포함되지 않은 실행 이력

최신 실행에서 확보된 `ptm45_combined.csv`, `metrics.csv`,
`data_manifest.csv`는 포함돼 있습니다. 당시 ngspice가 직접 작성한 5개 raw
text, 생성 netlist와 실행 log 원본은 제공된 결과 ZIP에 없었으므로 이
공개본에도 포함하지 않았습니다.

manifest에는 당시 raw 파일의 SHA-256이 기록돼 있지만 원본이 없으므로
배포본 내부에서 다시 대조할 수는 없습니다. 공식 모델을 준비해 `all`을
실행하면 raw·netlist·log를 새로 생성할 수 있습니다.

## 9. 검증 범위와 한계

- Excel 16/16 PASS는 동일한 가공 시뮬레이션 CSV를 수식으로 별도 구현해
  Python 결과와 일치함을 확인한 교차 구현 검산입니다. 독립 데이터셋이나
  PTM의 물리 정확성 검증은 아닙니다.
- SS 민감도 PASS는 평가 가능한 모든 결과가 21점 기준값에서 ±5% 이내라는
  프로젝트 정의 수치 기준입니다. 통계적 동등성이나 산업 규격이 아닙니다.
- 민감도 분석은 추출 알고리즘 설정에 대한 점검이지 실제 공정 변동성이나
  수율 민감도가 아닙니다.
- constant-current Vth와 DIBL은 이 프로젝트가 명시한 기준에 따른 추출값이며,
  다른 기준전류·보간법·바이어스 조합과 직접 혼용하지 않습니다.
- Vth 기준전류 민감도는 정의 선택의 영향을 확인하지만, 측정 데이터나 독립
  소자 모델에 대한 물리 정확성을 검증하지 않습니다.
- DIBL은 포함된 낮은·높은 VDS 두 곡선의 차분값이며 연속 VDS 회귀 결과가
  아닙니다.
- 분석 범위는 45 nm, 단일 W/L, 25 °C, 명목 PTM 모델의 DC 특성입니다.
- 실제 공정 최적화, 불량률 또는 수율 개선 성과로 표현하지 않습니다.

## 10. 수행 범위와 도구 사용

이 저장소가 보여주는 수행 범위는 비교 조건 설계, ngspice–Python 자동화,
Ion/Ioff/SS/Vth/DIBL 정의·추출, SS 경계 문제 분석, Excel 교차 구현,
기준전류 민감도·회귀·무결성 검증, 결과 한계 문서화입니다.

ngspice, Python, Excel을 계산·검산 도구로 사용했습니다. 공개본 정리와
감사 과정에서는 생성형 AI를 문서 구조화와 점검 보조에 사용했으며, 공개
수치와 파일은 코드·수식·자동 테스트·SHA-256으로 다시 확인했습니다.

## 11. 다음 단계

- 온도·PVT·형상 변화에 대한 분석 범위 확장
- 다른 모델·시뮬레이터 또는 측정 데이터로 Vth·DIBL을 독립 교차 검증
- capacitance와 회로 지연을 포함한 성능 지표 추가
- 전체 실행의 raw·netlist·log를 별도 검토된 릴리스 증거로 보존

## 12. 참고 자료·라이선스

- University of Minnesota, Predictive Technology Model: <https://mec.umn.edu/ptm>
- ngspice stable releases: <https://ngspice.sourceforge.io/download.html>
- ngspice user manual: <https://ngspice.sourceforge.io/docs/ngspice-html-manual/manual.xhtml>

직접 작성한 코드와 문서는 `LICENSE`의 MIT License를 따릅니다. PTM 모델
카드는 포함하지 않으며 MIT License의 적용 대상이 아닙니다. 제3자 자료와
파생 출력의 범위는 `THIRD_PARTY_NOTICES.md`를 확인하세요.
