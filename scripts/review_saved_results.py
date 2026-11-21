"""Serve the two published synthetic examples in the authenticated workspace."""
from getpass import getpass
from hashlib import sha256
from pathlib import Path
import secrets
import socket
import sys
from tempfile import TemporaryDirectory

import uvicorn

from controller.api import AppSettings, create_app
from controller.workspace import Workspace


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "reports" / "independent_api_validation_20261113"
HOST, PORT = "127.0.0.1", 8765
ORIGIN = f"http://{HOST}:{PORT}"
INPUTS = ("report.json", "verification_contract.json", "evidence.json")
# SHA-256 over the three binary file digests in INPUTS order. Copy only reviewed bytes.
EXAMPLES = (
    ("cookie-vulnerable-function-normal", "run_e573a6e9ec6d4823a48fe554e6b0790f",
     "a0581f0ce9cec3f9c72c656d966a54fef5acc16b75cab171c6ac925e35fcb5e5"),
    ("cookie-fixed-function-normal", "run_2225a84485d0462c825509cadf2307ab",
     "526afab052278de25e949f810149915fab17d7a55598db1b44f66e011108184b"),
)


def prepare_demo(directory: Path, token: str):
    reports = directory / "runs"
    for case, run_id, expected in EXAMPLES:
        source = ARCHIVE / case / "runs" / run_id
        files = {name: (source / name).read_bytes() for name in INPUTS}
        if sha256(b"".join(sha256(data).digest() for data in files.values())).hexdigest() != expected:
            raise ValueError(f"저장 예시의 원본을 확인하세요 ({case}).")
        dest = reports / run_id
        dest.mkdir(parents=True)
        for name, data in files.items():
            (dest / name).write_bytes(data)

    workspace = Workspace(profiles={}, state_path=directory / "state", reports_path=reports,
                          policy_client=None, client_factory=None)
    settings = AppSettings(database_path=directory / "sessions.sqlite3", reports_path=reports,
                           access_token=token, session_secret=secrets.token_hex(32),
                           allowed_origins=frozenset({ORIGIN}), allowed_hosts=frozenset({HOST}),
                           allowed_clients=frozenset({HOST}), saved_results_only=True)
    return create_app(settings=settings, clients={}, workspace=workspace)


def main():
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise SystemExit("먼저 npm --prefix frontend run build 를 실행하세요.")
    if not sys.stdin.isatty():
        raise SystemExit("PowerShell의 대화형 터미널에서 실행하세요.")
    with socket.socket() as listener:
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((HOST, PORT))
        except OSError:
            raise SystemExit(f"{ORIGIN} 포트를 사용할 수 없습니다.") from None
        print("저장된 합성 기록, 새 검사 아님")
        token = getpass("이번 실행에만 쓸 로그인 키를 입력하세요 (영문/숫자 16~128자, 입력 숨김): ")
        if not (16 <= len(token) <= 128 and token.isascii() and token.isalnum()):
            raise SystemExit("로그인 키는 영문/숫자 16~128자로 입력하세요.")
        with TemporaryDirectory(prefix="securityai-saved-review-") as temporary:
            app = prepare_demo(Path(temporary), token)
            print(f"{ORIGIN}/ 에서 방금 입력한 키로 로그인하세요. 종료는 Ctrl+C입니다.", flush=True)
            config = uvicorn.Config(app, host=HOST, port=PORT, proxy_headers=False, access_log=False)
            uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
