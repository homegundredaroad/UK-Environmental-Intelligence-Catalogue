# Windows upload and first run

## Add the release to GitHub

1. Download and extract the release ZIP.
2. Open your local clone of `UK-Environmental-Intelligence-Catalogue` in File Explorer.
3. Copy everything from inside the extracted folder into the clone, allowing `README.md` to be
   replaced. Do not copy the outer folder itself into the repository.
4. In GitHub Desktop, review the file list, use the summary `Build verified Sprint 0 foundation`,
   commit to `main`, and push.
5. Open the repository's **Actions** tab and confirm the `CI` workflow passes for Python 3.11, 3.12
   and 3.13.

Using a `develop` branch and pull request is preferable once the initial foundation is present, but
the first upload may go directly to the otherwise empty `main` branch.

## Run in PowerShell

From the repository directory:

```powershell
conda activate ukei
python --version
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src tests
pytest
ukei --version
ukei init
ukei status
```

Expected results for the supplied release are 37 passing tests, coverage above 90%, no lint or type
errors, and `Integrity: PASS` from `ukei status`.

Run `ukei demo` only if you want to exercise the catalogue with a synthetic, explicitly unverified
record. It is not required for installation.

