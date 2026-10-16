# Internal implementation contract

Python package `hsd_tool`, Chinese end-user interface, v1.4.0. Local Flask server + browser interface, bundled Windows executable. Default binding is loopback; explicit LAN mode provides browser-owned employee upload, processing and result download on one host. Client originals remain unchanged. Original XLSX and ZIP files are uploaded to this LAN host; eligible previews may then be sent to DeepSeek through the host backend under the existing authorization. Original XLSX, ZIP and AI files are never sent to DeepSeek. The browser never calls the provider directly. AI production qualification remains disabled by default.

## Workbook module (workbook.py)

`inspect_workbook(path: str, work_dir: str, sheet_name: str | None = None) -> dict`

Return `{sheets:[{name,hidden}], sheet_name, rows:[{id, row_number, number, image_path, issue}], reserved_numbers:[str]}`. Row IDs are `r<Excel row>`. Absolute image paths are extracted to work_dir and omitted from public snapshots. Read the first visible sheet by default. Image-bearing rows only; include unreadable image references with issue. Read column A number, B picture for current fixed template; preserve displayed leading zeros. `reserved_numbers` includes existing numbers in column A, including rows without pictures. Ignore huge empty/formatted trailing regions. WPS DISPIMG/cellimages required. Any supported floating drawing must associate an anchor to column B explicitly. Never include hidden sheets by default.

`write_numbered_workbook(source: str, destination: str, sheet_name: str, assignments: dict[int,str]) -> None`

Update only blank column A cells at assigned row numbers. Preserve every other XLSX part and all WPS images/drawings. Refuse replacement of any nonempty source number. Use ZIP/XML surgical updates (ordinary spreadsheet roundtrip destroys WPS-specific image features). Destination must differ from source and must not preexist. No sample workbook changes.

## Matching module (matching.py)

`scan_and_match(source_path: str, rows: list[dict], work_dir: str, progress=None) -> dict`

Input AI folder (recursive) or zip. Must reject traversal/symlinks, enforce extraction resource limits, decode legacy Chinese zip names, preserve originals. Render PDF-compatible AI previews locally (first page; multi-page files must be flagged for review instead of auto acceptance). Source extraction under work_dir only. Return `{files:[{id,name,relative_path,source_path,preview_path,issue}], matches:[{row_id,status,file_id,candidates:[{file_id,score}],reason,evidence}], warnings:[str]}`. `evidence` carries every signal behind the decision: method, colour distance, candidate gap, pixel RMS, changed / major-changed share, worst region, unexplained-content residual, inliers, coverage, MAE and thresholds. These are diagnostic data; the employee screen defaults to the business reason, with detail collapsed. Status is `auto`, `review`, or `unmatched`. IDs are deterministic `f0001` etc. Score is 0..1 similarity, never probability. Fail closed for near duplicates / reused file candidates; do not force a global assignment merely to obtain one-to-one matches. `progress(message: str, current: int, total: int)` is optional. All preview images remain under work_dir. Individual bad AI files are reported without aborting every readable file. Source AI bytes must remain unchanged.

v1.3.0 adds independently checked interpolation-edge pixels, detailed scale/phase measurement, measured repeated-pattern periods and complete candidate-content verification. `matching_verification.py` owns coverage proofs. Do not wrap an artboard as a presumed motif period: a period must be observed and validated across the query, then reproduce the complete candidate. Colour and coherent local differences remain blocking evidence. The historical v1.2.0 regression baseline is 44 local auto / 16 review; the unrelated unpublished 47 / 13 draft is not merged.

`evidence_version:2` retains separate `channels.features` and `channels.texture`, each with score/strong/auto_ok, metrics, failed_checks and alignment. `selected_channel` identifies the actual decision path; AI may not cherry-pick metrics across channels. Alignment describes candidate-to-query geometry, dimensions, measured matrices, query/source/ink coverage and independently checked edges. `competition` binds every evaluated file and score, credible rivals and completion status. A weak shared fragment does not claim ownership from a complete validated match; actual supported competing claims still require review. IDs only identify files; names/order/reference answers never prove identity.

## Service + UI API (owned by root)

Flask defaults to loopback. Explicit `--lan <private-IPv4>/<prefix> --lan-input-root <dir> --lan-output-root <dir> [--port <port>]` binds only the specified RFC1918 interface and admits only the supplied CIDR. The legacy input root must exist; the legacy output root is created if needed and must be outside it. These roots constrain host-only path compatibility requests; employee uploads use managed directories under `data_dir` instead. LAN paths reject escapes through symlinks/junctions and UNC/network-share paths. The service is not public internet hosting or remote desktop access.

Remote clients first use `POST /api/lan/login {code}` with a matching Origin. The per-start random code is persisted only in the local data directory's `instance.json` as `lan_access_code`; it must not appear in logs, Git, releases or remote snapshots. Host-only config may display it for the operator. Sessions expire after 8 hours without sliding renewal. Login attempts are limited per client address; excess attempts return 429. `POST /api/lan/logout {}` ends the remote session and requires the usual CSRF header. Local-host pages can enter directly.

Each LAN browser session receives a random `employee_id` stored in the signed session cookie. Every job-scoped route checks `_owner_id` against that session, including reads, images, resolve, undo, AI retry, export, download and host output-opening. A mismatched owner receives 404, even from the host browser. Login creates a new identity; there are no employee accounts, cross-browser recovery or reassignment APIs. All users share backend capacity and the host's AI settings, not a current batch. Different tabs in the same browser session share ownership and use revision checks to avoid stale changes.

`--data-dir` isolates employee uploads/tasks/results. `--settings-dir <existing-host-data-dir>` supplies the shared DPAPI-encrypted Key, AI settings, usage ledger and qualification registry without copying credentials; the same Windows user must run it. Remote clients never configure or obtain the Key, and their cumulative-usage endpoint is forbidden. Per-batch usage remains in their own summaries. Tasks remain process-local; logout/relogin, cookie removal or switching browsers loses the old task access identity, and process shutdown loses tasks. Do not advertise persistent employee task recovery.

Browser gets X-HSD-Token from `window.HSD_TOKEN` populated in index.html template placeholder `__HSD_TOKEN__` using a JSON literal. All POST requests, including multipart upload, use this header except access-code login. Remote session authentication and request token/origin validation both apply. Standard failures are `{error: Chinese string}`, HTTP 400/401/403/404/409/413/429 etc. JSON is not cached. Never return keys, raw provider request bodies or private process settings. LAN public job snapshots redact managed host paths.

- `GET /api/config` -> `{prefix:'HSD', digits:4, last_start:1, last_workbook:'', last_source:'', last_output:'', version:'1.4.0'}`. LAN mode adds `{access:{lan:true,remote:bool,upload:true,upload_limits:{workbook_bytes:104857600,source_bytes:1992294400,total_bytes:2147483648}}, active_job_id:str|null}`; only host-side `access` also contains `code`. Historical paths are blank. `active_job_id` and last start number refer only to the current browser owner's newest job, never another employee.
- `POST /api/pick` `{kind:'workbook'|'zip'|'folder'|'output'}` -> `{path: str}` (native host dialog; forbidden for remote clients)
- `POST /api/jobs` `{workbook_path,source_path,output_root,start_number:int}` -> `{id}`; local path workflow unchanged. In LAN mode, host-only compatibility API validates legacy roots and assigns the browser owner; remote requests are forbidden. The LAN UI on both host and remote uses upload instead.
- `POST /api/jobs/upload` -> `{id}`; LAN only, `multipart/form-data`, exactly one `workbook` XLSX file, one `source` ZIP file and one `start_number` string (1–9999), no other fields. Applies session, Origin and X-HSD-Token checks. Workbook maximum 100 MiB, source maximum 1900 MiB, whole request maximum 2 GiB. Writes streams to `data_dir/uploads/<random-batch>/workbook.xlsx` and `source.zip`; filenames are display-only. Validates true XLSX/ZIP content, traversal, links, encryption, repeated names, entry counts, 1–500 AI files and existing per-AI/expanded limits; failed uncommitted uploads are removed. Output is confined to `data_dir/employee_outputs/<random-batch>/`.
- `GET /api/jobs/<id>` -> full owned job as below, poll 1s while queued/importing/matching/ai_review/exporting. A single worker queues processing, AI retry and export; multiple employees may upload independently without sharing task state. Long work remains off the request/UI thread. Editing/exporting is unavailable for that busy job, and shutdown is unavailable while any job is queued or busy.
- `POST /api/jobs/<id>/resolve` `{row_id, file_id: str|null, revert?: bool, expected_revision?:int}`; null means skip, `revert: true` restores the matcher's own verdict for that row, otherwise confirm mapping; returns job. Refuse duplicate file ownership.
- `POST /api/jobs/<id>/undo` `{expected_revision?:int}` -> job with `last_undone_row_id`; restore the last employee change, recompute numbering, increment revision. `can_undo` indicates availability.
- `POST /api/jobs/<id>/export` `{expected_revision?: int}` -> `{id}`; background export. UI sends the revision of the reviewed summary. A mismatch rejects stale confirmation; reload the job and show the new summary. No need to view every auto result before export.
- `GET /api/jobs/<id>/image/row/<row_id>` and `/image/file/<file_id>` -> preview image; `?size=thumb` requests a proportional thumbnail. Stable job-specific URLs and ETag; LAN uses private no-cache/must-revalidate so every reuse checks the session and owner, while non-LAN keeps private immutable caching. Never append random timestamps.
- `GET /api/jobs/<id>/download` -> ZIP attachment `HSD编号结果.zip`, LAN owned upload jobs only, after `status:'done'` and `download_ready:true`. Exports only service-authorized rows after summary confirmation; contains numbered workbook, renamed AI copies and reports. Atomically packages verified output members and validates the stored archive SHA256 before serving. Invalid, altered, incomplete or another owner's downloads fail; never supplies arbitrary filesystem paths.
- `POST /api/jobs/<id>/open-output` `{}` -> `{ok:true}` (only completed job output; forbidden for remote clients).
- `POST /api/shutdown` `{}` -> `{ok:true}`; exits the local process when no task is busy; forbidden for remote clients. Closing the browser alone is not shutdown.

In LAN mode `resolve`, `undo` and `export` require `expected_revision` for both host and remote pages. A stale revision returns 409; the UI refreshes that owner's job rather than silently overwriting another tab's change. Only final server states make rows exportable; neither upload nor download bypasses summary confirmation, ownership, numbering conflicts or source-change checks. Managed upload/output/download files remain host-side copies; browser attachment download saves the result to the employee's computer without changing their originals.

Job schema:

```text
{id, status:'queued'|'importing'|'matching'|'ai_review'|'ready'|'exporting'|'done'|'error',
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
 queue_position:int, download_ready:bool, download_name:null|string,
 ai_review?, timings?}
```

`auto` includes both local and qualified AI acceptance; `ai_auto` is a subset of `auto`. Local auto count is `auto - ai_auto`. `confirmed` means employee confirmation only. `pending = review + unmatched + skipped`, while `needs_attention = review + unmatched`. `new_numbers` counts accepted blank-number rows; `exportable = auto + confirmed`. The UI's `awaiting` count and default “需要处理” filter include `review + unmatched`; skipped rows remain separate. Automatic entry to the summary depends on `review === 0`, so a batch with only unmatched/skipped items remaining does not require opening those rows. The summary states all unresolved counts. “Continue” and “All results” still provide optional access to unmatched rows and correction.

All unresolved rows retain their source numbers in output. Only matched rows with blank source numbers get planned new numbers. In non-LAN mode `output_target` is the destination folder; LAN public snapshots describe downloading to the employee computer instead of exposing host paths. Existing numbers remain exact, including non-HSD prefixes. Duplicate or unsafe output numbers block affected rows; no overwrites. Source changes invalidate affected decisions/export. An export error may return the task to `ready` with `error` populated so the UI can explain and retry. Inputs are typed/picked local paths in non-LAN mode and managed browser uploads in employee LAN mode. Session storage may remember the current owned job ID/selected row/filter for page refresh; no tasks survive process shutdown. Uploads and employee output copies are separate from disposable job caches and require host-side lifecycle management; do not claim shutdown deletes every uploaded original.

## DeepSeek settings, usage and workflow

- `GET /api/ai/settings` -> host sanitized `{enabled,configured,model:'deepseek-flash',mode:'evaluation'|'validated',key_source:'saved'|'environment'|'none',key_persistence,price_date,prices,price_basis,storage_warning,validation:{qualified,mode,model,categories,counts,message}}`. Remote responses are limited to `{enabled,configured,model,mode}`.
- `POST /api/ai/settings` `{enabled?:bool,api_key?:string,clear_key?:bool}` -> sanitized settings; host only, forbidden for remote clients. Blank/omitted key preserves the saved value. A new key and `clear_key:true` together are invalid. Windows persists the key with DPAPI CurrentUser; no plaintext fallback. Environment variable `DEEPSEEK_API_KEY` is used only when no saved key exists. Clearing a saved key does not clear that variable. No browser-readable existing key, mode toggle or validation override.
- `GET /api/ai/usage` -> cumulative usage below; host only in LAN mode, remote requests return403. Each employee's own batch usage remains in its job summary.
- `POST /api/jobs/<id>/ai-review` `{}` -> `{id}`, background `ai_review` (first `queued` for LAN jobs). UI shows this only when `job.ai_review.can_retry` is true. Server checks owner, ready/configured/enabled, batch limits and actual case eligibility. It never overrides employee decisions.

```text
job.ai_review = {mode,eligible,reviewed,suggested_same,auto_passed,
                 unresolved,skipped,usage,message,can_retry}
row.ai_review = {verdict?,candidate_id?,reason,checks?,differences?,protocol_diagnostics?,gate_failures?,
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

Preview-only payloads contain complete overviews and, for wide images, ordered exhaustive panels, task-local candidate IDs and neutral comparison instructions. Measured valid geometry may add an aligned pair and mapped/unmapped coverage diagram, while retaining all originals. No arbitrary crops/tiles or old local verdict are used to bias the model. Only actual plausible rivals are supplied; complete local competition evidence must account for all files, and more than five credible rivals stays manual. No original AI/XLSX/ZIP, filenames or local paths are included as prompt text. Visible text inside design images remains image content. Treat it as untrusted data, not instructions. Keys are sent only in backend authentication to the configured official provider; never in snapshots, logs, reports or front-end storage.

Eligibility is restricted to untouched `review` rows with readable single-page previews and verified source metadata. Duplicate previews anywhere in the batch, duplicate query images, actual competing ownership, number conflicts, unreadable images/multiple artboards and absent credible candidates are excluded before the request. Recheck image/source fingerprints before applying a response and before export. Hard conflicts cannot be overridden by the model.

## Independent validation and conditional automatic acceptance

Policy and prompt versions are `hsd-ai-review-2`. Wire response is exactly `{candidate_reviews:[{candidate_id,verdict,reason,checks,differences}]}`, one entry per locally supplied ID. Pair checks are content_same/colors_same/complete_coverage/extra_content_absent. Each entry describes only its own candidate. Missing/duplicate/unknown IDs or invalid schemas fail. Contradictory verdict/checks/differences are preserved in bounded `protocol_diagnostics.raw_decision`, flagged inconsistent and downgraded to uncertain. Provider bodies, prompts and credentials are never retained there.

The client normalizes the pair response to the existing decision fields. `unique_candidate` is locally derived only from one strict positive and every other supplied candidate explicitly different; identity still requires direct positive evidence. Categories remain geometry_review/texture_review. All five normalized checks must be true, verdict same, differences empty, and chosen candidate the local first. Independent signed qualification, native detail, complete local alignment/coverage, colour/content consistency and complete competition are separate gates. All failures are recorded together as `failed_checks`/`row.ai_review.gate_failures`, so missing qualification cannot conceal other contradictions. A model switching candidates, affirming unreadable detail or contradicting local evidence remains manual.

Case fingerprints bind selected-channel evidence, alignment, all competition scores, every compared preview/source digest (`comparison_inputs`), and the supplied images. Any competitor changing invalidates the earlier proof, even if not exported. Original comparison sources are verified before/after requests and before/after export. Every run checkpoints all planned cases and the five-module `implementation_sha256` before I/O and after each attempt; retries retain earlier failures. Changes during a request preserve the actual reply and charges but invalidate the case for qualification. Export records contain both the latest `ai_observations` and all `ai_observation_runs`.

`tools/run_ai_evaluation.py --synthetic --out <empty-dir> --settings-dir <data-dir> [--prepare-only]` prepares generated labelled cases; without `--prepare-only` it makes real billable calls using the existing settings. Output preserves all planned cases, including failures, plus frozen labels, fingerprints, responses and usage. It never activates business acceptance. Repository-local outputs must stay under ignored `tmp/`.

`tools/validate_ai_review.py --labels <labels.json> --observations <observations.json> --output <report.json>` makes no network calls and reads no key. It requires schema version 1, real `deepseek_live` records of the current protocol, exactly matching unique planned/case/request IDs, a single actual model, image/candidate/source fingerprints, and complete responses. Labels declare `case_id`, `case_fingerprint`, `batch_id`, `category`, `split:'calibration'|'holdout'`, `origin:'independent_manual'|'synthetic_known_truth'|'reference_map'`, `label:'same'|'different'|'uncertain'`, `candidate_ids`, `expected_candidate_id` and `controls`. The response's `case` binds `category`, `candidate_ids` and `image_digests`. Do not reuse query images across independent batches or mix calibration and holdout within a batch.

For each approved category, at least two independent holdout batches must each include a positive, a negative/uncertain case and a useful correctly accepted positive. At least one batch must include independently manually verified real business positives and negatives. Overall, at least two accepted positives and five negatives must cover `color_change`, `local_replacement`, `extra_content`, `shared_subset`, `near_duplicate`, with zero false accepts across all recorded cases. Synthetic data alone or an existing reference map cannot qualify production. Labels are independent and frozen before observing model output; do not relabel origins or omit failed cases to pass.

After reviewing a qualifying report, adding `--activate --data-dir <tool-data-dir>` explicitly signs/stores the qualification locally. The registry checks integrity, binds the actual model, categories, policy/prompt versions and five implementation modules (ai_policy, ai_client, ai_images, matching, matching_verification), and expires after 7 days. Observation artifacts must have recorded all five implementation signatures at call time, matching the current implementation; activation cannot re-sign old results as newly verified code. Missing/mismatching signatures remain usable only for regression analysis, never qualification. Changed implementations/protocols invalidate the record; an unqualified model/category cannot pass the per-row gate. No qualification is shipped in v1.3.0. These are minimum activation prerequisites for the measured scope, not a general accuracy guarantee. The user has reserved 10.12 for later and chosen employee verification of a new business batch after this general optimization.

## Ownership

Matching agent: matching.py, image matching helpers, tests/test_matching.py, matching investigation scripts/results under tools/matching_* and tmp/matching_*.
Workbook agent: workbook.py, tests/test_workbook.py.
UI agent: hsd_tool/static/*. Must follow API above. No server code. Current documentation-only assignment may edit the five delivery documents separately; no simultaneous root/static edits.
Root: service/server, orchestration, export, packaging, docs, integration testing.
