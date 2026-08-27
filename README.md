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
  TLITODOS에 함께 등록합니다. `0`은 오늘, `3`은 3일 뒤, `week`는 7일 뒤입니다.
- `!sync_tli <JFDI ID>`: 마감일이 설정된 기존 JFDI 항목을 TLITODOS에 생성합니다. 이미 연결됐다면
  내용을 갱신합니다. 마감일이 없다면 먼저 `!deadline <ID> YYYY-MM-DD`를 사용해야 합니다.
- `!delete <JFDI ID>`: 연결된 TLITODOS 항목이 있으면 원격 삭제가 성공한 뒤 JFDI에서도 삭제합니다.
- `!done <JFDI ID>`: 연결된 TLITODOS 항목을 완료 처리한 뒤 JFDI 목록에서 제거합니다.

`!reg_tli`는 토큰이 들어 있는 원본 Discord 메시지를 가능한 경우 즉시 삭제합니다. 토큰은
`tli_credentials.json`에 저장되며 파일 권한은 `0600`으로 설정됩니다. 이 파일은 Git에서 제외됩니다.
리프레시 토큰이 등록되어 있으면 API 요청이 `401`을 반환할 때 자동으로 세션을 갱신하고 실패한
요청을 한 번 재시도합니다. 서버가 새 리프레시 토큰을 발급하면 저장된 토큰도 즉시 교체합니다.
기존 `!reg_tli <accessToken>` 형식도 계속 지원하지만, 리프레시 토큰이 없으면 만료 후 재등록해야 합니다.

## 기존 JSON 마이그레이션

기존 `tasks_data.json`을 프로젝트 실행 디렉터리에 그대로 두고 봇을 실행하면 됩니다. 기존 필드와
ID를 보존한 채 스키마 버전 2로 자동 변환하며, 최초 변환 전에
`tasks_data.v1.backup.json`을 한 번 생성합니다. TLITODOS 연결 정보는 동기화된 항목에만 다음처럼
추가됩니다.

```json
{
  "tli": {
    "todo_id": 123,
    "owner_id": "DISCORD_USER_ID"
  }
}
```

기존 `counter`, `tasks`, `user_dnd` 구조와 알려지지 않은 추가 필드는 그대로 유지됩니다.
