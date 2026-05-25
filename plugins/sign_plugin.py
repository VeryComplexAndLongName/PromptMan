from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate_keypair(signer_id: str, output_dir: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_b64 = base64.b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("utf-8")

    _write_text(output_dir / f"{signer_id}.ed25519.private.pem", private_pem.decode("utf-8"))
    _write_text(output_dir / f"{signer_id}.ed25519.public.pem", public_pem.decode("utf-8"))
    _write_text(
        output_dir / f"{signer_id}.trusted-signer.json",
        json.dumps(
            {
                signer_id: {
                    "algorithm": "ed25519",
                    "public_key": public_b64,
                }
            },
            indent=2,
        ),
    )


def sign_plugin(plugin_path: Path, signer_id: str, private_key_path: Path) -> None:
    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    signature = private_key.sign(plugin_path.read_bytes())
    envelope = {
        "signer_id": signer_id,
        "algorithm": "ed25519",
        "file": plugin_path.name,
        "signature": base64.b64encode(signature).decode("utf-8"),
    }
    signature_path = plugin_path.with_suffix(".signature.json")
    _write_text(signature_path, json.dumps(envelope, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple PromptMan plugin signing helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate-key", help="Generate an Ed25519 key pair and trust-store snippet")
    generate.add_argument("signer_id")
    generate.add_argument("--output-dir", default="plugins/keys")

    sign = subparsers.add_parser("sign", help="Sign a plugin file and create a detached .signature.json sidecar")
    sign.add_argument("plugin_path")
    sign.add_argument("signer_id")
    sign.add_argument("private_key_path")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "generate-key":
        generate_keypair(args.signer_id, Path(args.output_dir))
        return 0
    if args.command == "sign":
        sign_plugin(Path(args.plugin_path), args.signer_id, Path(args.private_key_path))
        return 0
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())