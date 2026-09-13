# iram_tap

image by https://x.com/Drataniar

Windows 10/11과 OBS에서 사용하는 5이미지 입력 오버레이입니다. 전역 키보드와 마우스 이동을 감지하므로 게임이나 다른 창이 활성화된 상태에서도 동작합니다.

## 동작

- 중앙 캐릭터와 책상·키보드·마우스패드는 고정됩니다.
- 오른손과 마우스만 현재 모니터 안의 실제 커서 위치에 비례해 제한된 범위에서 움직입니다.
- 왼손 이미지는 손만 포함하며 입력 중에는 내린 자세로 교체됩니다.
- `Q W E R A S D F Space` 중 현재 눌린 키에 발광 효과가 표시됩니다.
- 여러 키를 동시에 누르면 해당 키가 모두 빛납니다.
- 마우스 버튼에 따른 별도 이미지는 사용하지 않습니다.
- Windows에서는 Scan Code를 우선 사용하므로 한/영 입력 상태와 관계없이 물리 키를 감지합니다.
- 숫자패드 `1~9`로 캐릭터를 바꾸고 `0`으로 기본 캐릭터로 돌아갑니다.
- 마이크 입력이 감지되면 현재 캐릭터의 열린 입 표정으로 바뀝니다.

## 이미지 파일과 아이콘

```text
image/
├─ character.png                 # 시작 및 숫자패드 0 기본 캐릭터
├─ character_open.png            # 마이크 입력 중 열린 입 캐릭터
├─ character1.png ~ character9.png # 숫자패드 1~9 캐릭터
├─ character1_open.png ~ character9_open.png # 숫자패드 캐릭터의 열린 입 표정
├─ desk_keyboard.png             # 책상, 키보드, 고정 마우스패드
├─ right_hand_mouse.png          # 함께 움직이는 오른손과 마우스
├─ left_hand_idle.png            # 입력이 없을 때 올린 왼손
├─ left_hand_pressed.png         # 키 입력 중 내린 왼손
└─ icon.png                      # 작업 표시줄, 트레이, EXE 아이콘
```

PNG가 없어도 프로그램은 종료되지 않고 해당 레이어만 건너뜁니다. 누락된 경로를 확인하려면 개발 환경에서 `python main.py`로 실행하십시오.

## 아이콘 변경

`image/icon.png`는 Windows 작업 표시줄과 알림 영역에 공통으로 사용됩니다. 기본 파일은 캐릭터 얼굴로 만든 256×256 투명 PNG입니다.

아이콘을 바꾸려면 같은 크기의 `image/icon.png`로 교체합니다. 실행 중인 창과 트레이에는 약 0.5초 안에 자동 반영됩니다. EXE 파일 자체의 아이콘까지 변경하려면 `build.bat`을 다시 실행해야 합니다.

## 이미지 교체

EXE 옆의 `image` 폴더에서 아래 PNG를 같은 이름으로 교체하면 실행 중에도 약 0.5초 안에 자동 반영됩니다.

- `character.png`
- `character_open.png`
- `character1.png` ~ `character9.png`
- `character1_open.png` ~ `character9_open.png`
- `desk_keyboard.png`
- `right_hand_mouse.png`
- `left_hand_idle.png`
- `left_hand_pressed.png`
- `icon.png`

파일 이름과 PNG 캔버스 비율은 유지하는 것을 권장합니다. 파일을 저장하는 순간에는 잠깐 이전 이미지나 빈 레이어가 보일 수 있지만 저장이 끝나면 다음 변경 감지 때 다시 불러옵니다.

## 설치

Python 3.10~3.13을 권장합니다. Python 3.14 이상에서는 `pygame-ce` 호환 패키지가 설치됩니다.

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 실행

```bat
python main.py
```

설정 화면만 열려면 다음 명령을 사용합니다.

```bat
python settings.py
```

## 단축키

| 키 | 동작 |
| --- | --- |
| F9 | 창 위치 잠금/해제 및 클릭 통과 전환 |
| F10 | 오버레이 표시/숨김 |
| F11 | Always On Top ON/OFF |
| F12 | 별도 설정 창 열기 |
| 숫자패드 1 | `character1.png`로 전환 |
| 숫자패드 2 | `character2.png`로 전환 |
| 숫자패드 3 | `character3.png`로 전환 |
| 숫자패드 4 | `character4.png`로 전환 |
| 숫자패드 5 | `character5.png`로 전환 |
| 숫자패드 6 | `character6.png`로 전환 |
| 숫자패드 7 | `character7.png`로 전환 |
| 숫자패드 8 | `character8.png`로 전환 |
| 숫자패드 9 | `character9.png`로 전환 |
| 숫자패드 0 | 기본 `character.png`로 복귀 |

숫자패드 캐릭터 전환은 Num Lock 상태와 관계없이 작동하며 일반 숫자열과 방향키에는 반응하지 않습니다. 선택은 실행 중에만 유지되고 프로그램을 다시 실행하면 기본 `character.png`로 시작합니다.

## 마이크 표정

F12 설정의 `마이크` 탭에서 마이크 감지 사용 여부, 입력 장치, 감지 임계값, 무음 복귀 시간과 열린 입 PNG 경로를 변경할 수 있습니다.

기본 입력 장치의 RMS 음량이 설정 임계값 이상이면 기본 캐릭터는 `character_open.png`, 숫자패드 캐릭터는 같은 번호의 `characterN_open.png`로 바뀝니다. 음량이 임계값 아래로 내려간 뒤 설정된 복귀 시간이 지나면 각 캐릭터의 일반 이미지로 돌아갑니다. 짧은 무음마다 표정이 깜빡이지 않도록 기본 복귀 시간은 180ms입니다.

마이크 표정은 숫자패드 `0~9`로 선택한 모든 캐릭터에 적용됩니다. 대응하는 `_open` PNG가 없으면 마이크 입력 중에도 일반 표정을 유지하며, 파일을 추가하면 실행 중에도 자동으로 반영됩니다. 현재 `character9_open.png`는 선택 사항입니다.

기본 마이크 설정:

```json
"microphone_enabled": true,
"microphone_device": "",
"microphone_threshold": 0.02,
"microphone_release_delay": 0.18,
"microphone_open_image": "image/character_open.png"
```

`microphone_device`가 빈 문자열이면 Windows 기본 입력 장치를 사용합니다. 주변 소음에도 반응하면 `감지 임계값 (%)`을 높이고, 말끝이 자주 끊기면 `무음 복귀 시간 (ms)`을 늘리십시오. 오디오 데이터는 저장하거나 전송하지 않습니다.

## 창 조작

위치 잠금이 해제된 상태에서는 보이는 캐릭터 부분을 좌클릭 드래그해 창을 옮길 수 있습니다. 위치 잠금을 켜면 창이 클릭을 통과시키므로 게임 입력을 가로채지 않습니다.

오버레이를 직접 우클릭하거나 Windows 알림 영역의 아이콘을 우클릭하면 다음 기능을 사용할 수 있습니다.

- 설정 열기
- 오버레이 표시/숨기기
- 크기 125%, 150%
- Always On Top
- 위치 잠금
- 프로그램 종료

창을 옮긴 위치는 `config.json`의 `window_x`, `window_y`에 저장됩니다.

## 이미지 설정

F12 설정 화면의 `이미지` 탭에서 5개 PNG의 경로, 위치, 크기를 조절할 수 있습니다. 오른손과 왼손 이미지를 선택하면 미리보기의 파란 점선 영역을 직접 드래그해 위치를 옮길 수 있으며, X/Y 입력값도 바로 갱신됩니다.

기본 논리 캔버스는 원본 그림에 맞춘 `300×300` 정사각형입니다. 크기 메뉴의 125%는 `375×375`, 150%는 `450×450`으로 표시됩니다.

- `[0, 0]` 크기: PNG 원본 크기
- 너비 또는 높이만 지정: 지정한 축에 맞춰 비율 유지
- 너비와 높이 지정 + 비율 유지: 지정 영역 안에 맞춤
- 비율 유지 해제: 지정한 너비와 높이로 변경

`왼손 (대기)`와 `왼손 (입력 중)`은 각각 독립적으로 위치를 조절합니다. 상태가 바뀔 때 흔들리지 않게 하려면 두 이미지에 같은 위치와 크기를 사용하세요. 오른손 X/Y는 마우스 추적 이동 범위의 중심 위치입니다. 기본 구성에서 이미지 위치는 다음과 같습니다.

```text
character                 0, 0     300×300
desk_keyboard             0, 0     300×300
right_hand_mouse          0, 0     300×300
left_hand_idle            0, 0     300×300
left_hand_pressed         0, 0     300×300
```

## 키 발광 설정

발광 위치는 300×300으로 표시된 `desk_keyboard.png` 내부 기준 좌표입니다. 책상·키보드 이미지 크기를 변경하면 발광 위치와 크기도 같은 비율로 자동 조정됩니다. 그림에 보이는 글자 그대로 위쪽 긴 키는 `Space`, 첫째 줄은 왼쪽부터 `F D S A`, 둘째 줄은 `R E W Q`에 대응합니다.

1. F12 설정에서 `키 발광` 탭을 엽니다.
2. `Q W E R A S D F Space` 중 하나를 선택합니다.
3. 미리보기의 노란 점선 영역을 해당 키 위로 드래그합니다.
4. 필요하면 발광 너비와 높이를 조절합니다.
5. `저장`을 누릅니다.

`창/동작` 탭에서는 키 발광 색과 투명도를 변경할 수 있습니다. 실제 실행 중에는 현재 눌린 키별 발광이 모두 동시에 렌더링됩니다.

## 마우스 클릭 발광 설정

1. F12 설정에서 `마우스 발광` 탭을 엽니다.
2. `왼쪽 클릭` 또는 `오른쪽 클릭`을 선택합니다.
3. 미리보기의 점선 영역을 원하는 마우스 버튼 위로 드래그합니다.
4. 필요하면 발광 너비, 높이, 색상과 투명도를 조절합니다.
5. `저장`을 누릅니다.

클릭 발광 좌표는 300×300 오른손 PNG 내부 기준이며, 오른손 이미지 크기를 변경하면 위치와 크기도 자동 조정됩니다.

## 오른손 마우스 추적

커서가 현재 위치한 모니터의 왼쪽 위는 `(0, 0)`, 오른쪽 아래는 `(1, 1)` 비율로 변환됩니다. 정면을 보는 캐릭터 시점에 맞춰 이 비율의 좌우와 상하를 모두 반전하고, 책상 방향에 맞게 26도 회전한 뒤 `right_hand_mouse` 기본 위치와 X/Y 이동 범위에 적용합니다. 패드는 `desk_keyboard.png`에 포함되어 이 좌표와 관계없이 고정됩니다.

```json
"right_hand_speed": 0.32,
"right_hand_range": [17, 10],
"smooth_movement": true
```

- `right_hand_range`: 기본 위치를 중심으로 움직일 최대 X/Y 거리
- `right_hand_speed`: 부드러운 이동의 추종 속도
- `smooth_movement`: 끄면 목표 위치로 즉시 이동

여러 모니터를 사용할 때도 커서가 있는 모니터 내부 비율을 반전해 사용하므로 화면 배치나 음수 좌표에 영향을 받지 않습니다.

마우스 버튼을 누르면 마우스 이미지 위의 작은 버튼 표시가 켜집니다. 왼쪽 클릭과 오른쪽 클릭은 서로 다른 위치에 독립적으로 표시되며, 두 버튼을 동시에 누르면 두 표시가 함께 켜집니다. 발광 위치는 움직이는 오른손과 마우스를 따라갑니다.

## 투명 배경과 OBS

`transparent_background`가 `true`이면 Windows 픽셀 알파를 사용해 이미지 바깥을 완전히 투명하게 표시합니다. 이 모드에서는 초록색 컬러키를 만들지 않으며 창은 자동으로 테두리 없이 표시됩니다. `background_color`는 투명 배경을 끈 경우에만 사용됩니다.

OBS 설정:

1. 오버레이를 실행합니다.
2. OBS에서 `소스 추가` -> `창 캡처`를 선택합니다.
3. `iram_tap` 창을 선택합니다.
4. 커서 캡처를 끕니다.
5. 소스 속성에 `투명도 허용`이 보이면 켭니다.

게임을 관리자 권한으로 실행했는데 입력이 감지되지 않으면 오버레이도 관리자 권한으로 실행하십시오.

## 주요 설정

| 항목 | 설명 |
| --- | --- |
| `window_width`, `window_height` | 논리 캔버스 및 시작 창 크기 |
| `window_x`, `window_y` | Windows 화면상의 창 위치 |
| `window_position_locked` | 클릭 통과 및 창 이동 잠금 |
| `transparent_background` | Windows 픽셀 알파 기반 완전 투명 배경 |
| `background_color` | 투명 배경을 껐을 때 사용할 불투명 배경색 |
| `icon_path` | 창과 트레이에서 사용하는 PNG 아이콘 경로 |
| `layer_order` | 캐릭터, 책상·키보드, 왼손, 오른손 합성 순서 |
| `right_hand_speed` | 오른손 추종 속도 |
| `right_hand_range` | 오른손 X/Y 최대 이동량 |
| `microphone_enabled` | 마이크 표정 사용 여부 |
| `microphone_device` | 입력 장치 이름, 빈 값은 시스템 기본 장치 |
| `microphone_threshold` | 마이크 RMS 감지 임계값 |
| `microphone_release_delay` | 무음 후 기본 표정 복귀 대기 시간(초) |
| `microphone_open_image` | 열린 입 캐릭터 PNG 경로 |
| `key_glow_color` | 키 발광 RGB 색상 |
| `key_glow_alpha` | 키 발광 투명도 |
| `key_glows` | 각 키의 발광 중심과 크기 |
| `mouse_glow_color` | 마우스 클릭 발광 RGB 색상 |
| `mouse_glow_alpha` | 마우스 클릭 발광 투명도 |
| `mouse_glows` | 좌·우 클릭 발광 중심과 크기 |
| `images` | 5개 PNG 경로, 위치, 크기 |

설정과 `image` 폴더의 PNG는 실행 중 0.5초 간격으로 변경 여부를 확인하고 자동으로 다시 불러옵니다.

## 코드 구성 및 검증

- `config_manager.py`: 기본 설정, 값 검증, 설정 파일 저장
- `image_geometry.py`: 이미지 크기 계산 및 발광 좌표 변환 (미리보기·렌더러 공용)
- `settings.py`: F12 설정 UI, 발광 편집·드래그
- `renderer.py`: 레이어 합성과 캐시된 캐릭터 이미지 전환
- `main.py`: 숫자패드/마이크 표정 우선순위, 설정·이미지 변경 반영
- `microphone_manager.py`: 마이크 스트림 수명 관리와 음량 감지

마이크 장치나 사용 여부를 바꾸면 스트림을 재설정합니다. 감도·복귀 시간은 다음 오디오 처리부터 적용하며, 창 위치·색상 변경은 마이크 스트림과 감지 상태를 유지합니다.

```bat
py -m unittest discover -s tests -v
```

`tests/test_microphone.py`는 실제 마이크 없이 장치 재설정, 감도 적용과 자원 해제를 검증합니다.

## EXE 빌드

```bat
build.bat
```

결과물은 `dist`에 생성됩니다.

```text
dist/
├─ iram_tap.exe
├─ config.json
└─ image/
```

배포할 때 위 세 항목을 함께 이동하십시오.

기존 `dist/config.json`이 있으면 빌드 시 사용자 설정을 보존합니다. 기본 설정으로 되돌리려면 해당 파일을 삭제한 뒤 다시 빌드하십시오.

## 문제 해결

- 이미지가 안 보임: 개발 환경에서 `python main.py`로 실행해 `[images] 누락된 이미지` 경로를 확인합니다.
- 키가 안 잡힘: 게임이 관리자 권한이면 오버레이도 관리자 권한으로 실행합니다.
- Space가 반응하지 않음: 최신 `pynput`을 설치하고 오버레이를 재시작합니다.
- 오른손 이동 폭이 너무 큼: 설정의 오른손 X/Y 이동 범위를 줄입니다.
- 발광이 키와 어긋남: F12의 `키 발광` 탭에서 점선 영역을 이동합니다.
- 마이크가 반응하지 않음: Windows 마이크 권한과 F12의 입력 장치를 확인합니다.
- 주변 소음에 계속 반응함: F12의 마이크 감지 임계값을 높입니다.
- 투명 배경이 OBS에서 검게 보임: 창 캡처 소스의 캡처 방식을 `Windows 10 (1903 이상)`으로 선택하고 `투명도 허용`을 켭니다.
