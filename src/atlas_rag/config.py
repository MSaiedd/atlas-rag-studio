"""Explicit model, identity and persistence settings for local and hosted deployments."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///data/atlas.db"
    data_dir: Path = Path("data")
    auth_mode: Literal["local", "oidc"] = "local"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    local_tenant: str = "northstar"
    local_client_networks: str = "127.0.0.0/8,::1/128"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_revision: str = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    reranker_revision: str = "1427fd652930e4ba29e8149678df786c240d8825"
    model_id: str = "Qwen/Qwen2.5-0.5B-Instruct"
    model_revision: str = "7ae557604adf67be50417f59c2c2f167def9a775"
    adapter_path: Path = Path("artifacts/grounded-lora")
    llm_backend: Literal["local", "compatible"] = "local"
    llm_base_url: str = "http://127.0.0.1:8080/v1"
    llm_api_key: SecretStr | None = None
    adapter_model: str = ""
    offline: bool = False
    cpu_threads: int = 2
    max_new_tokens: int = 256
    max_context_tokens: int = 4096
    retrieval_candidates: int = 16
    retrieval_top_k: int = 5
    min_rerank_score: float = -2.0
    max_upload_bytes: int = 10 * 1024 * 1024
    max_document_characters: int = 150000
    max_chunks: int = 256
    max_pending_generations: int = 4
    worker_enabled: bool = True
    model_loading: bool = True

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.auth_mode == "oidc":
            if not all((self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)):
                raise ValueError("OIDC mode requires issuer, audience and JWKS URL")
            if not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("OIDC JWKS must use HTTPS")
        if min(self.cpu_threads, self.max_pending_generations, self.retrieval_top_k) < 1:
            raise ValueError("Resource limits must be positive")
        if self.retrieval_top_k > self.retrieval_candidates:
            raise ValueError("top_k cannot exceed retrieval_candidates")
        return self
