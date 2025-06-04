# 🚀 CLIF-C2D2: ICU Data Transformation Pipeline

This repository provides a comprehensive workflow and codebase to seamlessly convert the **Common Longitudinal ICU data Format (CLIF)** dataset into the **SCCM C2D2** format.

## 🛠 Project Status

| Domain                         | ETL Notebook                                                                                 | Maturity Status       | Remarks                              |
| ------------------------------ | -------------------------------------------------------------------------------------------- | --------------------- | ------------------------------------ |
| Outcomes & Hospital Course     | [`etl/01_c2d2_cohort_built.ipynb`](etl/01_c2d2_cohort_built.ipynb)                           | 🟢 Beta               | Proof of Concept completed           |
| Advanced Directives            | [`etl/02_advanced_directives.ipynb`](etl/02_advanced_directives.ipynb)                       | 🚧 Under Construction | Awaiting CLIF 2.2 release            |
| Anthropometrics & Demographics | [`etl/03_anthropometrics_n_demographics.ipynb`](etl/03_anthropometrics_n_demographics.ipynb) | 🚧 Under Construction | Partial C2D2 elements in cohort data |
| Chronic Comorbid Illness       | [`etl/04_chronic_comorbid_illness.ipynb`](etl/04_chronic_comorbid_illness.ipynb)             | 🚧 Under Construction | Awaiting CLIF 2.2 release            |
| Diagnoses                      | [`etl/05_diagnoses.ipynb`](etl/05_diagnoses.ipynb)                                           | 🚧 Under Construction | Awaiting CLIF 2.2 release            |
| Diagnostic Tests               | [`etl/06_diagnostic_tests.ipynb`](etl/06_diagnostic_tests.ipynb)                             | 🟢 Beta               | Proof of Concept completed           |
| Interventions                  | [`etl/07_interventions.ipynb`](etl/07_interventions.ipynb)                                   | 🟢 Beta               | Proof of Concept completed           |
| Medications                    | [`etl/08_medications.ipynb`](etl/08_medications.ipynb)                                       | 🟢 Beta               | Proof of Concept completed           |
| Objective Assessments          | [`etl/09_objective_assessments.ipynb`](etl/09_objective_assessments.ipynb)                   | 🟢 Beta               | Proof of Concept completed           |

Each notebook generates domain-specific tables located at `../final/output/*.parquet`.

A final wide table for all domains can be generated using the `10_*` scripts.

If your project focuses on only a few domains, we recommend using the `cohort` table and selectively joining it with relevant domain-specific tables as needed.

Mapping files can be found here:

* 📄 [`mapping/ccm-53-e1045-s002.xlsx`](mapping/ccm-53-e1045-s002.xlsx) (alpha release for Proof of Concept)

## 📖 Table of Contents

* [🔧 Usage](#usage)
* [🌱 Contributing](#contributing)
* [📜 License](#license)

## 🔧 Usage

### Existing Users

To keep your version up-to-date:

```bash
git pull origin [your-branch-name]
```

Refer to the [CHANGELOG.md](CHANGELOG.md) for updates on CLIF tables that must be regenerated.

### New Users

1. **Fork** this repository.
2. Clone your forked copy:

```bash
git clone [your-repo-url]
```

### ⚙️ Configuration Setup

* Navigate to `/config/` directory.
* Rename `config_template.json` to `config.json`.
* Customize the following entries:

```json
{
    "site_name": "Your Site Name",
    "tables_path": "path/to/clif/tables",
    "file_type": "csv/parquet/fst",
    "timezone": "US/Central"
}
```

### ▶️ Running the Pipeline

Navigate to the `clif-c2d2` directory and execute:

```bash
# For Windows
./run_c2d2_etl.bat

# For Linux/Mac
./run_c2d2_etl.sh
```

The output will generate Proof of Concept tables from the CLIF-C2D2 transformation pipeline.

## 🌱 Contributing

We welcome contributions! To contribute, please:

* 🐞 **Report issues** for bugs or request new data features.
* 🌿 Use clear branch naming conventions (e.g., `feature/new-table-dialysis`).
* 📌 Submit a **Pull Request (PR)** for review.

## 📜 License

This project is licensed under the [MIT License](LICENSE).
