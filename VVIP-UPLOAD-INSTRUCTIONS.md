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
4. Select **Run workflow** and allow up to three hours.
5. When the run is green, open it and download **ukei-comprehensive-report**.

The artifact contains per-theme discovery evidence, the deduplicated catalogue before validation,
the comprehensive validation report, the catalogue after validation, and integrity status files.

## Important scope statement

“Comprehensive” means broad coverage of every provider currently implemented by this repository;
it must not be represented as literally every environmental dataset in the UK. Additional provider
connectors and pagination will still be required for that claim. The evidence reports retain this
distinction so source coverage is not overstated.
