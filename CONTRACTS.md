# Internal implementation contract

Python package `hsd_tool`, Chinese end-user interface. Local Flask server + browser interface, bundled Windows executable. No external AI calls. Source inputs remain unchanged.

## Workbook module (workbook.py)

`inspect_workbook(path: str, work_dir: str, sheet_name: str | None = None) -> dict`

Return `{sheets:[{name,hidden}], sheet_name, rows:[{id, row_number, number, image_path, issue}], reserved_numbers:[str]}`. Row IDs are `r<Excel row>`. Absolute image paths are extracted to work_dir. Read the first visible sheet by default. Image-bearing rows only; include unreadable image references with issue. Read column A number, B picture for current fixed template; preserve displayed leading zeros. `reserved_numbers` includes existing numbers in column A, including rows without pictures. Ignore huge empty/formatted trailing regions. WPS DISPIMG/cellimages required. Any supported floating drawing must associate an anchor to column B explicitly. Never include hidden sheets by default.

`write_numbered_workbook(source: str, destination: str, sheet_name: str, assignments: dict[int,str]) -> None`

Update only blank column A cells at assigned row numbers. Preserve every other XLSX part and all WPS images/drawings. Refuse replacement of any nonempty source number. Use ZIP/XML surgical updates (ordinary spreadsheet roundtrip destroys WPS-specific image features). Destination must differ from source and must not preexist. No sample workbook changes.

## Matching module (matching.py)

`scan_and_match(source_path: str, rows: list[dict], work_dir: str, progress=None) -> dict`

Input AI folder (recursive) or zip. Must reject traversal/symlinks, enforce extraction resource limits, decode legacy Chinese zip names, preserve originals. Render PDF-compatible AI previews locally (first page; multi-page files must be flagged for review instead of auto acceptance). Source extraction under work_dir only. Return `{files:[{id,name,relative_path,source_path,preview_path,issue}], matches:[{row_id,status,file_id,candidates:[{file_id,score}],reason,evidence}], warnings:[str]}  `evidence` carries every signal behind the decision - method, colour distance, candidate gap, pixel rms, changed / major-changed share, worst region, unexplained-content residual, inliers, coverage, mae and the thresholds applied - for diagnosis only; the employee screen shows only `reason`.. Status `auto`, `review`, or `unmatched`. IDs deterministic f0001 etc. score is 0..1 similarity, never probability. Fail closed for near duplicates / reused file candidates; don't force a global assignment merely to obtain one-to-one matches. Auto acceptance must be strong, unique and empirically validated with this sample. `progress(message: str, current: int, total: int)` optional. All preview images under work_dir. Individual bad AI files reported without aborting every readable file. Source AI bytes must remain unchanged.

## Service + UI API (owned by root)

Local only, Flask. Browser gets X-HSD-Token from `window.HSD_TOKEN` populated in index.html template placeholder `__HSD_TOKEN__`. All POST JSON uses this header. Standard failures `{error: Chinese string}`, HTTP 400/409 etc.

- `GET /api/config` -> `{prefix:'HSD', digits:4, last_start:1, last_workbook:'', last_source:'', last_output:'', version:'1.0.0'}`
- `POST /api/pick` `{kind:'workbook'|'zip'|'folder'|'output'}` -> `{path: str}` (native local dialog)
- `POST /api/jobs` `{workbook_path,source_path,output_root,start_number:int}` -> `{id}`; processing background job.
- `GET /api/jobs/<id>` -> full job as below, poll 1s while importing/matching/exporting.
- `POST /api/jobs/<id>/resolve` `{row_id, file_id: str|null, revert?: bool}`; null means skip, `revert: true` restores the matcher's own verdict for that row, otherwise confirm mapping; returns job. Refuse duplicate file ownership.
- `POST /api/jobs/<id>/export` `{}` -> `{id}`; background export.
- `GET /api/jobs/<id>/image/row/<row_id>` and `/image/file/<file_id>` -> preview image; served as a private cacheable response with conditional revalidation, because a preview never changes inside one job.
- `POST /api/jobs/<id>/open-output` `{}` -> `{ok:true}` (only completed job output).

Job schema: `{id,status:'importing'|'matching'|'ready'|'exporting'|'done'|'error',progress:{message,current,total},error:null|string, sheet_name, workbook_name, source_name, start_number, prefix:'HSD', stats:{total,auto,confirmed,review,unmatched,skipped,exportable,needs_attention}, rows:[{id,row_number,number,planned_number,status:'auto'|'confirmed'|'review'|'unmatched'|'skipped',file_id:null|str,candidates:[{file_id,score}],reason}], files:[{id,name,relative_path,issue}],warnings:[],output_dir:null|str,report:null|dict}`. All unresolved rows retain their source numbers in output. Only matched rows with blank source numbers get planned new numbers. `output_target` is the resolved destination folder so the summary screen can state it before export. Existing numbers remain exact (including non-HSD prefixes). Duplicate or unsafe output numbers block affected rows for review; no overwrites. Input locations local paths typed/picked, no uploads.

## Ownership

Matching agent: matching.py, image matching helpers, tests/test_matching.py, matching investigation scripts/results under tools/matching_* and tmp/matching_*.
Workbook agent: workbook.py, tests/test_workbook.py.
UI agent: hsd_tool/static/index.html, app.js, style.css. Must follow API above. No server code.
Root: service/server, orchestration, export, packaging, docs, integration testing.
