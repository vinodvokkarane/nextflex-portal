NextFlex-acknowledged papers bundle
===================================

Date window used
----------------
This bundle is a best-effort compilation for the last 10 years relative to 2026-05-01,
so the target publication window is approximately 2016-05-01 through 2026-05-01.

Strict inclusion rule
---------------------
A paper was included in public_pdfs/ only when I could access a public PDF and the
accessible PDF text itself explicitly acknowledged NextFlex support, such as:
- direct mention of NextFlex / NextFlex Institute / NextFlex Manufacturing Institute,
- a NextFlex project call or project code (for example PC 1.0, PC 2.5, PC 4.5, PC 6.4, PC 7.3, PC 7.6, PC 8.6.1), or
- wording like "as conducted through ... NextFlex" together with an AFRL agreement number.

What is in this folder
----------------------
- public_pdfs/: one downloaded public PDF for each paper that met the strict inclusion rule
- alternate_versions/: extra public PDF(s) for duplicate-source versions of an already included paper
- manifest.csv: detailed machine-readable list with status, file hashes, and evidence notes
- manifest_summary.md: quick human-readable list

Status meanings in manifest.csv
-------------------------------
- included_public_pdf: public PDF downloaded and included; explicit NextFlex support found in the PDF text
- alternate_public_pdf_duplicate_source: extra public PDF for a paper already counted above
- verified_online_no_public_pdf_downloaded: explicit NextFlex support verified from an online publisher page or search snippet, but I did not obtain a public PDF here
- public_pdf_found_download_failed: a public PDF appeared to exist, but it could not be fetched from this environment
- excluded_not_explicit_enough: a public PDF was downloaded and reviewed, but it did not meet the strict explicit-NextFlex criterion

Caveats
-------
- This is best-effort, not a guaranteed exhaustive bibliographic census.
- Some publisher pages were accessible while the PDF itself was blocked, rate-limited, or not directly downloadable from this environment.
- I favored precision over recall: papers were excluded when NextFlex appeared only as an affiliation or general project context without a clear funding/acknowledgment statement.
