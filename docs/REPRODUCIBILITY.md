# Reproducing BioFlow safely

This package separates **software acceptance** from **scientific reproduction**.
The helpers do not install anything, pull models/databases, migrate old accounts,
or submit analyses. Use a fresh clone on Linux x86_64, preferably Python 3.10.
Do not run them in a production checkout or point them at an existing database.
The account, generated data and local runtime remain private and ignored by Git.

## 1. Isolated software acceptance

From a fresh repository root, prepare an isolated Python environment manually:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r BioLLM_RawDataAnalysis/backend/requirements.txt
python repro/quickstart.py --help
python repro/quickstart.py check
```

Installation accesses package registries only when you run pip. The analysis
requirements contain pins; the root requirements contain ranges. They are not a
lock for all modules or bioinformatics tools. Keep `python -m pip freeze` with
your experiment record. Missing packages/platform support return nonzero from
`check`. A null Nextflow path explicitly means it is unavailable; Python package
presence is not verification of a working workflow or a database.

Create a new account **before** generating fixtures:

```bash
python repro/quickstart.py init --username researcher
python repro/quickstart.py fixtures
python repro/quickstart.py smoke
python repro/quickstart.py start --isolated-development
```

`init` prompts with hidden input (8–128 characters). For noninteractive use,
provide `BIOFLOW_REPRO_PASSWORD` through your environment/secret manager and unset
it immediately afterward; do not put secrets in command arguments or shell
history. No default working password is supplied or printed. Existing workspace
directories are refused rather than migrated or reset. Interrupted initialization
must be inspected manually; retry in a new empty workspace, never delete an old
account database just to bypass the guard.

Default workspace: `runtime/reproduction`. `--workspace` selects another fresh
directory; the launcher requires it under this clone's `runtime/`. Do not generate
fixtures first and then initialize the same directory. Existing fixtures are not
overwritten; use a fresh workspace to regenerate them.

Open [the local workbench](http://127.0.0.1:18800) and log in with your new account.
Gateway and analysis listen only on `127.0.0.1:18800` and `127.0.0.1:18803`.
Override with `--gateway-port` / `--analysis-port` if needed. The foreground
launcher refuses occupied ports (including healthy old services), owns only its
new process groups, and stops them on Ctrl+C, termination, startup failure or a
service exit. It never adopts/kills an existing listener. A stale `launcher.lock`
requires manual inspection of your previous run, not automatic process killing.
There is a small OS port-bind race; any child startup failure is fatal.

Light mode sets analysis concurrency to one, AI automatic retry off, automatic
task execution off, and no reference database profiles. MAG is not provisioned;
do not enable it. The explicit `--isolated-development` acknowledges development
`process_group` isolation: it is **not** systemd/cgroup resource containment, a
security boundary, or a production setting. Inherited BioFlow configuration is
dropped. No writing, literature, Skill, Ollama or vector service is started;
corresponding UI features may be unavailable. This is not full-stack acceptance.

Some existing asset writers use source-root runtime paths rather than the
selected state root. Hence **a fresh clone is required**, even with `--workspace`.
The launcher rejects unrelated existing runtime contents; this intentionally
conservative guard may require a new clone after using asset-writing features.
Do not loosen it to reuse production state. Historical
`scripts/bootstrap_developer.py` is a migration tool and must not be used here.

### Synthetic fixtures and manual UI checks

`fixtures` generates 16 deterministic paired reads (100 bases each), a canonical
long matrix and `matrix-contract.json` beneath the ignored workspace. All values
are invented and labeled **no biological significance**. The repetitive reads
can produce genuine QC warnings: keep those warnings visible. They do not test
host depletion, species recovery, annotation accuracy or biological inference.
There are no disease groups.

For manual UI checks, create a project, upload the generated paired FASTQs and
check pairing/preview without submitting real analysis. Upload `matrix.tsv` as
KO/counts/normalization `none`, inspect its canonical columns
`sample_id`, `feature_id`, `value`, then use descriptive matrix-summary workflows
only after configuring an appropriate execution environment. Light mode disables
automatic task execution; do not mistake a queued task for a computed result.

`smoke` runs helper tests; it explicitly reports that Nextflow was NOT executed.
To exercise the existing actual Nextflow adapters, install Java and Nextflow
separately following the [official installation guide](https://www.nextflow.io/docs/latest/install.html), then:

```bash
python repro/quickstart.py smoke --nextflow
```

This runs `BIOFLOW_TEST_NEXTFLOW=1 python -m pytest -q
backend/tests/test_typed_nextflow.py` from `BioLLM_RawDataAnalysis`. Missing Java or
Nextflow fails, not skips. The test uses real adapters and fixture consumers in
temporary directories; expensive biological consumers are replaced in that
existing test. It checks signatures, matrix output and cache behavior, **not**
FastQC/host-removal/Kraken/HUMAnN correctness. Nextflow itself may fetch its runtime
on first use; prepare it independently if offline execution is required.

## 2. Full public paired WGS input (explicit opt-in)

The pinned source is [ENA SRR9224248](https://www.ebi.ac.uk/ena/browser/view/SRR9224248),
study PRJNA544527, sample SAMN11950175, WGS/PAIRED human gut metagenome. This is one
public biological sample, not a case/control cohort or evidence for disease
associations. No subsampling, read rewriting or synthetic replacement is used.
`repro/public-data.json` records original HTTPS paths, ENA compressed sizes/MD5
and independently calculated SHA256. It does not ship the reads.

```bash
python repro/public_data.py --help
python repro/public_data.py plan
python repro/public_data.py download --allow-network
python repro/public_data.py verify
```

`plan` is offline. `download` without `--allow-network` fails before any write or
network request. The two compressed files total **1,090,553,272 bytes** (about
1.09 GB / 1.02 GiB). Default byte cap is 2 GiB plus a separate 1 GiB free-space
reserve; use `--byte-cap` and `--disk-reserve` in bytes only when appropriate.
Override `--dest` consistently in all commands if using another empty directory.

Only the pinned accession's exact HTTPS ENA host/path is accepted. TLS checks
remain enabled; redirects and environment proxies are not used. Restricted
networks may require a separately managed download with the same pinned URLs and
local verification, not disabling TLS. Downloads stream size, MD5 and SHA256,
stage `.part` files and publish without replacing any existing file. Any existing
valid/invalid/partial file stops the command; inspect it and explicitly choose a
new destination. No automatic resume, deletion, silent replacement or corrupt-file
cleanup occurs. Network failures preserve partials for inspection. Treat this as
a local single-user tool; do not allow another user to race changes inside the
destination. Symlink paths are rejected.

`verify` is read-only and streams both full compressed hashes, the full gzip CRC,
FASTQ structure and every mate identifier/count, with bounded per-record memory.
It does not infer processing validity from headers. It may take minutes on full
files. File integrity and paired structure do not establish consent status,
sample phenotype, biological quality, host-removal efficacy or database accuracy.

## 3. Scientific tools, databases and optional models

`repro/resources.json` lists primary sources, roles, known example-version hints
and explicit unpinned gaps. It is **not an exact scientific environment lock**.
Prepare FastQC, fastp, host Bowtie2 index, Kraken2/Bracken and HUMAnN/MetaPhlAn
resources separately; capture actual tool versions, database releases/checksums,
host assembly, parameters, input hashes, random seeds and hardware alongside each
run. Raw FASTQ analysis is different from the small adapter/software demo.

The existing registry template is
`BioLLM_RawDataAnalysis/workflow/assets/database-registry.example.json`. Its
`/external/db/...` paths, `example-release` and all-zero SHA256 are **placeholders,
not real or validated databases**. Make your own ignored local registry with real
absolute paths, release/compatibility metadata, required sentinels and the actual
inventory digest expected by the existing preflight. `tool_compatibility_version`
is a declaration, not proof of installed binaries or a complete provenance lock.
Do not replace preflight with this package or bypass failures. The example's
Kraken2 2.17.1 / Bracken 3.0.1 / HUMAnN 3.9 / MetaPhlAn 4.1.1 strings do not certify
a tested combined environment. Verify upstream availability and compatibility.

For full runs configure the existing production launcher/settings independently:
`BIOLLM_DATABASE_REGISTRY`, `BIOLLM_DATABASE_PROFILE`, `BIOLLM_HOST_INDEX` and the
resource-specific settings documented in `BioLLM_RawDataAnalysis/backend/app/config.py`.
Keep the existing registry/resource preflight, production isolation and capacity
limits. The light launcher deliberately drops those settings and disables auto-run;
it is not the launch path for full analysis. MAG requires its own complete tools,
classification/function profiles and resource budgeting before explicit enabling.

Optional local AI requires separately prepared Ollama and model weights.
`qwen3:14b` is a mutable tag, not a weight checksum or guarantee of paper results.
Record exact weights/digests and licenses; do not auto-pull on startup. Automatic
repair is off in the light profile. Review upstream licenses and redistribution
terms for each tool, database and model. Older exact releases may no longer be
available: report that limitation instead of silently substituting "latest".

## Verification boundary and troubleshooting

- `python -m unittest discover -s repro/tests -v`: local helper behavior only;
  reports platform/dependency skips explicitly. A skipped symlink test is not a pass.
- `check` fails on Windows (launcher unsupported) or missing Python packages;
  it prints missing tools but does not install them. Use supported Linux and the venv.
- Port occupied: choose different ports or inspect your own service manually.
  The helper will not kill or reuse it.
- Existing workspace/partial/lock: inspect ownership/state; choose fresh paths.
  There is no reset/migration/force mode.
- Missing database/tool: retain the real preflight error and prepare the requested
  resource; a toy database must not be presented as a full scientific database.
- Blank optional module: writing/literature/Skill services were not launched.

Local helper tests and a real Linux startup/Nextflow check are separate evidence.
Passing them does not certify complete biological execution, reproducibility of
paper numbers, correctness of third-party tools, or identical results on another
database release. Record the commit SHA and the tests actually run; never count
unrequested/skipped biological jobs as successful validation.
