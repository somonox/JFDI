# JFDI

Discord 명령으로 할 일을 관리하고, 원하는 항목만 사용자별 TLITODOS 계정과 동기화합니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 Discord 봇 토큰을 넣고 `python main.py`로 실행합니다.

## TLITODOS 명령

- `!reg_tli <accessToken> [refreshToken]`: 명령을 실행한 Discord 사용자의 TLITODOS 토큰을 등록합니다.
  리프레시 토큰 하나만 전달해도 자동으로 액세스 토큰을 발급합니다.
- `!add <내용>`: 기존 동작 그대로 JFDI에만 등록합니다.
- `!add_both <내용> <D-day 숫자|week>`: 마감일을 필수로 지정해 JFDI와 등록한 사용자의
  TLITODOS에 함께 등록합니다. 오늘부터 마감일까지(양 끝 날짜 포함) 매일 표시되는 루틴을
  생성합니다. `0`은 오늘 1개, `3`은 오늘부터 3일 뒤까지 4개, `week`는 8개입니다.
- `!sync_tli <JFDI ID>`: 마감일이 설정된 기존 JFDI 항목을 TLITODOS에 생성합니다. 이미 연결됐다면
  날짜별 루틴 개수와 내용을 맞춥니다. 마감일이 없다면 먼저 `!deadline <ID> YYYY-MM-DD`를 사용해야 합니다.
- `!delete <JFDI ID>`: 연결된 날짜별 TLITODOS 루틴을 모두 삭제한 뒤 JFDI에서도 삭제합니다.
- `!done <JFDI ID>`: 연결된 날짜별 TLITODOS 루틴을 모두 완료 처리한 뒤 JFDI 목록에서 제거합니다.

`!reg_tli`는 토큰이 들어 있는 원본 Discord 메시지를 가능한 경우 즉시 삭제합니다. 토큰은
`tli_credentials.json`에 저장되며 파일 권한은 `0600`으로 설정됩니다. 이 파일은 Git에서 제외됩니다.
리프레시 토큰이 등록되어 있으면 API 요청이 `401`을 반환할 때 자동으로 세션을 갱신하고 실패한
요청을 한 번 재시도합니다. 서버가 새 리프레시 토큰을 발급하면 저장된 토큰도 즉시 교체합니다.
기존 `!reg_tli <accessToken>` 형식도 계속 지원하지만, 리프레시 토큰이 없으면 만료 후 재등록해야 합니다.

TLITODOS로 보내는 마감일은 백엔드 날짜 검색과 호환되도록 `YYYY-MM-DD` 형식으로 저장합니다.
카테고리는 `할일`, `해야할 일`, `과제` 순으로 인식해 기본 TODO 카테고리를 사용하며 `취미`를
임의로 선택하지 않습니다. 기존에 잘못된 카테고리로 연결된 항목은 `!sync_tli <ID>`를 다시 실행하면
날짜와 카테고리가 함께 교정됩니다.
TLITODOS 항목은 사용자 계정이 가입한 첫 번째 그룹에 `GROUP` 공개로 등록됩니다. 가입한 그룹이
없으면 비공개 항목을 대신 만들지 않고 등록을 중단하며 오류를 안내합니다. 기존 비공개 연결 항목은
`!sync_tli <ID>`를 실행하면 그룹 공개로 갱신됩니다.
JFDI에서 TLITODOS에 새로 생성하는 항목은 일반 할 일이 아니라 `isRoutine: true`인 날짜별 루틴으로
등록됩니다. TLITODOS 프론트엔드와 마찬가지로 시작일~종료일을 펼쳐 각 날짜마다 생성 API를 호출합니다.
도중에 생성이 실패하면 이번 요청에서 먼저 생성된 항목을 삭제해 불완전한 루틴이 남지 않게 합니다.

## 기존 JSON 마이그레이션

기존 `tasks_data.json`을 프로젝트 실행 디렉터리에 그대로 두고 봇을 실행하면 됩니다. 기존 필드와
ID를 보존한 채 스키마 버전 2로 자동 변환하며, 최초 변환 전에
`tasks_data.v1.backup.json`을 한 번 생성합니다. TLITODOS 연결 정보는 동기화된 항목에만 다음처럼
추가됩니다.

```json
{
  "tli": {
    "todo_ids": [123, 124, 125],
    "owner_id": "DISCORD_USER_ID",
    "routine_start": "2026-08-28",
    "routine_end": "2026-08-30"
  }
}
```

기존 `counter`, `tasks`, `user_dnd` 구조와 알려지지 않은 추가 필드는 그대로 유지됩니다. 이전 버전의
단일 `todo_id` 연결도 계속 읽을 수 있으며, 다음 `!sync_tli` 실행 때 다중 루틴 형식으로 변환됩니다.
