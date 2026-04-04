# About Data Labeling

## `data/` Structure

```
.
├── catalogs
│   ├── action_catalog.csv         # Actions
│   ├── app_catalog.json           # Functionalities for each app type
│   └── object_catalog.csv         # Objects
├── data-preprocess.ipynb          # Notebook used for data preprocessing
├── final_dataset.csv              # Final dataset - Labeling sources
├── final-data-statistics.ipynb    # App-specific dataset statistics
├── grouping.py                    # Utility program that helps generated app-specific data and catalogs
├── labeled_data                   # Generated dataset to be labeled
└── source                         # Source data from existing datasets
```

## Labeling Steps

1. Execute `grouping.py` and get pre-labeled data.

```bash
python grouping.py --app-type commerce_platform
```
You can find arguments of `--app-types` and the number of rows for each app type in `data-preprocess.ipynb`.
`data_{app_type}.csv` and `prompt_template_{app_type}.txt` will be generated in `labeled_data/`.

2. Labeling.
`data_{app_type}.csv` includes all the data of that app type. `prompt_template_{app_type}.txt` is a potential prompt that could be used if you prefer AI labeling and munual verification.

3. If the action/object definition in `action_catalogs.csv` or `object_catalogs.csv` is wrong/misleading/vague. We'll discuss and revolve it.

Happy labeling!
