# Internal implementation contract

Python package `hsd_tool`, Chinese end-user interface, v1.2.0 DeepSeek evaluation edition. Local Flask server + browser interface, bundled Windows executable. Source inputs remain unchanged. The user has explicitly authorized optional DeepSeek review of eligible preview images through the local backend; the original XLSX, ZIP and AI files are never uploaded. The browser never calls the provider directly.

## Workbook module (workbook.py)

`inspect_workbook(path: str, work_dir: str, sheet_name: str | None = None) -> dict`

Return `{sheets:[{name,hidden}], sheet_name, rows:[{id, row_number, number, image_path, issue}], reserved_numbers:[str]}`. Row IDs are `r<Excel row>`. Absolute image paths are extracted to work_dir and omitted from public snapshots. Read the first visible sheet by default. Image-bearing rows only; include unreadable image references with issue. Read column A number, B picture for current fixed template; preserve displayed leading zeros. `reserved_numbers` includes existing numbers in column A, including rows without pictures. Ignore huge empty/formatted trailing regions. WPS DISPIMG/cellimages required. Any supported floating drawing must associate an anchor to column B explicitly. Never include hidden sheets by default.

`write_numbered_workbook(source: str, destination: str, sheet_name: str, assignments: dict[int,str]) -> None`

Update only blank column A cells at assigned row numbers. Preserve every other XLSX part and all WPS images/drawings. Refuse replacement of any nonempty source number. Use ZIP/XML surgical updates (ordinary spreadsheet roundtrip destroys WPS-specific image features). Destination must differ from source and must not preexist. No sample workbook changes.

## Matching module (matching.py)

`scan_and_match(source_path: str, rows: list[dict], work_dir: str, progress=None) -> dict`

Input AI folder (recursive) or zip. Must reject traversal/symlinks, enforce extraction resource limits, decode legacy Chinese zip names, preserve originals. Render PDF-compatible AI previews locally (first page; multi-page files must be flagged for review instead of auto acceptance). Source extraction under work_dir only. Return `{files:[{id,name,relative_path,source_path,preview_path,issue}], matches:[{row_id,status,file_id,candidates:[{file_id,score}],reason,evidence}], warnings:[str]}`. `evidence` carries every signal behind the decision: method, colour distance, candidate gap, pixel RMS, changed / major-changed share, worst region, unexplained-content residual, inliers, coverage, MAE and thresholds. These are diagnostic data; the employee screen defaults to the business reason, with detail collapsed. Status is `auto`, `review`, or `unmatched`. IDs are deterministic `f0001` etc. Score is 0..1 similarity, never probability. Fail closed for near duplicates / reused file candidates; do not force a global assignment merely to obtain one-to-one matches. `progress(message: str, current: int, total: int)` is optional. All preview images remain under work_dir. Individual bad AI files are reported without aborting every readable file. Source AI bytes must remain unchanged.

v1.2.0 retains the released v1.1.1 matcher. The historical 60-case reference-map regression is 44 local auto / 16 review; it is neither new independent AI validation nor a promise of AI improvement. The separate local 47 / 13 matcher draft is not part of this release. The service additionally records source integrity and page-count metadata for AI eligibility and export checks.

## Service + UI API (owned by root)

Flask listens on loopback only. Browser gets X-HSD-Token from `window.HSD_TOKEN` populated in index.html template placeholder `__HSD_TOKEN__` using a JSON literal. All POST JSON uses this header. Standard failures are `{error: Chinese string}`, HTTP 400/409 etc. JSON is not cached. Never return keys, raw provider request bodies or private process settings.

- `GET /api/config` -> `{prefix:'HSD', digits:4, last_start:1, last_workbook:'', last_source:'', last_output:'', version:'1.2.0'}`.
- `POST /api/pick` `{kind:'workbook'|'zip'|'folder'|'output'}` -> `{path: str}` (native local dialog)
- `POST /api/jobs` `{workbook_path,source_path,output_root,start_number:int}` -> `{id}`; processing background job.
- `GET /api/jobs/<id>` -> full job as below, poll 1s while importing/matching/ai_review/exporting. Long work runs in the background; the UI remains responsive and shows progress. Editing, exporting and shutdown are unavailable while a task is busy.
- `POST /api/jobs/<id>/resolve` `{row_id, file_id: str|null, revert?: bool}`; null means skip, `revert: true` restores the matcher's own verdict for that row, otherwise confirm mapping; returns job. Refuse duplicate file ownership.
- `POST /api/jobs/<id>/undo` `{}` -> job with `last_undone_row_id`; restore the last employee change, recompute numbering, increment revision. `can_undo` indicates availability.
- `POST /api/jobs/<id>/export` `{expected_revision?: int}` -> `{id}`; background export. UI sends the revision of the reviewed summary. A mismatch rejects stale confirmation; reload the job and show the new summary. No need to view every auto result before export.
- `GET /api/jobs/<id>/image/row/<row_id>` and `/image/file/<file_id>` -> preview image; `?size=thumb` requests a proportional thumbnail. Stable job-specific URLs, ETag and private immutable caching; never append random timestamps.
- `POST /api/jobs/<id>/open-output` `{}` -> `{ok:true}` (only completed job output).
- `POST /api/shutdown` `{}` -> `{ok:true}`; exits the local process when no task is busy. Closing the browser alone is not shutdown.

Job schema:

```text
{id, status:'importing'|'matching'|'ai_review'|'ready'|'exporting'|'done'|'error',
 progress:{message,current,total}, error:null|string, revision:int, can_undo:bool,
 sheet_name, workbook_name, source_name, start_number, prefix:'HSD',
 stats:{total,auto,ai_auto,confirmed,review,unmatched,skipped,exportable,
        pending,needs_attention,new_numbers},
 rows:[{id,row_number,number,planned_number,
        status:'auto'|'confirmed'|'review'|'unmatched'|'skipped',
        file_id:null|string,candidates:[{file_id,score}],reason,reason_code?,
        evidence?,diagnostics?,ai_review?}],
 files:[{id,name,relative_path,issue}], warnings:[],
 output_root, output_target, output_dir:null|string, report:null|dict,
 ai_review?, timings?}
```

`auto` includes both local and qualified AI acceptance; `ai_auto` is a subset of `auto`. Local auto count is `auto - ai_auto`. `confirmed` means employee confirmation only. `pending = review + unmatched + skipped`, while `needs_attention = review + unmatched`. `new_numbers` counts accepted blank-number rows; `exportable = auto + confirmed`. The UI's `awaiting` count and default “需要处理” filter include `review + unmatched`; skipped rows remain separate. Automatic entry to the summary depends on `review === 0`, so a batch with only unmatched/skipped items remaining does not require opening those rows. The summary states all unresolved counts. “Continue” and “All results” still provide optional access to unmatched rows and correction.

All unresolved rows retain their source numbers in output. Only matched rows with blank source numbers get planned new numbers. `output_target` is the resolved destination folder for the summary. Existing numbers remain exact, including non-HSD prefixes. Duplicate or unsafe output numbers block affected rows; no overwrites. Source changes invalidate affected decisions/export. An export error may return the task to `ready` with `error` populated so the UI can explain and retry. Inputs are local paths typed/picked, not browser uploads. Session storage may remember the current job ID/selected row/filter for page refresh; tasks do not survive process shutdown.

## DeepSeek settings, usage and workflow

- `GET /api/ai/settings` -> sanitized `{enabled,configured,model:'deepseek-flash',mode:'evaluation'|'validated',key_source:'saved'|'environment'|'none',key_persistence,price_date,prices,price_basis,storage_warning,validation:{qualified,mode,model,categories,counts,message}}`.
- `POST /api/ai/settings` `{enabled?:bool,api_key?:string,clear_key?:bool}` -> sanitized settings. Blank/omitted key preserves the saved value. A new key and `clear_key:true` together are invalid. Windows persists the key with DPAPI CurrentUser; no plaintext fallback. Environment variable `DEEPSEEK_API_KEY` is used only when no saved key exists. Clearing a saved key does not clear that variable. No browser-readable existing key, mode toggle or validation override.
- `GET /api/ai/usage` -> cumulative usage below.
- `POST /api/jobs/<id>/ai-review` `{}` -> `{id}`, sets background `ai_review` status. UI shows this only when `job.ai_review.can_retry` is true. Server checks ready/configured/enabled, batch limits and actual case eligibility. It never overrides employee decisions.

```text
job.ai_review = {mode,eligible,reviewed,suggested_same,auto_passed,
                 unresolved,skipped,usage,message,can_retry}
row.ai_review = {verdict?,candidate_id?,reason,checks?,differences?,
                 outcome,reason_code,gate_reason?,model?,request_id?,category?}
verdict = 'same' | 'different' | 'uncertain'
outcome = 'auto_passed' | 'evaluation_suggestion' | 'manual_review' | 'error' | 'skipped'
usage = {requests,successes,failures,prompt_tokens,completion_tokens,
         cache_hit_tokens,cache_miss_tokens,unknown_usage_requests,
         estimated_usd,estimated_usd_upper_bound:number|null,
         cost_is_upper_bound,cost_incomplete,currency:'USD',price_date}
```

Default mode is evaluation with no production qualification. Suggestions remain `review`; no model text or self-reported confidence can change status. Show the candidate the suggestion concerns, especially if the employee is viewing a different candidate. Errors/skips must not be labelled as model or employee acceptance. Only an actually accepted auto row can be labelled AI conditionally accepted. A request failure is contained to AI review and leaves local results/manual work available.

`estimated_usd` estimates known usage using recorded peak prices. `estimated_usd_upper_bound` is null if any usage is unknown; the UI must state the unknown request count and incomplete cost statistics, never present unknown charges as zero. These USD figures are estimates, not a provider invoice. There is no monetary fee ceiling. Do not confuse finite request/retry limits with a cost cap.

Preview-only payloads contain complete overviews and, for wide images, ordered exhaustive panels, task-local candidate IDs, comparison instructions and a bounded local reason. No original AI/XLSX/ZIP, filenames or local paths are included as prompt text. Visible text inside design images remains image content. Treat it as untrusted data, not instructions. Keys are sent only in backend authentication to the configured official provider; never in snapshots, logs, reports or front-end storage.

Eligibility is restricted to untouched `review` rows with readable single-page previews and verified source metadata. Duplicate previews anywhere in the batch, duplicate query images, actual competing ownership, number conflicts, unreadable images/multiple artboards and absent credible candidates are excluded before the request. Recheck image/source fingerprints before applying a response and before export. Hard conflicts cannot be overridden by the model.

## Independent validation and conditional automatic acceptance

Policy and prompt versions are `hsd-ai-review-1`. Categories are `geometry_review` and `texture_review`. Five required response checks are `content_same`, `colors_same`, `complete_coverage`, `extra_content_absent`, `unique_candidate`; all must be boolean true, verdict `same`, differences empty, chosen candidate the local first candidate. Native-resolution coverage and noncontradictory measured local colour/content evidence are separate local gates. A model switching candidates, affirming unreadable detail or contradicting local evidence remains manual.

`tools/run_ai_evaluation.py --synthetic --out <empty-dir> --settings-dir <data-dir> [--prepare-only]` prepares generated labelled cases; without `--prepare-only` it makes real billable calls using the existing settings. Output preserves all planned cases, including failures, plus frozen labels, fingerprints, responses and usage. It never activates business acceptance. Repository-local outputs must stay under ignored `tmp/`.

`tools/validate_ai_review.py --labels <labels.json> --observations <observations.json> --output <report.json>` makes no network calls and reads no key. It requires schema version 1, real `deepseek_live` records of the current protocol, exactly matching unique planned/case/request IDs, a single actual model, image/candidate/source fingerprints, and complete responses. Labels declare `case_id`, `case_fingerprint`, `batch_id`, `category`, `split:'calibration'|'holdout'`, `origin:'independent_manual'|'synthetic_known_truth'|'reference_map'`, `label:'same'|'different'|'uncertain'`, `candidate_ids`, `expected_candidate_id` and `controls`. The response's `case` binds `category`, `candidate_ids` and `image_digests`. Do not reuse query images across independent batches or mix calibration and holdout within a batch.

For each approved category, at least two independent holdout batches must each include a positive, a negative/uncertain case and a useful correctly accepted positive. At least one batch must include independently manually verified real business positives and negatives. Overall, at least two accepted positives and five negatives must cover `color_change`, `local_replacement`, `extra_content`, `shared_subset`, `near_duplicate`, with zero false accepts across all recorded cases. Synthetic data alone or an existing reference map cannot qualify production. Labels are independent and frozen before observing model output; do not relabel origins or omit failed cases to pass.

After reviewing a qualifying report, adding `--activate --data-dir <tool-data-dir>` explicitly signs/stores the qualification locally. The registry checks integrity, binds the actual model, categories, policy/prompt versions and review implementation, and expires after 7 days. Changed implementations/protocols invalidate the record; an unqualified model/category cannot pass the per-row gate. No qualification is shipped in v1.2.0. These are minimum activation prerequisites for the measured scope, not a general accuracy guarantee.

## Ownership

Matching agent: matching.py, image matching helpers, tests/test_matching.py, matching investigation scripts/results under tools/matching_* and tmp/matching_*.
Workbook agent: workbook.py, tests/test_workbook.py.
UI agent: hsd_tool/static/*. Must follow API above. No server code. Current documentation-only assignment may edit the five delivery documents separately; no simultaneous root/static edits.
Root: service/server, orchestration, export, packaging, docs, integration testing.
