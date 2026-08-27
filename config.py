import os

TOKEN = os.environ.get('DISCORD_TOKEN')
CHANNEL_ID = 1479135627046817989  # 알림을 보낼 채널 ID
SLEEP_START = 0   # 새벽 0시
SLEEP_END = 7     # 아침 7시
TASKS_DATA_FILE = os.environ.get('TASKS_DATA_FILE', 'tasks_data.json')
TLI_CREDENTIALS_FILE = os.environ.get('TLI_CREDENTIALS_FILE', 'tli_credentials.json')
TLI_BASE_URL = os.environ.get('TLI_BASE_URL', 'https://api-tlitodos.parafara.cloud')
