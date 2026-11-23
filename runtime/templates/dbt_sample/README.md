# dbt starter

Bootstrap copies this project to `/workspace/dbt_sample` only if that directory is absent. Existing files are kept unchanged on subsequent starts.

Load `dbt_sample_pipeline` in Workflows. Save & publish, then Execute. The flow runs **seed → build (including tests) → docs** in the `dbt_sample` schema of the bootstrap catalog. It has no enabled schedule and never runs automatically on startup.

Expected `customer_totals`: customer 101 has 2 orders / 150; customer 102 has 2 orders / 200; customer 103 has 1 order / 25.

Use Runs → dbt build → View for test results/logs/artifacts. In the dbt panel set Project directory to `dbt_sample`, leave Legacy project overrides empty (catalog/schema are declared in dbt_project.yml), then Open Docs for model descriptions, columns and lineage. Docs describe the project; execution/test status is in Runs.

The runner supplies the connection profile; no credentials belong in this project.
