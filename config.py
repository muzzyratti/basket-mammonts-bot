from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
import os

class Settings(BaseSettings):
    BOT_TOKEN: SecretStr
    SPREADSHEET_ID: str
    ADMIN_IDS: str
    GROUP_CHAT_ID: int
    
    @property
    def admin_ids_list(self):
        # Превращаем строку "123,456" в список чисел [123, 456]
        return [int(x) for x in self.ADMIN_IDS.split(",") if x.strip()]

    # Путь к ключу гугла
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    SERVICE_ACCOUNT_FILE: str = os.path.join(BASE_DIR, 'data', 'service_account.json')

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

config = Settings()