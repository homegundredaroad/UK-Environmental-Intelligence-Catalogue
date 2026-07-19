# VVIP comprehensive scan

This release expands the strongest safe scan currently supported by the project. It combines the
reviewed official-source seed list with multi-theme CKAN and Natural England ArcGIS discovery,
deduplicates records in one catalogue, and validates landing pages plus underlying resources.

## Upload

Upload every file from the supplied replacement ZIP to the same path in the GitHub repository.
Choose **Commit changes** once, after all files have been added or replaced.

## Run in the browser

1. Open **Actions** and select **CI**.
2. Select **Run workflow**.
3. Enable only **Run the broad multi-theme discovery and validation scan (VVIP)**.
4. Optionally enable AI enrichment and initially leave its record cap at 50.
5. Select **Run workflow** and allow approximately two hours; individual shards are capped at 90
   minutes.
6. When the run is green, download **ukei-comprehensive-report** and, if enabled,
   **ukei-intelligence-report**.

The main artifact contains the validated SQLite catalogue, compressed canonical JSON, coverage
ledger, integrity status, compact summary and review CSVs. Detailed record-level evidence is in the
separate **ukei-detailed-validation-evidence** artifact. The 31 shard artifacts are diagnostic and
normally do not need to be downloaded or uploaded to Drive.

## Important scope statement

“Comprehensive” means broad coverage of every provider currently implemented by this repository;
it must not be represented as literally every environmental dataset in the UK. Additional provider
connectors and pagination will still be required for that claim. The evidence reports retain this
distinction so source coverage is not overstated.
