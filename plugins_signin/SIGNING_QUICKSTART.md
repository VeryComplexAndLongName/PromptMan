# Plugin Signing Quickstart

Use these two commands from PromptMan root.

1. Sign plugin via PromptManSign (multipart upload):

```text
python plugins/sign_via_service.py plugins/my_plugin.py --service-url https://verycomplexandlongname.pythonanywhere.com --username <login> --password <password> --signer-id promptman-team
```

2. Sign plugin and merge trusted signer snippet into `plugins/trusted_signers.json`:

```text
python plugins/sign_via_service.py plugins/my_plugin.py --service-url https://verycomplexandlongname.pythonanywhere.com --username <login> --password <password> --signer-id promptman-team --trusted-signer-json /path/to/promptman-team.trusted-signer.json
```
