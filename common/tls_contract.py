"""Public TLS identity metadata: no filesystem paths or trust-store contents."""
from typing import Literal
from pydantic import Field
from common.api_contract import FrozenModel


class TLSVerification(FrozenModel):
    verification: Literal['dedicated-ca-ip-san-v1'] = 'dedicated-ca-ip-san-v1'
    ca_bundle_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    context_ca_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    minimum_version: Literal['TLSv1.2'] = 'TLSv1.2'
