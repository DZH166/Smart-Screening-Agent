from dataclasses import dataclass, field
from pathlib import Path
import os

from hsd_tool.retention_window import RETENTION_SECONDS

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('DATA_DIR', str(ROOT / 'data'))))
    provider: str = field(default_factory=lambda: os.getenv('AI_PROVIDER', 'test'))
    openai_api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY', ''), repr=False)
    language_model: str = field(default_factory=lambda: os.getenv('LANGUAGE_MODEL', ''))
    image_model: str = field(default_factory=lambda: os.getenv('IMAGE_MODEL', ''))
    model_timeout: int = field(default_factory=lambda: int(os.getenv('MODEL_TIMEOUT', '180')))
    image_quality: str = field(default_factory=lambda: os.getenv('IMAGE_QUALITY', 'medium'))
    start_worker: bool = False
    auth_mode: str = field(default_factory=lambda: os.getenv('AUTH_MODE', 'demo'))
    secure_cookie: bool = field(default_factory=lambda: os.getenv('SECURE_COOKIE', 'false').lower() == 'true')
    lease_seconds: int = 600
    session_hours: int = 24
    api_prefix: str = '/api'
    retention_seconds: int = RETENTION_SECONDS
    config_revision: str | int = 0
    enabled: bool = True
    deepseek_pool: object = field(default=None, repr=False)
    ark_key: str = field(default='', repr=False)
    runtime_validator: object = field(default=None, repr=False)
    usage_ledger: object = field(default=None, repr=False)
    space_reserver: object = field(default=None, repr=False)

    @property
    def ai_ready(self):
        if not self.enabled or not self.language_model or not self.image_model:
            return False
        if self.provider == 'openai':
            return bool(self.openai_api_key)
        if self.provider == 'deepseek_seedream':
            return bool(self.deepseek_pool and self.ark_key)
        return False

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).resolve()
        if self.provider not in ('test', 'openai', 'deepseek_seedream'):
            raise ValueError('AI_PROVIDER 无效')
        if self.auth_mode not in ('demo', 'local', 'hsd'):
            raise ValueError('AUTH_MODE 无效')
