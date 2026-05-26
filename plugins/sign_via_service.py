from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_multipart_body(fields: dict[str, str], file_field_name: str, file_name: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = "----PromptManSignBoundary7e4d2f"
    chunks: list[bytes] = []

    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{file_field_name}"; filename="{file_name}"\r\n'.encode("utf-8"),
            b"Content-Type: application/octet-stream\r\n\r\n",
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    return b"".join(chunks), boundary


def _post_multipart_with_bearer(
    url: str,
    *,
    bearer_token: str,
    fields: dict[str, str],
    file_field_name: str,
    file_name: str,
    file_bytes: bytes,
) -> dict[str, object]:
    body, boundary = _build_multipart_body(fields, file_field_name, file_name, file_bytes)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _merge_trusted_signers(target_path: Path, snippet_path: Path) -> None:
    target = _load_json(target_path) if target_path.exists() else {}
    snippet = _load_json(snippet_path)
    target.update(snippet)
    target_path.write_text(json.dumps(target, indent=2), encoding="utf-8")


def sign_plugin_via_service(
    *,
    service_base_url: str,
    username: str,
    password: str,
    plugin_path: Path,
    signer_id: str,
    valid_for_minutes: int,
    trusted_signer_json: Path | None,
    trusted_store_path: Path,
) -> Path:
    init_url = f"{service_base_url.rstrip('/')}/v1/promptman/init"
    sign_url = f"{service_base_url.rstrip('/')}/v1/promptman/sign"

    init_payload = {
        "username": username,
        "password": password,
        "valid_for_minutes": valid_for_minutes,
    }
    init_response = _post_json(init_url, init_payload)
    if not init_response.get("ok"):
        raise RuntimeError(f"Init request failed: {init_response}")

    data = init_response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Init response does not contain data object")

    window_token = data.get("token")
    auth_payload = data.get("auth")
    if not isinstance(window_token, str) or not window_token:
        raise RuntimeError("Init response does not contain a valid token")
    if not isinstance(auth_payload, dict) or not isinstance(auth_payload.get("access_token"), str):
        raise RuntimeError("Init response does not contain access token")

    sign_response = _post_multipart_with_bearer(
        sign_url,
        bearer_token=auth_payload["access_token"],
        fields={
            "token": window_token,
            "signer_id": signer_id,
        },
        file_field_name="plugin_file",
        file_name=plugin_path.name,
        file_bytes=plugin_path.read_bytes(),
    )
    if not sign_response.get("ok"):
        raise RuntimeError(f"Sign request failed: {sign_response}")

    sign_data = sign_response.get("data")
    if not isinstance(sign_data, dict) or not isinstance(sign_data.get("signature_json"), str):
        raise RuntimeError("Sign response does not contain signature_json")

    signature_path = plugin_path.with_suffix(".signature.json")
    signature_path.write_text(sign_data["signature_json"], encoding="utf-8")

    if trusted_signer_json is not None:
        _merge_trusted_signers(trusted_store_path, trusted_signer_json)

    return signature_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sign PromptMan plugin files via external PromptManSign service")
    parser.add_argument("plugin_path", help="Path to plugin file, for example plugins/my_plugin.py")
    parser.add_argument("--service-url", required=True, help="PromptManSign base URL")
    parser.add_argument("--username", required=True, help="PromptManSign init username")
    parser.add_argument("--password", required=True, help="PromptManSign init password")
    parser.add_argument("--signer-id", default="promptman-team", help="signer_id for detached signature envelope")
    parser.add_argument("--valid-for-minutes", type=int, default=30, help="Time window for init token")
    parser.add_argument(
        "--trusted-signer-json",
        help="Optional snippet file from PromptManSign, for example promptman-team.trusted-signer.json",
    )
    parser.add_argument("--trusted-store-path", default="plugins/trusted_signers.json", help="Trusted signer store path")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    plugin_path = Path(args.plugin_path)
    if not plugin_path.exists():
        parser.error(f"Plugin file does not exist: {plugin_path}")

    try:
        signature_path = sign_plugin_via_service(
            service_base_url=args.service_url,
            username=args.username,
            password=args.password,
            plugin_path=plugin_path,
            signer_id=args.signer_id,
            valid_for_minutes=args.valid_for_minutes,
            trusted_signer_json=Path(args.trusted_signer_json) if args.trusted_signer_json else None,
            trusted_store_path=Path(args.trusted_store_path),
        )
    except (ValueError, RuntimeError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Signature file created: {signature_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
